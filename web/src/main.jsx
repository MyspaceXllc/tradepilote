import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import QRCode from "qrcode";
import {
  ChevronDown,
  LockKeyhole,
  Power,
  QrCode,
  RefreshCw,
  Search,
  ShieldCheck,
  Wifi,
  X,
} from "lucide-react";
import "./styles.css";

const configuredApi = import.meta.env.VITE_API_URL;
const API =
  !configuredApi || configuredApi === "__SAME_ORIGIN__"
    ? window.location.origin
    : configuredApi;
const WS = API.replace(/^http/, "ws");

const money = (value) =>
  value == null
    ? "â€”"
    : Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });

const price = (value) =>
  value == null
    ? "â€”"
    : Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 5,
      });

const signedStat = (value, suffix = "") => {
  const number = Number(value || 0);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}${suffix}`;
};

const statTone = (value) => {
  const number = Number(value || 0);
  return number > 0 ? "positive" : number < 0 ? "negative" : "neutral";
};

const MARKET_SESSIONS = [
  {
    name: "SYDNEY",
    timeZone: "Australia/Sydney",
    open: 8,
    close: 17,
  },
  { name: "TOKYO", timeZone: "Asia/Tokyo", open: 9, close: 18 },
  { name: "LONDON", timeZone: "Europe/London", open: 8, close: 17 },
  {
    name: "NEW YORK",
    timeZone: "America/New_York",
    open: 8,
    close: 17,
  },
];

function zonedHourAndDay(timestamp, timeZone) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(timestamp));
  return {
    day: parts.find((part) => part.type === "weekday")?.value,
    hour: Number(parts.find((part) => part.type === "hour")?.value),
  };
}

function activeMarketSessions(timestamp) {
  return MARKET_SESSIONS.filter((session) => {
    const { day, hour } = zonedHourAndDay(timestamp, session.timeZone);
    return (
      day !== "Sat" &&
      day !== "Sun" &&
      hour >= session.open &&
      hour < session.close
    );
  }).map((session) => session.name);
}

function haptic(pattern = 35) {
  if ("vibrate" in navigator) {
    navigator.vibrate(pattern);
  }
}

function newCommandId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10).join(""),
  ].join("-");
}

function savedSharkSettings() {
  const defaults = {
    lots: ["0.03", "0.02", "0.01", "0.01"],
    spacing: "50",
    levels: "3",
  };
  try {
    const saved = JSON.parse(
      localStorage.getItem("tp_shark_settings") || "{}",
    );
    if (
      Array.isArray(saved.lots) &&
      saved.lots.length === 4 &&
      saved.lots.every((item) => Number(item) > 0)
    ) {
      defaults.lots = saved.lots.map(String);
    }
    if (Number(saved.spacing) > 0) {
      defaults.spacing = String(saved.spacing);
    }
    if ([1, 2, 3].includes(Number(saved.levels))) {
      defaults.levels = String(saved.levels);
    }
  } catch {
    // Invalid saved settings fall back to the safe defaults.
  }
  return defaults;
}

function App() {
  const initialSharkSettings = useRef(savedSharkSettings()).current;
  const [token, setToken] = useState(localStorage.getItem("tp_token") || "");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState(
    localStorage.getItem("tp_device") || "",
  );
  const [symbol, setSymbol] = useState("XAUUSD");
  const [symbols, setSymbols] = useState([]);
  const [symbolsBusy, setSymbolsBusy] = useState(false);
  const [symbolPickerOpen, setSymbolPickerOpen] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [volume, setVolume] = useState(0.01);
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [limitSide, setLimitSide] = useState("BUY_LIMIT");
  const [sharkLots, setSharkLots] = useState(initialSharkSettings.lots);
  const [sharkSpacing, setSharkSpacing] = useState(
    initialSharkSettings.spacing,
  );
  const [sharkLevels, setSharkLevels] = useState(
    initialSharkSettings.levels,
  );
  const [serverStatus, setServerStatus] = useState("offline");
  const [message, setMessage] = useState("");
  const [pairing, setPairing] = useState("");
  const [qr, setQr] = useState("");
  const [busy, setBusy] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [clockNow, setClockNow] = useState(Date.now());
  const [tapFeedback, setTapFeedback] = useState(null);
  const [pressedAction, setPressedAction] = useState("");
  const feedbackTimer = useRef(null);
  const pressTimer = useRef(null);
  const audioContext = useRef(null);
  const setupToken = new URLSearchParams(window.location.search).get("setup");

  const selected = devices.find((device) => device.id === deviceId);
  const selectedSymbol = symbols.find((item) => item.name === symbol);
  const volumeStep = selectedSymbol?.volume_step || 0.01;
  const volumeMin = selectedSymbol?.volume_min || volumeStep;
  const volumeDecimals = Math.min(
    8,
    Math.max(2, (String(volumeStep).split(".")[1] || "").length),
  );
  const connected = selected?.status === "online";
  const symbolQuery = symbolSearch.trim().toUpperCase();
  const filteredSymbols = symbols
    .filter(
      (item) =>
        !symbolQuery ||
        item.name.toUpperCase().includes(symbolQuery) ||
        item.description.toUpperCase().includes(symbolQuery) ||
        item.path.toUpperCase().includes(symbolQuery),
    )
    .slice(0, 200);
  const sessions = activeMarketSessions(clockNow);
  const sessionLabel = sessions.length
    ? sessions.join(" + ")
    : "MARKETS CLOSED";
  const currentTime = new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(new Date(clockNow));
  const hasPosition = (snapshot?.positions_total || 0) > 0;
  const pnlClass = !hasPosition
    ? "neutral"
    : snapshot.profit >= 0
      ? "winner"
      : "loser";
  const performance = snapshot?.stats;
  const visibleMessage =
    message && !["Device connected", "Authenticated"].includes(message)
      ? message
      : "";
  const sharkReady =
    sharkLots.length === 4 &&
    sharkLots.every((item) => Number(item) > 0) &&
    Number(sharkSpacing) > 0 &&
    [1, 2, 3].includes(Number(sharkLevels));

  function showTapFeedback(label, pattern = 35) {
    haptic(pattern);
    clearTimeout(feedbackTimer.current);
    setTapFeedback({ label, id: Date.now() });
    feedbackTimer.current = setTimeout(() => setTapFeedback(null), 900);
  }

  function playClickSound(kind = "neutral") {
    try {
      const AudioContextClass =
        window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      const context =
        audioContext.current ||
        (audioContext.current = new AudioContextClass());
      if (context.state === "suspended") context.resume();

      const now = context.currentTime;

      function tone(frequency, start, duration, volume = 0.045, type = "sine") {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const begins = now + start;
        oscillator.type = type;
        oscillator.frequency.setValueAtTime(frequency, begins);
        oscillator.frequency.exponentialRampToValueAtTime(
          Math.max(40, frequency * 0.94),
          begins + duration,
        );
        gain.gain.setValueAtTime(0.0001, begins);
        gain.gain.exponentialRampToValueAtTime(volume, begins + 0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001, begins + duration);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start(begins);
        oscillator.stop(begins + duration + 0.01);
      }

      const patterns = {
        buy: [
          [520, 0, 0.065, 0.04, "triangle"],
          [760, 0.055, 0.1, 0.045, "sine"],
        ],
        sell: [
          [620, 0, 0.065, 0.04, "triangle"],
          [430, 0.055, 0.11, 0.045, "sine"],
        ],
        cash: [
          [1250, 0, 0.035, 0.028, "square"],
          [880, 0.025, 0.17, 0.045, "sine"],
          [1320, 0.08, 0.2, 0.05, "sine"],
          [1760, 0.145, 0.28, 0.035, "sine"],
        ],
        winner: [
          [590, 0, 0.1, 0.038, "triangle"],
          [790, 0.075, 0.13, 0.044, "sine"],
          [1080, 0.15, 0.2, 0.045, "sine"],
        ],
        loser: [
          [440, 0, 0.11, 0.038, "triangle"],
          [330, 0.09, 0.14, 0.04, "sine"],
          [220, 0.18, 0.22, 0.035, "sine"],
        ],
        neutral: [[620, 0, 0.075, 0.04, "triangle"]],
      };
      (patterns[kind] || patterns.neutral).forEach((note) => tone(...note));
    } catch {
      // Sound feedback is best-effort; trading must never depend on it.
    }
  }

  function actionFeedback(key, label, sound = "neutral", pattern = 35) {
    playClickSound(sound);
    showTapFeedback(label, pattern);
    clearTimeout(pressTimer.current);
    setPressedAction(key);
    pressTimer.current = setTimeout(() => setPressedAction(""), 220);
  }

  function changeVolume(direction) {
    setVolume((current) => {
      const next = current + direction * volumeStep;
      const bounded = Math.max(volumeMin, Math.min(1, next));
      return Number(bounded.toFixed(volumeDecimals));
    });
  }

  useEffect(
    () => () => {
      clearTimeout(feedbackTimer.current);
      clearTimeout(pressTimer.current);
      audioContext.current?.close().catch(() => {});
    },
    [],
  );

  async function api(path, opts = {}) {
    const response = await fetch(API + path, {
      ...opts,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(data.detail || "Request failed");
    return data;
  }

  async function auth(mode) {
    try {
      const data = await api(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem("tp_token", data.access_token);
      setToken(data.access_token);
      setMessage("");
    } catch (error) {
      setMessage(error.message);
    }
  }

  useEffect(() => {
    if (!setupToken) return;
    let active = true;
    api("/setup/claim", {
      method: "POST",
      body: JSON.stringify({ setup_token: setupToken }),
    })
      .then((data) => {
        if (!active) return;
        localStorage.setItem("tp_token", data.access_token);
        localStorage.setItem("tp_device", data.device_id);
        setDeviceId(data.device_id);
        setToken(data.access_token);
        setMessage("");
        history.replaceState({}, "", window.location.pathname);
      })
      .catch((error) => {
        if (active) setMessage(error.message);
      });
    return () => {
      active = false;
    };
  }, [setupToken]);

  async function loadDevices() {
    if (!token) return;
    try {
      const data = await api("/devices");
      setDevices(data);
      const storedExists = data.some((device) => device.id === deviceId);
      if ((!deviceId || !storedExists) && data[0]) {
        setDeviceId(data[0].id);
        localStorage.setItem("tp_device", data[0].id);
      }
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function loadSnapshot() {
    if (!selected || selected.status !== "online" || !symbol) return;
    try {
      const result = await api(
        `/devices/${selected.id}/snapshot?symbol=${encodeURIComponent(symbol)}`,
      );
      if (result.ok) setSnapshot(result.raw || null);
    } catch {
      setSnapshot(null);
    }
  }

  async function loadSymbols() {
    if (!selected || selected.status !== "online") return;
    setSymbolsBusy(true);
    try {
      const result = await api(`/devices/${selected.id}/symbols`);
      if (!result.ok) throw Error(result.message || "Could not load symbols");
      const available = result.raw?.symbols || [];
      setSymbols(available);

      const saved = localStorage.getItem(`tp_symbol_${selected.id}`);
      const preferred =
        available.find((item) => item.name === saved)?.name ||
        available.find((item) => item.name === symbol)?.name ||
        available.find((item) => item.name === "XAUUSD")?.name ||
        available.find((item) => item.name.startsWith("XAUUSD"))?.name ||
        available.find((item) => item.name === "EURUSD")?.name ||
        available[0]?.name;
      if (preferred && preferred !== symbol) setSymbol(preferred);
    } catch (error) {
      setSymbols([]);
      setMessage(error.message);
    } finally {
      setSymbolsBusy(false);
    }
  }

  async function openSymbolPicker() {
    setSymbolSearch("");
    setSymbolPickerOpen(true);
    if (!symbols.length && connected) await loadSymbols();
  }

  function chooseSymbol(nextSymbol) {
    setSymbol(nextSymbol);
    setSymbolPickerOpen(false);
    setSymbolSearch("");
    showTapFeedback(`${nextSymbol} SELECTED`);
  }

  useEffect(() => {
    const timer = setInterval(() => setClockNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    loadDevices();
    const timer = setInterval(loadDevices, 5000);
    return () => clearInterval(timer);
  }, [token, deviceId]);

  useEffect(() => {
    if (!token) return;
    let socket;
    let reconnectTimer;
    let stopped = false;

    function connectUserSocket() {
      if (stopped) return;
      socket = new WebSocket(
        `${WS}/ws/user?token=${encodeURIComponent(token)}`,
      );
      socket.onopen = () => setServerStatus("online");
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        setServerStatus("offline");
        if (!stopped) {
          reconnectTimer = setTimeout(connectUserSocket, 1200);
        }
      };
      socket.onmessage = (event) => {
        const update = JSON.parse(event.data);
        if (update.type === "command_result") {
          const result = update.payload;
          setMessage(
            `${result.ok ? "âœ“" : "âœ•"} ${result.message}${
              result.ticket ? ` â€¢ #${result.ticket}` : ""
            }`,
          );
          setBusy(false);
          loadDevices();
          loadSnapshot();
        }
      };
    }

    connectUserSocket();
    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  useEffect(() => {
    setSnapshot(null);
    if (!selected || selected.status !== "online") return;
    loadSnapshot();
    const timer = setInterval(loadSnapshot, 3000);
    return () => clearInterval(timer);
  }, [token, selected?.id, selected?.status, symbol]);

  useEffect(() => {
    setSymbols([]);
    if (!selected || selected.status !== "online") return;
    const saved = localStorage.getItem(`tp_symbol_${selected.id}`);
    if (saved) setSymbol(saved);
    loadSymbols();
  }, [token, selected?.id, selected?.status]);

  useEffect(() => {
    if (!selected || !symbol) return;
    localStorage.setItem(`tp_symbol_${selected.id}`, symbol);
  }, [selected?.id, symbol]);

  useEffect(() => {
    localStorage.setItem(
      "tp_shark_settings",
      JSON.stringify({
        lots: sharkLots,
        spacing: sharkSpacing,
        levels: sharkLevels,
      }),
    );
  }, [sharkLots, sharkSpacing, sharkLevels]);

  async function command(action, extra = {}) {
    if (!selected) {
      setMessage("Select a connected MT5 device first");
      return;
    }
    setBusy(true);
    setMessage("Sendingâ€¦");
    try {
      const commandId = newCommandId();
      await api("/commands", {
        method: "POST",
        body: JSON.stringify({
          command_id: commandId,
          device_id: selected.id,
          action,
          symbol,
          volume,
          sl: sl ? Number(sl) : null,
          tp: tp ? Number(tp) : null,
          price: limitPrice ? Number(limitPrice) : null,
          ...extra,
        }),
      });
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        const status = await api(`/commands/${commandId}`);
        if (status.status !== "queued") {
          const result = status.result || {};
          setMessage(
            `${result.ok ? "âœ“" : "âœ•"} ${result.message || status.status}${
              result.ticket ? ` â€¢ #${result.ticket}` : ""
            }`,
          );
          setBusy(false);
          loadDevices();
          loadSnapshot();
          return;
        }
      }
      setBusy(false);
      setMessage("Command timed out â€” check MT5 before retrying");
    } catch (error) {
      setBusy(false);
      setMessage(error.message);
    }
  }

  async function emergency() {
    if (!confirm("Close positions, cancel orders, and lock trading?")) return;
    showTapFeedback("EMERGENCY STOP", [45, 30, 45]);
    try {
      await api("/emergency-stop", { method: "POST" });
      setMessage("Emergency stop sent â€” trading locked");
      loadDevices();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function emergencyReset() {
    if (!confirm("Unlock trading for all paired devices?")) return;
    try {
      await api("/emergency-reset", { method: "POST" });
      setMessage("Trading unlocked");
      loadDevices();
    } catch (error) {
      setMessage(error.message);
    }
  }

  function closePositionGroup(action) {
    const winners = action === "CLOSE_WINNERS";
    actionFeedback(
      winners ? "winners" : "losers",
      winners ? "CLOSE WINNERS" : "CLOSE LOSERS",
      winners ? "winner" : "loser",
      [45, 30, 45],
    );
    command(action);
  }

  async function doubleTrade() {
    if (!selected) {
      setMessage("Select a connected MT5 device first");
      return;
    }
    if (!connected) {
      setMessage("MT5 device is not connected");
      return;
    }
    setBusy(true);
    actionFeedback("doubleTrade", "DOUBLE TRADE", "winner", [50, 25, 50]);
    setMessage("Sending BUY + SELLâ€¦");
    const submitOne = async (action) => {
      const commandId = newCommandId();
      await api("/commands", {
        method: "POST",
        body: JSON.stringify({
          command_id: commandId,
          device_id: selected.id,
          action,
          symbol,
          volume,
          sl: sl ? Number(sl) : null,
          tp: tp ? Number(tp) : null,
          price: limitPrice ? Number(limitPrice) : null,
        }),
      });
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 350));
        const status = await api(`/commands/${commandId}`);
        if (status.status !== "queued") {
          return status.result || {};
        }
      }
      return { ok: false, message: "Command timed out" };
    };
    try {
      // Submit both legs together. This avoids the old sequential behavior where
      // the second leg could be delayed until the first leg had already changed
      // the account position. On a hedging MT5 account this produces one BUY
      // and one SELL at market. A netting account cannot hold both directions.
      const [buy, sell] = await Promise.all([submitOne("BUY"), submitOne("SELL")]);
      const buyText = buy.ok ? `BUY âœ“${buy.ticket ? ` #${buy.ticket}` : ""}` : `BUY âœ• ${buy.message || "failed"}`;
      const sellText = sell.ok ? `SELL âœ“${sell.ticket ? ` #${sell.ticket}` : ""}` : `SELL âœ• ${sell.message || "failed"}`;
      setMessage(`${buyText} â€¢ ${sellText}`);
      loadDevices();
      loadSnapshot();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  function updateSharkLot(index, value) {
    setSharkLots((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? value : item)),
    );
  }

  function runShark(action) {
    const isBuy = action === "SHARK_BUY";
    const isBoth = action === "SHARK_BOTH";
    actionFeedback(
      isBoth ? "sharkBoth" : isBuy ? "sharkBuy" : "sharkSell",
      isBoth ? "SHARK BOTH" : isBuy ? "SHARK BUY" : "SHARK SELL",
      isBoth ? "winner" : isBuy ? "buy" : "sell",
      isBoth ? [50, 25, 50, 25, 50] : [50, 25, 50],
    );
    command(action, {
      shark_lots: sharkLots.map(Number),
      shark_spacing_points: Number(sharkSpacing),
      shark_levels: Number(sharkLevels),
    });
  }

  async function createPairing() {
    try {
      const data = await api("/pairing/create", { method: "POST" });
      setPairing(data.pairing_token);
      setQr(
        await QRCode.toDataURL(
          `tradepilot://pair?server=${encodeURIComponent(
            API,
          )}&token=${encodeURIComponent(data.pairing_token)}`,
          { width: 280, margin: 2 },
        ),
      );
    } catch (error) {
      setMessage(error.message);
    }
  }

  function lock() {
    localStorage.removeItem("tp_token");
    location.reload();
  }

  if (!token) {
    return (
      <Auth
        username={username}
        setUsername={setUsername}
        password={password}
        setPassword={setPassword}
        auth={auth}
        message={message}
      />
    );
  }

  return (
    <div className="app">
      {symbolPickerOpen ? (
        <div
          className="symbolOverlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget)
              setSymbolPickerOpen(false);
          }}
        >
          <section
            className="symbolModal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="symbol-picker-title"
          >
            <header>
              <div>
                <h2 id="symbol-picker-title">Choose MT5 symbol</h2>
                <p>
                  {symbols.length.toLocaleString()} symbols from your broker
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSymbolPickerOpen(false)}
                aria-label="Close symbol picker"
              >
                <X size={20} />
              </button>
            </header>
            <label className="symbolSearch">
              <Search size={18} />
              <input
                autoFocus
                value={symbolSearch}
                onChange={(event) => setSymbolSearch(event.target.value)}
                placeholder="Search EURUSD, gold, NASDAQâ€¦"
                autoComplete="off"
                spellCheck="false"
              />
            </label>
            <div className="symbolResults">
              {symbolsBusy ? (
                <div className="symbolEmpty">Loading symbols from MT5â€¦</div>
              ) : filteredSymbols.length ? (
                filteredSymbols.map((item) => (
                  <button
                    type="button"
                    key={item.name}
                    className={item.name === symbol ? "selected" : ""}
                    onClick={() => chooseSymbol(item.name)}
                  >
                    <span>
                      <strong>{item.name}</strong>
                      <small>{item.description || "MT5 instrument"}</small>
                    </span>
                    <em>
                      {item.path || (item.visible ? "Market Watch" : "MT5")}
                    </em>
                  </button>
                ))
              ) : (
                <div className="symbolEmpty">
                  No symbol matches â€œ{symbolSearch}â€
                </div>
              )}
            </div>
            {!symbolQuery && symbols.length > filteredSymbols.length ? (
              <p className="symbolHint">
                Showing the first {filteredSymbols.length}. Search to find any
                of the {symbols.length.toLocaleString()} MT5 symbols.
              </p>
            ) : null}
          </section>
        </div>
      ) : null}
      <header className="compactStatusBar">
        <div className={`sessionStatus ${sessions.length ? "open" : ""}`}>
          <i />
          <span>
            <small>ACTIVE SESSION</small>
            <strong>{sessionLabel}</strong>
          </span>
        </div>
        <div className="liveTime">
          <small>UTC TIME</small>
          <strong>{currentTime}</strong>
        </div>
        <div className={`connection ${connected ? "live" : ""}`}>
          <i />
          <span>
            <small>TERMINAL</small>
            <strong>
              {connected
                ? serverStatus === "online"
                  ? "MT5 CONNECTED"
                  : "MT5 SYNCING"
                : "OFFLINE"}
            </strong>
          </span>
        </div>
      </header>
      <section className="mobilePerformance" aria-label="Today's performance">
        <div className="mobileStat period">
          <small>PERIOD</small>
          <strong>TODAY</strong>
        </div>
        <div className="mobileStat">
          <small>PIPS</small>
          <strong className={statTone(performance?.closed_pips)}>
            {performance
              ? signedStat(performance.closed_pips, "P")
              : "â€”"}
          </strong>
        </div>
        <div className="mobileStat">
          <small>BAL</small>
          <strong>{performance ? money(performance.balance) : "â€”"}</strong>
        </div>
        <div className="mobileStat">
          <small>EQUITY</small>
          <strong
            className={
              performance
                ? statTone(performance.equity - performance.balance)
                : "neutral"
            }
          >
            {performance ? money(performance.equity) : "â€”"}
          </strong>
        </div>
        <div className="mobileStat">
          <small>CLOSED</small>
          <strong className={statTone(performance?.closed_profit)}>
            {performance ? signedStat(performance.closed_profit) : "â€”"}
          </strong>
        </div>
        <div className="mobileStat">
          <small>WIN</small>
          <strong className="positive">
            {performance ? signedStat(performance.gross_win) : "â€”"}
          </strong>
        </div>
        <div className="mobileStat">
          <small>LOSS</small>
          <strong className="negative">
            {performance
              ? signedStat(-Math.abs(performance.gross_loss))
              : "â€”"}
          </strong>
        </div>
        <div className="mobileStat">
          <small>W / L</small>
          <strong>
            {performance
              ? `${performance.closed_wins} / ${performance.closed_losses}`
              : "0 / 0"}
          </strong>
        </div>
        <div className="mobileStat">
          <small>OPEN</small>
          <strong className={statTone(performance?.open_profit)}>
            {performance ? signedStat(performance.open_profit) : "â€”"}
          </strong>
        </div>
      </section>

      <main className="shell">
        {tapFeedback ? (
          <div key={tapFeedback.id} className="tapFeedback" role="status">
            âœ“ {tapFeedback.label} PRESSED
          </div>
        ) : null}
        <section className="terminal">
          <div className="marketHeader">
            <div className="instrument">
              <span>{symbol || "SYMBOL"}</span>
              <strong>
                {hasPosition
                  ? `${snapshot.direction || "OPEN"} â€¢ ${snapshot.volume}`
                  : "NO OPEN POSITION"}
              </strong>
            </div>
            <div className="quote">
              <small>ENTRY</small>
              <strong>{price(snapshot?.entry_price)}</strong>
            </div>
            <div className="quote">
              <small>CURRENT</small>
              <strong>{price(snapshot?.current_price)}</strong>
            </div>
            <div className={`pnl ${pnlClass}`}>
              <small>P / L</small>
              <strong>{hasPosition ? money(snapshot.profit) : "â€”"}</strong>
            </div>
          </div>

          <div className="compactRow">
            <label>
              <span>DEVICE</span>
              <select
                value={deviceId}
                onChange={(event) => {
                  setDeviceId(event.target.value);
                  localStorage.setItem("tp_device", event.target.value);
                }}
              >
                <option value="">Select MT5</option>
                {devices.map((device) => (
                  <option key={device.id} value={device.id}>
                    {device.name} â€¢ {device.status}
                  </option>
                ))}
              </select>
            </label>
            <label className="symbolControl">
              <span>
                SYMBOL
                {symbols.length ? ` â€¢ ${symbols.length}` : ""}
              </span>
              <div className="symbolPicker">
                <button
                  type="button"
                  className="symbolSelectButton"
                  onClick={openSymbolPicker}
                  disabled={!connected}
                  aria-haspopup="dialog"
                >
                  <span>{symbolsBusy ? "Loadingâ€¦" : symbol || "Choose"}</span>
                  <ChevronDown size={17} />
                </button>
                <button
                  type="button"
                  className="symbolRefresh"
                  onClick={loadSymbols}
                  disabled={!connected || symbolsBusy}
                  aria-label="Refresh MT5 symbols"
                  title="Refresh symbols from MT5"
                >
                  <RefreshCw size={16} className={symbolsBusy ? "spin" : ""} />
                </button>
              </div>
            </label>
          </div>

          <div className="lotControl">
            <button aria-label="Decrease lot" onClick={() => changeVolume(-1)}>
              âˆ’
            </button>
            <div>
              <small>LOT SIZE</small>
              <strong>{volume.toFixed(volumeDecimals)}</strong>
            </div>
            <button aria-label="Increase lot" onClick={() => changeVolume(1)}>
              +
            </button>
          </div>

          <div className="tradeActions">
            <button
              className={`trade sell ${
                pressedAction === "sell" ? "commandPressed" : ""
              }`}
              disabled={busy || !connected}
              onClick={() => {
                actionFeedback("sell", "SELL", "sell");
                command("SELL");
              }}
            >
              <span>SELL</span>
              <small>MARKET</small>
            </button>
            <button
              className={`trade buy ${
                pressedAction === "buy" ? "commandPressed" : ""
              }`}
              disabled={busy || !connected}
              onClick={() => {
                actionFeedback("buy", "BUY", "buy");
                command("BUY");
              }}
            >
              <span>BUY</span>
              <small>MARKET</small>
            </button>
          </div>

          <button
            className={`closePosition ${
              pressedAction === "close" ? "commandPressed" : ""
            }`}
            disabled={busy || !connected}
            onClick={() => {
              actionFeedback("close", "CLOSE POSITION", "cash", [45, 30, 45]);
              command("CLOSE");
            }}
          >
            <span>CLOSE POSITION</span>
            <small>Closes all open positions</small>
          </button>

          <div className="quickBulkClose">
            <p>SELECTIVE CLOSE â€¢ EXECUTES IMMEDIATELY</p>
            <div>
              <button
                className={`closeWinners ${
                  pressedAction === "winners" ? "commandPressed" : ""
                }`}
                disabled={busy || !connected}
                onClick={() => closePositionGroup("CLOSE_WINNERS")}
              >
                CLOSE WINNERS
              </button>
            </div>
          </div>

          <details className="sharkPanel">
            <summary>
              <div>
                <strong>Shark grid</strong>
                <span>Buy, Sell, Both and grid settings</span>
              </div>
              <ChevronDown size={20} />
            </summary>
            <div className="sharkBlock">
            <p>SHARK GRID â€¢ EXECUTES IMMEDIATELY</p>
            <div className="sharkActions">
              <button
                className={`sharkSell ${
                  pressedAction === "sharkSell" ? "commandPressed" : ""
                }`}
                disabled={busy}
                onClick={() => runShark("SHARK_SELL")}
              >
                <strong>SHARK SELL</strong>
                <span>
                  MARKET + {sharkLevels} SELL STOP
                  {Number(sharkLevels) > 1 ? "S" : ""}
                </span>
              </button>
              <button
                className={`sharkBuy ${
                  pressedAction === "sharkBuy" ? "commandPressed" : ""
                }`}
                disabled={busy}
                onClick={() => runShark("SHARK_BUY")}
              >
                <strong>SHARK BUY</strong>
                <span>
                  MARKET + {sharkLevels} BUY STOP
                  {Number(sharkLevels) > 1 ? "S" : ""}
                </span>
              </button>
            </div>
            <button
              className={`sharkBoth ${
                pressedAction === "sharkBoth" ? "commandPressed" : ""
              }`}
              disabled={busy}
              onClick={() => runShark("SHARK_BOTH")}
            >
              <strong>SHARK BOTH</strong>
              <span>OPEN BUY + SELL GRIDS â€¢ HEDGING ONLY</span>
            </button>
            <button
              type="button"
              className="doubleTrade"
              disabled={busy || !connected}
              onClick={doubleTrade}
            >
              <strong>DOUBLE TRADE</strong>
              <span>OPEN BUY + SELL AT MARKET</span>
            </button>
            <details className="sharkAdvanced">
              <summary>
                <div>
                  <strong>Shark settings</strong>
                  <span>1â€“3 lines, lots and spacing</span>
                </div>
                <ChevronDown size={18} />
              </summary>
              <div className="sharkSettingsBody">
                <div className="sharkLevelPicker">
                  <span>PENDING LINES PER SIDE</span>
                  <div>
                    {[1, 2, 3].map((level) => (
                      <button
                        key={level}
                        type="button"
                        className={
                          Number(sharkLevels) === level ? "active" : ""
                        }
                        onClick={() => setSharkLevels(String(level))}
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="sharkLots">
                  {sharkLots.map((lot, index) => (
                    <label
                      key={index}
                      className={
                        index > Number(sharkLevels) ? "inactive" : ""
                      }
                    >
                      <span>
                        {index === 0 ? "NEAR â€¢ MARKET" : `LEVEL ${index + 1}`}
                      </span>
                      <input
                        inputMode="decimal"
                        type="number"
                        min={volumeMin}
                        step={volumeStep}
                        value={lot}
                        disabled={index > Number(sharkLevels)}
                        onChange={(event) =>
                          updateSharkLot(index, event.target.value)
                        }
                      />
                    </label>
                  ))}
                </div>
                <label className="sharkSpacing">
                  <span>SPACING â€¢ BROKER POINTS</span>
                  <input
                    inputMode="numeric"
                    type="number"
                    min="1"
                    step="1"
                    value={sharkSpacing}
                    onChange={(event) => setSharkSpacing(event.target.value)}
                  />
                  <small>
                    Default 50. MT5 may increase it to the broker minimum.
                  </small>
                </label>
                <div className="sharkPreview">
                  <span>NEAREST</span>
                  <strong>
                    {sharkLots
                      .slice(0, Number(sharkLevels) + 1)
                      .join(" â†’ ")}{" "}
                    â€¢ {sharkSpacing || "â€”"} points
                  </strong>
                  <span>FARTHEST</span>
                </div>
                <p className="sharkSafety">
                  SHARK BOTH requires a Hedging account. CLOSE POSITION closes
                  active trades only; use CANCEL PENDING for unfilled levels.
                </p>
              </div>
            </details>
            </div>
          </details>

          <details className="advanced">
            <summary>
              <div>
                <strong>Advanced order</strong>
                <span>SL, TP and pending limits</span>
              </div>
              <ChevronDown size={20} />
            </summary>
            <div className="advancedBody">
              <div className="fieldGrid">
                <label>
                  <span>STOP LOSS</span>
                  <input
                    inputMode="decimal"
                    placeholder="Optional"
                    value={sl}
                    onChange={(event) => setSl(event.target.value)}
                  />
                </label>
                <label>
                  <span>TAKE PROFIT</span>
                  <input
                    inputMode="decimal"
                    placeholder="Optional"
                    value={tp}
                    onChange={(event) => setTp(event.target.value)}
                  />
                </label>
              </div>
              <div className="fieldGrid">
                <label>
                  <span>LIMIT SIDE</span>
                  <select
                    value={limitSide}
                    onChange={(event) => setLimitSide(event.target.value)}
                  >
                    <option value="BUY_LIMIT">BUY LIMIT</option>
                    <option value="SELL_LIMIT">SELL LIMIT</option>
                  </select>
                </label>
                <label>
                  <span>LIMIT PRICE</span>
                  <input
                    inputMode="decimal"
                    placeholder="Required"
                    value={limitPrice}
                    onChange={(event) => setLimitPrice(event.target.value)}
                  />
                </label>
              </div>
              <div className="advancedActions">
                <button
                  className="cancel"
                  disabled={busy || !connected}
                  onClick={() => {
                    showTapFeedback("CANCEL PENDING");
                    command("CANCEL");
                  }}
                >
                  CANCEL PENDING
                </button>
                <button
                  className="placeLimit"
                  disabled={busy || !connected || !limitPrice}
                  onClick={() => {
                    showTapFeedback("PLACE LIMIT");
                    command(limitSide);
                  }}
                >
                  PLACE LIMIT
                </button>
              </div>
            </div>
          </details>

          <details className="controlPanel">
            <summary>
              <div>
                <strong>Device controls</strong>
                <span>Pair device, emergency and lock</span>
              </div>
              <ChevronDown size={20} />
            </summary>
            <div className="controlPanelBody">
              <section className="utilityBar">
                <button onClick={createPairing}>
                  <QrCode size={18} />
                  PAIR DEVICE
                </button>
                <button className="danger" onClick={emergency}>
                  <Power size={18} />
                  EMERGENCY
                </button>
                <button onClick={lock}>
                  <LockKeyhole size={18} />
                  LOCK
                </button>
              </section>

              {selected?.trading_locked ? (
                <button className="unlock" onClick={emergencyReset}>
                  <ShieldCheck size={18} />
                  TRADING LOCKED â€” TAP TO UNLOCK
                </button>
              ) : null}
            </div>
          </details>

          {visibleMessage ? (
            <div
              className={`result ${
                visibleMessage.startsWith("âœ•") ? "error" : ""
              }`}
            >
              {visibleMessage}
            </div>
          ) : null}
        </section>

        {qr ? (
          <section className="pairingCard">
            <h3>One-time pairing</h3>
            <img src={qr} alt="One-time pairing QR code" />
            <code>{pairing}</code>
            <p>Expires quickly. Never share this code publicly.</p>
          </section>
        ) : null}

        <section className="deviceMeta">
          <div>
            <ShieldCheck size={18} />
            <span>
              Mode <b>{selected?.mode || "â€”"}</b>
            </span>
          </div>
          <div>
            <Wifi size={18} />
            <span>{selected?.broker || "No broker connected"}</span>
          </div>
          <span className="account">
            {selected?.mt5_account
              ? `Account â€¢â€¢â€¢â€¢${selected.mt5_account.slice(-4)}`
              : "No account"}
          </span>
        </section>
      </main>
    </div>
  );
}

function Auth({ username, setUsername, password, setPassword, auth, message }) {
  return (
    <main className="auth">
      <section>
        <img className="authBrand" src="/tradepilot-logo.png" alt="TradePilot" />
        <p className="eyebrow">MT5 REMOTE CONTROL</p>
        <h1>TradePilot</h1>
        <p className="authIntro">
          Secure, fast trading control from your phone.
        </p>
        <div className="authCard">
          <label>
            <span>USERNAME</span>
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label>
            <span>PASSWORD</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <div className="authActions">
            <button onClick={() => auth("login")}>LOGIN</button>
            <button className="secondary" onClick={() => auth("register")}>
              CREATE ACCOUNT
            </button>
          </div>
          <p className="authMessage">{message}</p>
        </div>
      </section>
    </main>
  );
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("/sw.js").catch(() => {}),
  );
}

createRoot(document.getElementById("root")).render(<App />);

