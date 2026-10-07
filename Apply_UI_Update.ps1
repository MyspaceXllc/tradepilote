# Apply_UI_Update.ps1
$ErrorActionPreference = "Stop"

Write-Host "جاري إنشاء ملفات الواجهة الجديدة..." -ForegroundColor Cyan

# 1. إنشاء مجلد المكونات الجديد
$componentDir = ".\web\src\components\SignalFusionPro"
if (!(Test-Path $componentDir)) {
    New-Item -ItemType Directory -Path $componentDir -Force | Out-Null
}

# 2. إنشاء ملف CSS للتصميم الاحترافي
$cssContent = @'
/* SignalFusionPro.css - Pro UI/UX */
:root {
  --bg-dark: #0B0E14;
  --bg-card: rgba(20, 26, 38, 0.7);
  --border-glow: rgba(255, 255, 255, 0.1);
  --buy-color: #FF8C00;
  --buy-glow: rgba(255, 140, 0, 0.4);
  --sell-color: #00BFFF;
  --sell-glow: rgba(0, 191, 255, 0.4);
  --text-primary: #E2E8F0;
  --text-secondary: #94A3B8;
}

.signal-fusion-pro {
  background-color: var(--bg-dark);
  color: var(--text-primary);
  font-family: 'Inter', system-ui, sans-serif;
  min-height: 100vh;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Header */
.pro-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-glow);
  border-radius: 12px;
  padding: 15px 25px;
}

.pro-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #FBBF24;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.pro-controls {
  display: flex;
  gap: 15px;
  align-items: center;
}

.pro-select {
  background: rgba(0,0,0,0.3);
  border: 1px solid var(--border-glow);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 8px;
  outline: none;
}

.pro-btn-analyze {
  background: #FBBF24;
  color: #000;
  font-weight: 700;
  border: none;
  padding: 10px 24px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.pro-btn-analyze:hover { transform: scale(1.05); box-shadow: 0 0 15px rgba(251, 191, 36, 0.5); }

/* Cards */
.pro-cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 15px;
}

.pro-card {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-glow);
  border-radius: 12px;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pro-card-label { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }
.pro-card-value { font-size: 1.2rem; font-weight: 700; }
.pro-card-sub { font-size: 0.8rem; color: var(--text-secondary); }

/* Matrix */
.pro-matrix-container {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-glow);
  border-radius: 12px;
  padding: 20px;
  flex: 1;
  position: relative;
  overflow: hidden;
}

.matrix-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.matrix-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: relative;
}

.lane-row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
  position: relative;
}

.lane-label {
  width: 120px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-align: right;
  padding-right: 10px;
}

.lane-blocks {
  flex: 1;
  display: flex;
  gap: 2px;
  height: 100%;
  position: relative;
}

.block {
  flex: 1;
  border-radius: 2px;
  transition: all 0.2s;
}
.block:hover { transform: scaleY(1.2); filter: brightness(1.5); z-index: 10; }
.block.buy { background-color: var(--buy-color); box-shadow: 0 0 8px var(--buy-glow); }
.block.sell { background-color: var(--sell-color); box-shadow: 0 0 8px var(--sell-glow); }
.block.neutral { background-color: #475569; }

/* The 5 Lines Overlay */
.lines-overlay {
  position: absolute;
  top: 0;
  left: 120px; /* Match lane-label width */
  right: 0;
  bottom: 0;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  z-index: 5;
}

.line-sell {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--sell-color), transparent);
  opacity: 0.6;
  position: relative;
}
.line-sell::after {
  content: 'SELL';
  position: absolute;
  right: 10px;
  top: -8px;
  font-size: 0.6rem;
  color: var(--sell-color);
}

.line-buy {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--buy-color), transparent);
  opacity: 0.6;
  position: relative;
}
.line-buy::after {
  content: 'BUY';
  position: absolute;
  right: 10px;
  top: -8px;
  font-size: 0.6rem;
  color: var(--buy-color);
}

/* Sidebar */
.pro-sidebar {
  width: 300px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}
'@

Set-Content -Path "$componentDir\SignalFusionPro.css" -Value $cssContent -Encoding UTF8

# 3. إنشاء ملف React Component
$jsxContent = @'
import React from 'react';
import './SignalFusionPro.css';

