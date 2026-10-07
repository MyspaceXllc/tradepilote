import asyncio, json, secrets, hashlib, logging, os, time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from .config import settings
from .db import init_db, fetchone, fetchall, execute
from .security import hash_password, verify_password, create_access_token, decode_access_token
from .schemas import (
    RegisterIn, LoginIn, DeviceRegisterIn, ClaimDeviceIn, CommandIn,
    SetupCreateIn, SetupClaimIn, ConnectorHello, CommandResult
)

app = FastAPI(title=settings.app_name, version="2.9.2")
logger = logging.getLogger("tradepilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.allowed_origins.split(",") if x.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
connector_sockets = {}
user_sockets = {}
snapshot_waiters = {}
rate_state = {}

@app.on_event("startup")
async def startup():
    if len(settings.secret_key) < 16:
        raise RuntimeError("SECRET_KEY must be set to a strong random value")
    init_db()

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(token: str = Depends(oauth2)):
    try:
        uid = decode_access_token(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    row = fetchone("SELECT * FROM users WHERE id=?", (uid,))
    if not row:
        raise HTTPException(401, "User not found")
    return row

def audit(user_id, device_id, event, detail=""):
    execute(
        "INSERT INTO audit(user_id,device_id,event,detail,created_at) VALUES(?,?,?,?,?)",
        (user_id, device_id, event, detail[:1000], datetime.now(timezone.utc).isoformat())
    )

def rate_limit(user_id):
    now = time.time()
    arr = rate_state.setdefault(user_id, [])
    arr[:] = [t for t in arr if now - t < 60]
    if len(arr) >= settings.max_commands_per_minute:
        raise HTTPException(429, "Command rate limit exceeded")
    arr.append(now)

@app.get("/health")
def health():
    return {"ok": True, "demo_only": settings.demo_only}

@app.post("/auth/register")
def register(data: RegisterIn):
    if fetchone("SELECT id FROM users WHERE username=?", (data.username,)):
        raise HTTPException(409, "Username already exists")
    uid = str(uuid4())
    execute(
        "INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)",
        (uid, data.username, hash_password(data.password),
         datetime.now(timezone.utc).isoformat())
    )
    return {"access_token": create_access_token(uid), "token_type": "bearer"}

@app.post("/auth/login")
def login(data: LoginIn):
    row = fetchone("SELECT * FROM users WHERE username=?", (data.username,))
    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": create_access_token(row["id"]), "token_type": "bearer"}

@app.get("/me")
def me(user=Depends(current_user)):
    return {"id": user["id"], "username": user["username"]}

@app.post("/devices/bootstrap")
def bootstrap_device(data: DeviceRegisterIn):
    existing = fetchone("SELECT * FROM devices WHERE id=?", (data.device_id,))
    h = token_hash(data.connector_token)
    if existing:
        if existing["connector_token_hash"] != h:
            raise HTTPException(401, "Invalid connector token")
        return {"ok": True, "device_id": data.device_id, "status": existing["status"]}
    execute(
        "INSERT INTO devices(id,user_id,name,connector_token_hash,created_at) VALUES(?,?,?,?,?)",
        (data.device_id, None, data.name, h, datetime.now(timezone.utc).isoformat())
    )
    return {"ok": True, "device_id": data.device_id, "status": "offline"}

@app.post("/pairing/create")
def create_pairing(user=Depends(current_user)):
    raw = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO pairings(token_hash,user_id,expires_at) VALUES(?,?,?)",
        (token_hash(raw), user["id"], time.time() + settings.pairing_ttl_seconds)
    )
    return {"pairing_token": raw, "expires_in": settings.pairing_ttl_seconds}

@app.post("/setup/create")
def create_setup_token(data: SetupCreateIn):
    device = fetchone("SELECT * FROM devices WHERE id=?", (data.device_id,))
    if not device or device["connector_token_hash"] != token_hash(data.connector_token):
        raise HTTPException(401, "Invalid device credentials")
    execute(
        "DELETE FROM setup_tokens WHERE expires_at<? OR used=1",
        (time.time(),)
    )
    raw = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO setup_tokens(token_hash,device_id,user_id,expires_at) "
        "VALUES(?,?,?,?)",
        (
            token_hash(raw), data.device_id, device["user_id"],
            time.time() + settings.pairing_ttl_seconds
        )
    )
    return {"setup_token": raw, "expires_in": settings.pairing_ttl_seconds}

