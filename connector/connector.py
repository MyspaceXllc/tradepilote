import hashlib, json, os, secrets, threading, time, uuid
from datetime import datetime, time as datetime_time
from pathlib import Path
import MetaTrader5 as mt5
import websocket
import requests
from dotenv import load_dotenv
from connector.premium_strategy import analyze_mt5
from connector.signal_fusion import analyze_mt5 as analyze_signal_fusion

load_dotenv()
STATE = Path(
    os.getenv("STATE_PATH")
    or Path(__file__).with_name("connector_state.json")
)
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
WS_URL = os.getenv("WS_URL", SERVER_URL.replace("https://","wss://").replace("http://","ws://") + "/ws/connector")
MAX_LOT = float(os.getenv("MAX_LOT", "1.0"))
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "XAUUSD")
DEFAULT_VOLUME = float(os.getenv("DEFAULT_VOLUME", "0.01"))
MT5_PATH = os.getenv("MT5_PATH", "")
PAIRING_TOKEN = os.getenv("PAIRING_TOKEN", "")
ALLOW_LIVE_TRADING = os.getenv("ALLOW_LIVE_TRADING", "false").lower() == "true"

def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    data = {
        "device_id": os.getenv("DEVICE_ID") or str(uuid.uuid4()),
        "connector_token": os.getenv("CONNECTOR_TOKEN") or secrets.token_urlsafe(36)
    }
    save_state(data)
    print("FIRST RUN - Device ID:", data["device_id"])
    print("Connector token:", data["connector_token"])
    return data

def bootstrap_device(state):
    r = requests.post(
        SERVER_URL + "/devices/bootstrap",
        json={
            "device_id": state["device_id"],
            "name": os.getenv("DEVICE_NAME", "My MT5 Connector"),
            "connector_token": state["connector_token"]
        },
        timeout=10
    )
    r.raise_for_status()
    print("Device registered with server:", r.json())

    pairing_fingerprint = hashlib.sha256(PAIRING_TOKEN.encode()).hexdigest() if PAIRING_TOKEN else ""
    if PAIRING_TOKEN and state.get("claimed_pairing") != pairing_fingerprint:
        r = requests.post(
            SERVER_URL + "/pairing/claim-device",
            json={
                "device_id": state["device_id"],
                "connector_token": state["connector_token"],
                "pairing_token": PAIRING_TOKEN
            },
            timeout=10
        )
        r.raise_for_status()
        print("Device paired:", r.json())
        state["claimed_pairing"] = pairing_fingerprint
        save_state(state)

def connect_mt5():
    kwargs = {"path": MT5_PATH} if MT5_PATH else {}
    if not mt5.initialize(**kwargs):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    info = mt5.account_info()
    if not info:
        raise RuntimeError("MT5 account is not logged in.")
    return info

def account_mode(info):
    return "demo" if info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "live"

def live_guard():
    info = mt5.account_info()
    if not info:
        raise RuntimeError("MT5 account is not logged in.")
    if account_mode(info) == "live" and not ALLOW_LIVE_TRADING:
        raise RuntimeError("Live trading is locked in this connector")
    return info

def ensure_symbol(symbol):
    info = mt5.symbol_info(symbol)
    if not info:
        raise RuntimeError(f"Symbol not found: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol: {symbol}")
    return mt5.symbol_info(symbol)

def normalize_volume(symbol, volume):
    info = ensure_symbol(symbol)
    volume = min(float(volume), MAX_LOT)
    step = info.volume_step or 0.01
    minimum = info.volume_min or step
    maximum = min(info.volume_max or MAX_LOT, MAX_LOT)
    volume = max(minimum, min(volume, maximum))
    return round(round(volume / step) * step, 8)

def response(cid, ok, message, ticket=None, raw=None):
    return json.dumps({"type":"result","payload":{
        "command_id":cid, "ok":ok, "message":message, "ticket":ticket, "raw":raw
    }})

