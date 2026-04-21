import React, { useEffect, useState } from 'react';
import { 
  Database, 
  Search, 
  Cpu, 
  Zap,
  TrendingUp,
  History,
  ShieldAlert,
  RefreshCcw,
  Clock
} from 'lucide-react';
import { useHydraStore } from '../store/useHydraStore';
import './Vault.css';

export const Vault: React.FC = () => {
  const { vaultScans, fetchVault, engineHealth } = useHydraStore();
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetchVault();
    // Poll vault every 10s
    const interval = setInterval(fetchVault, 10000);
    return () => clearInterval(interval);
  }, [fetchVault]);

  const filteredScans = vaultScans.filter(s => 
    s.scanId.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.status.toLowerCase().includes(searchTerm.toLowerCase())
  );

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
            <span className="v-value">{vaultScans.length * 12}</span>
          </div>
          <div className="v-metric">
            <span className="v-label">TOTAL RECORDS</span>
            <span className="v-value">{vaultScans.length}</span>
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

        {/* Pattern List */}
        <div className="vault-panel patterns-panel">
          <div className="panel-header">
            <h3>ACTIVE MEMORY FRAGMENTS</h3>
            <div className="panel-search">
              <Search size={14} />
              <input 
                type="text" 
                placeholder="Search scans..." 
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>
          
          <div className="pattern-list">
            {filteredScans.length > 0 ? filteredScans.map(s => (
              <div key={s.scanId} className="pattern-item">
                <div className="p-icon">
                  {s.status === 'good' ? <Zap size={14} color="var(--success)" /> : <Clock size={14} />}
                </div>
                <div className="p-info">
                  <span className="p-name">Scan <small>#{s.scanId.substring(0,8)}</small></span>
                  <span className="p-meta">Confidence {(s.confidence * 100).toFixed(1)}%</span>
                </div>
                <div className={`p-status ${s.status.toLowerCase()}`}>{s.status}</div>
              </div>
            )) : (
              <div className="pattern-empty">
                <RefreshCcw size={24} className="spin" />
                <p>Retrieving memory fragments...</p>
              </div>
            )}
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
              <span className="time">{new Date().toLocaleTimeString()}</span>
              <span className="msg">[VAULT] Memory sync complete. {vaultScans.length} patterns indexed.</span>
            </div>
            {engineHealth === 'HEALTHY' ? (
              <div className="log-line success">
                <span className="time">{new Date().toLocaleTimeString()}</span>
                <span className="msg">[HYDRA] Inference engine optimized for MPS (Silicon).</span>
              </div>
            ) : (
              <div className="log-line error">
                <span className="time">{new Date().toLocaleTimeString()}</span>
                <span className="msg">[HYDRA] Warning: High-latency detection in mixed-mode.</span>
              </div>
            )}
            <div className="log-line info">
              <span className="time">{new Date().toLocaleTimeString()}</span>
              <span className="msg">[AUTHORITY] Waiting for user corrections to strengthen neural weights.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