@app.post("/setup/claim")
def claim_setup_token(data: SetupClaimIn):
    setup = fetchone(
        "SELECT * FROM setup_tokens WHERE token_hash=? AND used=0",
        (token_hash(data.setup_token),)
    )
    if not setup or setup["expires_at"] < time.time():
        raise HTTPException(400, "Setup QR is invalid or expired")
    device = fetchone("SELECT * FROM devices WHERE id=?", (setup["device_id"],))
    if not device:
        raise HTTPException(404, "Device not found")

    user_id = device["user_id"] or setup["user_id"]
    if not user_id:
        user_id = str(uuid4())
        username = f"owner_{user_id.replace('-', '')[:10]}"
        random_password = secrets.token_urlsafe(48)
        execute(
            "INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)",
            (
                user_id, username, hash_password(random_password),
                datetime.now(timezone.utc).isoformat()
            )
        )
        execute(
            "UPDATE devices SET user_id=? WHERE id=?",
            (user_id, setup["device_id"])
        )
    execute(
        "UPDATE setup_tokens SET used=1,user_id=? WHERE token_hash=?",
        (user_id, token_hash(data.setup_token))
    )
    audit(user_id, setup["device_id"], "SETUP_QR_CLAIMED")
    return {
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
        "device_id": setup["device_id"],
    }

@app.post("/pairing/claim-device")
def claim_device(data: ClaimDeviceIn):
    pair = fetchone(
        "SELECT * FROM pairings WHERE token_hash=? AND used=0",
        (token_hash(data.pairing_token),)
    )
    if not pair or pair["expires_at"] < time.time():
        raise HTTPException(400, "Pairing token invalid or expired")
    device = fetchone("SELECT * FROM devices WHERE id=?", (data.device_id,))
    if not device or device["connector_token_hash"] != token_hash(data.connector_token):
        raise HTTPException(401, "Invalid device credentials")
    if device["user_id"] and device["user_id"] != pair["user_id"]:
        raise HTTPException(409, "Device is already paired; unpair it first")
    execute("UPDATE devices SET user_id=? WHERE id=?", (pair["user_id"], data.device_id))
    execute(
        "UPDATE pairings SET used=1 WHERE token_hash=?",
        (token_hash(data.pairing_token),)
    )
    audit(pair["user_id"], data.device_id, "DEVICE_PAIRED")
    return {"ok": True, "device_id": data.device_id}

@app.post("/pairing/bind")
def bind_pairing(data: ClaimDeviceIn, user=Depends(current_user)):
    row = fetchone(
        "SELECT * FROM pairings WHERE token_hash=? AND used=0",
        (token_hash(data.pairing_token),)
    )
    if not row or row["expires_at"] < time.time():
        raise HTTPException(400, "Pairing token invalid or expired")
    device = fetchone("SELECT * FROM devices WHERE id=?", (data.device_id,))
    if not device:
        raise HTTPException(404, "Device not found")
    if device["connector_token_hash"] != token_hash(data.connector_token):
        raise HTTPException(401, "Invalid device credentials")
    if device["user_id"] and device["user_id"] != user["id"]:
        raise HTTPException(409, "Device is already paired; unpair it first")
    if row["user_id"] != user["id"]:
        raise HTTPException(403, "Pairing belongs to another user")
    execute("UPDATE devices SET user_id=? WHERE id=?", (user["id"], data.device_id))
    execute(
        "UPDATE pairings SET used=1 WHERE token_hash=?",
        (token_hash(data.pairing_token),)
    )
    audit(user["id"], data.device_id, "DEVICE_PAIRED")
    return {"ok": True, "device_id": data.device_id}

