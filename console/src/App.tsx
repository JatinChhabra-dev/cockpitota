import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { FleetTab } from './components/FleetTab';
import { SignalsTab } from './components/SignalsTab';
import { ScenariosTab } from './components/ScenariosTab';
import { OtaTab } from './components/OtaTab';
import { VariantConfig, FleetInstance, ScenarioMeta, api } from './api';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'fleet' | 'signals' | 'scenarios' | 'ota'>('fleet');
  const [backendOnline, setBackendOnline] = useState<boolean>(false);
  const [variants, setVariants] = useState<Record<string, VariantConfig>>({});
  const [instances, setInstances] = useState<FleetInstance[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>([]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);

  const fetchStaticCatalog = async () => {
    try {
      const [vars, scs] = await Promise.all([
        api.getVariants().catch(() => ({})),
        api.getScenarios().catch(() => []),
      ]);
      setVariants(vars);
      setScenarios(scs);
    } catch (err) {
      console.error('Error fetching static catalog:', err);
    }
  };

  const fetchInstances = async () => {
    try {
      const insts = await api.getInstances();
      setBackendOnline(true);
      setInstances(insts);

      // Auto-select first online instance if none selected
      setSelectedInstanceId((prev) => {
        if (prev && insts.some((i) => i.instance_id === prev && i.status === 'ONLINE')) {
          return prev;
        }
        const firstOnline = insts.find((i) => i.status === 'ONLINE');
        return firstOnline ? firstOnline.instance_id : (insts[0]?.instance_id ?? null);
      });
    } catch {
      setBackendOnline(false);
    }
  };

  const fetchHealthAndData = async () => {
    await Promise.all([fetchStaticCatalog(), fetchInstances()]);
  };

  useEffect(() => {
    fetchHealthAndData();
    // Poll only live fleet instances every 5s (variants & scenarios are static config)
    const interval = setInterval(fetchInstances, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectInstanceForSignals = (instanceId: string) => {
    setSelectedInstanceId(instanceId);
    setActiveTab('signals');
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#0A0F1D] text-slate-100">
      <Header
        backendOnline={backendOnline}
        activeCount={instances.filter((i) => i.status === 'ONLINE').length}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'fleet' && (
          <FleetTab
            variants={variants}
            instances={instances}
            refreshData={fetchHealthAndData}
            onSelectInstanceForSignals={handleSelectInstanceForSignals}
          />
        )}

        {activeTab === 'signals' && (
          <SignalsTab
            instances={instances}
            selectedInstanceId={selectedInstanceId}
            setSelectedInstanceId={setSelectedInstanceId}
          />
        )}

        {activeTab === 'scenarios' && (
          <ScenariosTab
            scenarios={scenarios}
            instances={instances}
            selectedInstanceId={selectedInstanceId}
            setSelectedInstanceId={setSelectedInstanceId}
          />
        )}

        {activeTab === 'ota' && <OtaTab />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-4 px-6 text-center text-xs text-slate-500 font-mono">
        CORA Release Assurance Twin · Fictional OEM &quot;Aurelia Motors&quot; · UNECE R156 Alignment
      </footer>
    </div>
  );
};

export default App;
