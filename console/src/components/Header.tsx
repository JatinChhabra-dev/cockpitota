import React from 'react';
import { Activity, ShieldCheck, Cpu } from 'lucide-react';

interface HeaderProps {
  backendOnline: boolean;
  activeCount: number;
  activeTab: 'fleet' | 'signals' | 'scenarios' | 'ota' | 'equivalence' | 'ai' | 'dossier';
  setActiveTab: (tab: 'fleet' | 'signals' | 'scenarios' | 'ota' | 'equivalence' | 'ai' | 'dossier') => void;
}

export const Header: React.FC<HeaderProps> = ({
  backendOnline,
  activeCount,
  activeTab,
  setActiveTab,
}) => {
  return (
    <header className="border-b border-slate-800 bg-slate-950/80 sticky top-0 z-50 backdrop-blur-md">
      {/* Top Compliance Disclaimer Banner per Spec §1, §10 */}
      <div className="bg-[#13294C] text-blue-200 text-xs py-1.5 px-4 text-center font-medium border-b border-blue-900/40 flex items-center justify-center gap-2">
        <ShieldCheck className="w-3.5 h-3.5 text-blue-400" />
        <span>
          Evidence prepared for SUMS review. Not a type-approval or certification decision. (Aurelia Motors OEM Twin)
        </span>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
        {/* Brand & Title */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-[#2E74C9] to-[#13294C] flex items-center justify-center border border-blue-400/30 shadow-lg shadow-blue-500/20">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">CORA</h1>
              <span className="text-xs px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800/60 font-mono">
                POC v1.0
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Cockpit & OTA Release Assurance — Operations Twin
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center bg-slate-900/90 p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => setActiveTab('fleet')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'fleet'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Virtual Fleet (M1)
          </button>
          <button
            onClick={() => setActiveTab('signals')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'signals'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Signal Control Deck (M2)
          </button>
          <button
            onClick={() => setActiveTab('scenarios')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'scenarios'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Scenario Replay (M2)
          </button>
          <button
            onClick={() => setActiveTab('ota')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'ota'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            OTA &amp; Ledger (M4)
          </button>
          <button
            onClick={() => setActiveTab('equivalence')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'equivalence'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Equivalence &amp; Gate (M5)
          </button>
          <button
            onClick={() => setActiveTab('ai')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'ai'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            AI Review (M6)
          </button>
          <button
            onClick={() => setActiveTab('dossier')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'dossier'
                ? 'bg-[#2E74C9] text-white shadow-md shadow-blue-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            R156 Dossier (M7)
          </button>
        </nav>

        {/* Backend Status & Counters */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-2 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800">
            <span
              className={`w-2 h-2 rounded-full ${
                backendOnline ? 'bg-emerald-500 shadow-sm shadow-emerald-500' : 'bg-red-500'
              } animate-pulse`}
            />
            <span className={backendOnline ? 'text-emerald-400' : 'text-red-400'}>
              {backendOnline ? 'API 8001 ONLINE' : 'API OFFLINE'}
            </span>
          </div>

          <div className="bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-blue-400" />
            <span>FLEET: <strong className="text-white">{activeCount}</strong> ACTIVE</span>
          </div>
        </div>
      </div>
    </header>
  );
};
