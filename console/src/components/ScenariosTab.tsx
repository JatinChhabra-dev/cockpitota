import React, { useState } from 'react';
import { Play, CheckCircle2, Clock, FastForward, ShieldCheck, ListOrdered, FileText } from 'lucide-react';
import { FleetInstance, ScenarioMeta, TraceStep, api } from '../api';

interface ScenariosTabProps {
  scenarios: ScenarioMeta[];
  instances: FleetInstance[];
  selectedInstanceId: string | null;
  setSelectedInstanceId: (id: string) => void;
}

export const ScenariosTab: React.FC<ScenariosTabProps> = ({
  scenarios,
  instances,
  selectedInstanceId,
  setSelectedInstanceId,
}) => {
  const onlineInstances = instances.filter((i) => i.status === 'ONLINE');
  const activeInst = instances.find((i) => i.instance_id === selectedInstanceId) || onlineInstances[0];

  const [activeScenarioId, setActiveScenarioId] = useState<string>('SC-01');
  const [speedFactor, setSpeedFactor] = useState<number>(3.0);
  const [isReplaying, setIsReplaying] = useState<boolean>(false);
  const [replayResult, setReplayResult] = useState<{
    status: string;
    step_count: number;
    wall_time_seconds: number;
    trace: TraceStep[];
  } | null>(null);

  const [selectedScenarioDetail, setSelectedScenarioDetail] = useState<any | null>(null);

  const handleSelectScenario = async (sid: string) => {
    setActiveScenarioId(sid);
    try {
      const detail = await api.getScenario(sid);
      setSelectedScenarioDetail(detail);
    } catch {
      // best-effort
    }
  };

  const handleRunReplay = async () => {
    if (!activeInst) {
      alert('Please start or select an online cockpit instance first.');
      return;
    }

    try {
      setIsReplaying(true);
      setReplayResult(null);
      const res = await api.replayScenario(
        activeScenarioId,
        activeInst.instance_id,
        speedFactor,
        activeInst.adb_serial
      );
      setReplayResult(res);
    } catch (err: any) {
      alert(`Replay error: ${err.message}`);
    } finally {
      setIsReplaying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Scenario Catalogue Grid */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <ListOrdered className="w-4 h-4 text-blue-400" />
              Standard Scenario Catalogue (Spec §7)
            </h2>
            <p className="text-xs text-slate-400">
              Deterministic VSS-based drive cycles designed to validate cockpit software across all variants.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {scenarios.map((sc) => {
            const isSelected = activeScenarioId === sc.scenario_id;
            return (
              <div
                key={sc.scenario_id}
                onClick={() => handleSelectScenario(sc.scenario_id)}
                className={`cursor-pointer p-3.5 rounded-xl border transition-all ${
                  isSelected
                    ? 'bg-[#13294C]/80 border-[#2E74C9] shadow-lg shadow-blue-500/10 ring-1 ring-blue-500'
                    : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-mono font-bold px-1.5 py-0.5 rounded bg-blue-950 text-blue-300">
                    {sc.scenario_id}
                  </span>
                  <span className="text-[11px] font-mono text-slate-400">{sc.duration_seconds}s</span>
                </div>
                <h3 className="text-xs font-bold text-white truncate">{sc.name}</h3>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">{sc.description}</p>
                <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                  <span>{sc.step_count} steps</span>
                  <span>v{sc.version}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Replay Controller & Target Header */}
      <div className="glass-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <label className="text-[11px] text-slate-400 block font-mono mb-1">Target Instance:</label>
              <select
                value={activeInst?.instance_id}
                onChange={(e) => setSelectedInstanceId(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-mono focus:border-blue-500 focus:outline-none"
              >
                {onlineInstances.map((inst) => (
                  <option key={inst.instance_id} value={inst.instance_id}>
                    {inst.variant_id} — {inst.vin_like} ({inst.adb_serial})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[11px] text-slate-400 block font-mono mb-1">Speed Multiplier:</label>
              <div className="flex items-center gap-1.5">
                {[1.0, 2.0, 3.0, 5.0, 10.0].map((s) => (
                  <button
                    key={s}
                    onClick={() => setSpeedFactor(s)}
                    className={`px-2.5 py-1 rounded text-xs font-mono font-semibold transition-all ${
                      speedFactor === s
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    {s}x
                  </button>
                ))}
              </div>
            </div>
          </div>

          <button
            onClick={handleRunReplay}
            disabled={isReplaying || !activeInst}
            className="btn-primary py-2.5 px-6 text-sm"
          >
            {isReplaying ? (
              <>
                <Clock className="w-4 h-4 animate-spin text-white" />
                <span>Replaying {activeScenarioId} on Cockpit...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Start Deterministic Replay</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Execution Summary & Trace Log Table */}
      {replayResult && (
        <div className="glass-panel p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-white">
                  Replay Run Completed: {replayResult.scenario_id}
                </h3>
                <span className="text-xs px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 font-mono font-bold">
                  {replayResult.status}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-mono">
                Instance: {replayResult.instance_id} · Speed: {speedFactor}x
              </p>
            </div>

            <div className="flex items-center gap-6 font-mono text-xs">
              <div>
                <span className="text-slate-400">Total Steps: </span>
                <strong className="text-white">{replayResult.step_count}</strong>
              </div>
              <div>
                <span className="text-slate-400">Wall Time: </span>
                <strong className="text-emerald-400">{replayResult.wall_time_seconds}s</strong>
              </div>
            </div>
          </div>

          {/* Trace Events Table (M7 TraceStep Schema) */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">#</th>
                  <th className="py-2.5 px-3">Sim Time</th>
                  <th className="py-2.5 px-3">Phase</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Signal / Target</th>
                  <th className="py-2.5 px-3">Injected Value</th>
                  <th className="py-2.5 px-3">Latency</th>
                  <th className="py-2.5 px-3">VHAL Prop ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {replayResult.trace.map((step, idx) => {
                  const isAction = step.kind === 'ACTION_TRIGGER';
                  const isReverse = step.signal?.includes('SelectedGear') && step.injected_value === 2;

                  return (
                    <tr
                      key={idx}
                      className={`hover:bg-slate-900/40 transition-colors ${
                        isReverse ? 'bg-amber-950/20' : ''
                      }`}
                    >
                      <td className="py-2 px-3 text-slate-500">{step.step_index}</td>
                      <td className="py-2 px-3 text-slate-300">{step.simulated_time_s.toFixed(1)}s</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                          {step.phase}
                        </span>
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                            isAction
                              ? 'bg-purple-950/70 text-purple-300 border border-purple-800/60'
                              : 'bg-blue-950/70 text-blue-300 border border-blue-800/60'
                          }`}
                        >
                          {step.kind || 'SIGNAL'}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-white font-medium truncate max-w-[200px]">
                        {isAction ? step.action : step.signal}
                      </td>
                      <td className="py-2 px-3">
                        <span className="font-bold text-amber-300">
                          {isAction ? String(step.action_value) : String(step.injected_value)}
                        </span>
                      </td>
                      <td className="py-2 px-3">
                        {step.latency_ms !== undefined ? (
                          <span
                            className={`font-semibold ${
                              step.latency_ms < 500 ? 'text-emerald-400' : 'text-red-400'
                            }`}
                          >
                            {step.latency_ms.toFixed(1)} ms
                            {step.latency_ms < 500 && (
                              <span className="text-[10px] text-emerald-500 ml-1">✓</span>
                            )}
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-slate-400">{step.vhal_property_id || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
