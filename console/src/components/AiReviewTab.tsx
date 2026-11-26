import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileText,
  RefreshCw,
  Power,
  Cpu,
} from 'lucide-react';
import { AiRecord, AiTestProposal, api } from '../api';

export const AiReviewTab: React.FC = () => {
  const [aiEnabled, setAiEnabled] = useState<boolean>(true);
  const [modelInfo, setModelInfo] = useState<string>('cora-rule-engine-v1');
  const [proposals, setProposals] = useState<AiTestProposal[]>([]);
  const [records, setRecords] = useState<AiRecord[]>([]);
  const [latestTriage, setLatestTriage] = useState<AiRecord | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [toast, setToast] = useState<string | null>(null);

  const notify = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const refreshAll = async () => {
    try {
      const [st, pr, rc] = await Promise.all([
        api.getAiStatus(),
        api.getProposals(),
        api.getAiRecords(),
      ]);
      setAiEnabled(st.enabled);
      setModelInfo(`${st.provider} / ${st.model}`);
      setProposals(pr.proposals || []);
      setRecords(rc.records || []);
      const tri = [...(rc.records || [])].reverse().find((r) => r.task === 'FAILURE_TRIAGE') || null;
      if (tri) setLatestTriage(tri);
    } catch (err) {
      console.error('AI tab load error:', err);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  const handleToggleAi = async () => {
    try {
      const res = await api.toggleAi(!aiEnabled);
      setAiEnabled(res.enabled);
      notify(res.enabled ? 'AI Copilot ENABLED' : 'AI Copilot DISABLED (M5 Release Gate remains 100% functional)');
    } catch (err: any) {
      notify(`Toggle error: ${err.message}`);
    }
  };

  const handleGenerate = async () => {
    try {
      setBusy(true);
      const res = await api.generateProposals('v1.1');
      notify(`Generated ${res.proposals.length} test proposals from release_notes_v1.1.yaml!`);
      await refreshAll();
    } catch (err: any) {
      notify(`Generate error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleReview = async (proposalId: string, decision: 'approve' | 'reject') => {
    try {
      setBusy(true);
      await api.reviewProposal(proposalId, decision, 'QA Lead');
      notify(`Proposal ${proposalId} marked ${decision.toUpperCase()}D`);
      await refreshAll();
    } catch (err: any) {
      notify(`Review error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleRunTriage = async () => {
    try {
      setBusy(true);
      const res = await api.runAiTriage('v1.1', 'VAR-B');
      setLatestTriage(res.ai_record);
      notify(`AI Triage completed for ${res.bundle_summary.run_id} (VAR-B)`);
      await refreshAll();
    } catch (err: any) {
      notify(`Triage error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#13294C] border border-[#2E74C9] text-white px-4 py-2.5 rounded-xl shadow-2xl text-xs font-medium flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span>{toast}</span>
        </div>
      )}

      {/* Top AI Layer Control Bar */}
      <div className="glass-panel p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-400" />
              AI Review Queue &amp; Failure Triage (M6)
            </h2>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-blue-300">
              {modelInfo}
            </span>
          </div>
          <p className="text-xs text-slate-400">
            AI assists, never decides: engineers approve proposed tests before execution, and every prompt + hash is logged to evidence.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={handleToggleAi}
            className={`text-xs py-1.5 px-3 rounded-lg font-mono font-semibold flex items-center gap-1.5 border ${
              aiEnabled ? 'badge-online' : 'badge-error'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            AI: {aiEnabled ? 'ENABLED' : 'DISABLED'}
          </button>

          <button onClick={refreshAll} className="btn-secondary text-xs py-1.5 px-3">
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
            Refresh
          </button>

          <button onClick={handleGenerate} disabled={busy || !aiEnabled} className="btn-primary text-xs py-1.5 px-3.5">
            <Sparkles className="w-3.5 h-3.5" />
            Propose Tests (v1.1)
          </button>

          <button onClick={handleRunTriage} disabled={busy || !aiEnabled} className="btn-secondary text-xs py-1.5 px-3.5 hover:border-blue-400">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            Triage VAR-B Failure
          </button>
        </div>
      </div>

      {/* Latest AI Failure Triage Card (Demo Beat 5 — M6-FR3) */}
      {latestTriage && (
        <div className="glass-panel p-5 border-amber-500/30 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              AI Failure Triage — {latestTriage.output?.variant_id || 'VAR-B'} ({latestTriage.output?.run_id || 'M5 Evidence'})
            </h3>
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full badge-error">
              Confidence: {Math.round((latestTriage.output?.confidence || 0.95) * 100)}%
            </span>
          </div>

          <div className="bg-slate-900/80 rounded-xl p-4 border border-slate-800 space-y-2 text-xs">
            <div>
              <span className="text-slate-400 font-semibold">Likely Cause: </span>
              <span className="text-white font-medium">{latestTriage.output?.likely_cause}</span>
            </div>
            <div className="flex flex-wrap gap-6 font-mono text-[11px] pt-1">
              <span className="text-slate-400">
                Component: <strong className="text-blue-300">{latestTriage.output?.affected_component}</strong>
              </span>
              <span className="text-slate-400">
                Suggested Owner: <strong className="text-emerald-400">{latestTriage.output?.suggested_owner}</strong>
              </span>
            </div>
            {latestTriage.output?.logcat_reference && (
              <div className="bg-slate-950 rounded-lg p-2.5 font-mono text-[11px] text-red-400 border border-slate-800">
                Logcat: {latestTriage.output.logcat_reference}
              </div>
            )}
            {latestTriage.output?.screenshot_uri && (
              <div className="text-[11px] font-mono text-slate-400">
                Screenshot Evidence: <span className="text-slate-200">{latestTriage.output.screenshot_uri}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Test Proposals Human Review Queue (Demo Beat 2 — M6-FR1 & M6-FR2) */}
      <div className="glass-panel p-5 space-y-4">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <FileText className="w-4 h-4 text-blue-400" />
            AI Test Proposals — Human Review Queue ({proposals.length})
          </h3>
          <p className="text-xs text-slate-400">
            Generated from <code>apps/release_notes_v1.1.yaml</code>. Proposals remain gated until an engineer clicks Approve.
          </p>
        </div>

        {proposals.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-8 text-center text-slate-400 text-xs">
            Click <strong>Propose Tests (v1.1)</strong> above to generate test proposals from the v1.1 release notes.
          </div>
        ) : (
          <div className="space-y-3">
            {proposals.map((p) => (
              <div key={p.proposal_id} className="bg-slate-900/70 rounded-xl p-4 border border-slate-800 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 font-bold">
                      {p.scenario_ref}
                    </span>
                    <span className="text-sm font-semibold text-white">{p.title}</span>
                    {p.linked_change_id && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        {p.linked_change_id}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        p.status === 'APPROVED' || p.status === 'EDITED'
                          ? 'badge-online'
                          : p.status === 'REJECTED'
                          ? 'badge-error'
                          : 'badge-starting'
                      }`}
                    >
                      {p.status}
                    </span>

                    {p.status === 'PENDING_REVIEW' && (
                      <>
                        <button
                          onClick={() => handleReview(p.proposal_id, 'approve')}
                          disabled={busy}
                          className="btn-primary text-[11px] py-1 px-2.5"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          Approve
                        </button>
                        <button
                          onClick={() => handleReview(p.proposal_id, 'reject')}
                          disabled={busy}
                          className="btn-danger text-[11px] py-1 px-2.5"
                        >
                          <XCircle className="w-3 h-3" />
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <p className="text-xs text-slate-400">{p.rationale}</p>
                <pre className="bg-slate-950 rounded-lg p-2.5 text-[11px] font-mono text-slate-300 border border-slate-800 overflow-y-auto">
                  {p.runner_yaml}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Auditable AIRecord Trail (M6-FR5) */}
      <div className="glass-panel p-5">
        <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-cyan-400" />
          AI Evidence Audit Log ({records.length} Records · evidence/ai_records.json)
        </h3>
        <div className="overflow-y-auto max-h-[240px] rounded-lg border border-slate-800">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-900 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-2.5">AI Record ID</th>
                <th className="p-2.5">Task</th>
                <th className="p-2.5">Model / Prompt</th>
                <th className="p-2.5">Input SHA-256</th>
                <th className="p-2.5">Decision</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.ai_id} className="border-b border-slate-800/60">
                  <td className="p-2.5 text-white">{r.ai_id}</td>
                  <td className="p-2.5 text-blue-300">{r.task}</td>
                  <td className="p-2.5 text-slate-300">{r.model} ({r.prompt_version})</td>
                  <td className="p-2.5 text-slate-400">{r.input_hash.slice(0, 16)}…</td>
                  <td className="p-2.5 text-emerald-400">{r.decision}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
