from pydantic import BaseModel, Field
from typing import Literal, Optional

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)

class LoginIn(RegisterIn):
    pass

class DeviceRegisterIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    connector_token: str = Field(min_length=20, max_length=200)

class CommandIn(BaseModel):
    command_id: str = Field(min_length=8, max_length=100)
    device_id: str
    action: Literal[
        "BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT",
        "SHARK_BUY", "SHARK_SELL", "SHARK_BOTH",
        "CLOSE", "CLOSE_WINNERS", "CLOSE_LOSERS",
        "CANCEL", "STATUS", "SYMBOLS", "EMERGENCY_STOP"
    ]
    symbol: Optional[str] = None
    volume: float = Field(default=0.01, gt=0, le=100)
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    ticket: Optional[int] = None
    shark_lots: Optional[list[float]] = None
    shark_spacing_points: Optional[int] = Field(default=50, ge=1, le=100000)
    shark_levels: Optional[int] = Field(default=3, ge=1, le=3)
    comment: str = Field(default="TradePilot", max_length=50)

class PairIn(BaseModel):
    pairing_token: str = Field(min_length=20, max_length=300)

class ClaimDeviceIn(PairIn):
    device_id: str = Field(min_length=8, max_length=128)
    connector_token: str = Field(min_length=20, max_length=200)

class SetupCreateIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=128)
    connector_token: str = Field(min_length=20, max_length=200)

class SetupClaimIn(BaseModel):
    setup_token: str = Field(min_length=20, max_length=300)

class ConnectorHello(BaseModel):
    device_id: str
    connector_token: str
    name: str
    mt5_account: Optional[str] = None
    broker: Optional[str] = None
    terminal: Optional[str] = None
    mode: Literal["demo", "live"] = "demo"

class CommandResult(BaseModel):
    command_id: str
    ok: bool
    message: str
    ticket: Optional[int] = None
    raw: Optional[dict] = None
