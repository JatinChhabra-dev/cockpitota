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
  }
};
