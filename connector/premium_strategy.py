"""TradePilot Premium Strategy analysis engine.

The deterministic calculations in this module mirror the active concepts in
aswa9i-v15-backend-clean: EMA/RSI/ATR/ADX/MACD, pivot structure, BOS/CHOCH,
entry-quality penalties and exhaustion review.

Important:
* Only closed MT5 candles are used (copy_rates_from_pos starts at position 1).
* The probability conversion and projected path are explicitly PROPOSED UI
  layers.  They are scenarios, not future market data or trade permission.
* This module never sends an order.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math


EPS = 1e-12
TIMEFRAME_NAMES = ("M5", "M15", "H1", "H4")


def _ema(values, period):
    alpha = 2.0 / (period + 1.0)
    out = []
    value = float(values[0])
    for current in values:
        value = alpha * float(current) + (1.0 - alpha) * value
        out.append(value)
    return out


def _wilder(values, period=14):
    alpha = 1.0 / period
    out = []
    value = float(values[0])
    for current in values:
        value = alpha * float(current) + (1.0 - alpha) * value
        out.append(value)
    return out


def _enrich(rows):
    closes = [float(x["close"]) for x in rows]
    highs = [float(x["high"]) for x in rows]
    lows = [float(x["low"]) for x in rows]
    opens = [float(x["open"]) for x in rows]
    ema9 = _ema(closes, 9)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)

    gains, losses, tr = [], [], []
    plus_dm, minus_dm = [], []
    for i, close in enumerate(closes):
        if i == 0:
            change = 0.0
            previous_close = close
            up_move = down_move = 0.0
        else:
            change = close - closes[i - 1]
            previous_close = closes[i - 1]
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
        tr.append(max(highs[i] - lows[i], abs(highs[i] - previous_close), abs(lows[i] - previous_close)))
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    avg_gain = _wilder(gains)
    avg_loss = _wilder(losses)
    rsi = [
        50.0 if loss <= EPS else 100.0 - (100.0 / (1.0 + gain / loss))
        for gain, loss in zip(avg_gain, avg_loss)
    ]
    atr = _wilder(tr)
    smooth_plus = _wilder(plus_dm)
    smooth_minus = _wilder(minus_dm)
    dx = []
    for p, m, a in zip(smooth_plus, smooth_minus, atr):
        plus_di = 100.0 * p / max(a, EPS)
        minus_di = 100.0 * m / max(a, EPS)
        dx.append(100.0 * abs(plus_di - minus_di) / max(plus_di + minus_di, EPS))
    adx = _wilder(dx)

    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    macd = [a - b for a, b in zip(fast, slow)]
    signal = _ema(macd, 9)
    hist = [a - b for a, b in zip(macd, signal)]

    enriched = []
    for i, row in enumerate(rows):
        item = dict(row)
        item.update(
            ema9=ema9[i], ema20=ema20[i], ema50=ema50[i],
            rsi14=rsi[i], atr14=atr[i], adx14=adx[i],
            macd=macd[i], macd_signal=signal[i], macd_hist=hist[i],
            volatility_ratio=atr[i] / max(abs(closes[i]), EPS),
            body=abs(closes[i] - opens[i]),
        )
        enriched.append(item)
    return enriched


def _pivots(rows, window=2):
    highs, lows = [], []
    for i in range(window, len(rows) - window):
        scope = rows[i - window:i + window + 1]
        high, low = float(rows[i]["high"]), float(rows[i]["low"])
        if high >= max(float(x["high"]) for x in scope):
            highs.append((i, high))
        if low <= min(float(x["low"]) for x in scope):
            lows.append((i, low))
    return highs, lows


def _pair_bias(high_a, high_b, low_a, low_b):
    if high_b > high_a and low_b > low_a:
        return "BUY"
    if high_b < high_a and low_b < low_a:
        return "SELL"
    return "NEUTRAL"


def _structure(enriched):
    recent = enriched[-80:]
    highs, lows = _pivots(recent)
    current, previous = recent[-1], recent[-2]
    swing_high = highs[-1][1] if highs else max(float(x["high"]) for x in recent[-20:])
    swing_low = lows[-1][1] if lows else min(float(x["low"]) for x in recent[-20:])
    bias, previous_bias, pattern, quality = "NEUTRAL", "NEUTRAL", "MIXED", 0.45

    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = highs[-2][1], highs[-1][1]
        l1, l2 = lows[-2][1], lows[-1][1]
        if len(highs) >= 3 and len(lows) >= 3:
            previous_bias = _pair_bias(highs[-3][1], h1, lows[-3][1], l1)
        if h2 > h1 and l2 > l1:
            bias, pattern, quality = "BUY", "HH_HL", 0.90
        elif h2 < h1 and l2 < l1:
            bias, pattern, quality = "SELL", "LH_LL", 0.90
        elif h2 > h1 and l2 < l1:
            pattern, quality = "EXPANDING", 0.55
        else:
            pattern, quality = "COMPRESSION", 0.50
    else:
        close = float(current["close"])
        if close > current["ema20"] > recent[-5]["ema20"]:
            bias, pattern, quality = "BUY", "EMA_TREND_UP", 0.65
        elif close < current["ema20"] < recent[-5]["ema20"]:
            bias, pattern, quality = "SELL", "EMA_TREND_DOWN", 0.65

    close, prev_close = float(current["close"]), float(previous["close"])
    bos = choch = "NEUTRAL"
    broken = None
    if highs and close > highs[-1][1] and prev_close <= highs[-1][1]:
        bos, broken = "BUY", highs[-1][1]
        if bias == "SELL":
            choch = "BUY"
    if lows and close < lows[-1][1] and prev_close >= lows[-1][1]:
        bos, broken = "SELL", lows[-1][1]
        if bias == "BUY":
            choch = "SELL"

    atr = max(float(current["atr14"]), EPS)
    body = abs(close - float(current["open"]))
    upper_wick = float(current["high"]) - max(float(current["open"]), close)
    lower_wick = min(float(current["open"]), close) - float(current["low"])
    candle_context = "DOJI"
    if body >= atr * 0.15:
        candle_context = "BULL_BODY" if close > current["open"] else "BEAR_BODY"
    if upper_wick >= body * 1.25 and lower_wick < upper_wick:
        candle_context = "UPPER_REJECTION"
    elif lower_wick >= body * 1.25 and upper_wick < lower_wick:
        candle_context = "LOWER_REJECTION"

    pullback = (bias == "BUY" and close <= current["ema9"]) or (bias == "SELL" and close >= current["ema9"])
    reclaim = (
        prev_close <= previous["ema20"] < close
        or prev_close >= previous["ema20"] > close
    )
    sweep_high = bool(highs) and float(current["high"]) > highs[-1][1] and close <= highs[-1][1]
    sweep_low = bool(lows) and float(current["low"]) < lows[-1][1] and close >= lows[-1][1]
    retest = False
    if broken is not None:
        retest = (
            bos == "BUY" and float(current["low"]) <= broken <= close
        ) or (
            bos == "SELL" and float(current["high"]) >= broken >= close
        )

    return {
        "bias": bias, "previous_bias": previous_bias, "pattern": pattern,
        "quality": quality, "swing_high": swing_high, "swing_low": swing_low,
        "bos": bos, "choch": choch, "broken_swing_level": broken,
        "close_beyond_level": broken is not None, "retest": retest,
        "breakout": bos != "NEUTRAL", "pullback": pullback,
        "rejection": candle_context in ("UPPER_REJECTION", "LOWER_REJECTION"),
        "reclaim": reclaim, "liquidity_sweep": sweep_high or sweep_low,
        "candle_context": candle_context,
        "impulse_strength": min(1.0, body / (atr * 1.25)),
    }


def _macd_state(enriched):
    cur, prev = enriched[-1], enriched[-2]
    macd, signal, hist = cur["macd"], cur["macd_signal"], cur["macd_hist"]
    p_macd, p_signal, p_hist = prev["macd"], prev["macd_signal"], prev["macd_hist"]
    bullish_cross = p_macd <= p_signal and macd > signal
    bearish_cross = p_macd >= p_signal and macd < signal
    above_zero, below_zero = macd > 0, macd < 0
    green, red = hist > 0, hist < 0
    expanding = (
        (hist > 0 and p_hist >= 0 and hist > p_hist)
        or (hist < 0 and p_hist <= 0 and abs(hist) > abs(p_hist))
        or (hist > 0 >= p_hist) or (hist < 0 <= p_hist)
    )
    delta = macd - p_macd
    epsilon = max(abs(macd), abs(p_macd), 1.0) * 1e-8
    slope = "UP" if delta > epsilon else "DOWN" if delta < -epsilon else "FLAT"
    if above_zero and bullish_cross and green:
        trigger = "FRESH_BULLISH"
    elif below_zero and bearish_cross and red:
        trigger = "FRESH_BEARISH"
    elif above_zero and macd > signal and green and slope == "UP":
        trigger = "BULLISH_CONTINUATION"
    elif below_zero and macd < signal and red and slope == "DOWN":
        trigger = "BEARISH_CONTINUATION"
    elif below_zero and bullish_cross:
        trigger = "BULLISH_PULLBACK_BELOW_ZERO"
    elif above_zero and bearish_cross:
        trigger = "BEARISH_PULLBACK_ABOVE_ZERO"
    else:
        trigger = "NEUTRAL"
    strength = (
        (0.55 if trigger.startswith("FRESH") else 0.35 if "CONTINUATION" in trigger else 0.0)
        + (0.20 if expanding else 0.0)
        + (0.15 if abs(macd - signal) > abs(p_macd - p_signal) else 0.0)
        + (0.10 if slope != "FLAT" else 0.0)
    )
    return {
        "line": macd, "signal": signal, "histogram": hist,
        "above_zero": above_zero, "below_zero": below_zero,
        "bullish_cross": bullish_cross, "bearish_cross": bearish_cross,
        "histogram_green": green, "histogram_red": red,
        "histogram_expanding": expanding, "slope": slope,
        "trigger": trigger, "strength": min(1.0, strength),
    }


def _snapshot(rows, timeframe):
    enriched = _enrich(rows)
    last = enriched[-1]
    return {
        "timeframe": timeframe,
        "bar_time": datetime.fromtimestamp(int(last["time"]), timezone.utc).isoformat(),
        "open": float(last["open"]), "high": float(last["high"]),
        "low": float(last["low"]), "close": float(last["close"]),
        "volume": float(last.get("tick_volume", 0)),
        "ema9": last["ema9"], "ema20": last["ema20"], "ema50": last["ema50"],
        "rsi14": last["rsi14"], "atr14": last["atr14"], "adx14": last["adx14"],
        "volatility_ratio": last["volatility_ratio"],
        "macd": _macd_state(enriched), "structure": _structure(enriched),
        "_bars": enriched,
    }


def _session(now):
    hour = now.hour
    london = 7 <= hour < 16
    new_york = 13 <= hour < 22
    tokyo = 0 <= hour < 9
    if london and new_york:
        return "LONDON + NEW YORK"
    if london:
        return "LONDON"
    if new_york:
        return "NEW YORK"
    if tokyo:
        return "ASIA"
    return "OFF SESSION"


def _entry_quality(direction, frames, session):
    m5, m15 = frames["M5"], frames["M15"]
    opposite = "SELL" if direction == "BUY" else "BUY"
    score, warnings, hard = 0.0, [], []

    def extension(tf):
        if direction == "SELL":
            return max(0.0, (tf["ema20"] - tf["close"]) / max(tf["atr14"], EPS))
        return max(0.0, (tf["close"] - tf["ema20"]) / max(tf["atr14"], EPS))

    m5_ext, m15_ext = extension(m5), extension(m15)
    checks = []
    if direction == "BUY":
        checks = [
            (m5["rsi14"] >= 67 and m15["rsi14"] >= 62, 1.0, "stacked_overbought_rsi"),
            (m5_ext >= 0.45 and m15_ext >= 0.55, 1.0, "extended_above_ema"),
            (m5["macd"]["bearish_cross"], 1.0, "m5_bearish_macd_cross"),
            (m5["macd"]["slope"] == "DOWN", 0.5, "m5_macd_slope_down"),
            (not m5["macd"]["histogram_expanding"], 0.4, "m5_bullish_momentum_weakening"),
        ]
        if m5["structure"]["choch"] == "SELL":
            hard.append("hard_m5_opposite_choch")
        if m5["structure"]["bos"] == "SELL":
            hard.append("hard_m5_opposite_bos")
        if m15_ext >= 2.0 and (m15["rsi14"] >= 72 or m5_ext >= 1.5):
            hard.append("hard_buy_overextended_wait_pullback")
    else:
        checks = [
            (m5["rsi14"] <= 33 and m15["rsi14"] <= 38, 1.0, "stacked_oversold_rsi"),
            (m5_ext >= 0.45 and m15_ext >= 0.55, 1.0, "extended_below_ema"),
            (m5["macd"]["bullish_cross"], 1.0, "m5_bullish_macd_cross"),
            (m5["macd"]["slope"] == "UP", 0.5, "m5_macd_slope_up"),
            (not m5["macd"]["histogram_expanding"], 0.4, "m5_bearish_momentum_weakening"),
        ]
        if m5["structure"]["choch"] == "BUY":
            hard.append("hard_m5_opposite_choch")
        if m5["structure"]["bos"] == "BUY":
            hard.append("hard_m5_opposite_bos")
        if m15_ext >= 2.0 and (m15["rsi14"] <= 28 or m5_ext >= 1.5):
            hard.append("hard_sell_overextended_wait_pullback")
    for condition, weight, label in checks:
        if condition:
            score += weight
            warnings.append(label)
    if session in ("ASIA", "OFF SESSION") and ((direction == "BUY" and m5["rsi14"] >= 64) or (direction == "SELL" and m5["rsi14"] <= 36)):
        score += 0.8
        warnings.append("extended_offsession")
    return {
        "result": "WAIT_RECHECK" if hard else "PASS",
        "score": round(score, 4), "hard_blockers": hard,
        "soft_warnings": warnings,
        "interpretation": "timing penalty; lower is better",
    }


def _exhaustion(direction, frames, session):
    m5, m15, h1 = frames["M5"], frames["M15"], frames["H1"]
    ex = cont = 0.0
    reasons = []
    if direction == "BUY":
        tests = [
            (m5["rsi14"] >= 67, 1.1, "m5_rsi_overbought"),
            (m15["rsi14"] >= 65, 0.9, "m15_rsi_overbought"),
            (h1["rsi14"] >= 60, 0.5, "h1_rsi_overbought"),
            (m5["structure"]["liquidity_sweep"], 0.7, "m5_liquidity_sweep"),
            (m5["macd"]["bearish_cross"], 1.0, "m5_bearish_cross"),
        ]
        continuation = [
            (m5["macd"]["above_zero"], 0.7), (m5["macd"]["histogram_green"], 0.5),
            (m15["structure"]["bias"] == "BUY", 0.8), (h1["structure"]["bias"] == "BUY", 0.8),
            (m5["adx14"] >= 30, 0.5),
        ]
    else:
        tests = [
            (m5["rsi14"] <= 33, 1.1, "m5_rsi_oversold"),
            (m15["rsi14"] <= 35, 0.9, "m15_rsi_oversold"),
            (h1["rsi14"] <= 40, 0.5, "h1_rsi_oversold"),
            (m5["structure"]["liquidity_sweep"], 0.7, "m5_liquidity_sweep"),
            (m5["macd"]["bullish_cross"], 1.0, "m5_bullish_cross"),
        ]
        continuation = [
            (m5["macd"]["below_zero"], 0.7), (m5["macd"]["histogram_red"], 0.5),
            (m15["structure"]["bias"] == "SELL", 0.8), (h1["structure"]["bias"] == "SELL", 0.8),
            (m5["adx14"] >= 30, 0.5),
        ]
    for condition, weight, label in tests:
        if condition:
            ex += weight
            reasons.append(label)
    if session in ("ASIA", "OFF SESSION"):
        ex += 0.6
    cont = sum(weight for condition, weight in continuation if condition)
    approved = not (ex >= 2.0 and cont < ex + 0.5)
    return {
        "approved": approved,
        "reason": "timing_still_confirms_continuation" if approved else "exhaustion_review_required",
        "exhaustion_score": round(ex, 3), "continuation_score": round(cont, 3),
        "factors": reasons,
    }


def _probabilities(frames, spread_to_atr):
    """PROPOSED conversion of deterministic evidence to three probabilities."""
    buy = sell = 1.0
    evidence_buy, evidence_sell = [], []
    weights = {"M1": 1.35, "M5": 2.0, "M15": 1.65, "H1": 1.15, "H4": 0.65}
    for name, weight in weights.items():
        tf = frames[name]
        bias = tf["structure"]["bias"]
        if bias == "BUY":
            buy += weight * tf["structure"]["quality"]
            evidence_buy.append(f"{name} bullish structure")
        elif bias == "SELL":
            sell += weight * tf["structure"]["quality"]
            evidence_sell.append(f"{name} bearish structure")
        if tf["ema9"] > tf["ema20"] > tf["ema50"]:
            buy += weight * 0.45
            evidence_buy.append(f"{name} EMA alignment")
        elif tf["ema9"] < tf["ema20"] < tf["ema50"]:
            sell += weight * 0.45
            evidence_sell.append(f"{name} EMA alignment")
        trigger = tf["macd"]["trigger"]
        if "BULLISH" in trigger:
            buy += weight * (0.35 + tf["macd"]["strength"] * 0.35)
        elif "BEARISH" in trigger:
            sell += weight * (0.35 + tf["macd"]["strength"] * 0.35)
    conflict = abs(buy - sell) / max(buy + sell, EPS)
    wait = 2.0 + (1.0 - conflict) * 4.0
    if spread_to_atr > 0.15:
        wait += 3.0
    total = buy + sell + wait
    result = {"buy": buy / total, "sell": sell / total, "wait": wait / total}
    rounded = {k: round(v, 4) for k, v in result.items()}
    rounded["wait"] = round(1.0 - rounded["buy"] - rounded["sell"], 4)
    return rounded, evidence_buy, evidence_sell


def _trade_plan(direction, frames, bid, ask, spread):
    if direction not in ("BUY", "SELL"):
        return {"entry": None, "stop_loss": None, "take_profit": None, "expected_rr": None}
    m5, m15, h1 = frames["M5"], frames["M15"], frames["H1"]
    entry = ask if direction == "BUY" else bid
    buffer = max(spread * 1.5, m5["atr14"] * 0.08, m15["atr14"] * 0.04)
    if direction == "BUY":
        anchor = min(m5["structure"]["swing_low"], m15["structure"]["swing_low"], h1["structure"]["swing_low"])
        stop = anchor - buffer
        candidates = [x["structure"]["swing_high"] for x in (m5, m15, h1, frames["H4"]) if x["structure"]["swing_high"] > entry]
        target = min(candidates) if candidates else entry + abs(entry - stop)
    else:
        anchor = max(m5["structure"]["swing_high"], m15["structure"]["swing_high"], h1["structure"]["swing_high"])
        stop = anchor + buffer
        candidates = [x["structure"]["swing_low"] for x in (m5, m15, h1, frames["H4"]) if x["structure"]["swing_low"] < entry]
        target = max(candidates) if candidates else entry - abs(entry - stop)
    risk = abs(entry - stop)
    rr = abs(target - entry) / max(risk, EPS)
    return {
        "entry": entry, "stop_loss": stop, "take_profit": target,
        "risk_distance": risk, "expected_rr": rr, "buffer": buffer,
        "source": "STRUCTURE_DYNAMIC_STOP",
    }


def _projection(direction, frames, current, confidence):
    """PROPOSED short-horizon scenario, never presented as future data."""
    atr = frames["M1"]["atr14"]
    sign = 1.0 if direction == "BUY" else -1.0 if direction == "SELL" else 0.0
    if not sign:
        offsets = [0.0, 0.05, -0.04, 0.03, 0.0]
    else:
        # A modest retest followed by continuation; amplitude is ATR-based.
        offsets = [0.0, -0.12 * sign, 0.20 * sign, 0.48 * sign, 0.72 * sign, 0.92 * sign]
    width = atr * (0.22 + (1.0 - confidence) * 0.45)
    return [
        {
            "step": i, "price": current + atr * offset,
            "upper": current + atr * offset + width * (1 + i * 0.12),
            "lower": current + atr * offset - width * (1 + i * 0.12),
        }
        for i, offset in enumerate(offsets)
    ]


# --- v2.8 multi-timeframe market-map and historical-analogue engine ---

MODE_CONFIG = {
    "FAST": {
        "primary": "M5", "confirm": "M15", "horizon": 6,
        "weights": {"M5": .40, "M15": .30, "H1": .20, "H4": .10},
    },
    "INTRADAY": {
        "primary": "M5", "confirm": "M15", "horizon": 8,
        "weights": {"M5": .28, "M15": .32, "H1": .28, "H4": .12},
    },
    "TREND": {
        "primary": "M15", "confirm": "H1", "horizon": 8,
        "weights": {"M5": .10, "M15": .25, "H1": .40, "H4": .25},
    },
    "CONSENSUS": {
        "primary": "M5", "confirm": "M15", "horizon": 7,
        "weights": {"M5": .22, "M15": .27, "H1": .28, "H4": .23},
    },
}

_BIAS_MEMORY = {}


def _quantile(values, q):
    values = sorted(float(x) for x in values)
    if not values:
        return 0.0
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _linear_regression(values):
    count = len(values)
    if count < 2:
        return 0.0, float(values[-1] if values else 0.0)
    mean_x = (count - 1) / 2.0
    mean_y = sum(values) / count
    denominator = sum((index - mean_x) ** 2 for index in range(count)) or 1.0
    slope = sum((index - mean_x) * (float(value) - mean_y) for index, value in enumerate(values)) / denominator
    return slope, mean_y - slope * mean_x


def _tf_vote(frame):
    score = 0.0
    structure = frame["structure"]
    if structure["bias"] == "BUY":
        score += 0.50 * structure["quality"]
    elif structure["bias"] == "SELL":
        score -= 0.50 * structure["quality"]
    if frame["ema9"] > frame["ema20"] > frame["ema50"]:
        score += 0.28
    elif frame["ema9"] < frame["ema20"] < frame["ema50"]:
        score -= 0.28
    trigger = frame["macd"]["trigger"]
    if "BULLISH" in trigger:
        score += 0.16 + 0.12 * frame["macd"]["strength"]
    elif "BEARISH" in trigger:
        score -= 0.16 + 0.12 * frame["macd"]["strength"]
    if structure["bos"] == "BUY" or structure["choch"] == "BUY":
        score += 0.18
    elif structure["bos"] == "SELL" or structure["choch"] == "SELL":
        score -= 0.18
    return max(-1.0, min(1.0, score))


def _mode_probabilities(frames, config, spread_to_atr):
    weighted = sum(_tf_vote(frames[name]) * weight for name, weight in config["weights"].items())
    disagreement = sum(
        weight for name, weight in config["weights"].items()
        if _tf_vote(frames[name]) * weighted < 0
    )
    edge = abs(weighted)
    wait_raw = 0.14 + disagreement * 0.70 + max(0.0, 0.18 - edge) * 1.6
    if spread_to_atr > 0.15:
        wait_raw += 0.18
    wait = min(0.62, max(0.08, wait_raw))
    directional = 1.0 - wait
    buy_share = (weighted + 1.0) / 2.0
    buy = directional * buy_share
    sell = directional * (1.0 - buy_share)
    result = {"buy": round(buy, 4), "sell": round(sell, 4), "wait": round(wait, 4)}
    result["wait"] = round(1.0 - result["buy"] - result["sell"], 4)
    return result, weighted, disagreement


def _sticky_direction(symbol, mode, candidate, edge, bar_time, frames, config):
    key = (symbol, mode)
    state = _BIAS_MEMORY.get(key)
    if state is None:
        state = {"direction": candidate, "opposite_bars": 0, "last_bar": bar_time}
        _BIAS_MEMORY[key] = state
        return candidate, "FORMING"
    if bar_time == state["last_bar"]:
        return state["direction"], "ACTIVE"
    state["last_bar"] = bar_time
    if candidate == state["direction"]:
        state["opposite_bars"] = 0
        return state["direction"], "CONFIRMED" if edge >= .24 else "WEAKENING"
    primary = frames[config["primary"]]["structure"]
    confirm = frames[config["confirm"]]["structure"]
    structure_confirms = (
        primary["bos"] == candidate or primary["choch"] == candidate
        or confirm["bias"] == candidate
    )
    if edge >= .14 and structure_confirms:
        state["opposite_bars"] += 1
    else:
        state["opposite_bars"] = 0
    if state["opposite_bars"] >= 2:
        state["direction"] = candidate
        state["opposite_bars"] = 0
        return candidate, "REVERSAL_CONFIRMED"
    return state["direction"], "REVERSAL_RISK" if state["opposite_bars"] else "WEAKENING"


def _historical_analogs(frame, horizon, current_price):
    bars = frame["_bars"]
    window = 12
    if len(bars) < window + horizon + 30:
        return {"status": "INSUFFICIENT_DATA", "matches": 0, "points": []}
    recent = bars[-window:]
    current_atr = max(float(frame["atr14"]), EPS)
    recent_returns = [
        (float(recent[index]["close"]) - float(recent[index - 1]["close"])) / current_atr
        for index in range(1, window)
    ]
    recent_shape = [
        (float(item["close"]) - float(item["ema20"])) / max(float(item["atr14"]), EPS)
        for item in recent
    ]
    candidates = []
    latest_allowed = len(bars) - window - horizon - 2
    for start in range(30, max(31, latest_allowed)):
        sample = bars[start:start + window]
        sample_atr = max(float(sample[-1]["atr14"]), EPS)
        sample_returns = [
            (float(sample[index]["close"]) - float(sample[index - 1]["close"])) / sample_atr
            for index in range(1, window)
        ]
        sample_shape = [
            (float(item["close"]) - float(item["ema20"])) / max(float(item["atr14"]), EPS)
            for item in sample
        ]
        shape_distance = sum(abs(a - b) for a, b in zip(recent_returns, sample_returns)) / len(recent_returns)
        ema_distance = sum(abs(a - b) for a, b in zip(recent_shape, sample_shape)) / len(recent_shape)
        indicator_distance = (
            abs(float(sample[-1]["rsi14"]) - float(recent[-1]["rsi14"])) / 100.0
            + abs(float(sample[-1]["adx14"]) - float(recent[-1]["adx14"])) / 100.0
        )
        distance = shape_distance * .55 + ema_distance * .30 + indicator_distance * .15
        end = start + window - 1
        future = bars[end + 1:end + 1 + horizon]
        if len(future) != horizon:
            continue
        base = float(sample[-1]["close"])
        offsets = [(float(item["close"]) - base) / sample_atr for item in future]
        candidates.append((distance, offsets, int(sample[-1]["time"])))
    candidates.sort(key=lambda item: item[0])
    selected = candidates[:min(36, len(candidates))]
    if len(selected) < 12:
        return {"status": "INSUFFICIENT_MATCHES", "matches": len(selected), "points": []}
    paths = [item[1] for item in selected]
    points = []
    for step in range(horizon):
        values = [path[step] for path in paths]
        points.append({
            "step": step + 1,
            "price": current_price + _quantile(values, .50) * current_atr,
            "lower": current_price + _quantile(values, .25) * current_atr,
            "upper": current_price + _quantile(values, .75) * current_atr,
        })
    outcomes = [path[-1] for path in paths]
    buy = sum(value >= .20 for value in outcomes)
    sell = sum(value <= -.20 for value in outcomes)
    ranging = len(outcomes) - buy - sell
    similarity = max(0.0, 1.0 - _quantile([item[0] for item in selected], .50))
    return {
        "status": "READY", "matches": len(selected),
        "similarity": round(similarity * 100.0, 1),
        "outcomes": {
            "buy": round(buy / len(outcomes), 4),
            "sell": round(sell / len(outcomes), 4),
            "range": round(ranging / len(outcomes), 4),
        },
        "points": points,
        "source": "CLOSED_CANDLE_NEAREST_ANALOGS_NO_FUTURE_LEAKAGE",
    }


def _market_map(frames, primary_name, current):
    primary_atr = max(frames[primary_name]["atr14"], EPS)
    tolerance = primary_atr * .35
    raw_levels = []
    tf_weight = {"M1": 1, "M5": 2, "M15": 3, "H1": 4, "H4": 5}
    for name in (primary_name, "M15", "H1", "H4"):
        frame = frames[name]
        bars = frame["_bars"][-140:]
        highs, lows = _pivots(bars)
        for _, value in highs[-8:]:
            raw_levels.append((float(value), name, "HIGH", tf_weight[name]))
        for _, value in lows[-8:]:
            raw_levels.append((float(value), name, "LOW", tf_weight[name]))
    raw_levels.sort(key=lambda item: item[0])
    clusters = []
    for value, timeframe, kind, weight in raw_levels:
        target = next((cluster for cluster in clusters if abs(cluster["center"] - value) <= tolerance), None)
        if target is None:
            clusters.append({"values": [value], "center": value, "score": weight, "timeframes": {timeframe}, "kinds": {kind}})
        else:
            target["values"].append(value)
            target["center"] = sum(target["values"]) / len(target["values"])
            target["score"] += weight
            target["timeframes"].add(timeframe)
            target["kinds"].add(kind)
    zones = []
    for cluster in clusters:
        center = cluster["center"]
        zones.append({
            "center": center, "low": min(cluster["values"]) - tolerance * .18,
            "high": max(cluster["values"]) + tolerance * .18,
            "type": "SUPPORT" if center < current else "RESISTANCE",
            "strength": min(100, 18 + cluster["score"] * 5),
            "touches": len(cluster["values"]),
            "timeframes": sorted(cluster["timeframes"]),
        })
    supports = sorted((zone for zone in zones if zone["type"] == "SUPPORT"), key=lambda zone: current - zone["center"])
    resistances = sorted((zone for zone in zones if zone["type"] == "RESISTANCE"), key=lambda zone: zone["center"] - current)
    return {"supports": supports[:3], "resistances": resistances[:3], "tolerance": tolerance}


def _channel_pattern(frame):
    bars = frame["_bars"][-34:]
    highs = [float(item["high"]) for item in bars]
    lows = [float(item["low"]) for item in bars]
    upper_slope, upper_intercept = _linear_regression(highs)
    lower_slope, lower_intercept = _linear_regression(lows)
    atr = max(frame["atr14"], EPS)
    upper_norm, lower_norm = upper_slope / atr, lower_slope / atr
    convergence = upper_slope - lower_slope
    if upper_norm > .025 and lower_norm > .025:
        pattern = "RISING_CHANNEL"
    elif upper_norm < -.025 and lower_norm < -.025:
        pattern = "FALLING_CHANNEL"
    elif upper_slope < 0 < lower_slope:
        pattern = "CONVERGING_WEDGE"
    elif convergence < -atr * .01:
        pattern = "NARROWING_CHANNEL"
    else:
        pattern = "RANGE_OR_MIXED"
    end = len(bars) - 1
    return {
        "name": pattern,
        "upper": {"start": upper_intercept, "end": upper_intercept + upper_slope * end},
        "lower": {"start": lower_intercept, "end": lower_intercept + lower_slope * end},
        "upper_slope_atr": round(upper_norm, 4),
        "lower_slope_atr": round(lower_norm, 4),
    }


def _scenario_geometry(direction, market_map, current, bid, ask, spread, atr):
    supports = market_map["supports"]
    resistances = market_map["resistances"]
    buffer = max(spread * 1.5, atr * .10)
    if direction == "BUY":
        trigger = resistances[0]["high"] if resistances else current + atr * .20
        invalidation = supports[0]["low"] - buffer if supports else current - atr
        targets = [zone["center"] for zone in resistances if zone["center"] > trigger]
        if not targets:
            targets = [trigger + abs(trigger - invalidation), trigger + abs(trigger - invalidation) * 1.6]
        entry = ask
    else:
        trigger = supports[0]["low"] if supports else current - atr * .20
        invalidation = resistances[0]["high"] + buffer if resistances else current + atr
        targets = [zone["center"] for zone in supports if zone["center"] < trigger]
        if not targets:
            targets = [trigger - abs(invalidation - trigger), trigger - abs(invalidation - trigger) * 1.6]
        entry = bid
    target1 = targets[0]
    target2 = targets[1] if len(targets) > 1 else targets[0]
    risk = abs(entry - invalidation)
    rr = abs(target1 - entry) / max(risk, EPS)
    return {
        "entry": entry, "trigger": trigger, "stop_loss": invalidation,
        "take_profit": target1, "take_profit_2": target2,
        "risk_distance": risk, "expected_rr": rr,
    }


def analyze_mt5(mt5, symbol, mode="INTRADAY"):
    mode = str(mode or "INTRADAY").upper()
    if mode not in MODE_CONFIG:
        mode = "INTRADAY"
    config = MODE_CONFIG[mode]
    info = mt5.symbol_info(symbol)
    if not info:
        raise RuntimeError(f"Symbol not found: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol: {symbol}")
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError("No live tick available")

    constants = {
        "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    }
    frames = {}
    for name, constant in constants.items():
        count = 900 if name in {"M1", "M5", "M15"} else 600
        rates = mt5.copy_rates_from_pos(symbol, constant, 1, count)
        if rates is None or len(rates) < 120:
            raise RuntimeError(f"Not enough closed {name} candles")
        rows = [
            {field: (rate[field].item() if hasattr(rate[field], "item") else rate[field]) for field in rates.dtype.names}
            for rate in rates
        ]
        frames[name] = _snapshot(rows, name)

    now = datetime.now(timezone.utc)
    bid, ask = float(tick.bid), float(tick.ask)
    current = (bid + ask) / 2.0
    spread = max(0.0, ask - bid)
    spread_to_atr = spread / max(frames["M5"]["atr14"], EPS)
    probabilities, directional_score, disagreement = _mode_probabilities(frames, config, spread_to_atr)
    candidate = "BUY" if directional_score >= 0 else "SELL"
    direction, direction_state = _sticky_direction(
        symbol, mode, candidate, abs(directional_score),
        frames[config["primary"]]["bar_time"], frames, config,
    )
    confidence = probabilities[direction.lower()]

    session = _session(now)
    entry_quality = _entry_quality(direction, frames, session)
    exhaustion = _exhaustion(direction, frames, session)
    hard_blockers = list(entry_quality["hard_blockers"])
    if spread_to_atr > 0.15:
        hard_blockers.append("spread_too_large_relative_to_atr")
    if not exhaustion["approved"]:
        hard_blockers.append("exhaustion_review_required")

    market_map = _market_map(frames, config["primary"], current)
    pattern = _channel_pattern(frames[config["primary"]])
    analogs = _historical_analogs(frames[config["primary"]], config["horizon"], current)
    geometry = _scenario_geometry(
        direction, market_map, current, bid, ask, spread,
        frames[config["primary"]]["atr14"],
    )
    if geometry["expected_rr"] < 1.0:
        hard_blockers.append("reward_smaller_than_risk")

    confirm_bias = frames[config["confirm"]]["structure"]["bias"]
    primary_structure = frames[config["primary"]]["structure"]
    timing_confirms = (
        confirm_bias == direction
        or primary_structure["bos"] == direction
        or primary_structure["choch"] == direction
    )
    historical_confirms = (
        analogs["status"] == "READY"
        and analogs["outcomes"][direction.lower()] >= .45
    )
    setup_status = "READY" if timing_confirms and not hard_blockers and historical_confirms else "FORMING"
    if hard_blockers or direction_state in {"WEAKENING", "REVERSAL_RISK"}:
        setup_status = "WAIT"
    plan_type = "TRADE_READY" if setup_status == "READY" else "WATCH_SCENARIO"

    evidence_for, evidence_against = [], []
    for name in TIMEFRAME_NAMES:
        vote = _tf_vote(frames[name])
        if (direction == "BUY" and vote > 0) or (direction == "SELL" and vote < 0):
            evidence_for.append(f"{name} supports {direction.lower()} direction")
        elif abs(vote) > .15:
            evidence_against.append(f"{name} conflicts with {direction.lower()} direction")
    if historical_confirms:
        evidence_for.append(f"{analogs['matches']} historical analogs support the scenario")
    elif analogs["status"] == "READY":
        evidence_against.append("historical analogs do not confirm the primary direction")

    primary_points = []
    alternative_points = []
    alternative_direction = "SELL" if direction == "BUY" else "BUY"
    historical_conflict = False
    if analogs["status"] == "READY":
        historical_path = [{"step": 0, "price": current, "lower": current, "upper": current}, *analogs["points"]]
        direction_rate = analogs["outcomes"][direction.lower()]
        opposite_rate = analogs["outcomes"][alternative_direction.lower()]
        if direction_rate >= opposite_rate and direction_rate >= analogs["outcomes"]["range"]:
            primary_points = historical_path
        else:
            historical_conflict = True
            alternative_points = historical_path

    public_frames = {
        name: {key: value for key, value in frame.items() if key != "_bars"}
        for name, frame in frames.items()
    }
    chart_bars = [
        {"time": int(item["time"]), "open": float(item["open"]), "high": float(item["high"]),
         "low": float(item["low"]), "close": float(item["close"]), "volume": float(item.get("tick_volume", 0))}
        for item in frames[config["primary"]]["_bars"][-140:]
    ]
    account = mt5.account_info()
    return {
        "engine": "TradePilot Premium Strategy", "engine_version": "2.9.2",
        "symbol": symbol, "captured_at": now.isoformat(), "analysis_mode": mode,
        "data_policy": "CLOSED_CANDLES_ONLY; LIVE_TICK_FOR_DISPLAY_AND_EXECUTION_CHECKS",
        "market_state": {
            "session": session, "bid": bid, "ask": ask, "spread": spread,
            "spread_points": spread / max(float(info.point or 0), EPS),
            "spread_to_atr": spread_to_atr,
            "volatility": "HIGH" if frames["M5"]["adx14"] >= 30 else "NORMAL" if frames["M5"]["adx14"] >= 18 else "LOW",
            "regime": frames["M15"]["structure"]["pattern"],
            "current_location": (
                "NEAR SUPPORT" if market_map["supports"] and current - market_map["supports"][0]["center"] <= frames[config["primary"]]["atr14"] * .45
                else "NEAR RESISTANCE" if market_map["resistances"] and market_map["resistances"][0]["center"] - current <= frames[config["primary"]]["atr14"] * .45
                else "BETWEEN STRUCTURAL LEVELS"
            ),
        },
        "timeframes": public_frames, "probabilities": probabilities,
        "probability_model": "PROPOSED_MODE_WEIGHTED_V2",
        "decision": direction, "direction_state": direction_state,
        "signal_strength": "STRONG" if abs(directional_score) >= .45 else "MODERATE" if abs(directional_score) >= .25 else "WEAK",
        "confidence": round(confidence * 100.0, 1), "directional_score": round(directional_score, 4),
        "direction_source": f"{config['primary']}_PRIMARY_{config['confirm']}_CONFIRMATION_MULTI_TF_CONTEXT",
        "setup_status": setup_status, "plan_type": plan_type, "execution_status": "ANALYSIS_ONLY",
        "entry": geometry["entry"], "trigger": geometry["trigger"],
        "stop_loss": geometry["stop_loss"], "take_profit": geometry["take_profit"],
        "take_profit_2": geometry["take_profit_2"],
        "risk_distance": geometry["risk_distance"], "expected_rr": geometry["expected_rr"],
        "hard_blockers": hard_blockers, "soft_warnings": entry_quality["soft_warnings"],
        "entry_quality": entry_quality, "exhaustion": exhaustion,
        "market_map": market_map, "pattern": pattern, "historical_analogs": analogs,
        "freshness": {"status": "FRESH", "captured_at": now.isoformat(), "primary_closed_bar": frames[config["primary"]]["bar_time"]},
        "invalidation_conditions": [
            f"{config['primary']} close beyond {geometry['stop_loss']:.{int(info.digits)}f}",
            f"Opposite structure confirmed on {config['confirm']}",
            "Spread-to-ATR above configured safety limit",
        ],
        "evidence_for": evidence_for, "evidence_against": evidence_against,
        "plain_language_explanation": (
            f"{direction} remains the main direction ({direction_state}). "
            f"Price is {('near support' if market_map['supports'] else 'inside the current structure')}. "
            f"Entry is {setup_status}; wait for the {config['confirm']} trigger when not ready."
        ),
        "projection": {
            "model": "HISTORICAL_ANALOG_MEDIAN_V2", "label": "HISTORICAL SCENARIO — NOT FUTURE DATA",
            "horizon": f"NEXT_{config['horizon']}_{config['primary']}_BARS",
            "points": primary_points, "alternative_points": alternative_points,
            "alternative_direction": alternative_direction, "historical_conflict": historical_conflict,
            "invalidation": geometry["stop_loss"], "trigger": geometry["trigger"],
        },
        "chart": {"timeframe": config["primary"], "bars": chart_bars},
        "account": {"balance": float(account.balance) if account else None, "equity": float(account.equity) if account else None, "profit": float(account.profit) if account else None},
    }
