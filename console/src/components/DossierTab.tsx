import React, { useState, useEffect } from 'react';
import {
  FileCheck2,
  Download,
  ExternalLink,
  RefreshCw,
  Clock,
  Activity,
  ShieldCheck,
  DollarSign,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { M7Metrics, M7ReleaseSummary, api } from '../api';

export const DossierTab: React.FC = () => {
  const [releases, setReleases] = useState<M7ReleaseSummary[]>([]);
  const [metrics, setMetrics] = useState<M7Metrics | null>(null);
  const [selectedRelease, setSelectedRelease] = useState<string>('v1.1-fix');
  const [reviewer, setReviewer] = useState<string>('Lead Homologation Engineer');
  const [dossier, setDossier] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const loadAll = async () => {
    try {
      const [relRes, metRes] = await Promise.all([api.getReleases(), api.getMetrics()]);
      setReleases(relRes.releases || []);
      setMetrics(metRes);
    } catch (err) {
      console.error('Error loading M7 data:', err);
    }
  };

  const loadPreview = async (rid = selectedRelease) => {
    try {
      setLoading(true);
      const data = await api.getDossierJson(rid, reviewer);
      setDossier(data);
    } catch (err) {
      console.error('Dossier preview error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    loadPreview('v1.1-fix');
  }, []);

  return (
    <div className="space-y-6">
      {/* Measured Metrics Panel (Spec M7-FR7) */}
      {metrics && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="glass-panel p-4">
            <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 mb-1">
              <Clock className="w-3.5 h-3.5 text-blue-400" />
              AVG COCKPIT BOOT TIME
            </div>
            <div className="text-2xl font-bold text-white font-mono">{metrics.measured_avg_boot_seconds}s</div>
            <div className="text-[11px] text-slate-500">Measured AAOS cold boot</div>
          </div>

          <div className="glass-panel p-4">
            <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 mb-1">
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              AVG M5 SUITE WALL TIME
            </div>
            <div className="text-2xl font-bold text-emerald-400 font-mono">{metrics.measured_avg_run_wall_seconds}s</div>
            <div className="text-[11px] text-slate-500">{metrics.total_runs_recorded} live runs recorded</div>
          </div>

          <div className="glass-panel p-4">
            <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 mb-1">
              <DollarSign className="w-3.5 h-3.5 text-cyan-400" />
              COST PER RELEASE RUN
            </div>
            <div className="text-2xl font-bold text-cyan-400 font-mono">${metrics.measured_avg_cost_per_run_usd}</div>
            <div className="text-[11px] text-slate-500">Total compute: ${metrics.measured_total_compute_cost_usd}</div>
          </div>

          <div className="glass-panel p-4">
            <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 mb-1">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              EVIDENCE ARTEFACTS
            </div>
            <div className="text-2xl font-bold text-white font-mono">
              {metrics.total_screenshots_captured + metrics.total_ai_records + metrics.total_ota_ledger_records}
            </div>
            <div className="text-[11px] text-slate-500">
              {metrics.total_screenshots_captured} PNGs · {metrics.total_ai_records} AI · {metrics.total_ota_ledger_records} OTA
            </div>
          </div>
        </div>
      )}

      {/* Releases Overview (Spec §10 Releases Screen) */}
      <div className="glass-panel p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <FileCheck2 className="w-4 h-4 text-blue-400" />
            Release Registry &amp; UNECE R156 Dossier Export (M7)
          </h2>
          <button onClick={loadAll} className="btn-secondary text-xs py-1.5 px-3">
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
          {releases.map((rel) => {
            const isSel = selectedRelease === rel.release_id;
            return (
              <div
                key={rel.release_id}
                onClick={() => {
                  setSelectedRelease(rel.release_id);
                  loadPreview(rel.release_id);
                }}
                className={`cursor-pointer rounded-xl p-4 border transition-all ${
                  isSel ? 'bg-[#13294C]/80 border-[#2E74C9] ring-1 ring-blue-500' : 'bg-slate-900/70 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-mono font-bold text-white">{rel.release_id}</span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      rel.gate_outcome === 'PASS' || rel.gate_outcome === 'BASELINE'
                        ? 'badge-online'
                        : rel.gate_outcome === 'BLOCK'
                        ? 'badge-error'
                        : 'badge-stopped'
                    }`}
                  >
                    {rel.gate_outcome}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mb-2">{rel.description}</p>
                <div className="text-[11px] font-mono text-slate-400 flex justify-between">
                  <span>Runs: {rel.recorded_variant_runs.join(', ') || 'none'}</span>
                  {rel.rxswin_impact && <span className="text-amber-400 font-bold">RXSWIN</span>}
                </div>
              </div>
            );
          })}
        </div>

        {/* One-Click Export Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-800">
          <div className="flex items-center gap-2">
            <label className="text-xs font-mono text-slate-400">Reviewer Sign-Off:</label>
            <input
              type="text"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-1.5 text-xs font-mono"
            />
            <button onClick={() => loadPreview(selectedRelease)} disabled={loading} className="btn-secondary text-xs py-1.5 px-3">
              {loading ? 'Assembling...' : 'Rebuild Preview'}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <a
              href={api.getDossierExportUrl(selectedRelease, 'html', reviewer)}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary text-xs py-1.5 px-3"
              style={{ textDecoration: 'none' }}
            >
              <ExternalLink className="w-3.5 h-3.5 text-blue-400" />
              Open HTML Dossier
            </a>
            <a
              href={api.getDossierExportUrl(selectedRelease, 'json', reviewer)}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary text-xs py-1.5 px-3"
              style={{ textDecoration: 'none' }}
            >
              <Download className="w-3.5 h-3.5 text-cyan-400" />
              Export JSON
            </a>
            <a
              href={api.getDossierExportUrl(selectedRelease, 'pdf', reviewer)}
              target="_blank"
              rel="noreferrer"
              className="btn-primary text-xs py-1.5 px-4"
              style={{ textDecoration: 'none' }}
            >
              <Download className="w-3.5 h-3.5" />
              Download R156 PDF
            </a>
          </div>
        </div>
      </div>

      {/* Live 9-Section R156 Dossier Preview */}
      {dossier && (
        <div className="glass-panel p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-800">
            <div>
              <h3 className="text-sm font-bold text-white">
                Dossier Preview — {dossier.release_id} ({dossier.dossier_id})
              </h3>
              <p className="text-[11px] font-mono text-slate-400">
                Integrity SHA-256: <span className="text-emerald-400">{dossier.sha256}</span>
              </p>
            </div>
            <span className="text-[11px] font-mono px-2.5 py-1 rounded-lg bg-blue-950 text-blue-300 border border-blue-800/60">
              All 9 UNECE R156 Sections Populated From Pipeline Records
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            {Object.entries(dossier.sections || {}).map(([key, sec]: [string, any]) => (
              <div key={key} className="bg-slate-900/70 rounded-xl p-3.5 border border-slate-800 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white">{sec.title}</span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <div className="text-[11px] text-blue-300 font-mono">{sec.r156_ref}</div>
                <div className="text-[11px] text-slate-400">
                  {key === '1_release_identification' && `${sec.artefacts?.length || 0} signed APK artefacts with SHA-256 hashes`}
                  {key === '2_purpose_of_update' && `${sec.declared_changes?.length || 0} declared changes from release notes`}
                  {key === '3_affected_systems' && `${sec.components?.length || 0} registered components (APP-1..APP-3)`}
                  {key === '4_approval_impact' && (sec.rxswin_impact ? `RXSWIN IMPACT: ${sec.triggered_components?.join(', ')}` : 'No type-approval impact detected')}
                  {key === '5_compatibility' && `Gate: ${sec.gate_outcome_overall} across ${sec.variants?.length || 0} variants`}
                  {key === '6_verification_evidence' && `${sec.suite_runs?.length || 0} live runs · ${sec.ai_records?.length || 0} AI records`}
                  {key === '7_execution_safeguards' && 'Parked + SoC >= 30% + SHA-256 signing + Rollback'}
                  {key === '8_per_vehicle_records' && `${sec.total_records || 0} R156 per-vehicle update ledger records`}
                  {key === '9_sign_off' && `Reviewer: ${sec.reviewer}`}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
