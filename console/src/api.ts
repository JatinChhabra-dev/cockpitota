/**
 * CORA Console API Client
 * Interfaces with FastAPI Fleet Manager (Port 8001 / via Vite Proxy)
 */

export interface VariantConfig {
  id: string;
  name: string;
  avd_name: string;
  display: {
    width: number;
    height: number;
    orientation: string;
    density?: number;
  };
  locale: string;
  feature_flags: Record<string, string>;
  system_props: Record<string, string>;
  description: string;
}

export interface FleetInstance {
  instance_id: string;
  variant_id: string;
  vin_like: string;
  build_tag: string;
  adb_serial?: string;
  adb_port?: number;
  stream_url?: string;
  status: 'STARTING' | 'ONLINE' | 'STOPPING' | 'STOPPED' | 'ERROR';
  pid?: number;
  created_at: string;
  boot_time_seconds?: number;
  properties: Record<string, string>;
  last_screenshot?: string;
}

export interface ScenarioMeta {
  scenario_id: string;
  name: string;
  description: string;
  version: string;
  duration_seconds: number;
  step_count: number;
}

export interface TraceStep {
  instance_id: string;
  scenario_id: string;
  step_index: number;
  simulated_time_s: number;
  timestamp: number;
  phase: string;
  description?: string;
  kind?: string;
  signal?: string;
  injected_value?: any;
  latency_ms?: number;
  vhal_property_id?: number;
  action?: string;
  action_value?: any;
}

export interface ReplayResponse {
  scenario_id: string;
  instance_id: string;
  status: string;
  step_count: number;
  wall_time_seconds: number;
  trace: TraceStep[];
}

export interface RolloutGroup {
  group_index: number;
  name: string;
  percentage: number;
  target_vehicle_ids: string[];
  status: string;
  success_threshold_pct: number;
  installed_count: number;
  deferred_count: number;
  failed_count: number;
}

export interface OtaCampaign {
  campaign_id: string;
  release_id: string;
  apk_filename: string;
  package_name: string;
  target_version: string;
  artefact_sha256: string;
  hawkbit_rollout_id?: string;
  hawkbit_mode: string;
  status: string;
  groups: RolloutGroup[];
  created_at: string;
  updated_at: string;
}

export interface UpdateRecord {
  record_id: string;
  vehicle_id: string;
  vin_like: string;
  variant_id: string;
  campaign_id: string;
  release_id: string;
  group_index: number;
  pre_versions: Record<string, string>;
  post_versions: Record<string, string>;
  agent_state: string;
  outcome: string;
  defer_reasons: string[];
  failure_reason?: string;
  artefact_sha256?: string;
  signature_verified: boolean;
  started_at: string;
  ended_at?: string;
}

export interface OtaVehicle {
  vehicle_id: string;
  vin_like: string;
  variant_id: string;
  adb_serial?: string;
  mode: string;
  current_versions: Record<string, string>;
  preconditions: {
    gear: number;
    speed_ms: number;
    parking_brake: boolean;
    soc_percent: number;
    passed: boolean;
    defer_reasons: string[];
  };
}

export interface M5TestResult {
  result_id: string;
  run_id: string;
  test_id: string;
  suite: string;
  scenario_id: string;
  status: 'pass' | 'fail' | 'flaky' | 'skipped';
  message: string;
  timing_ms?: number;
  retries: number;
  evidence_uris: string[];
}

export interface M5RunRecord {
  run_id: string;
  release_id: string;
  variant_id: string;
  instance_id: string;
  adb_serial: string;
  scenarios: string[];
  status: string;
  started_at: string;
  ended_at?: string;
  wall_time_seconds: number;
  compute_minutes: number;
  cost_usd: number;
  results: M5TestResult[];
  junit_xml_path?: string;
  trace_json_path?: string;
}

export interface M5Difference {
  diff_id: string;
  baseline_run: string;
  candidate_run: string;
  variant_id: string;
  step: string;
  kind: string;
  diff_class: 'declared' | 'cosmetic' | 'unexplained';
  change_id?: string;
  ui_id?: string;
  baseline_value?: any;
  candidate_value?: any;
  detail: string;
  evidence_uris: string[];
}

