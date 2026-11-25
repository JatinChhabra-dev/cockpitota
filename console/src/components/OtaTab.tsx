import React, { useState, useEffect } from 'react';
import {
  Rocket,
  Pause,
  Play,
  XCircle,
  RefreshCw,
  ShieldAlert,
  CheckCircle2,
  Clock,
  FileCheck,
  Car,
  BatteryCharging,
  Gauge,
} from 'lucide-react';
import { OtaCampaign, OtaVehicle, UpdateRecord, api } from '../api';

const RELEASE_OPTIONS = [
  { release_id: 'v1.1-fix', apk_filename: 'aurelia-ev-v1.1-fix.apk', target_version: '1.1.1-fix', label: 'v1.1-fix (Gate Approved)' },
  { release_id: 'v1.0', apk_filename: 'aurelia-ev-v1.0.apk', target_version: '1.0.0', label: 'v1.0 (Baseline Rollback)' },
  { release_id: 'v1.1', apk_filename: 'aurelia-ev-v1.1.apk', target_version: '1.1.0', label: 'v1.1 (Planted Defect)' },
];

export const OtaTab: React.FC = () => {
  const [vehicles, setVehicles] = useState<OtaVehicle[]>([]);
  const [campaigns, setCampaigns] = useState<OtaCampaign[]>([]);
  const [hawkbitLive, setHawkbitLive] = useState<boolean>(false);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [campaignRecords, setCampaignRecords] = useState<UpdateRecord[]>([]);
  const [selectedRelease, setSelectedRelease] = useState<string>('v1.1-fix');
  const [tamperTest, setTamperTest] = useState<boolean>(false);
  const [useVirtualScaleFleet, setUseVirtualScaleFleet] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [toast, setToast] = useState<string | null>(null);

  const notify = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const refreshAll = async (includeVirtual = useVirtualScaleFleet) => {
    try {
      const [vRes, cRes] = await Promise.all([
        api.getOtaVehicles(includeVirtual ? 'all' : 'live'),
        api.getCampaigns(),
      ]);
      setVehicles(vRes.vehicles || []);
      setCampaigns(cRes.campaigns || []);
      setHawkbitLive(cRes.hawkbit_live);

      const targetCid = selectedCampaignId || (cRes.campaigns.length > 0 ? cRes.campaigns[cRes.campaigns.length - 1].campaign_id : null);
      if (targetCid) {
        setSelectedCampaignId(targetCid);
        const detail = await api.getCampaignDetail(targetCid);
        setCampaignRecords(detail.records || []);
      }
    } catch (err: any) {
      console.error('OTA refresh error:', err);
    }
  };

  useEffect(() => {
    refreshAll(useVirtualScaleFleet);
  }, [useVirtualScaleFleet]);

  const handleCreateCampaign = async () => {
    const rel = RELEASE_OPTIONS.find((r) => r.release_id === selectedRelease) || RELEASE_OPTIONS[0];
    try {
      setBusy(true);
      const res = await api.createCampaign({
        release_id: rel.release_id,
        apk_filename: rel.apk_filename,
        target_version: rel.target_version,
        target_mode: useVirtualScaleFleet ? 'virtual10' : 'live',
        gate_passed: true,
        tamper_test: tamperTest,
        auto_start: true,
      });
      setSelectedCampaignId(res.campaign.campaign_id);
      setCampaignRecords(res.records || []);
      notify(`Campaign ${res.campaign.campaign_id} started (${res.campaign.hawkbit_mode})`);
      await refreshAll();
    } catch (err: any) {
      notify(`Error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleCampaignAction = async (cid: string, action: 'tick' | 'pause' | 'resume' | 'cancel') => {
    try {
      setBusy(true);
      const res = await api.campaignAction(cid, action);
      setSelectedCampaignId(res.campaign.campaign_id);
      setCampaignRecords(res.records || []);
      notify(`Campaign ${cid}: ${action.toUpperCase()} -> ${res.campaign.status}`);
      await refreshAll();
    } catch (err: any) {
      notify(`Action error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSimulateState = async (vehicleId: string, preset: 'SC01_MOVING' | 'SC05_LOW_SOC' | 'READY') => {
    try {
      setBusy(true);
      if (preset === 'SC01_MOVING') {
        await api.setVehicleState(vehicleId, { gear: 'GEAR_DRIVE', speed_kmh: 50, soc_percent: 80 });
        notify(`${vehicleId}: Set to SC-01 Moving (50 km/h, DRIVE)`);
      } else if (preset === 'SC05_LOW_SOC') {
        await api.setVehicleState(vehicleId, { gear: 'GEAR_PARK', speed_kmh: 0, soc_percent: 20 });
        notify(`${vehicleId}: Set to SC-05 Low Battery (SoC 20%)`);
      } else {
        await api.setVehicleState(vehicleId, { gear: 'GEAR_PARK', speed_kmh: 0, soc_percent: 80 });
        notify(`${vehicleId}: Parked & Charged (SoC 80% — OTA Ready)`);
      }
      await refreshAll();
    } catch (err: any) {
      notify(`State update error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const activeCampaign = campaigns.find((c) => c.campaign_id === selectedCampaignId) || campaigns[campaigns.length - 1];

  const getOutcomeBadge = (outcome: string) => {
    switch (outcome) {
      case 'INSTALLED':
        return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-online">INSTALLED</span>;
      case 'DEFERRED':
        return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-starting">DEFERRED</span>;
      case 'REJECTED':
      case 'FAILED':
      case 'ROLLED_BACK':
        return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-error">{outcome}</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-stopped">{outcome}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#13294C] border border-[#2E74C9] text-white px-4 py-2.5 rounded-xl shadow-2xl text-xs font-medium flex items-center gap-2">
          <Rocket className="w-4 h-4 text-blue-400" />
          <span>{toast}</span>
        </div>
      )}

      {/* Top Campaign Launcher Bar */}
      <div className="glass-panel p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Rocket className="w-4 h-4 text-blue-400" />
              Staged OTA Rollout &amp; R156 Ledger (M4)
            </h2>
            <span className={`text-[11px] font-mono px-2 py-0.5 rounded-full ${hawkbitLive ? 'badge-online' : 'badge-stopped'}`}>
              {hawkbitLive ? 'hawkBit 1.0 LIVE (:8080)' : 'hawkBit LOCAL MIRROR'}
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Two-stage rollout (10% Canary → 100% Fleet) with SHA-256 signature verification and VHAL parked + SoC ≥ 30% preconditions.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedRelease}
            onChange={(e) => setSelectedRelease(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-mono"
          >
            {RELEASE_OPTIONS.map((opt) => (
              <option key={opt.release_id} value={opt.release_id}>
                {opt.label}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800">
            <input
              type="checkbox"
              checked={useVirtualScaleFleet}
              onChange={(e) => setUseVirtualScaleFleet(e.target.checked)}
            />
            <span>10-Vehicle Scale Sim (M1-FR7)</span>
          </label>

          <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800">
            <input
              type="checkbox"
              checked={tamperTest}
              onChange={(e) => setTamperTest(e.target.checked)}
            />
            <span>Tamper Sig Test (M4-FR3)</span>
          </label>

          <button onClick={() => refreshAll()} className="btn-secondary text-xs py-1.5 px-3">
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
            Refresh
          </button>

          <button
            onClick={handleCreateCampaign}
            disabled={busy || (!useVirtualScaleFleet && vehicles.length === 0)}
            className="btn-primary text-xs py-1.5 px-4"
          >
            <Rocket className="w-3.5 h-3.5" />
            {busy ? 'Rolling out...' : useVirtualScaleFleet ? 'Launch 10-Car Rollout' : 'Push OTA to Live Cockpits'}
          </button>
        </div>
      </div>

      {/* Active Campaign Rollout Groups */}
      {activeCampaign && (
        <div className="glass-panel p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-blue-900/60 text-blue-300">
                  {activeCampaign.campaign_id}
                </span>
                <span className="text-sm font-bold text-white">
                  Release {activeCampaign.release_id} ({activeCampaign.apk_filename})
                </span>
                <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${activeCampaign.status === 'FINISHED'
                    ? 'badge-online'
                    : activeCampaign.status === 'FAILED' || activeCampaign.status === 'CANCELED'
                      ? 'badge-error'
                      : 'badge-starting'
                  }`}>
                  {activeCampaign.status}
                </span>
              </div>
              <p className="text-[11px] font-mono text-slate-400 mt-1">
                SHA-256: {activeCampaign.artefact_sha256.slice(0, 24)}… · hawkBit Rollout: {activeCampaign.hawkbit_rollout_id}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => handleCampaignAction(activeCampaign.campaign_id, 'tick')}
                disabled={busy}
                className="btn-primary text-xs py-1.5 px-3"
                title="Re-evaluate vehicle preconditions and advance eligible groups"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Re-check Preconditions (Tick)
              </button>
              {activeCampaign.status === 'PAUSED' ? (
                <button
                  onClick={() => handleCampaignAction(activeCampaign.campaign_id, 'resume')}
                  disabled={busy}
                  className="btn-secondary text-xs py-1.5 px-3"
                >
                  <Play className="w-3.5 h-3.5 text-emerald-400" />
                  Resume
                </button>
              ) : (
                <button
                  onClick={() => handleCampaignAction(activeCampaign.campaign_id, 'pause')}
                  disabled={busy || activeCampaign.status === 'FINISHED' || activeCampaign.status === 'CANCELED'}
                  className="btn-secondary text-xs py-1.5 px-3"
                >
                  <Pause className="w-3.5 h-3.5 text-amber-400" />
                  Pause
                </button>
              )}
              <button
                onClick={() => handleCampaignAction(activeCampaign.campaign_id, 'cancel')}
                disabled={busy || activeCampaign.status === 'FINISHED' || activeCampaign.status === 'CANCELED'}
                className="btn-danger text-xs py-1.5 px-3"
              >
                <XCircle className="w-3.5 h-3.5" />
                Cancel
              </button>
            </div>
          </div>

          {/* Staged Groups Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {activeCampaign.groups.map((g) => (
              <div key={g.group_index} className="bg-slate-900/70 rounded-xl p-4 border border-slate-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white">{g.name}</span>
                  <span className="text-[11px] font-mono text-blue-300">{g.status}</span>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono text-slate-300">
                  <span>Targets: <strong>{g.target_vehicle_ids.length}</strong></span>
                  <span className="text-emerald-400">Installed: <strong>{g.installed_count}</strong></span>
                  <span className="text-amber-400">Deferred: <strong>{g.deferred_count}</strong></span>
                  <span className="text-red-400">Failed/Rej: <strong>{g.failed_count}</strong></span>
                </div>
              </div>
            ))}
          </div>

          {/* Per-Vehicle R156 Ledger Table */}
          <div>
            <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
              <FileCheck className="w-4 h-4 text-emerald-400" />
              Per-Vehicle R156 Update Ledger ({campaignRecords.length} vehicles)
            </h3>
            <div className="overflow-y-auto max-h-[320px] rounded-lg border border-slate-800">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="p-2.5">Vehicle / VIN</th>
                    <th className="p-2.5">Variant</th>
                    <th className="p-2.5">Group</th>
                    <th className="p-2.5">Pre → Post Version</th>
                    <th className="p-2.5">Outcome</th>
                    <th className="p-2.5">Deferral / Verification Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {campaignRecords.map((rec) => (
                    <tr key={rec.record_id} className="border-b border-slate-800/60 hover:bg-slate-900/60">
                      <td className="p-2.5 text-white font-semibold">
                        {rec.vehicle_id}
                        <div className="text-[10px] text-slate-400 font-normal">{rec.vin_like}</div>
                      </td>
                      <td className="p-2.5 text-blue-300">{rec.variant_id}</td>
                      <td className="p-2.5 text-slate-300">G{rec.group_index}</td>
                      <td className="p-2.5 text-slate-200">
                        {rec.pre_versions?.['com.aurelia.ev'] || '—'} → <strong className="text-emerald-400">{rec.post_versions?.['com.aurelia.ev'] || '—'}</strong>
                      </td>
                      <td className="p-2.5">{getOutcomeBadge(rec.outcome)}</td>
                      <td className="p-2.5 text-[11px] text-slate-400">
                        {rec.failure_reason ? (
                          <span className="text-red-400">{rec.failure_reason}</span>
                        ) : rec.defer_reasons?.length > 0 ? (
                          <span className="text-amber-300">{rec.defer_reasons.join('; ')}</span>
                        ) : rec.signature_verified ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> SHA-256 &amp; Sig Verified
                          </span>
                        ) : (
                          <span>Awaiting Group 1 completion</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Live Cockpits (or Optional 10-Vehicle Fleet) Preconditions Panel */}
      <div className="glass-panel p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Car className="w-4 h-4 text-cyan-400" />
              {useVirtualScaleFleet
                ? `OTA Fleet — Live + 10-Vehicle Scale Sim (${vehicles.length} Vehicles)`
                : `Live AAOS Cockpits Ready for OTA (${vehicles.length} Online)`}
            </h3>
            <p className="text-xs text-slate-400">
              {useVirtualScaleFleet
                ? 'Includes the 10-vehicle headless M1-FR7 rollout fleet alongside your live AAOS emulators.'
                : 'Showing only your real running AAOS emulators. Updates install real signed APKs via ADB after checking live VHAL preconditions.'}
            </p>
          </div>
        </div>

        {vehicles.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
            <ShieldAlert className="w-7 h-7 text-amber-400 mx-auto mb-2" />
            <p className="text-sm font-semibold text-white">No Live AAOS Cockpits Currently Online</p>
            <p className="text-xs text-slate-400 mt-1">
              Boot <strong>VAR-A</strong>, <strong>VAR-B</strong>, or <strong>VAR-C</strong> in the <strong>Virtual Fleet (M1)</strong> tab to push real OTA updates, or enable <strong>10-Vehicle Scale Sim (M1-FR7)</strong> above.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {vehicles.slice(0, 13).map((v) => (
              <div key={v.vehicle_id} className="bg-slate-900/70 rounded-xl p-3.5 border border-slate-800 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-mono font-bold text-white">{v.adb_serial || v.vehicle_id}</span>
                    <span className="text-[10px] font-mono ml-2 px-1.5 py-0.5 rounded bg-slate-800 text-blue-300">{v.variant_id}</span>
                  </div>
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${v.preconditions.passed ? 'badge-online' : 'badge-starting'}`}>
                    {v.preconditions.passed ? 'OTA READY' : 'WILL DEFER'}
                  </span>
                </div>

                <div className="text-[11px] font-mono text-slate-400 flex justify-between">
                  <span>Speed: <strong className="text-slate-200">{Math.round(v.preconditions.speed_ms * 3.6)} km/h</strong></span>
                  <span>SoC: <strong className="text-cyan-300">{v.preconditions.soc_percent}%</strong></span>
                  <span>EV: <strong className="text-emerald-400">{v.current_versions?.['com.aurelia.ev'] || '1.0.0'}</strong></span>
                </div>

                <div className="grid grid-cols-3 gap-1.5">
                  <button
                    onClick={() => handleSimulateState(v.vehicle_id, 'SC01_MOVING')}
                    disabled={busy}
                    className="btn-secondary text-[10px] py-1 px-1.5"
                    title="Simulate SC-01 Driving (50 km/h)"
                  >
                    <Gauge className="w-3 h-3 text-amber-400" />
                    SC-01
                  </button>
                  <button
                    onClick={() => handleSimulateState(v.vehicle_id, 'SC05_LOW_SOC')}
                    disabled={busy}
                    className="btn-secondary text-[10px] py-1 px-1.5"
                    title="Simulate SC-05 Low SoC (20%)"
                  >
                    <BatteryCharging className="w-3 h-3 text-red-400" />
                    SoC 20%
                  </button>
                  <button
                    onClick={() => handleSimulateState(v.vehicle_id, 'READY')}
                    disabled={busy}
                    className="btn-secondary text-[10px] py-1 px-1.5"
                    title="Park & Charge to 80%"
                  >
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    Ready
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
