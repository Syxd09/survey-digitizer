import React, { useState } from 'react';
import { 
  Database, 
  Search, 
  Cpu, 
  Zap,
  TrendingUp,
  History,
  ShieldAlert
} from 'lucide-react';
import { useHydraStore } from '../store/useHydraStore';
import './Vault.css';

export const Vault: React.FC = () => {
  const { engineHealth } = useHydraStore();

  return (
    <div className="vault-station">
      <div className="vault-header">
        <div className="vault-title">
          <Database size={24} className="title-icon" />
          <div>
            <h1>HYDRA MEMORY VAULT</h1>
            <p>Active Learning Intelligence & Pattern Repository</p>
          </div>
        </div>
        <div className="vault-metrics">
          <div className="v-metric">
            <span className="v-label">LEARNED PATTERNS</span>
            <span className="v-value">1,248</span>
          </div>
          <div className="v-metric">
            <span className="v-label">ACCURACY GAIN</span>
            <span className="v-value text-success">+14.2%</span>
          </div>
        </div>
      </div>

      <div className="vault-grid">
        {/* Memory Stats */}
        <div className="vault-panel stats-panel">
          <h3>INTELLIGENCE OVERVIEW</h3>
          <div className="stats-list">
            <div className="stat-row">
              <div className="s-info">
                <Cpu size={16} />
                <span>Neural Weight Optimization</span>
              </div>
              <div className="s-bar-container">
                <div className="s-bar" style={{ width: '85%' }} />
              </div>
            </div>
            <div className="stat-row">
              <div className="s-info">
                <History size={16} />
                <span>Feedback Loop Latency</span>
              </div>
              <div className="s-bar-container">
                <div className="s-bar" style={{ width: '12%', background: 'var(--success)' }} />
              </div>
            </div>
          </div>
        </div>

        {/* Pattern List Mockup */}
        <div className="vault-panel patterns-panel">
          <div className="panel-header">
            <h3>ACTIVE MEMORY FRAGMENTS</h3>
            <div className="panel-search">
              <Search size={14} />
              <input type="text" placeholder="Search memory..." />
            </div>
          </div>
          
          <div className="pattern-list">
            {[
              { id: 'h782', type: 'Signature', confidence: 0.98, status: 'VERIFIED' },
              { id: 'n291', type: 'Handwritten Digit', confidence: 0.94, status: 'LEARNING' },
              { id: 's012', type: 'Checkmark V3', confidence: 0.89, status: 'VERIFIED' },
              { id: 'f441', type: 'Text Block Line', confidence: 0.72, status: 'DIFFICULT' },
            ].map(p => (
              <div key={p.id} className="pattern-item">
                <div className="p-icon"><Zap size={14} /></div>
                <div className="p-info">
                  <span className="p-name">{p.type} <small>#{p.id}</small></span>
                  <span className="p-meta">Confidence {(p.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className={`p-status ${p.status.toLowerCase()}`}>{p.status}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Engine Diagnostics */}
        <div className="vault-panel diag-panel">
          <div className="panel-header">
            <h3>ENGINE DIAGNOSTICS</h3>
            <div className={`engine-badge ${engineHealth.toLowerCase()}`}>
              {engineHealth}
            </div>
          </div>
          <div className="diag-logs">
            <div className="log-line">
              <span className="time">22:25:01</span>
              <span className="msg">[VAULT] Memory sync complete. 12 new patterns ingested.</span>
            </div>
            <div className="log-line info">
              <span className="time">22:25:05</span>
              <span className="msg">[HYDRA] Active learning loop recalibrating weights...</span>
            </div>
            <div className="log-line success">
              <span className="time">22:25:10</span>
              <span className="msg">[AUTHORITY] Optimization complete. Global confidence +0.2%.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
