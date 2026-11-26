import React, { useState, useEffect } from 'react';
import {
  Play,
  ShieldCheck,
  ShieldAlert,
  GitCompare,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
} from 'lucide-react';
import {
  FleetInstance,
  M5EquivalenceReport,
  M5GateBundle,
  M5RunRecord,
  api,
} from '../api';

interface EquivalenceTabProps {
  instances: FleetInstance[];
}

export const EquivalenceTab: React.FC<EquivalenceTabProps> = ({ instances }) => {
  const onlineInstances = instances.filter((i) => i.status === 'ONLINE');

  const [selectedRelease, setSelectedRelease] = useState<'v1.0' | 'v1.1' | 'v1.1-fix'>('v1.1');
  const [baselineRelease, setBaselineRelease] = useState<'v1.0'>('v1.0');
  const [runs, setRuns] = useState<M5RunRecord[]>([]);
  const [equivReport, setEquivReport] = useState<M5EquivalenceReport | null>(null);
  const [gateBundle, setGateBundle] = useState<M5GateBundle | null>(null);
  const [diffFilter, setDiffFilter] = useState<'all' | 'unexplained' | 'declared' | 'cosmetic'>('all');

  const [running, setRunning] = useState<boolean>(false);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [toast, setToast] = useState<string | null>(null);

  const notify = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  const refreshRuns = async () => {
    try {
      const res = await api.getRuns();
      setRuns(res.runs || []);
    } catch (err) {
      console.error('Error loading M5 runs:', err);
    }
  };

  useEffect(() => {
    refreshRuns();
  }, []);

  const handleStartLiveRun = async () => {
    if (onlineInstances.length === 0) {
      notify('No ONLINE AAOS cockpits found. Boot VAR-A / VAR-B / VAR-C in Virtual Fleet (M1) first.');
      return;
    }
    try {
      setRunning(true);
      notify(`Running live SC-01..SC-04 suites for ${selectedRelease} on ${onlineInstances.length} online cockpit(s)...`);
      const res = await api.startRuns(selectedRelease, ['SC-01', 'SC-02', 'SC-03', 'SC-04']);
      notify(`Completed ${res.total} live run(s) for ${selectedRelease}!`);
      await refreshRuns();

      // Auto-evaluate equivalence & gate if comparing against baseline
      if (selectedRelease !== baselineRelease) {
        await handleEvaluateGate(selectedRelease);
      }
    } catch (err: any) {
      notify(`Run error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const handleEvaluateGate = async (targetRelease = selectedRelease) => {
    try {
      setEvaluating(true);
      const [eq, gate] = await Promise.all([
        api.getEquivalence(targetRelease, baselineRelease),
        api.evaluateGate(targetRelease, baselineRelease),
      ]);
      setEquivReport(eq);
      setGateBundle(gate);
      notify(`Gate for ${targetRelease}: ${gate.overall_outcome} (Unexplained: ${eq.summary.unexplained})`);
    } catch (err: any) {
      notify(`Evaluate error: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  // Latest run per variant for currently selected release
  const latestByVariant: Record<string, M5RunRecord> = {};
  for (const r of runs) {
    if (r.release_id === selectedRelease) {
      const prev = latestByVariant[r.variant_id];
      if (!prev || r.started_at >= prev.started_at) {
        latestByVariant[r.variant_id] = r;
      }
    }
  }
  const variantRows = Object.values(latestByVariant).sort((a, b) => a.variant_id.localeCompare(b.variant_id));

  const filteredDiffs = (equivReport?.differences || []).filter(
    (d) => diffFilter === 'all' || d.diff_class === diffFilter
  );

  const renderStatusPill = (status: string) => {
    if (status === 'pass') {
      return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-online">PASS</span>;
    }
    if (status === 'flaky') {
      return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-starting">FLAKY</span>;
    }
    return <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold badge-error">FAIL</span>;
  };

  const renderDiffBadge = (cls: string, changeId?: string) => {
    if (cls === 'unexplained') {
      return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold badge-error">UNEXPLAINED</span>;
    }
    if (cls === 'declared') {
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-900/60 text-blue-300 border border-blue-800/60">
          DECLARED {changeId ? `(${changeId})` : ''}
        </span>
      );
    }
    return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold badge-stopped">COSMETIC</span>;
  };

  const getSuiteResult = (run: M5RunRecord, suite: string) =>
    run.results.filter((r) => r.suite === suite);

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#13294C] border border-[#2E74C9] text-white px-4 py-2.5 rounded-xl shadow-2xl text-xs font-medium flex items-center gap-2">
          <GitCompare className="w-4 h-4 text-blue-400" />
          <span>{toast}</span>
        </div>
      )}

      {/* Control Bar */}
      <div className="glass-panel p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <GitCompare className="w-4 h-4 text-blue-400" />
            Test &amp; Equivalence Engine + Release Gate (M5)
          </h2>
          <p className="text-xs text-slate-400">
            Run live ADB suites (SC-01..SC-04) across online variants, diff UI trees/z-order/screenshots vs baseline, and compute RXSWIN-impact.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <select
            value={selectedRelease}
            onChange={(e) => setSelectedRelease(e.target.value as 'v1.0' | 'v1.1' | 'v1.1-fix')}
            className="bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-mono"
          >
            <option value="v1.0">Target: v1.0 (Baseline)</option>
            <option value="v1.1">Target: v1.1 (Planted Defect)</option>
            <option value="v1.1-fix">Target: v1.1-fix (Fixed)</option>
          </select>

          <select
            value={baselineRelease}
            onChange={(e) => setBaselineRelease(e.target.value as 'v1.0')}
            className="bg-slate-900 border border-slate-700 text-slate-300 rounded-lg px-3 py-1.5 text-xs font-mono"
          >
            <option value="v1.0">Baseline: v1.0</option>
          </select>

          <button onClick={refreshRuns} className="btn-secondary text-xs py-1.5 px-3">
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
            Refresh
          </button>

          <button
            onClick={handleStartLiveRun}
            disabled={running || onlineInstances.length === 0}
            className="btn-primary text-xs py-1.5 px-3.5"
          >
            <Play className="w-3.5 h-3.5" />
            {running ? 'Running Live Suites...' : `Run ${selectedRelease} Live`}
          </button>

          <button
            onClick={() => handleEvaluateGate(selectedRelease)}
            disabled={evaluating || selectedRelease === baselineRelease}
            className="btn-secondary text-xs py-1.5 px-3.5 hover:border-blue-400"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            {evaluating ? 'Evaluating...' : 'Evaluate Gate'}
          </button>
        </div>
      </div>

      {/* Release Gate Decision Banner (Spec Figure 3 + M5-FR7) */}
      {gateBundle && (
        <div
          className={`rounded-2xl p-5 border ${
            gateBundle.overall_outcome === 'PASS'
              ? 'bg-emerald-950/60 border-emerald-700'
              : 'bg-red-950/80 border-red-800/80'
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-3">
              {gateBundle.overall_outcome === 'PASS' ? (
                <CheckCircle2 className="w-8 h-8 text-emerald-400" />
              ) : (
                <XCircle className="w-8 h-8 text-red-400" />
              )}
              <div>
                <h3 className="text-lg font-bold text-white">
                  Release Gate ({gateBundle.release_id} vs {gateBundle.baseline_release_id}):{' '}
                  <span className={gateBundle.overall_outcome === 'PASS' ? 'text-emerald-300' : 'text-red-400'}>
                    {gateBundle.overall_outcome}
                  </span>
                </h3>
                <p className="text-xs text-slate-300">
                  {gateBundle.ota_eligible
                    ? 'All suites passed with only DECLARED/COSMETIC differences — cleared for staged OTA rollout (M4).'
                    : 'Release BLOCKED — unexplained safety/equivalence defect detected; OTA campaign creation denied.'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 font-mono text-xs">
              <span
                className={`px-3 py-1 rounded-lg font-bold border ${
                  gateBundle.rxswin_impact
                    ? 'bg-amber-600 text-white border-amber-500/30'
                    : 'bg-slate-900 text-slate-300 border-slate-700'
                }`}
              >
                RXSWIN-IMPACT: {gateBundle.rxswin_impact ? 'YES (HOMOLOGATION)' : 'NONE'}
              </span>
            </div>
          </div>

          {/* Per-Variant Gate Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {gateBundle.variants.map((v) => (
              <div key={v.gate_id} className="bg-slate-950/80 rounded-xl p-3.5 border border-slate-800 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-white">{v.variant_id}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${v.outcome === 'PASS' ? 'badge-online' : 'badge-error'}`}>
                    {v.outcome}
                  </span>
                </div>
                {v.rxswin_impact && (
                  <div className="text-[11px] font-mono text-amber-300 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    {v.rxswin_components.join(', ')}
                  </div>
                )}
                <ul className="text-[11px] text-slate-300 space-y-1">
                  {v.reasons.map((reason, idx) => (
                    <li key={idx} className="truncate" title={reason}>
                      • {reason}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Variant Matrix (Spec §10 M7-FR1) */}
      <div className="glass-panel p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Variant Matrix — {selectedRelease} ({variantRows.length} Variant Runs)
            </h3>
            <p className="text-xs text-slate-400">
              Live suite outcomes per cockpit variant (SC-01 UX Lock, SC-02 EV Charge, SC-03 Rear-view &lt;500 ms, SC-04 HVAC).
            </p>
          </div>
        </div>

        {variantRows.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
            <ShieldAlert className="w-7 h-7 text-slate-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-white">No recorded runs for {selectedRelease} yet.</p>
            <p className="text-xs text-slate-400 mt-1">
              Click <strong>Run {selectedRelease} Live</strong> above (with VAR-A / VAR-B online) or run <code>python engine\test_m5_acceptance.py</code>.
            </p>
          </div>
        ) : (
          <div className="overflow-y-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-900 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">Variant / Serial</th>
                  <th className="p-3">UX Restriction (SC-01)</th>
                  <th className="p-3">Functional (SC-02 / SC-04)</th>
                  <th className="p-3">Safety Display (SC-03)</th>
                  <th className="p-3">Wall Time</th>
                </tr>
              </thead>
              <tbody>
                {variantRows.map((run) => {
                  const ux = getSuiteResult(run, 'ux_restriction')[0];
                  const funcs = getSuiteResult(run, 'functional');
                  const safety = getSuiteResult(run, 'safety_display')[0];
                  const allFuncPass = funcs.length > 0 && funcs.every((f) => f.status === 'pass');

                  return (
                    <tr key={run.run_id} className="border-b border-slate-800/60 hover:bg-slate-900/60">
                      <td className="p-3 text-white font-semibold">
                        {run.variant_id}
                        <div className="text-[10px] text-slate-400 font-normal">{run.adb_serial} · {run.run_id}</div>
                      </td>
                      <td className="p-3">
                        {ux ? renderStatusPill(ux.status) : <span className="text-slate-500">—</span>}
                      </td>
                      <td className="p-3">
                        {funcs.length > 0 ? (
                          <div className="flex items-center gap-2">
                            {renderStatusPill(allFuncPass ? 'pass' : 'fail')}
                            <span className="text-[10px] text-slate-400">
                              {funcs.filter((f) => f.status === 'pass').length}/{funcs.length}
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="p-3">
                        {safety ? (
                          <div>
                            {renderStatusPill(safety.status)}
                            <div className="text-[10px] text-slate-400 mt-1">
                              {safety.timing_ms != null ? `${safety.timing_ms} ms` : safety.message.slice(0, 48)}
                            </div>
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="p-3 text-slate-300">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3 text-blue-400" />
                          {run.wall_time_seconds}s
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Equivalence Report (Spec §10 M7-FR3) */}
      {equivReport && (
        <div className="glass-panel p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <GitCompare className="w-4 h-4 text-cyan-400" />
                Equivalence Diff Report ({equivReport.release_id} vs {equivReport.baseline_release_id})
              </h3>
              <p className="text-xs text-slate-400">
                Every UI tree, z-order, VHAL property, timing, and Pillow visual difference classified against <code>release_notes_v1.1.yaml</code>.
              </p>
            </div>

            <div className="flex items-center gap-2 text-xs font-mono">
              <button
                onClick={() => setDiffFilter('all')}
                className={`px-2.5 py-1 rounded-lg border ${diffFilter === 'all' ? 'bg-blue-600 text-white border-blue-500' : 'bg-slate-900 text-slate-300 border-slate-700'}`}
              >
                All ({equivReport.summary.total})
              </button>
              <button
                onClick={() => setDiffFilter('unexplained')}
                className={`px-2.5 py-1 rounded-lg border ${diffFilter === 'unexplained' ? 'bg-red-600 text-white border-red-800/80' : 'bg-slate-900 text-red-400 border-slate-700'}`}
              >
                UNEXPLAINED ({equivReport.summary.unexplained})
              </button>
              <button
                onClick={() => setDiffFilter('declared')}
                className={`px-2.5 py-1 rounded-lg border ${diffFilter === 'declared' ? 'bg-blue-600 text-white border-blue-500' : 'bg-slate-900 text-blue-300 border-slate-700'}`}
              >
                DECLARED ({equivReport.summary.declared})
              </button>
              <button
                onClick={() => setDiffFilter('cosmetic')}
                className={`px-2.5 py-1 rounded-lg border ${diffFilter === 'cosmetic' ? 'bg-slate-700 text-white border-slate-700' : 'bg-slate-900 text-slate-400 border-slate-700'}`}
              >
                COSMETIC ({equivReport.summary.cosmetic})
              </button>
            </div>
          </div>

          <div className="overflow-y-auto max-h-[360px] rounded-lg border border-slate-800">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-900 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-2.5">Variant</th>
                  <th className="p-2.5">Step</th>
                  <th className="p-2.5">Kind</th>
                  <th className="p-2.5">Class</th>
                  <th className="p-2.5">Detail</th>
                </tr>
              </thead>
              <tbody>
                {filteredDiffs.slice(0, 100).map((d) => (
                  <tr key={d.diff_id} className="border-b border-slate-800/60 hover:bg-slate-900/60">
                    <td className="p-2.5 text-blue-300 font-semibold">{d.variant_id}</td>
                    <td className="p-2.5 text-slate-300">{d.step}</td>
                    <td className="p-2.5 text-slate-400">{d.kind}</td>
                    <td className="p-2.5">{renderDiffBadge(d.diff_class, d.change_id)}</td>
                    <td className="p-2.5 text-slate-200">{d.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