export interface M5EquivalenceReport {
  release_id: string;
  baseline_release_id: string;
  generated_at: string;
  variants_compared: string[];
  summary: {
    declared: number;
    cosmetic: number;
    unexplained: number;
    total: number;
  };
  differences: M5Difference[];
}

export interface M5GateDecision {
  gate_id: string;
  release_id: string;
  baseline_release_id: string;
  variant_id: string;
  outcome: 'PASS' | 'BLOCK';
  reasons: string[];
  rxswin_impact: boolean;
  rxswin_components: string[];
  failed_tests: string[];
  unexplained_diff_ids: string[];
  decided_at: string;
}

export interface M5GateBundle {
  release_id: string;
  baseline_release_id: string;
  overall_outcome: 'PASS' | 'BLOCK';
  ota_eligible: boolean;
  rxswin_impact: boolean;
  decided_at: string;
  variants: M5GateDecision[];
  equivalence_summary: {
    declared: number;
    cosmetic: number;
    unexplained: number;
    total: number;
  };
}

export interface AiTestProposal {
  proposal_id: string;
  release_id: string;
  origin: string;
  title: string;
  suite: string;
  scenario_ref: string;
  target_variants: string[];
  linked_change_id?: string;
  rationale: string;
  runner_yaml: string;
  status: 'PENDING_REVIEW' | 'APPROVED' | 'EDITED' | 'REJECTED';
  approved_by?: string;
  approved_at?: string;
  reviewer_notes?: string;
  ai_record_id: string;
}

export interface AiRecord {
  ai_id: string;
  task: string;
  model: string;
  provider: string;
  prompt_version: string;
  input_hash: string;
  latency_ms: number;
  output: any;
  reviewer?: string;
  decision: string;
  created_at: string;
}

export interface M7ReleaseSummary {
  release_id: string;
  description: string;
  app_versions: string[];
  created_by: string;
  created_at: string;
  gate_outcome: string;
  ota_eligible: boolean;
  rxswin_impact: boolean;
  recorded_variant_runs: string[];
}

export interface M7Metrics {
  measured_avg_boot_seconds: number;
  measured_avg_run_wall_seconds: number;
  measured_avg_cost_per_run_usd: number;
  measured_total_compute_cost_usd: number;
  total_runs_recorded: number;
  total_ai_records: number;
  total_ota_ledger_records: number;
  total_screenshots_captured: number;
}

const BASE_URL = ''; // Relative via Vite proxy

