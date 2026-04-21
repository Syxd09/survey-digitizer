import React from 'react';
import { 
  BarChart3, 
  TrendingUp, 
  PieChart, 
  Activity,
  ArrowUpRight,
  Clock
} from 'lucide-react';
import './Analytics.css';

export const Analytics: React.FC = () => {
  return (
    <div className="analytics-station">
      <div className="analytics-header">
        <h1>ENGINE ANALYTICS</h1>
        <div className="time-filter">
          <button className="active">Last 24h</button>
          <button>7 Days</button>
          <button>30 Days</button>
        </div>
      </div>

      <div className="metrics-summary">
        {[
          { label: 'TOTAL SCANS', value: '4,281', trend: '+12%', icon: <Activity size={20} /> },
          { label: 'AVG. CONFIDENCE', value: '94.2%', trend: '+2.4%', icon: <TrendingUp size={20} /> },
          { label: 'PROCESSING TIME', value: '1.2s', trend: '-0.3s', icon: <Clock size={20} /> },
          { label: 'AUTO-VERIFIED', value: '88%', trend: '+5%', icon: <BarChart3 size={20} /> },
        ].map((m, idx) => (
          <div key={idx} className="summary-card">
            <div className="card-header">
              <div className="icon-box">{m.icon}</div>
              <span className="trend">{m.trend} <ArrowUpRight size={12} /></span>
            </div>
            <div className="card-body">
              <span className="value">{m.value}</span>
              <span className="label">{m.label}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="analytics-grid">
        <div className="chart-panel">
          <div className="panel-header">
            <h3>THROUGHPUT OVER TIME</h3>
            <span className="subtitle">Scans processed per hour</span>
          </div>
          <div className="mock-chart bar-chart">
            {[40, 60, 45, 90, 100, 80, 70, 85, 110, 95, 120, 105].map((h, i) => (
              <div key={i} className="bar-wrapper">
                <div className="bar" style={{ height: `${h}%` }}>
                  <div className="bar-glow" />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-panel">
          <div className="panel-header">
            <h3>CONFIDENCE DISTRIBUTION</h3>
            <span className="subtitle">Extraction quality breakdown</span>
          </div>
          <div className="dist-list">
            {[
              { label: '90-100% (High)', count: '3.8k', color: 'var(--success)' },
              { label: '70-90% (Medium)', count: '412', color: 'var(--primary)' },
              { label: '< 70% (Low)', count: '69', color: 'var(--tertiary)' },
            ].map((d, i) => (
              <div key={i} className="dist-item">
                <div className="dist-info">
                  <span className="d-label">{d.label}</span>
                  <span className="d-count">{d.count}</span>
                </div>
                <div className="d-bar-bg">
                  <div className="d-bar" style={{ width: i === 0 ? '80%' : i === 1 ? '15%' : '5%', background: d.color }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