const SignalFusionPro = () => {
  // Mock data for demonstration
  const lanes = [
    { id: '01', name: 'MACD REGIME', data: Array(30).fill('buy') },
    { id: '02', name: 'CANDLE STATE', data: Array(30).fill('sell') },
    { id: '03', name: 'CANDLE PRESSURE', data: Array(30).fill('neutral') },
    { id: '04', name: 'TRADE TIMELINE', data: Array(30).fill('buy') },
  ];

  // 5 Buy Lines (Orange) and 5 Sell Lines (Blue)
  const renderLines = () => (
    <div className="lines-overlay">
      {/* Sell Lines (Blue) */}
      <div className="line-sell" style={{ top: '10%' }}></div>
      <div className="line-sell" style={{ top: '25%' }}></div>
      <div className="line-sell" style={{ top: '40%' }}></div>
      <div className="line-sell" style={{ top: '55%' }}></div>
      <div className="line-sell" style={{ top: '70%' }}></div>
      
      {/* Buy Lines (Orange) */}
      <div className="line-buy" style={{ top: '30%' }}></div>
      <div className="line-buy" style={{ top: '45%' }}></div>
      <div className="line-buy" style={{ top: '60%' }}></div>
      <div className="line-buy" style={{ top: '75%' }}></div>
      <div className="line-buy" style={{ top: '90%' }}></div>
    </div>
  );

  return (
    <div className="signal-fusion-pro">
      {/* Header */}
      <div className="pro-header">
        <div className="pro-title">Signal Fusion PRO</div>
        <div className="pro-controls">
          <select className="pro-select"><option>XAUUSD</option></select>
          <select className="pro-select"><option>M1</option></select>
          <button className="pro-btn-analyze">ANALYZE</button>
        </div>
      </div>

      {/* Top Cards */}
      <div className="pro-cards-grid">
        <div className="pro-card">
          <div className="pro-card-label">MACD Regime</div>
          <div className="pro-card-value" style={{color: 'var(--sell-color)'}}>Bearish</div>
          <div className="pro-card-sub">Held until a confirmed crossover</div>
        </div>
        <div className="pro-card">
          <div className="pro-card-label">Latest Candle State</div>
          <div className="pro-card-value" style={{color: 'var(--sell-color)'}}>Bearish</div>
          <div className="pro-card-sub">Separation -0.61</div>
        </div>
        <div className="pro-card">
          <div className="pro-card-label">Candle Pressure</div>
          <div className="pro-card-value" style={{color: 'var(--buy-color)'}}>+43.9 • Medium</div>
          <div className="pro-card-sub">Bullish • Medium</div>
        </div>
        <div className="pro-card">
          <div className="pro-card-label">Entry Zone</div>
          <div className="pro-card-value" style={{color: 'var(--sell-color)'}}>SELL POSITION OPEN</div>
          <div className="pro-card-sub">3:10:01 PM</div>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ display: 'flex', gap: '20px', flex: 1 }}>
        {/* Matrix */}
        <div className="pro-matrix-container">
          <div className="matrix-header">
            <span>XAUUSD - M1 - SIGNAL FUSION MATRIX</span>
            <span>Closed candles only</span>
          </div>
          <div className="matrix-grid">
            {lanes.map((lane) => (
              <div className="lane-row" key={lane.id}>
                <div className="lane-label">{lane.name}</div>
                <div className="lane-blocks">
                  {lane.data.map((type, i) => (
                    <div className={`block ${type}`} key={i}></div>
                  ))}
                </div>
              </div>
            ))}
            {/* 5 Lines Overlay */}
            {renderLines()}
          </div>
        </div>

        {/* Sidebar */}
        <div className="pro-sidebar">
          <div className="pro-card">
            <div className="pro-card-label">Latest Reading</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '10px' }}>
              <div>
                <div className="pro-card-sub">MACD</div>
                <div className="pro-card-value" style={{fontSize: '1rem'}}>-6.44928</div>
              </div>
              <div>
                <div className="pro-card-sub">SIGNAL</div>
                <div className="pro-card-value" style={{fontSize: '1rem'}}>-5.99231</div>
              </div>
            </div>
          </div>
          <div className="pro-card">
            <div className="pro-card-label">Candle Pressure Levels</div>
            <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '5px', fontSize: '0.8rem' }}>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Strong</span><span style={{color: 'var(--buy-color)'}}>65 — 100</span></div>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Medium</span><span style={{color: 'var(--buy-color)'}}>35 — 64</span></div>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Weak</span><span style={{color: 'var(--sell-color)'}}>22 — 34</span></div>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Neutral</span><span>-21 — +21</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignalFusionPro;
'@

Set-Content -Path "$componentDir\SignalFusionPro.jsx" -Value $jsxContent -Encoding UTF8

Write-Host "✅ تم إنشاء الملفات بنجاح في: $componentDir" -ForegroundColor Green
Write-Host "⚠️ يرجى الآن استبدال محتوى ملف Signal Fusion القديم بـ SignalFusionPro" -ForegroundColor Yellow