def order_send_with_fill_fallback(req):
    """Retry only when MT5 explicitly reports an unsupported filling mode."""
    invalid_fill = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)
    modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
    last = None
    for mode in modes:
        attempt = dict(req, type_filling=mode)
        last = mt5.order_send(attempt)
        if not last or last.retcode != invalid_fill:
            return last
    return last

def close_positions(positions):
    closed, failures = 0, []
    last = None
    for p in positions:
        tick = mt5.symbol_info_tick(p.symbol)
        if not tick:
            failures.append({
                "ticket": p.ticket, "retcode": None,
                "comment": "No market tick available"
            })
            continue
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
            "type": close_type, "position": p.ticket, "price": price,
            "deviation": 20, "magic": 260927, "comment": "TradePilot close",
            "type_time": mt5.ORDER_TIME_GTC
        }
        last = order_send_with_fill_fallback(req)
        if last and last.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
        else:
            failures.append({
                "ticket": p.ticket,
                "retcode": getattr(last, "retcode", None),
                "comment": getattr(last, "comment", "No result")
            })
    return closed, failures

def cancel_orders(orders):
    cancelled, failures = 0, []
    for order in orders:
        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order.ticket
        })
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            cancelled += 1
        else:
            failures.append({
                "ticket": order.ticket,
                "retcode": getattr(result, "retcode", None),
                "comment": getattr(result, "comment", "No result")
            })
    return cancelled, failures

def close_profit_group(winners):
    closed_total = 0
    found_tickets = set()
    failed_tickets = set()
    all_failures = []
    passes = 0

    for _ in range(6):
        current = mt5.positions_get() or []
        selected = [
            position
            for position in current
            if (
                (position.profit > 0 if winners else position.profit < 0)
                and position.ticket not in failed_tickets
            )
        ]
        if not selected:
            break

        passes += 1
        found_tickets.update(position.ticket for position in selected)
        closed, failures = close_positions(selected)
        closed_total += closed
        all_failures.extend(failures)
        failed_tickets.update(
            failure["ticket"] for failure in failures
        )

        if closed == 0:
            break
        time.sleep(0.15)

    return closed_total, len(found_tickets), passes, all_failures


def market_performance_stats(positions=None):
    positions = positions if positions is not None else (mt5.positions_get() or [])
    account = mt5.account_info()
    now = datetime.now()
    day_start = datetime.combine(now.date(), datetime_time.min)
    deals = mt5.history_deals_get(day_start, now) or []
    exit_kinds = {
        getattr(mt5, "DEAL_ENTRY_OUT", 1),
        getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
    }
    closing_deals = [
        item
        for item in deals
        if item.entry in exit_kinds and item.position_id
    ]
    closed_position_ids = sorted(
        {int(item.position_id) for item in closing_deals}
    )
    closed_results = []
    closed_pips = 0.0

    for position_id in closed_position_ids:
        position_deals = mt5.history_deals_get(position=position_id) or []
        trade_deals = [
            item
            for item in position_deals
            if item.type
            in {
                getattr(mt5, "DEAL_TYPE_BUY", 0),
                getattr(mt5, "DEAL_TYPE_SELL", 1),
            }
        ]
        net = sum(
            float(item.profit or 0)
            + float(item.swap or 0)
            + float(item.commission or 0)
            + float(getattr(item, "fee", 0) or 0)
            for item in trade_deals
        )
        closed_results.append(net)

        opening = [
            item
            for item in trade_deals
            if item.entry == getattr(mt5, "DEAL_ENTRY_IN", 0)
        ]
        exits = [
            item
            for item in closing_deals
            if int(item.position_id) == position_id
        ]
        open_volume = sum(float(item.volume) for item in opening)
        exit_volume = sum(float(item.volume) for item in exits)
        if not opening or not exits or not open_volume or not exit_volume:
            continue
        open_price = sum(
            float(item.price) * float(item.volume) for item in opening
        ) / open_volume
        exit_price = sum(
            float(item.price) * float(item.volume) for item in exits
        ) / exit_volume
        symbol_info = mt5.symbol_info(opening[0].symbol)
        if not symbol_info or not symbol_info.point:
            continue
        pip_size = float(symbol_info.point)
        if int(symbol_info.digits) in (3, 5):
            pip_size *= 10
        is_buy = opening[0].type == getattr(mt5, "DEAL_TYPE_BUY", 0)
        move = (
            exit_price - open_price if is_buy else open_price - exit_price
        )
        closed_pips += move / pip_size

    gross_win = sum(value for value in closed_results if value > 0)
    gross_loss = abs(sum(value for value in closed_results if value < 0))
    open_profit = sum(float(item.profit) for item in positions)
    return {
        "period": "TODAY",
        "balance": float(account.balance) if account else 0.0,
        "equity": float(account.equity) if account else 0.0,
        "account_profit": float(account.profit) if account else open_profit,
        "open_profit": open_profit,
        "closed_profit": sum(closed_results),
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "closed_wins": len([value for value in closed_results if value > 0]),
        "closed_losses": len([value for value in closed_results if value < 0]),
        "closed_pips": closed_pips,
    }


