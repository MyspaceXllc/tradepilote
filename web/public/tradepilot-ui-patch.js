(() => {
  const STYLE_ID = "tradepilot-double-trade-ui";
  const M1_STYLE_ID = "tradepilot-m1-fusion-ui";

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .quickBulkClose > div { grid-template-columns: 1fr !important; }
      .quickBulkClose .closeWinners {
        min-height: 82px !important;
        width: 100% !important;
        display: grid !important;
        place-content: center !important;
        gap: 5px !important;
        border-radius: 12px !important;
      }
      .quickBulkClose .closeWinners strong,
      .quickBulkClose .closeWinners span { display: block; }
      .quickBulkClose .closeWinners strong { font-size: 20px; letter-spacing: .04em; }
      .quickBulkClose .closeWinners span { margin-top: 5px; color: rgba(214,235,255,.72); font-size: 10px; letter-spacing: .04em; }
      .doubleTradeLegacy {
        width: 100%; min-height: 70px; margin-top: 10px; padding: 10px 12px;
        display: grid; place-content: center; gap: 5px; color: #fff4d1;
        background: linear-gradient(145deg,#4b3a12,#8e6a20);
        border: 1px solid rgba(255,222,133,.72); border-radius: 12px;
        box-shadow: 0 1px 0 rgba(255,255,255,.3) inset, 0 12px 28px rgba(127,87,16,.24); cursor: pointer;
      }
      .doubleTradeLegacy strong, .doubleTradeLegacy span { display: block; }
      .doubleTradeLegacy strong { font-size: 18px; letter-spacing: .06em; }
      .doubleTradeLegacy span { color: rgba(255,244,209,.74); font-size: 8px; font-weight: 800; letter-spacing: .09em; }
    `;
    document.head.appendChild(style);
  }

  function injectM1Styles() {
    if (document.getElementById(M1_STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = M1_STYLE_ID;
    style.textContent = `
      .tpM1FusionStrip { width: min(100%, 940px); min-height: 34px; margin: 0 auto; padding: 4px 10px;
        display: grid; grid-template-columns: 1.5fr .7fr .9fr 1fr 1.2fr; align-items:center; gap:4px;
        background: linear-gradient(180deg,rgba(15,23,32,.98),rgba(8,12,17,.98));
        border-bottom:1px solid rgba(104,157,221,.18); box-shadow:0 6px 18px rgba(0,0,0,.14); }
      .tpM1FusionStrip .title, .tpM1FusionStrip .metric { min-width:0; text-align:center; }
      .tpM1FusionStrip .title { text-align:left; }
      .tpM1FusionStrip small { display:block; color:rgba(255,255,255,.38); font-size:6px; font-weight:850; letter-spacing:.08em; }
      .tpM1FusionStrip strong { display:block; color:#dfe7ef; font-size:8px; font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .tpM1FusionStrip .signal { justify-self:center; min-width:56px; padding:5px 9px; border-radius:999px; text-align:center; font-size:8px; font-weight:900; letter-spacing:.08em; }
      .tpM1FusionStrip .buy { color:#07140f; background:#31d1a0; }
      .tpM1FusionStrip .sell { color:#fff; background:#ff5e74; }
      .tpM1FusionStrip .wait { color:#dbe2e8; background:#53616d; }
      .tpM1FusionStrip .metric { padding-left:7px; border-left:1px solid rgba(255,255,255,.07); }
      @media (max-width: 700px) {
        .tpM1FusionStrip { min-height:32px; padding:3px 5px; grid-template-columns:1.35fr .7fr .8fr .9fr 1.15fr; }
        .tpM1FusionStrip small { font-size:5px; }
        .tpM1FusionStrip strong, .tpM1FusionStrip .signal { font-size:7px; }
        .tpM1FusionStrip .signal { min-width:48px; padding:4px 7px; }
      }
    `;
    document.head.appendChild(style);
  }

  function removeLosers() {
    document.querySelectorAll(".quickBulkClose .closeLosers").forEach((el) => el.remove());
  }

  function addLegacyDoubleTrade() {
    document.querySelectorAll(".sharkBlock").forEach((block) => {
      if (block.querySelector(".doubleTrade, .doubleTradeLegacy")) return;
      const sharkBoth = block.querySelector(".sharkBoth");
      if (!sharkBoth) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "doubleTradeLegacy";
      button.innerHTML = "<strong>DOUBLE TRADE</strong><span>OPEN BUY + SELL AT MARKET • HEDGING ONLY</span>";
      button.addEventListener("click", () => {
        const buy = document.querySelector(".trade.buy");
        const sell = document.querySelector(".trade.sell");
        if (!buy || !sell || buy.disabled || sell.disabled) return;
        if (!window.confirm("Open BUY and SELL at market at the same time? This requires an MT5 hedging account.")) return;
        buy.click();
        sell.click();
      });
      sharkBoth.parentNode.insertBefore(button, sharkBoth);
    });
  }

  function utcTime() {
    return new Intl.DateTimeFormat("en-GB", { timeZone:"UTC", hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23" }).format(new Date()) + " UTC";
  }

  function updateUtcClock() {
    const live = document.querySelector(".liveTime");
    if (!live) return;
    const small = live.querySelector("small");
    const strong = live.querySelector("strong");
    if (small) small.textContent = "UTC TIME";
    if (strong) strong.textContent = utcTime();
  }

  function addM1Strip() {
    const performance = document.querySelector(".mobilePerformance");
    if (!performance || document.querySelector(".tpM1FusionStrip")) return;
    injectM1Styles();
    const strip = document.createElement("section");
    strip.className = "tpM1FusionStrip";
    strip.setAttribute("aria-label", "M1 Fusion Strategy");
    strip.innerHTML = `
      <div class="title"><small>M1 FUSION STRATEGY</small><strong class="minute">1 MIN • UTC --:--</strong></div>
      <div class="signal wait">WAIT</div>
      <div class="metric"><small>PRESSURE</small><strong class="pressure">—</strong></div>
      <div class="metric"><small>RESULT NOW</small><strong class="result">—</strong></div>
      <div class="metric"><small>LAST M1 BAR</small><strong class="bar">—</strong></div>`;
    performance.insertAdjacentElement("afterend", strip);
    refreshM1Strip();
  }

  async function refreshM1Strip() {
    const strip = document.querySelector(".tpM1FusionStrip");
    if (!strip) return;
    const minute = new Intl.DateTimeFormat("en-GB", { timeZone:"UTC", hour:"2-digit", minute:"2-digit", hourCycle:"h23" }).format(new Date());
    const minuteEl = strip.querySelector(".minute");
    if (minuteEl) minuteEl.textContent = `1 MIN • UTC ${minute}`;
    try {
      const symbolSelect = document.querySelector(".symbolSelectButton span");
      const symbol = (symbolSelect?.textContent || "").trim().split(" ")[0];
      if (!symbol || symbol === "Choose" || symbol === "Loading…") return;
      const r = await fetch(`/local/signal-fusion/data?symbol=${encodeURIComponent(symbol)}&timeframe=M1&minimum_separation=0.25&count=60`, { cache:"no-store" });
      if (!r.ok) return;
      const j = await r.json();
      const d = j.raw || j;
      const latest = d.latest || {};
      const signal = latest.trade_state || "WAIT";
      const signalEl = strip.querySelector(".signal");
      signalEl.textContent = signal;
      signalEl.className = `signal ${signal === "BUY" ? "buy" : signal === "SELL" ? "sell" : "wait"}`;
      const pressure = strip.querySelector(".pressure");
      pressure.textContent = latest.pressure_score == null ? "—" : Number(latest.pressure_score).toFixed(1);
      const last = Array.isArray(d.rows) && d.rows.length ? d.rows[d.rows.length - 1] : null;
      if (last?.time) {
        strip.querySelector(".bar").textContent = new Intl.DateTimeFormat("en-GB", { timeZone:"UTC", hour:"2-digit", minute:"2-digit", hourCycle:"h23" }).format(new Date(Number(last.time) * 1000)) + " UTC";
      }
      const pnl = document.querySelector(".pnl strong")?.textContent?.trim();
      if (pnl) strip.querySelector(".result").textContent = pnl;
    } catch { /* keep last known M1 display */ }
  }

  function sync() {
    injectStyles();
    removeLosers();
    addLegacyDoubleTrade();
    addM1Strip();
    updateUtcClock();
  }

  const observer = new MutationObserver(sync);
  const start = () => {
    sync();
    observer.observe(document.body, { childList:true, subtree:true });
    setInterval(() => { updateUtcClock(); refreshM1Strip(); }, 60000);
    setInterval(updateUtcClock, 1000);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once:true });
  else start();
})();