@app.get("/devices")
def devices(user=Depends(current_user)):
    rows = fetchall(
        "SELECT id,name,status,mt5_account,broker,terminal,mode,trading_locked,"
        "last_seen,created_at "
        "FROM devices WHERE user_id=?", (user["id"],)
    )
    return [dict(r) for r in rows]

@app.get("/devices/{device_id}/snapshot")
async def device_snapshot(
    device_id: str,
    symbol: str,
    user=Depends(current_user),
):
    if not symbol or len(symbol) > 40:
        raise HTTPException(400, "Invalid symbol")
    device = fetchone(
        "SELECT * FROM devices WHERE id=? AND user_id=?",
        (device_id, user["id"])
    )
    if not device:
        raise HTTPException(404, "Device not found")
    ws = connector_sockets.get(device_id)
    if not ws:
        raise HTTPException(409, "Connector offline")

    command_id = str(uuid4())
    future = asyncio.get_running_loop().create_future()
    snapshot_waiters[command_id] = future
    try:
        await ws.send_text(json.dumps({
            "type": "command",
            "payload": {
                "command_id": command_id,
                "device_id": device_id,
                "action": "STATUS",
                "symbol": symbol,
            }
        }))
        return await asyncio.wait_for(future, timeout=3)
    except asyncio.TimeoutError:
        raise HTTPException(504, "MT5 snapshot timed out")
    finally:
        snapshot_waiters.pop(command_id, None)


@app.get("/local/market-lab/positions")
async def local_market_lab_positions(request: Request):
    """Loopback-only position feed for the installed Windows Market Lab."""
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Local Market Lab access only")

    device = fetchone(
        "SELECT * FROM devices WHERE status='online' "
        "ORDER BY last_seen DESC LIMIT 1"
    )
    if not device:
        return {"ok": True, "raw": {"positions": []}}
    ws = connector_sockets.get(device["id"])
    if not ws:
        return {"ok": True, "raw": {"positions": []}}

    command_id = str(uuid4())
    future = asyncio.get_running_loop().create_future()
    snapshot_waiters[command_id] = future
    try:
        await ws.send_text(json.dumps({
            "type": "command",
            "payload": {
                "command_id": command_id,
                "device_id": device["id"],
                "action": "POSITIONS",
            },
        }))
        return await asyncio.wait_for(future, timeout=3)
    except asyncio.TimeoutError:
        raise HTTPException(504, "MT5 positions timed out")
    finally:
        snapshot_waiters.pop(command_id, None)


@app.get("/local/signal-fusion/data")
async def local_signal_fusion_data(
    request: Request,
    symbol: str,
    timeframe: str = "M5",
    minimum_separation: float = 0.25,
    count: int = 180,
):
    """Loopback-only closed-candle feed for Signal Fusion."""
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Local Signal Fusion access only")
    if not symbol or len(symbol) > 40:
        raise HTTPException(400, "Invalid symbol")
    timeframe = timeframe.upper()
    if timeframe not in {"M1", "M5", "M15", "H1", "H4", "D1"}:
        raise HTTPException(400, "Timeframe must be M1, M5, M15, H1, H4, or D1")
    if not 0 <= minimum_separation <= 2:
        raise HTTPException(400, "Minimum separation must be between 0 and 2")
    count = max(120, min(420, count))

    device = fetchone(
        "SELECT * FROM devices WHERE status='online' "
        "ORDER BY last_seen DESC LIMIT 1"
    )
    if not device:
        raise HTTPException(409, "No online MT5 connector")
    ws = connector_sockets.get(device["id"])
    if not ws:
        raise HTTPException(409, "MT5 connector offline")

    command_id = str(uuid4())
    future = asyncio.get_running_loop().create_future()
    snapshot_waiters[command_id] = future
    try:
        await ws.send_text(json.dumps({
            "type": "command",
            "payload": {
                "command_id": command_id,
                "device_id": device["id"],
                "action": "SIGNAL_FUSION_DATA",
                "symbol": symbol,
                "timeframe": timeframe,
                "minimum_separation": minimum_separation,
                "count": count,
            },
        }))
        result = await asyncio.wait_for(future, timeout=12)
        if not result.get("ok"):
            raise HTTPException(422, result.get("message") or "Signal Fusion failed")
        return result
    except asyncio.TimeoutError:
        raise HTTPException(504, "Signal Fusion timed out")
    finally:
        snapshot_waiters.pop(command_id, None)


