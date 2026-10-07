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
          <div className="pro-card-value" style={{color: 'var(--buy-color)'}}>+43.9 â€¢ Medium</div>
          <div className="pro-card-sub">Bullish â€¢ Medium</div>
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
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Strong</span><span style={{color: 'var(--buy-color)'}}>65 â€” 100</span></div>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Medium</span><span style={{color: 'var(--buy-color)'}}>35 â€” 64</span></div>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Weak</span><span style={{color: 'var(--sell-color)'}}>22 â€” 34</span></div>
              <div style={{display: 'flex', justifyContent: 'space-between'}}><span>Neutral</span><span>-21 â€” +21</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignalFusionPro;
