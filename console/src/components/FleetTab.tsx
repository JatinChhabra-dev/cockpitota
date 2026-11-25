import React, { useState } from 'react';
import { Play, Square, Camera, Smartphone, Layers, Globe, Zap, ExternalLink, RefreshCw } from 'lucide-react';
import { VariantConfig, FleetInstance, api } from '../api';

interface FleetTabProps {
  variants: Record<string, VariantConfig>;
  instances: FleetInstance[];
  refreshData: () => void;
  onSelectInstanceForSignals: (instanceId: string) => void;
}

export const FleetTab: React.FC<FleetTabProps> = ({
  variants,
  instances,
  refreshData,
  onSelectInstanceForSignals,
}) => {
  const [launchingVariant, setLaunchingVariant] = useState<string | null>(null);
  const [selectedBuild, setSelectedBuild] = useState<'v1.0' | 'v1.1' | 'v1.1-fix'>('v1.0');
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [screenshotLoadingId, setScreenshotLoadingId] = useState<string | null>(null);
  const [activeModalScreenshot, setActiveModalScreenshot] = useState<{ url: string; title: string } | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  const handleLaunch = async (variantId: string) => {
    try {
      setLaunchingVariant(variantId);
      await api.launchInstance(variantId, selectedBuild, 1);
      showNotification(`Launch request accepted for ${variantId} (${selectedBuild}). Booting...`);
      setTimeout(refreshData, 1000);
    } catch (err: any) {
      showNotification(`Launch error: ${err.message}`);
    } finally {
      setLaunchingVariant(null);
    }
  };

  const handleLaunchAllThree = async () => {
    try {
      setLaunchingVariant('ALL');
      await Promise.all([
        api.launchInstance('VAR-A', selectedBuild, 1),
        api.launchInstance('VAR-B', selectedBuild, 1),
        api.launchInstance('VAR-C', selectedBuild, 1),
      ]);
      showNotification(`Parallel launch initiated for VAR-A, VAR-B, VAR-C (${selectedBuild})!`);
      setTimeout(refreshData, 1000);
    } catch (err: any) {
      showNotification(`Parallel launch error: ${err.message}`);
    } finally {
      setLaunchingVariant(null);
    }
  };

  const handleStop = async (instanceId: string) => {
    try {
      setStoppingId(instanceId);
      await api.stopInstance(instanceId);
      showNotification(`Instance ${instanceId} stopped.`);
      refreshData();
    } catch (err: any) {
      showNotification(`Error stopping instance: ${err.message}`);
    } finally {
      setStoppingId(null);
    }
  };

  const handleCaptureScreenshot = async (instance: FleetInstance) => {
    try {
      setScreenshotLoadingId(instance.instance_id);
      const res = await api.captureScreenshot(instance.instance_id);
      showNotification(`Captured screenshot: ${res.filename}`);
      refreshData();
    } catch (err: any) {
      showNotification(`Screenshot error: ${err.message}`);
    } finally {
      setScreenshotLoadingId(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ONLINE':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold badge-online flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>ONLINE</span>;
      case 'STARTING':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold badge-starting flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping"></span>BOOTING</span>;
      case 'ERROR':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold badge-error">ERROR</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold badge-stopped">{status}</span>;
    }
  };

  return (
    <div className="space-y-8">
      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#13294C] border border-[#2E74C9] text-white px-4 py-2.5 rounded-xl shadow-2xl text-xs font-medium flex items-center gap-2 animate-bounce">
          <Zap className="w-4 h-4 text-blue-400" />
          <span>{notification}</span>
        </div>
      )}

      {/* Variant Specifications Section */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-blue-400" />
              Target Vehicle Variants (Spec §4)
            </h2>
            <p className="text-xs text-slate-400">
              Three predefined cockpit variants covering landscape, portrait, and European localization specifications.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <select
              value={selectedBuild}
              onChange={(e) => setSelectedBuild(e.target.value as 'v1.0' | 'v1.1' | 'v1.1-fix')}
              className="bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-mono"
              title="Select Aurelia EV build tag to auto-install on boot"
            >
              <option value="v1.0">Build: v1.0 (Baseline)</option>
              <option value="v1.1">Build: v1.1 (Planted Defect)</option>
              <option value="v1.1-fix">Build: v1.1-fix (Fixed)</option>
            </select>
            <button
              onClick={refreshData}
              className="btn-secondary text-xs py-1.5 px-3"
              title="Refresh instances"
            >
              <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
              Refresh
            </button>
            <button
              onClick={handleLaunchAllThree}
              disabled={launchingVariant !== null}
              className="btn-primary text-xs py-1.5 px-4"
            >
              <Play className="w-3.5 h-3.5" />
              {launchingVariant === 'ALL' ? 'Launching Fleet...' : 'Launch All 3 in Parallel'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {Object.entries(variants).map(([vid, cfg]) => {
            const isLandscape = cfg.display?.orientation === 'landscape';
            const isPortrait = cfg.display?.orientation === 'portrait';
            const isTargetDefect = vid === 'VAR-B';

            return (
              <div
                key={vid}
                className={`glass-panel p-5 relative overflow-hidden flex flex-col justify-between ${
                  isTargetDefect ? 'border-amber-500/30' : ''
                }`}
              >
                {isTargetDefect && (
                  <div className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    Defect Target (M3)
                  </div>
                )}

                <div>
                  <div className="flex items-center gap-2.5 mb-2">
                    <span className="text-xs px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 font-mono font-bold">
                      {cfg.id}
                    </span>
                    <h3 className="text-sm font-semibold text-white truncate">{cfg.name}</h3>
                  </div>

                  <p className="text-xs text-slate-400 mb-4">{cfg.description}</p>

                  <div className="space-y-2 text-xs font-mono bg-slate-900/70 p-3 rounded-lg border border-slate-800">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Display:</span>
                      <span className="text-slate-200 font-semibold">
                        {cfg.display?.width}×{cfg.display?.height} ({cfg.display?.orientation})
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Locale:</span>
                      <span className="text-slate-200 flex items-center gap-1">
                        <Globe className="w-3 h-3 text-blue-400" />
                        {cfg.locale}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400">EV Schedule:</span>
                      <span className={`text-[11px] px-1.5 rounded ${cfg.feature_flags?.EV_CHARGE_SCHEDULE === 'on' ? 'text-emerald-400 bg-emerald-950/60' : 'text-slate-400'}`}>
                        {cfg.feature_flags?.EV_CHARGE_SCHEDULE || 'off'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400">EU Data Consent:</span>
                      <span className={`text-[11px] px-1.5 rounded ${cfg.feature_flags?.EU_DATA_CONSENT_PROMPT === 'on' ? 'text-emerald-400 bg-emerald-950/60' : 'text-slate-400'}`}>
                        {cfg.feature_flags?.EU_DATA_CONSENT_PROMPT || 'off'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-5 pt-4 border-t border-slate-800/80 flex items-center justify-between">
                  <span className="text-[11px] text-slate-400 font-mono">AVD: {cfg.avd_name}</span>
                  <button
                    onClick={() => handleLaunch(vid)}
                    disabled={launchingVariant !== null}
                    className="btn-primary text-xs py-1.5 px-3"
                  >
                    <Play className="w-3 h-3" />
                    {launchingVariant === vid ? 'Launching...' : `Launch ${vid}`}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Active Fleet Instances */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Smartphone className="w-4 h-4 text-emerald-400" />
              Live Virtual Cockpits ({instances.length})
            </h2>
            <p className="text-xs text-slate-400">
              Active AAOS cockpit instances connected via ADB and reachable by VHAL signal simulator.
            </p>
          </div>
        </div>

        {instances.length === 0 ? (
          <div className="glass-panel p-10 text-center text-slate-400">
            <Smartphone className="w-8 h-8 text-slate-600 mx-auto mb-2 animate-bounce" />
            <p className="text-sm font-medium">No cockpit instances currently running.</p>
            <p className="text-xs text-slate-500 mt-1">
              Click &quot;Launch All 3 in Parallel&quot; above or launch a specific variant to start an AAOS virtual instance.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {instances.map((inst) => (
              <div key={inst.instance_id} className="glass-panel p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-blue-300">
                      {inst.variant_id}
                    </span>
                    {getStatusBadge(inst.status)}
                  </div>

                  <div className="space-y-1.5 text-xs font-mono mb-4">
                    <div className="flex justify-between">
                      <span className="text-slate-400">VIN:</span>
                      <span className="text-white font-semibold">{inst.vin_like}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Instance ID:</span>
                      <span className="text-slate-300 truncate max-w-[170px]">{inst.instance_id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">ADB Serial:</span>
                      <span className="text-emerald-400 font-semibold">{inst.adb_serial || `port ${inst.adb_port}`}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Boot Time:</span>
                      <span className="text-slate-300">
                        {inst.boot_time_seconds ? `${inst.boot_time_seconds}s` : 'measuring...'}
                      </span>
                    </div>
                  </div>

                  {/* Properties Summary */}
                  {Object.keys(inst.properties || {}).length > 0 && (
                    <div className="bg-slate-900/90 rounded-lg p-2.5 text-[11px] font-mono border border-slate-800 mb-4 space-y-1">
                      {inst.properties['ro.product.locale'] && (
                        <div className="text-slate-400">
                          Locale: <span className="text-slate-200">{inst.properties['ro.product.locale']}</span>
                        </div>
                      )}
                      {inst.properties['ro.build.characteristics'] && (
                        <div className="text-slate-400">
                          Build: <span className="text-slate-200">{inst.properties['ro.build.characteristics']}</span>
                        </div>
                      )}
                      {inst.properties['app.aurelia.ev'] && (
                        <div className="text-slate-400">
                          Aurelia EV: <span className="text-emerald-400 font-semibold">v{inst.properties['app.aurelia.ev']}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="space-y-2 pt-3 border-t border-slate-800">
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => handleCaptureScreenshot(inst)}
                      disabled={inst.status !== 'ONLINE' || screenshotLoadingId === inst.instance_id}
                      className="btn-secondary text-xs py-1.5 px-2 flex items-center justify-center gap-1.5"
                    >
                      <Camera className="w-3.5 h-3.5 text-blue-400" />
                      {screenshotLoadingId === inst.instance_id ? 'Snapping...' : 'Screenshot'}
                    </button>

                    <button
                      onClick={() => onSelectInstanceForSignals(inst.instance_id)}
                      disabled={inst.status !== 'ONLINE'}
                      className="btn-secondary text-xs py-1.5 px-2 flex items-center justify-center gap-1.5 hover:border-blue-400"
                    >
                      <Zap className="w-3.5 h-3.5 text-amber-400" />
                      Inject Signals
                    </button>
                  </div>

                  <button
                    onClick={() => handleStop(inst.instance_id)}
                    disabled={stoppingId === inst.instance_id}
                    className="btn-danger w-full text-xs py-1.5 flex items-center justify-center gap-1.5"
                  >
                    <Square className="w-3.5 h-3.5" />
                    {stoppingId === inst.instance_id ? 'Stopping...' : 'Teardown Instance'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Screenshot Preview Modal */}
      {activeModalScreenshot && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setActiveModalScreenshot(null)}
        >
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-4 max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-white">{activeModalScreenshot.title}</h3>
              <button
                onClick={() => setActiveModalScreenshot(null)}
                className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800"
              >
                Close ✕
              </button>
            </div>
            <img src={activeModalScreenshot.url} alt="Cockpit Screen" className="rounded-xl border border-slate-800 w-full object-contain max-h-[75vh]" />
          </div>
        </div>
      )}
    </div>
  );
};