@app.get("/local/premium-strategy/analyze")
async def local_premium_strategy_analysis(request: Request, symbol: str, mode: str = "INTRADAY"):
    """Loopback-only deterministic Premium Strategy feed from local MT5."""
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Local Premium Strategy access only")
    if not symbol or len(symbol) > 40:
        raise HTTPException(400, "Invalid symbol")

    device = fetchone(
        "SELECT * FROM devices WHERE status='online' "
        "ORDER BY last_seen DESC LIMIT 1"
    )
    if not device:
        raise HTTPException(409, "No online MT5 connector")
    ws = connector_sockets.get(device["id"])
    if not ws:
        raise HTTPException(409, "MT5 connector offline")

    command_id = str(uuid4())
    future = asyncio.get_running_loop().create_future()
    snapshot_waiters[command_id] = future
    try:
        await ws.send_text(json.dumps({
            "type": "command",
            "payload": {
                "command_id": command_id,
                "device_id": device["id"],
                "action": "PREMIUM_ANALYSIS",
                "symbol": symbol,
                "analysis_mode": mode,
            },
        }))
        result = await asyncio.wait_for(future, timeout=12)
        if not result.get("ok"):
            raise HTTPException(422, result.get("message") or "Analysis failed")
        return result
    except asyncio.TimeoutError:
        raise HTTPException(504, "Premium Strategy analysis timed out")
    finally:
        snapshot_waiters.pop(command_id, None)


@app.get("/local/market-lab/symbols")
async def local_market_lab_symbols(request: Request):
    """Loopback-only broker symbol list for installed analysis pages."""
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Local Market Lab access only")
    device = fetchone(
        "SELECT * FROM devices WHERE status='online' "
        "ORDER BY last_seen DESC LIMIT 1"
    )
    if not device:
        raise HTTPException(409, "No online MT5 connector")
    ws = connector_sockets.get(device["id"])
    if not ws:
        raise HTTPException(409, "MT5 connector offline")
    command_id = str(uuid4())
    future = asyncio.get_running_loop().create_future()
    snapshot_waiters[command_id] = future
    try:
        await ws.send_text(json.dumps({
            "type": "command",
            "payload": {
                "command_id": command_id,
                "device_id": device["id"],
                "action": "SYMBOLS",
            },
        }))
        return await asyncio.wait_for(future, timeout=8)
    except asyncio.TimeoutError:
        raise HTTPException(504, "MT5 symbol list timed out")
    finally:
        snapshot_waiters.pop(command_id, None)


@app.get("/devices/{device_id}/symbols")
async def device_symbols(device_id: str, user=Depends(current_user)):
    device = fetchone(
        "SELECT * FROM devices WHERE id=? AND user_id=?",
        (device_id, user["id"])
    )
    if not device:
        raise HTTPException(404, "Device not found")
    ws = connector_sockets.get(device_id)
    if not ws:
        raise HTTPException(409, "Connector offline")

    command_id = str(uuid4())
    future = asyncio.get_running_loop().create_future()
    snapshot_waiters[command_id] = future
    try:
        await ws.send_text(json.dumps({
            "type": "command",
            "payload": {
                "command_id": command_id,
                "device_id": device_id,
                "action": "SYMBOLS",
            }
        }))
        return await asyncio.wait_for(future, timeout=8)
    except asyncio.TimeoutError:
        raise HTTPException(504, "MT5 symbol list timed out")
    finally:
        snapshot_waiters.pop(command_id, None)

