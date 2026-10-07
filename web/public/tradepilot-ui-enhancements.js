(() => {
  const STYLE_ID = "tradepilot-premium-enhancements-style";
  const utc = (date = new Date()) => new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
  }).format(date);

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .quickBulkClose > div { grid-template-columns: 1fr !important; }
      .quickBulkClose .closeWinners { width: 100% !important; min-height: 82px !important; font-size: 18px !important; }
      .quickBulkClose .closeLosers { display: none !important; }
    `;
    document.head.appendChild(style);
  }

  function updateClock() {
    const live = document.querySelector(".liveTime");
    if (!live) return;
    const small = live.querySelector("small");
    const strong = live.querySelector("strong");
    if (small) small.textContent = "UTC TIME";
    if (strong) strong.textContent = `${utc()} UTC`;
  }

  function removeLosers() {
    document.querySelectorAll(".quickBulkClose .closeLosers").forEach(el => el.remove());
  }

  function symbol() {
    const saved = localStorage.getItem("tp_fusion_symbol");
    if (saved) return saved;
    const button = document.querySelector(".symbolSelectButton span");
    const value = (button?.textContent || "").trim();
    if (value && !/choose|loading/i.test(value)) return value.split("—")[0].trim();
    return "XAUUSD";
  }

  async function directDoubleTrade(button) {
    const token = localStorage.getItem("tp_token") || "";
    const deviceId = localStorage.getItem("tp_device") || "";
    const symbolValue = symbol();
    const lotText = document.querySelector(".lotControl strong")?.textContent || "0.01";
    const volume = Number(String(lotText).replace(/[^0-9.]/g, "")) || 0.01;
    if (!token || !deviceId) { alert("Select a connected MT5 device first"); return; }
    button.disabled = true;
    button.dataset.original = button.querySelector("span")?.textContent || "OPEN BUY + SELL AT MARKET";
    if (button.querySelector("span")) button.querySelector("span").textContent = "SENDING BUY + SELL…";
    const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
    const command = async action => {
      const id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${action}`);
      const response = await fetch("/commands", { method:"POST", headers, body:JSON.stringify({command_id:id,device_id:deviceId,action,symbol:symbolValue,volume,sl:null,tp:null,price:null}) });
      const data = await response.json().catch(()=>({}));
      if (!response.ok) throw new Error(data.detail || `${action} request failed`);
      for(let i=0;i<30;i++){
        await new Promise(r=>setTimeout(r,350));
        const status=await fetch(`/commands/${id}`,{headers,cache:"no-store"});
        const j=await status.json().catch(()=>({}));
        if(j.status!=="queued") return j.result||{};
      }
      return {ok:false,message:"Command timed out"};
    };
    try {
      const [buy,sell]=await Promise.all([command("BUY"),command("SELL")]);
      const message=`${buy.ok?"✓ BUY":"✕ BUY"}${buy.ticket?` #${buy.ticket}`:""} • ${sell.ok?"✓ SELL":"✕ SELL"}${sell.ticket?` #${sell.ticket}`:""}`;
      const result = document.querySelector(".result");
      if(result){result.textContent=message;result.classList.toggle("error",!buy.ok||!sell.ok);}
    } catch(e) {
      const result = document.querySelector(".result");
      if(result){result.textContent=`✕ ${e.message}`;result.classList.add("error");}
    } finally {
      button.disabled=false;
      if(button.querySelector("span")) button.querySelector("span").textContent=button.dataset.original || "OPEN BUY + SELL AT MARKET";
    }
  }

  function ensureDoubleTrade() {
    const existing = document.querySelector("button.doubleTrade");
    const shark = document.querySelector(".sharkPanel");
    if (!shark) return;
    if (existing && existing.dataset.tpBound === "1") return;
    let button = existing;
    if (existing) {
      button = existing.cloneNode(true);
      existing.replaceWith(button);
    } else {
      button = document.createElement("button");
      button.className = "doubleTrade";
      button.innerHTML = "<strong>DOUBLE TRADE</strong><span>OPEN BUY + SELL AT MARKET</span>";
      shark.querySelector(".sharkAdvanced")?.before(button);
    }
    button.dataset.tpBound="1";
    button.onclick = ev => { ev.preventDefault(); ev.stopPropagation(); directDoubleTrade(button); };
  }

  function start() {
    installStyle(); updateClock(); removeLosers(); ensureDoubleTrade();
    setInterval(() => { updateClock(); removeLosers(); ensureDoubleTrade(); }, 1000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true }); else start();
})();
