import React, { useEffect } from 'react';
import { Shell } from './components/Layout/Shell';
import { Scanner } from './stations/Scanner';
import { Workbench } from './stations/Workbench';
import { Vault } from './stations/Vault';
import { Analytics } from './stations/Analytics';
import { useHydraStore, ROUTE_MAP } from './store/useHydraStore';
import './index.css';

const App: React.FC = () => {
  const { activeStation, setStation } = useHydraStore();

  useEffect(() => {
    // 1. Initial Path Normalization
    if (window.location.pathname === '/' || window.location.pathname === '') {
      window.history.replaceState({ station: 'COMMAND_CENTER' }, '', '/scanner');
    }

    // 2. Browser Navigation Listener (Back/Forward)
    const handlePopState = (event: PopStateEvent) => {
      const path = window.location.pathname;
      const station = ROUTE_MAP[path];
      if (station) {
        // Sync to store without pushing to history again
        setStation(station, false);
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [setStation]);

  const renderStation = () => {
    switch (activeStation) {
      case 'COMMAND_CENTER':
        return <Scanner />;
      case 'WORKBENCH':
        return <Workbench />;
      case 'VAULT':
        return <Vault />;
      case 'ANALYTICS':
        return <Analytics />;
      default:
        return <Scanner />;
    }
  };

  return (
    <Shell>
      {renderStation()}
    </Shell>
  );
};

export default App;
