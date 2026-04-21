import React, { useEffect } from 'react';
import { Shell } from './components/Layout/Shell';
import { Scanner } from './stations/Scanner';
import { Workbench } from './stations/Workbench';
import { Vault } from './stations/Vault';
import { Analytics } from './stations/Analytics';
import { useHydraStore } from './store/useHydraStore';

const App: React.FC = () => {
  const { activeStation, setStation, pollPendingScans, fetchVault, fetchMetrics } = useHydraStore();

  // 1. Global URL Persistence & Routing
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (e.state?.station) {
        setStation(e.state.station, false);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [setStation]);

  // 2. Background Polling Engine (V11.0 Polling)
  useEffect(() => {
    // Poll for pending scans every 2.5s
    const scanInterval = setInterval(() => {
      pollPendingScans();
    }, 2500);

    // Refresh vault and metrics every 10s
    const dataInterval = setInterval(() => {
      fetchVault();
      fetchMetrics();
    }, 10000);

    return () => {
      clearInterval(scanInterval);
      clearInterval(dataInterval);
    };
  }, [pollPendingScans, fetchVault, fetchMetrics]);

  const renderStation = () => {
    switch (activeStation) {
      case 'COMMAND_CENTER': return <Scanner />;
      case 'WORKBENCH': return <Workbench />;
      case 'VAULT': return <Vault />;
      case 'ANALYTICS': return <Analytics />;
      default: return <Scanner />;
    }
  };

  return (
    <Shell>
      {renderStation()}
    </Shell>
  );
};

export default App;
