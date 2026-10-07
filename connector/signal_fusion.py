"""TradePilot Signal Fusion indicator engine.

Phase one exposes three closed-candle lanes:
1. MACD regime with hysteresis (continuous bullish/bearish state).
2. Per-candle MACD state (bullish, bearish, or neutral separation zone).
3. Candle pressure from body, close location, ATR expansion, close-to-close
   momentum, and wick rejection.

This module is analytical only and never sends an order.
"""
from __future__ import annotations

EPS = 1e-12
ALLOWED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4", "D1"}
MULTI_TIMEFRAMES = ("D1", "H4", "H1", "M15", "M5", "M1")


def _ema(values, period):
    alpha = 2.0 / (period + 1.0)
    out, current = [], float(values[0])
    for value in values:
        current = alpha * float(value) + (1.0 - alpha) * current
        out.append(current)
    return out


def _wilder(values, period=14):
    alpha = 1.0 / period
    out, current = [], float(values[0])
    for value in values:
        current = alpha * float(value) + (1.0 - alpha) * current
        out.append(current)
    return out


def _clamp(value, low=-1.0, high=1.0):
    return max(low, min(high, float(value)))


def calculate_signal_fusion(rows, timeframe="M5", minimum_separation=0.18):
    if len(rows) < 80:
        raise RuntimeError("Signal Fusion needs at least 80 closed candles")
    timeframe = str(timeframe).upper()
    if timeframe not in ALLOWED_TIMEFRAMES:
        timeframe = "M5"
    threshold = max(0.0, min(2.0, float(minimum_separation)))

    closes = [float(row["close"]) for row in rows]
    opens = [float(row["open"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    fast, slow = _ema(closes, 12), _ema(closes, 26)
    macd = [a - b for a, b in zip(fast, slow)]
    signal = _ema(macd, 9)
    histogram = [a - b for a, b in zip(macd, signal)]
    histogram_scale = _ema([abs(value) for value in histogram], 20)

    true_ranges = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close
        true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - previous), abs(lows[index] - previous)))
    atr = _wilder(true_ranges, 14)

    result, regime = [], "NEUTRAL"
    for index, row in enumerate(rows):
        normalized_separation = histogram[index] / max(histogram_scale[index], EPS)
        if normalized_separation >= threshold:
            candle_state = "BULLISH"
            regime = "BULLISH"
        elif normalized_separation <= -threshold:
            candle_state = "BEARISH"
            regime = "BEARISH"
        else:
            candle_state = "NEUTRAL"
            if regime == "NEUTRAL" and index:
                regime = result[-1]["regime"]

        candle_range = max(highs[index] - lows[index], EPS)
        body = (closes[index] - opens[index]) / candle_range
        close_location = 2.0 * ((closes[index] - lows[index]) / candle_range) - 1.0
        previous_close = closes[index - 1] if index else opens[index]
        momentum = _clamp((closes[index] - previous_close) / max(atr[index], EPS))
        upper_wick = (highs[index] - max(opens[index], closes[index])) / candle_range
        lower_wick = (min(opens[index], closes[index]) - lows[index]) / candle_range
        rejection = lower_wick - upper_wick
        activity = max(0.35, min(1.25, candle_range / max(atr[index], EPS)))
        pressure = _clamp((0.45 * body + 0.25 * close_location + 0.20 * momentum + 0.10 * rejection) * activity) * 100.0
        absolute_pressure = abs(pressure)
        if absolute_pressure < 22.0:
            pressure_state = "NEUTRAL"
            pressure_level = "NEUTRAL"
        else:
            pressure_state = "BULLISH" if pressure > 0 else "BEARISH"
            pressure_level = "STRONG" if absolute_pressure >= 65 else "MEDIUM" if absolute_pressure >= 35 else "WEAK"

        result.append({
            "time": int(row["time"]),
            "open": opens[index], "high": highs[index], "low": lows[index], "close": closes[index],
            "macd": macd[index], "signal": signal[index], "histogram": histogram[index],
            "separation": normalized_separation,
            "regime": regime, "macd_state": candle_state,
            "pressure_score": round(pressure, 2),
            "pressure_state": pressure_state, "pressure_level": pressure_level,
        })

    trade_state = "WAIT"
    for item in result:
        event = None
        bullish_votes = sum((
            item["regime"] == "BULLISH",
            item["macd_state"] == "BULLISH",
            item["pressure_state"] == "BULLISH",
        ))
        bearish_votes = sum((
            item["regime"] == "BEARISH",
            item["macd_state"] == "BEARISH",
            item["pressure_state"] == "BEARISH",
        ))
        if trade_state == "WAIT":
            if bullish_votes == 3:
                trade_state, event = "BUY", "BUY_OPEN"
            elif bearish_votes == 3:
                trade_state, event = "SELL", "SELL_OPEN"
        elif trade_state == "BUY" and bullish_votes < 2:
            trade_state, event = "WAIT", "BUY_CLOSE"
        elif trade_state == "SELL" and bearish_votes < 2:
            trade_state, event = "WAIT", "SELL_CLOSE"
        item["trade_state"] = trade_state
        item["trade_event"] = event
        item["bullish_votes"] = bullish_votes
        item["bearish_votes"] = bearish_votes

    latest = result[-1]
    return {
        "engine": "TradePilot Signal Fusion",
        "engine_version": "2.9.2",
        "timeframe": timeframe,
        "closed_candles_only": True,
        "settings": {
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "ma_type": "EMA", "source": "CLOSE",
            "minimum_separation": threshold,
            "pressure_neutral_threshold": 22,
            "pressure_medium_threshold": 35,
            "pressure_strong_threshold": 65,
        },
        "latest": latest,
        "rows": result,
    }


