import React, { useEffect, useCallback } from 'react';
import { Shell } from './components/Layout/Shell';
import { Scanner } from './stations/Scanner';
import { Workbench } from './stations/Workbench';
import { Vault } from './stations/Vault';
import { Analytics } from './stations/Analytics';
import { useHydraStore } from './store/useHydraStore';
import { useWebSocket } from './hooks/useWebSocket';

const App: React.FC = () => {
  const { activeStation, setStation, updatePageStatus, setVaultScans, setMetrics } = useHydraStore();

  // WebSocket message handler — replaces all polling
  const handleWSMessage = useCallback((message: any) => {
    switch (message.type) {
      case 'scan_complete': {
        const scanData = message.data;
        if (scanData) {
          updatePageStatus(message.scanId, scanData.status || 'good', scanData);
        }
        break;
      }
      case 'scan_failed': {
        updatePageStatus(message.scanId, 'failed');
        break;
      }
      case 'scan_update': {
        const scanData = message.data;
        if (scanData) {
          const status = scanData.status || 'processing';
          updatePageStatus(message.scanId, status, scanData);
        }
        break;
      }
      case 'vault_update': {
        if (message.data) setVaultScans(message.data);
        break;
      }
      case 'metrics_update': {
        if (message.data) setMetrics(message.data);
        break;
      }
    }
  }, [updatePageStatus, setVaultScans, setMetrics]);

  const { isConnected, requestVault, requestMetrics, requestScanStatus } = useWebSocket(handleWSMessage);

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

  // 2. On connect: fetch vault and metrics immediately, then periodically request refreshes
  useEffect(() => {
    if (!isConnected) return;

    // Initial fetch
    requestVault();
    requestMetrics();

    // Periodic refresh via WebSocket (much lighter than HTTP polling)
    const refreshInterval = setInterval(() => {
      requestVault();
      requestMetrics();
    }, 10000);

    return () => clearInterval(refreshInterval);
  }, [isConnected, requestVault, requestMetrics]);

  // 3. Poll pending scans via WebSocket (lightweight request vs HTTP)
  useEffect(() => {
    if (!isConnected) return;

    const { scannedPages } = useHydraStore.getState();
    const pending = scannedPages.filter(p => p.status === 'uploaded' || p.status === 'processing');
    
    if (pending.length === 0) return;

    // Request status for any pending scans
    const pollInterval = setInterval(() => {
      const currentState = useHydraStore.getState();
      const stillPending = currentState.scannedPages.filter(
        p => p.status === 'uploaded' || p.status === 'processing'
      );
      stillPending.forEach(page => requestScanStatus(page.id));
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [isConnected, requestScanStatus, useHydraStore.getState().scannedPages.length]);

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