def execute(p):
    cid, action = p["command_id"], p["action"]
    try:
        if action not in ("STATUS", "SYMBOLS", "POSITIONS", "PREMIUM_ANALYSIS", "SIGNAL_FUSION_DATA"):
            live_guard()
        if action == "SIGNAL_FUSION_DATA":
            symbol = p.get("symbol") or DEFAULT_SYMBOL
            analysis = analyze_signal_fusion(
                mt5,
                symbol,
                p.get("timeframe") or "M5",
                p.get("minimum_separation", 0.25),
                p.get("count", 180),
            )
            return response(
                cid,
                True,
                f"Signal Fusion data ready for {symbol}",
                raw=analysis,
            )
        if action == "PREMIUM_ANALYSIS":
            symbol = p.get("symbol") or DEFAULT_SYMBOL
            analysis = analyze_mt5(mt5, symbol, p.get("analysis_mode") or "INTRADAY")
            return response(
                cid,
                True,
                f"Premium analysis ready for {symbol}",
                raw=analysis,
            )
        if action == "SYMBOLS":
            symbols = mt5.symbols_get()
            if symbols is None:
                return response(
                    cid,
                    False,
                    f"Could not read MT5 symbols: {mt5.last_error()}",
                )
            disabled = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
            available = [
                {
                    "name": item.name,
                    "description": item.description or "",
                    "path": item.path or "",
                    "visible": bool(item.visible),
                    "digits": int(item.digits),
                    "volume_min": float(item.volume_min or 0),
                    "volume_max": float(item.volume_max or 0),
                    "volume_step": float(item.volume_step or 0),
                }
                for item in symbols
                if item.name and item.trade_mode != disabled
            ]
            available.sort(
                key=lambda item: (
                    not item["visible"],
                    item["path"].lower(),
                    item["name"].lower(),
                )
            )
            return response(
                cid,
                True,
                f"Loaded {len(available)} tradeable symbol(s)",
                raw={"symbols": available},
            )
        if action == "POSITIONS":
            positions = mt5.positions_get() or []
            stats = market_performance_stats(positions)
            return response(
                cid,
                True,
                f"Loaded {len(positions)} open position(s)",
                raw={
                    "positions": [
                        {
                            "ticket": int(item.ticket),
                            "symbol": item.symbol,
                            "direction": (
                                "BUY"
                                if item.type == mt5.POSITION_TYPE_BUY
                                else "SELL"
                            ),
                            "volume": float(item.volume),
                            "entry_price": float(item.price_open),
                            "current_price": float(item.price_current),
                            "sl": float(item.sl or 0),
                            "tp": float(item.tp or 0),
                            "profit": float(item.profit),
                        }
                        for item in positions
                    ],
                    "stats": stats,
                },
            )

        if action == "STATUS":
            info = mt5.account_info()
            symbol = p.get("symbol") or DEFAULT_SYMBOL
            ensure_symbol(symbol)
            tick = mt5.symbol_info_tick(symbol)
            positions = mt5.positions_get(symbol=symbol) or []
            total_volume = sum(float(x.volume) for x in positions)
            entry_price = (
                sum(float(x.price_open) * float(x.volume) for x in positions)
                / total_volume
                if total_volume else None
            )
            position_types = {x.type for x in positions}
            if len(position_types) > 1:
                direction = "MIXED"
            elif positions:
                direction = (
                    "BUY"
                    if positions[0].type == mt5.POSITION_TYPE_BUY
                    else "SELL"
                )
            else:
                direction = None
            stats = market_performance_stats(mt5.positions_get() or [])
            return response(cid, True, "OK", raw={
                "login": str(info.login) if info else None,
                "balance": info.balance if info else None,
                "equity": info.equity if info else None,
                "symbol": symbol,
                "bid": float(tick.bid) if tick else None,
                "ask": float(tick.ask) if tick else None,
                "current_price": (
                    float(positions[0].price_current)
                    if positions else (float(tick.last or tick.bid) if tick else None)
                ),
                "entry_price": entry_price,
                "profit": sum(float(x.profit) for x in positions),
                "volume": total_volume,
                "positions_total": len(positions),
                "direction": direction,
                "stats": stats,
            })

        if action in ("CLOSE_WINNERS", "CLOSE_LOSERS"):
            winners = action == "CLOSE_WINNERS"
            closed, found, passes, failures = close_profit_group(winners)
            group_label = "winning" if winners else "losing"
            return response(
                cid,
                not failures,
                (
                    f"Closed {closed} of {found} {group_label} position(s)"
                    f" in {passes} pass(es)"
                ),
                raw={"failures": failures, "passes": passes},
            )

        if action in ("CLOSE", "EMERGENCY_STOP"):
            positions = mt5.positions_get()
            if action == "CLOSE" and p.get("ticket"):
                positions = mt5.positions_get(ticket=int(p["ticket"]))
            positions = positions or []
            closed, failures = close_positions(positions)
            cancelled, cancel_failures = 0, []
            if action == "EMERGENCY_STOP":
                orders = mt5.orders_get() or []
                cancelled, cancel_failures = cancel_orders(orders)
                failures.extend(cancel_failures)
            return response(
                cid, not failures,
                (
                    f"Closed {closed} of {len(positions)} position(s); "
                    f"cancelled {cancelled} pending order(s)"
                    if action == "EMERGENCY_STOP"
                    else f"Closed {closed} of {len(positions)} position(s)"
                ),
                raw={"failures": failures}
            )

        if action == "CANCEL":
            orders = mt5.orders_get() or []
            target = p.get("ticket")
            selected_orders = [
                o for o in orders if not target or o.ticket == int(target)
            ]
            count, failures = cancel_orders(selected_orders)
            return response(
                cid, not failures,
                f"Cancelled {count} of {len(selected_orders)} pending order(s)",
                raw={"failures": failures}
            )

        symbol = p.get("symbol") or DEFAULT_SYMBOL
        ensure_symbol(symbol)
        volume = normalize_volume(symbol, p.get("volume", DEFAULT_VOLUME))
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return response(cid, False, "No market tick available")

        if action in ("SHARK_BUY", "SHARK_SELL", "SHARK_BOTH"):
            raw_lots = p.get("shark_lots") or [0.03, 0.02, 0.01, 0.01]
            if (
                len(raw_lots) != 4
                or any(float(item) <= 0 for item in raw_lots)
            ):
                return response(
                    cid,
                    False,
                    "Shark requires exactly four positive lot values",
                )
            level_count = max(1, min(3, int(p.get("shark_levels") or 3)))
            lots = [normalize_volume(symbol, item) for item in raw_lots]
            active_lots = lots[: level_count + 1]
            info = ensure_symbol(symbol)
            requested_spacing = max(
                1,
                int(p.get("shark_spacing_points") or 50),
            )
            minimum_spacing = int(info.trade_stops_level or 0) + 1
            spacing_points = max(requested_spacing, minimum_spacing)
            point = float(info.point)
            digits = int(info.digits)
            done_codes = (
                mt5.TRADE_RETCODE_DONE,
                mt5.TRADE_RETCODE_PLACED,
            )

            if action == "SHARK_BOTH":
                account = mt5.account_info()
                hedging_mode = getattr(
                    mt5,
                    "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING",
                    2,
                )
                margin_mode = getattr(account, "margin_mode", None)
                if margin_mode is not None and margin_mode != hedging_mode:
                    return response(
                        cid,
                        False,
                        "SHARK BOTH requires an MT5 Hedging account",
                    )

            def place_shark_side(is_buy):
                side_name = "Buy" if is_buy else "Sell"
                current_tick = mt5.symbol_info_tick(symbol)
                if not current_tick:
                    return {
                        "side": side_name.upper(),
                        "orders": [],
                        "failures": [{"comment": "No market tick available"}],
                    }
                market_type = (
                    mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
                )
                market_price = float(
                    current_tick.ask if is_buy else current_tick.bid
                )
                market_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": active_lots[0],
                    "type": market_type,
                    "price": market_price,
                    "sl": 0.0,
                    "tp": 0.0,
                    "deviation": 20,
                    "magic": 260927,
                    "comment": f"TradePilot Shark {side_name} 1",
                    "type_time": mt5.ORDER_TIME_GTC,
                }
                market_result = order_send_with_fill_fallback(market_request)
                if not market_result or market_result.retcode not in done_codes:
                    return {
                        "side": side_name.upper(),
                        "orders": [],
                        "failures": [{
                            "level": 1,
                            "lot": active_lots[0],
                            "price": market_price,
                            "retcode": getattr(market_result, "retcode", None),
                            "comment": (
                                getattr(market_result, "comment", None)
                                if market_result
                                else str(mt5.last_error())
                            ),
                        }],
                    }

                orders = [{
                    "level": 1,
                    "kind": "MARKET",
                    "ticket": (
                        getattr(market_result, "order", None)
                        or getattr(market_result, "deal", None)
                    ),
                    "lot": active_lots[0],
                    "price": market_price,
                }]
                failures = []
                pending_type = (
                    mt5.ORDER_TYPE_BUY_STOP
                    if is_buy
                    else mt5.ORDER_TYPE_SELL_STOP
                )
                direction = 1 if is_buy else -1
                for level, lot in enumerate(active_lots[1:], start=1):
                    pending_price = round(
                        market_price
                        + direction * spacing_points * point * level,
                        digits,
                    )
                    pending_request = {
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": symbol,
                        "volume": lot,
                        "type": pending_type,
                        "price": pending_price,
                        "sl": 0.0,
                        "tp": 0.0,
                        "deviation": 20,
                        "magic": 260927,
                        "comment": f"TradePilot Shark {side_name} {level + 1}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_RETURN,
                    }
                    result = order_send_with_fill_fallback(pending_request)
                    if result and result.retcode in done_codes:
                        orders.append({
                            "level": level + 1,
                            "kind": "STOP",
                            "ticket": (
                                getattr(result, "order", None)
                                or getattr(result, "deal", None)
                            ),
                            "lot": lot,
                            "price": pending_price,
                        })
                    else:
                        failures.append({
                            "level": level + 1,
                            "lot": lot,
                            "price": pending_price,
                            "retcode": getattr(result, "retcode", None),
                            "comment": (
                                getattr(result, "comment", None)
                                if result
                                else str(mt5.last_error())
                            ),
                        })
                return {
                    "side": side_name.upper(),
                    "orders": orders,
                    "failures": failures,
                }

            sides = (
                [True, False]
                if action == "SHARK_BOTH"
                else [action == "SHARK_BUY"]
            )
            side_results = [place_shark_side(is_buy) for is_buy in sides]
            opened = sum(len(item["orders"]) for item in side_results)
            expected = len(sides) * (level_count + 1)
            failures = [
                failure
                for item in side_results
                for failure in item["failures"]
            ]
            first_ticket = next(
                (
                    order.get("ticket")
                    for item in side_results
                    for order in item["orders"]
                    if order.get("ticket")
                ),
                None,
            )
            label = (
                "Shark Both"
                if action == "SHARK_BOTH"
                else f"Shark {'Buy' if action == 'SHARK_BUY' else 'Sell'}"
            )
            return response(
                cid,
                not failures and opened == expected,
                (
                    f"{label} opened {opened} of {expected} order(s) • "
                    f"{level_count} line(s) • {spacing_points} points"
                ),
                first_ticket,
                {
                    "levels": level_count,
                    "spacing_points": spacing_points,
                    "sides": side_results,
                    "failures": failures,
                },
            )

        if action in ("BUY","SELL"):
            typ = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
            price = tick.ask if action == "BUY" else tick.bid
            req = {
                "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
                "type": typ, "price": price, "sl": p.get("sl") or 0.0, "tp": p.get("tp") or 0.0,
                "deviation": 20, "magic": 260927, "comment": p.get("comment","TradePilot"),
                "type_time": mt5.ORDER_TIME_GTC
            }
            r = order_send_with_fill_fallback(req)
            if not r:
                return response(cid, False, f"order_send returned None: {mt5.last_error()}")
            ok = r.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
            return response(cid, ok, str(r.comment),
                            getattr(r, "order", None) or getattr(r, "deal", None),
                            {"retcode": r.retcode, "comment": r.comment})

        if action in ("BUY_LIMIT", "SELL_LIMIT"):
            price = float(p["price"])
            if action == "BUY_LIMIT" and price >= tick.ask:
                return response(cid, False, "BUY LIMIT price must be below the current ask")
            if action == "SELL_LIMIT" and price <= tick.bid:
                return response(cid, False, "SELL LIMIT price must be above the current bid")
            typ = mt5.ORDER_TYPE_BUY_LIMIT if action == "BUY_LIMIT" else mt5.ORDER_TYPE_SELL_LIMIT
            req = {
                "action": mt5.TRADE_ACTION_PENDING, "symbol": symbol, "volume": volume,
                "type": typ, "price": price, "sl": p.get("sl") or 0.0, "tp": p.get("tp") or 0.0,
                "deviation": 20, "magic": 260927, "comment": p.get("comment","TradePilot limit"),
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_RETURN
            }
            r = order_send_with_fill_fallback(req)
            if not r:
                return response(cid, False, f"order_send returned None: {mt5.last_error()}")
            ok = r.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
            return response(cid, ok, str(r.comment), getattr(r, "order", None),
                            {"retcode": r.retcode, "comment": r.comment})

        return response(cid, False, f"Unsupported action: {action}")
    except Exception as e:
        return response(cid, False, str(e))

def main():
    state = load_state()
    bootstrap_device(state)
    info = connect_mt5()
    print("Connected to MT5:", info.login, info.company)

    def on_open(ws):
        current = connect_mt5()
        ws.send(json.dumps({
            "device_id": state["device_id"],
            "connector_token": state["connector_token"],
            "name": os.getenv("DEVICE_NAME","My MT5 Connector"),
            "mt5_account": str(current.login),
            "broker": current.company,
            "terminal": getattr(current, "server", ""),
            "mode": account_mode(current)
        }))
        def heartbeat():
            while ws.sock and ws.sock.connected:
                time.sleep(15)
                try:
                    ws.send(json.dumps({"type": "heartbeat"}))
                except Exception:
                    break
        threading.Thread(target=heartbeat, daemon=True).start()

    def on_message(ws, message):
        msg = json.loads(message)
        if msg.get("type") == "command":
            ws.send(execute(msg["payload"]))

    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL, on_open=on_open, on_message=on_message,
                on_error=lambda ws,e: print("WS error:",e),
                on_close=lambda ws,c,m: print("WS closed:",c,m)
            )
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except Exception as e:
            print("Connector loop:", e)
        time.sleep(3)

if __name__ == "__main__":
    main()