def analyze_mt5(mt5, symbol, timeframe="M5", minimum_separation=0.18, count=180):
    timeframe = str(timeframe).upper()
    if timeframe not in ALLOWED_TIMEFRAMES:
        timeframe = "M5"
    constants = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    info = mt5.symbol_info(symbol)
    if not info:
        raise RuntimeError(f"Symbol not found: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol: {symbol}")
    requested = max(120, min(420, int(count)))
    rates = mt5.copy_rates_from_pos(symbol, constants[timeframe], 1, requested + 80)
    if rates is None or len(rates) < 80:
        raise RuntimeError(f"Not enough closed {timeframe} candles")
    rows = [
        {field: (rate[field].item() if hasattr(rate[field], "item") else rate[field]) for field in rates.dtype.names}
        for rate in rates
    ]
    output = calculate_signal_fusion(rows, timeframe, minimum_separation)
    output["symbol"] = symbol
    output["digits"] = int(info.digits)
    output["rows"] = output["rows"][-requested:]
    return output


def analyze_mt5_multi(mt5, symbol, execution_timeframe="M5", minimum_separation=0.25, count=180):
    """Return compact MACD regimes for five timeframes plus execution lanes."""
    execution_timeframe = str(execution_timeframe).upper()
    if execution_timeframe not in MULTI_TIMEFRAMES:
        execution_timeframe = "M5"
    analyses = {
        timeframe: analyze_mt5(
            mt5,
            symbol,
            timeframe,
            minimum_separation,
            count if timeframe == execution_timeframe else 120,
        )
        for timeframe in MULTI_TIMEFRAMES
    }
    execution = analyses[execution_timeframe]
    return {
        "engine": "TradePilot Signal Fusion",
        "engine_version": "2.9.2",
        "symbol": symbol,
        "execution_timeframe": execution_timeframe,
        "settings": execution["settings"],
        "latest": execution["latest"],
        "rows": execution["rows"],
        "timeframes": {
            timeframe: {
                "latest": analysis["latest"],
                "rows": analysis["rows"],
            }
            for timeframe, analysis in analyses.items()
        },
    }
