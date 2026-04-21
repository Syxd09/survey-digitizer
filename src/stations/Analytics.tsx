import React, { useEffect } from 'react';
import { 
  BarChart3, 
  TrendingUp, 
  PieChart, 
  Activity,
  ArrowUpRight,
  Clock,
  Zap,
  RefreshCcw
} from 'lucide-react';
import { useHydraStore } from '../store/useHydraStore';
import './Analytics.css';

export const Analytics: React.FC = () => {
  const { metrics, fetchMetrics } = useHydraStore();

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000); // Live metrics every 5s
    return () => clearInterval(interval);
  }, [fetchMetrics]);

  if (!metrics) {
    return (
      <div className="analytics-loading">
        <RefreshCcw size={48} className="spin" />
        <p>Initializing Neural Analytics Engine...</p>
      </div>
    );
  }

  const statCards = [
    { 
      label: 'TOTAL FORMS', 
      value: metrics.total_forms.toLocaleString(), 
      trend: `${metrics.throughput_fpm.toFixed(1)} FPM`, 
      icon: <Activity size={20} /> 
    },
    { 
      label: 'AVG. CONFIDENCE', 
      value: `${(metrics.avg_confidence * 100).toFixed(1)}%`, 
      trend: metrics.avg_confidence > 0.9 ? 'OPTIMAL' : 'LEARNING', 
      icon: <TrendingUp size={20} /> 
    },
    { 
      label: 'PROCESSING TIME', 
      value: `${metrics.avg_processing_time.toFixed(2)}s`, 
      trend: 'ASYNC', 
      icon: <Clock size={20} /> 
    },
    { 
      label: 'CONFLICT RATE', 
      value: `${(metrics.conflict_rate * 100).toFixed(1)}%`, 
      trend: `-${(metrics.failure_rate * 100).toFixed(1)}% ERROR`, 
      icon: <BarChart3 size={20} /> 
    },
  ];

  return (
    <div className="analytics-station">
      <div className="analytics-header">
        <div className="analytics-title">
          <BarChart3 size={24} className="title-icon" />
          <h1>ENGINE ANALYTICS</h1>
        </div>
        <div className="time-filter">
          <button className="active">Live Dashboard</button>
        </div>
      </div>

      <div className="metrics-summary">
        {statCards.map((m, idx) => (
          <div key={idx} className="summary-card">
            <div className="card-header">
              <div className="icon-box">{m.icon}</div>
              <span className="trend">{m.trend} <Zap size={12} fill="var(--primary)" /></span>
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
            <h3>DISTRIBUTION BY STATUS</h3>
            <span className="subtitle">Real-time validation gating</span>
          </div>
          <div className="dist-list">
            {Object.entries(metrics.status_distribution).map(([status, count], i) => (
              <div key={status} className="dist-item">
                <div className="dist-info">
                  <span className="d-label">{status.toUpperCase()}</span>
                  <span className="d-count">{count}</span>
                </div>
                <div className="d-bar-bg">
                  <div 
                    className="d-bar" 
                    style={{ 
                      width: `${(count / metrics.total_forms) * 100}%`, 
                      background: status === 'good' ? 'var(--success)' : 
                                  status === 'conflict' ? 'var(--tertiary)' : 
                                  status === 'bad' ? 'var(--error)' : 'var(--primary)'
                    }} 
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-panel throughput-panel">
          <div className="panel-header">
            <h3>NEURAL THROUGHPUT (FPM)</h3>
            <span className="subtitle">Forms processed per minute</span>
          </div>
          <div className="throughput-value">
            <span className="giant-value">{metrics.throughput_fpm.toFixed(1)}</span>
            <span className="unit">FPM</span>
          </div>
          <div className="throughput-visual">
            <div className="scanner-line" />
            <div className="data-particles">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="particle" style={{ animationDelay: `${i * 0.5}s` }} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