@app.post("/devices/{device_id}/unpair")
def unpair(device_id: str, user=Depends(current_user)):
    row = fetchone("SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user["id"]))
    if not row:
        raise HTTPException(404, "Device not found")
    execute("UPDATE devices SET user_id=NULL,status='offline' WHERE id=?", (device_id,))
    audit(user["id"], device_id, "DEVICE_UNPAIRED")
    return {"ok": True}

@app.post("/commands")
async def command(data: CommandIn, user=Depends(current_user)):
    device = fetchone("SELECT * FROM devices WHERE id=? AND user_id=?", (data.device_id, user["id"]))
    if not device:
        raise HTTPException(404, "Device not found")
    old = fetchone("SELECT * FROM commands WHERE command_id=?", (data.command_id,))
    if old:
        if old["user_id"] != user["id"]:
            raise HTTPException(409, "Command ID already exists")
        return {
            "command_id": data.command_id,
            "status": old["status"],
            "result": json.loads(old["result"]) if old["result"] else None
        }
    rate_limit(user["id"])
    if settings.demo_only and device["mode"] != "demo":
        raise HTTPException(403, "Server is configured for DEMO ONLY")
    if device["trading_locked"] and data.action != "STATUS":
        raise HTTPException(423, "Trading is locked by Emergency Stop")
    if data.action in {
        "BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT",
        "SHARK_BUY", "SHARK_SELL", "SHARK_BOTH",
    } and not data.symbol:
        raise HTTPException(400, "Symbol is required")
    if data.action in {"BUY_LIMIT", "SELL_LIMIT"} and not data.price:
        raise HTTPException(400, "Price is required for a limit order")
    if data.action in {"SHARK_BUY", "SHARK_SELL", "SHARK_BOTH"}:
        lots = data.shark_lots or [0.03, 0.02, 0.01, 0.01]
        if len(lots) != 4 or any(lot <= 0 or lot > 100 for lot in lots):
            raise HTTPException(
                400,
                "Shark requires exactly four positive lot values",
            )

    payload = data.model_dump()
    now = datetime.now(timezone.utc).isoformat()
    execute(
        "INSERT INTO commands(command_id,user_id,device_id,payload,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (data.command_id, user["id"], data.device_id, json.dumps(payload), "queued", now, now)
    )
    audit(user["id"], data.device_id, "COMMAND_SENT", json.dumps(payload))
    ws = connector_sockets.get(data.device_id)
    if not ws:
        execute(
            "UPDATE commands SET status='failed',result=?,updated_at=? WHERE command_id=?",
            (json.dumps({"ok": False, "message": "Connector offline"}),
             datetime.now(timezone.utc).isoformat(), data.command_id)
        )
        raise HTTPException(409, "Connector offline")
    await ws.send_text(json.dumps({"type": "command", "payload": payload}))
    return {"command_id": data.command_id, "status": "queued"}

@app.get("/commands/{command_id}")
def command_status(command_id: str, user=Depends(current_user)):
    row = fetchone(
        "SELECT command_id,status,result,created_at,updated_at FROM commands "
        "WHERE command_id=? AND user_id=?",
        (command_id, user["id"])
    )
    if not row:
        raise HTTPException(404, "Command not found")
    return {
        "command_id": row["command_id"],
        "status": row["status"],
        "result": json.loads(row["result"]) if row["result"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

@app.post("/emergency-stop")
async def emergency_stop(user=Depends(current_user)):
    devices = fetchall("SELECT id,mode FROM devices WHERE user_id=?", (user["id"],))
    results = []
    for d in devices:
        if settings.demo_only and d["mode"] != "demo":
            results.append({
                "device_id": d["id"], "sent": False,
                "reason": "Server is configured for DEMO ONLY"
            })
            continue
        cid = str(uuid4())
        payload = {"command_id": cid, "device_id": d["id"], "action": "EMERGENCY_STOP"}
        execute("UPDATE devices SET trading_locked=1 WHERE id=?", (d["id"],))
        ws = connector_sockets.get(d["id"])
        if ws:
            await ws.send_text(json.dumps({"type": "command", "payload": payload}))
            results.append({"device_id": d["id"], "sent": True})
        else:
            results.append({"device_id": d["id"], "sent": False})
    audit(user["id"], None, "EMERGENCY_STOP", json.dumps(results))
    return {"ok": True, "results": results}

@app.post("/emergency-reset")
def emergency_reset(user=Depends(current_user)):
    execute("UPDATE devices SET trading_locked=0 WHERE user_id=?", (user["id"],))
    audit(user["id"], None, "EMERGENCY_RESET")
    return {"ok": True}

@app.websocket("/ws/connector")
async def connector_ws(ws: WebSocket):
    await ws.accept()
    device_id = None
    try:
        hello = ConnectorHello.model_validate(json.loads(await ws.receive_text()))
        row = fetchone("SELECT * FROM devices WHERE id=?", (hello.device_id,))
        if not row or row["connector_token_hash"] != token_hash(hello.connector_token):
            await ws.send_text(json.dumps({"type": "error", "message": "Invalid connector credentials"}))
            await ws.close(code=1008)
            return
        device_id = hello.device_id
        connector_sockets[device_id] = ws
        execute(
            "UPDATE devices SET status='online',mt5_account=?,broker=?,terminal=?,mode=?,last_seen=? WHERE id=?",
            (hello.mt5_account, hello.broker, hello.terminal, hello.mode,
             datetime.now(timezone.utc).isoformat(), device_id)
        )
        await ws.send_text(json.dumps({"type": "hello_ok", "device_id": device_id}))
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "heartbeat":
                execute(
                    "UPDATE devices SET last_seen=?,status='online' WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), device_id)
                )
            elif msg.get("type") == "result":
                r = CommandResult.model_validate(msg["payload"])
                waiter = snapshot_waiters.pop(r.command_id, None)
                if waiter and not waiter.done():
                    waiter.set_result(r.model_dump())
                    continue
                row = fetchone(
                    "SELECT * FROM commands WHERE command_id=? AND device_id=?",
                    (r.command_id, device_id)
                )
                if row and row["status"] == "queued":
                    result = r.model_dump()
                    execute(
                        "UPDATE commands SET status=?,result=?,updated_at=? WHERE command_id=?",
                        ("completed" if r.ok else "failed", json.dumps(result),
                         datetime.now(timezone.utc).isoformat(), r.command_id)
                    )
                    await send_user(row["user_id"], {"type": "command_result", "payload": result})
                    audit(row["user_id"], device_id, "COMMAND_RESULT", json.dumps(result))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Connector WebSocket failed for device %s", device_id)
    finally:
        if device_id and connector_sockets.get(device_id) is ws:
            connector_sockets.pop(device_id, None)
            execute("UPDATE devices SET status='offline' WHERE id=?", (device_id,))

async def send_user(user_id, message):
    ws = user_sockets.get(user_id)
    if ws:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            logger.exception("User WebSocket send failed for user %s", user_id)
            user_sockets.pop(user_id, None)

@app.websocket("/ws/user")
async def user_ws(ws: WebSocket):
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=1008)
        return
    try:
        uid = decode_access_token(token)
        user = fetchone("SELECT * FROM users WHERE id=?", (uid,))
        if not user:
            await ws.close(code=1008)
            return
    except Exception:
        await ws.close(code=1008)
        return
    await ws.accept()
    user_sockets[user["id"]] = ws
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if user_sockets.get(user["id"]) is ws:
            user_sockets.pop(user["id"], None)

web_dist_value = os.getenv("WEB_DIST_DIR")
web_dist = Path(web_dist_value) if web_dist_value else None
if web_dist and web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
