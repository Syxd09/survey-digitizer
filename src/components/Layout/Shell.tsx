import React from 'react';
import { 
  Scan, 
  Table, 
  Database, 
  Activity, 
  Settings, 
  ChevronRight,
  ShieldCheck,
  Zap
} from 'lucide-react';
import { useHydraStore, Station } from '../../store/useHydraStore';
import './Shell.css';

interface NavItemProps {
  id: Station;
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: (id: Station) => void;
}

const NavItem: React.FC<NavItemProps> = ({ id, icon, label, active, onClick }) => (
  <button 
    className={`nav-item ${active ? 'active' : ''}`}
    onClick={() => onClick(id)}
  >
    <div className="nav-icon">{icon}</div>
    <span className="nav-label">{label}</span>
    {active && <div className="nav-active-pill" />}
  </button>
);

export const Shell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { activeStation, setStation, engineHealth } = useHydraStore();

  return (
    <div className="shell-container">
      <aside className="shell-sidebar">
        <div className="sidebar-brand">
          <div className="brand-logo">
            <Zap size={20} fill="var(--primary)" color="var(--primary)" />
          </div>
          <div className="brand-text">
            <h2>HYDRA</h2>
            <span>V10.1 AUTHORITY</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-group-label">STATIONS</div>
          <NavItem 
            id="COMMAND_CENTER" 
            icon={<Scan size={18} />} 
            label="Scanner" 
            active={activeStation === 'COMMAND_CENTER'}
            onClick={setStation}
          />
          <NavItem 
            id="WORKBENCH" 
            icon={<Table size={18} />} 
            label="Workbench" 
            active={activeStation === 'WORKBENCH'}
            onClick={setStation}
          />
          <NavItem 
            id="VAULT" 
            icon={<Database size={18} />} 
            label="Memory Vault" 
            active={activeStation === 'VAULT'}
            onClick={setStation}
          />
          <NavItem 
            id="ANALYTICS" 
            icon={<Activity size={18} />} 
            label="Analytics" 
            active={activeStation === 'ANALYTICS'}
            onClick={setStation}
          />
        </nav>

        <div className="sidebar-footer">
          <div className={`engine-status ${engineHealth.toLowerCase()}`}>
            <div className="status-indicator">
              <div className="status-ping" />
            </div>
            <div className="status-text">
              <span className="status-label">Hydra Engine</span>
              <span className="status-value">{engineHealth}</span>
            </div>
          </div>
          <button className="settings-btn">
            <Settings size={18} />
          </button>
        </div>
      </aside>

      <main className="shell-main">
        <header className="shell-header">
          <div className="header-breadcrumbs">
            <span className="breadcrumb-root">Survey Digitizer</span>
            <ChevronRight size={14} className="breadcrumb-sep" />
            <span className="breadcrumb-current">{activeStation.replace('_', ' ')}</span>
          </div>
          <div className="header-actions">
            <div className="authority-badge">
              <ShieldCheck size={14} />
              <span>Full Authority Mode</span>
            </div>
          </div>
        </header>
        <section className="station-content">
          {children}
        </section>
      </main>
    </div>
  );
};