export const api = {
  async getHealth() {
    const res = await fetch(`${BASE_URL}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return res.json();
  },

  async getVariants(): Promise<Record<string, VariantConfig>> {
    const res = await fetch(`${BASE_URL}/v1/fleet/variants`);
    if (!res.ok) throw new Error('Failed to load variants');
    const data = await res.json();
    return data.variants;
  },

  async getInstances(): Promise<FleetInstance[]> {
    const res = await fetch(`${BASE_URL}/v1/fleet/instances`);
    if (!res.ok) throw new Error('Failed to load instances');
    const data = await res.json();
    return data.instances || [];
  },

  async launchInstance(variant_id: string, build_tag = 'v1.0', count = 1): Promise<{ instances: FleetInstance[] }> {
    const res = await fetch(`${BASE_URL}/v1/fleet/instances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variant_id, build_tag, count })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to launch instance');
    }
    return res.json();
  },

  async stopInstance(instanceId: string): Promise<boolean> {
    const res = await fetch(`${BASE_URL}/v1/fleet/instances/${instanceId}`, {
      method: 'DELETE'
    });
    return res.status === 204 || res.ok;
  },

  async captureScreenshot(instanceId: string): Promise<{ path: string; filename: string; instance_id: string }> {
    const res = await fetch(`${BASE_URL}/v1/fleet/instances/${instanceId}/screenshot`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Screenshot capture failed');
    }
    return res.json();
  },

  async injectSignal(instanceId: string, vss_path: string, value: any): Promise<any> {
    const res = await fetch(`${BASE_URL}/v1/fleet/instances/${instanceId}/signals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vss_path, value })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Signal injection failed');
    }
    return res.json();
  },

  async getScenarios(): Promise<ScenarioMeta[]> {
    const res = await fetch(`${BASE_URL}/v1/scenarios`);
    if (!res.ok) throw new Error('Failed to load scenarios');
    return res.json();
  },

  async getScenario(id: string): Promise<any> {
    const res = await fetch(`${BASE_URL}/v1/scenarios/${id}`);
    if (!res.ok) throw new Error(`Scenario ${id} not found`);
    return res.json();
  },

  async replayScenario(scenarioId: string, instanceId: string, speedFactor = 2.0, adbSerial?: string): Promise<ReplayResponse> {
    const res = await fetch(`${BASE_URL}/v1/scenarios/${scenarioId}/replay`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instance_id: instanceId,
        speed_factor: speedFactor,
        adb_serial: adbSerial
      })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Replay execution failed');
    }
    return res.json();
  },

  // --- Module 4: OTA Rollout & R156 Ledger ---
  async getOtaVehicles(mode: 'live' | 'all' = 'live'): Promise<{ vehicles: OtaVehicle[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/vehicles?mode=${mode}`);
    if (!res.ok) throw new Error('Failed to load OTA vehicles');
    return res.json();
  },

  async setVehicleState(
    vehicleId: string,
    state: { gear?: string; speed_kmh?: number; parking_brake?: boolean; soc_percent?: number }
  ): Promise<any> {
    const res = await fetch(`${BASE_URL}/v1/vehicles/${vehicleId}/state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state)
    });
    if (!res.ok) throw new Error('Failed to update vehicle state');
    return res.json();
  },

  async getVehicleLedger(vehicleId: string): Promise<{ vehicle_id: string; records: UpdateRecord[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/vehicles/${vehicleId}/ledger`);
    if (!res.ok) throw new Error('Failed to load vehicle ledger');
    return res.json();
  },

  async getCampaigns(): Promise<{ hawkbit_live: boolean; campaigns: OtaCampaign[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/campaigns`);
    if (!res.ok) throw new Error('Failed to load OTA campaigns');
    return res.json();
  },

  async getCampaignDetail(campaignId: string): Promise<{ campaign: OtaCampaign; records: UpdateRecord[] }> {
    const res = await fetch(`${BASE_URL}/v1/campaigns/${campaignId}`);
    if (!res.ok) throw new Error('Failed to load campaign detail');
    return res.json();
  },

  async createCampaign(payload: {
    release_id: string;
    apk_filename: string;
    target_version: string;
    target_mode?: 'live' | 'virtual10';
    gate_passed?: boolean;
    tamper_test?: boolean;
    auto_start?: boolean;
  }): Promise<{ campaign: OtaCampaign; records: UpdateRecord[] }> {
    const res = await fetch(`${BASE_URL}/v1/campaigns`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gate_passed: true, auto_start: true, target_mode: 'live', ...payload })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Campaign creation failed');
    }
    return res.json();
  },

  async campaignAction(campaignId: string, action: 'tick' | 'pause' | 'resume' | 'cancel'): Promise<{ campaign: OtaCampaign; records: UpdateRecord[] }> {
    const res = await fetch(`${BASE_URL}/v1/campaigns/${campaignId}/${action}`, { method: 'POST' });
    if (!res.ok) throw new Error(`Campaign ${action} failed`);
    return res.json();
  },

  // --- Module 5: Test Runner, Equivalence Differ & Release Gate ---
  async getRuns(releaseId?: string): Promise<{ runs: M5RunRecord[]; total: number }> {
    const q = releaseId ? `?release_id=${encodeURIComponent(releaseId)}` : '';
    const res = await fetch(`${BASE_URL}/v1/runs${q}`);
    if (!res.ok) throw new Error('Failed to load test runs');
    return res.json();
  },

  async startRuns(releaseId: string, scenarios = ['SC-01', 'SC-02', 'SC-03', 'SC-04']): Promise<{ release_id: string; runs: M5RunRecord[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ release_id: releaseId, scenarios })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Test run failed');
    }
    return res.json();
  },

  async getEquivalence(releaseId: string, baseline = 'v1.0'): Promise<M5EquivalenceReport> {
    const res = await fetch(`${BASE_URL}/v1/releases/${encodeURIComponent(releaseId)}/equivalence?baseline=${encodeURIComponent(baseline)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Equivalence report unavailable');
    }
    return res.json();
  },

  async evaluateGate(releaseId: string, baseline = 'v1.0'): Promise<M5GateBundle> {
    const res = await fetch(`${BASE_URL}/v1/releases/${encodeURIComponent(releaseId)}/gate?baseline=${encodeURIComponent(baseline)}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Gate evaluation failed');
    }
    return res.json();
  },

  // --- Module 6: AI Layer & Human Review Queue ---
  async getAiStatus(): Promise<{ enabled: boolean; provider: string; model: string; records_count: number; proposals_count: number }> {
    const res = await fetch(`${BASE_URL}/v1/ai/status`);
    if (!res.ok) throw new Error('Failed to load AI status');
    return res.json();
  },

  async toggleAi(enabled: boolean): Promise<{ enabled: boolean }> {
    const res = await fetch(`${BASE_URL}/v1/ai/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    if (!res.ok) throw new Error('Failed to toggle AI layer');
    return res.json();
  },

  async generateProposals(releaseId: string): Promise<{ release_id: string; proposals: AiTestProposal[]; ai_record: AiRecord }> {
    const res = await fetch(`${BASE_URL}/v1/releases/${encodeURIComponent(releaseId)}/ai/test-proposals`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Test proposal generation failed');
    }
    return res.json();
  },

  async getProposals(): Promise<{ proposals: AiTestProposal[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/test-proposals`);
    if (!res.ok) throw new Error('Failed to load test proposals');
    return res.json();
  },

  async reviewProposal(proposalId: string, decision: 'approve' | 'reject', reviewer = 'QA Lead', notes?: string): Promise<AiTestProposal> {
    const res = await fetch(`${BASE_URL}/v1/test-proposals/${proposalId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, reviewer, notes })
    });
    if (!res.ok) throw new Error('Failed to submit review decision');
    return res.json();
  },

  async runAiTriage(releaseId = 'v1.1', variantId = 'VAR-B'): Promise<{ ai_record: AiRecord; bundle_summary: any }> {
    const res = await fetch(`${BASE_URL}/v1/ai/triage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ release_id: releaseId, variant_id: variantId })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'AI triage failed');
    }
    return res.json();
  },

  async getAiRecords(): Promise<{ records: AiRecord[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/ai/records`);
    if (!res.ok) throw new Error('Failed to load AI audit records');
    return res.json();
  },

  // --- Module 7: Releases, Metrics & UNECE R156 Dossier ---
  async getReleases(): Promise<{ releases: M7ReleaseSummary[]; total: number }> {
    const res = await fetch(`${BASE_URL}/v1/releases`);
    if (!res.ok) throw new Error('Failed to load releases');
    return res.json();
  },

  async getMetrics(): Promise<M7Metrics> {
    const res = await fetch(`${BASE_URL}/v1/metrics`);
    if (!res.ok) throw new Error('Failed to load measured metrics');
    return res.json();
  },

  async getDossierJson(releaseId: string, reviewer = 'Homologation Reviewer'): Promise<any> {
    const res = await fetch(
      `${BASE_URL}/v1/releases/${encodeURIComponent(releaseId)}/dossier?format=json&reviewer=${encodeURIComponent(reviewer)}`
    );
    if (!res.ok) throw new Error('Failed to generate dossier');
    return res.json();
  },

  getDossierExportUrl(releaseId: string, format: 'html' | 'pdf' | 'json', reviewer = 'Homologation Reviewer'): string {
    return `${BASE_URL}/v1/releases/${encodeURIComponent(releaseId)}/dossier?format=${format}&reviewer=${encodeURIComponent(reviewer)}`;
  }
};
