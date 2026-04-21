import React from 'react';
import { Shell } from './components/Layout/Shell';
import { useHydraStore } from './store/useHydraStore';

import { Scanner } from './stations/Scanner';
import { Workbench } from './stations/Workbench';
import { Vault } from './stations/Vault';
import { Analytics } from './stations/Analytics';

const App: React.FC = () => {
  const { activeStation } = useHydraStore();

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
