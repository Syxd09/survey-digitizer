import { create } from 'zustand';
import { hydraApi, ScanStatusResponse, DatasetMetrics } from '../services/api';

export type Station = 'COMMAND_CENTER' | 'WORKBENCH' | 'VAULT' | 'ANALYTICS';

const ROUTE_MAP: Record<string, Station> = {
  '/scanner': 'COMMAND_CENTER',
  '/workbench': 'WORKBENCH',
  '/vault': 'VAULT',
  '/analytics': 'ANALYTICS'
};

const PATH_MAP: Record<Station, string> = {
  'COMMAND_CENTER': '/scanner',
  'WORKBENCH': '/workbench',
  'VAULT': '/vault',
  'ANALYTICS': '/analytics'
};

interface ScannedPage {
  id: string;
  image: string; // base64
  status: 'uploaded' | 'good' | 'bad' | 'conflict' | 'failed' | 'processing';
  result?: ScanStatusResponse;
  timestamp: string;
}

interface HydraState {
  activeStation: Station;
  scannedPages: ScannedPage[];
  vaultScans: ScanStatusResponse[];
  metrics: DatasetMetrics | null;
  activeDatasetId: string;
  engineHealth: 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
  
  // Actions
  setStation: (station: Station, syncURL?: boolean) => void;
  addPage: (image: string, scanId: string) => void;
  updatePageStatus: (scanId: string, status: ScannedPage['status'], result?: ScanStatusResponse) => void;
  removePage: (scanId: string) => void;
  setEngineHealth: (health: HydraState['engineHealth']) => void;
  
  // Async fetches
  fetchVault: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
}

export const useHydraStore = create<HydraState>((set, get) => ({
  // Initialize from URL
  activeStation: ROUTE_MAP[window.location.pathname] || 'COMMAND_CENTER',
  scannedPages: [],
  vaultScans: [],
  metrics: null,
  activeDatasetId: 'default-authority',
  engineHealth: 'HEALTHY',

  setStation: (station, syncURL = true) => {
    set({ activeStation: station });
    if (syncURL) {
      const path = PATH_MAP[station];
      if (window.location.pathname !== path) {
        window.history.pushState({ station }, '', path);
      }
    }
  },
  
  addPage: (image, scanId) => {
    set((state) => ({
      scannedPages: [
        {
          id: scanId,
          image,
          status: 'uploaded',
          timestamp: new Date().toISOString(),
        },
        ...state.scannedPages,
      ],
    }));
  },

  updatePageStatus: (scanId, status, result) =>
    set((state) => ({
      scannedPages: state.scannedPages.map((p) =>
        p.id === scanId ? { ...p, status, result: result || p.result } : p
      ),
    })),

  removePage: (scanId) =>
    set((state) => ({
      scannedPages: state.scannedPages.filter((p) => p.id !== scanId),
    })),

  setEngineHealth: (health) => set({ engineHealth: health }),

  fetchVault: async () => {
    try {
      const scans = await hydraApi.listScans();
      set({ vaultScans: scans });
    } catch (err) {
      console.error('Vault fetch failed:', err);
    }
  },

  fetchMetrics: async () => {
    try {
      const metrics = await hydraApi.getDatasetMetrics();
      set({ metrics });
    } catch (err) {
      console.error('Metrics fetch failed:', err);
    }
  },
}));

// Export the maps for use in App.tsx
export { ROUTE_MAP, PATH_MAP };
