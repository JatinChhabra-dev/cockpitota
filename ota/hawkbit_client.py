"""
Eclipse hawkBit 1.0 Management API Adapter (Spec §4 M4, §6.1).
Connects to a live Eclipse hawkBit server (http://localhost:8080 from infra/docker-compose.yml)
when running, and transparently mirrors identical campaign state in LOCAL_MIRROR mode if offline.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ota.hawkbit")


class HawkBitAdapter:
    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = (base_url or os.environ.get("HAWKBIT_URL", "http://localhost:8080")).rstrip("/")
        self.username = username or os.environ.get("HAWKBIT_USER", "admin")
        self.password = password or os.environ.get("HAWKBIT_PASS", "admin")
        token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        self._auth_header = f"Basic {token}"

    def _req(self, method: str, path: str, body: Any = None, timeout: float = 3.0) -> Tuple[Optional[Any], int]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth_header)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return (json.loads(raw) if raw else {}), resp.status
        except urllib.error.HTTPError as e:
            return None, e.code
        except Exception:
            return None, 0

    def is_available(self) -> bool:
        """Returns True if live Eclipse hawkBit 1.0 Management API is reachable."""
        _, code = self._req("GET", "/rest/v1/softwaremodules?limit=1", timeout=1.5)
        return code == 200

    def sync_targets(self, vehicles: List[Dict[str, str]]) -> bool:
        """Registers virtual fleet vehicles as hawkBit targets if live server is reachable."""
        if not self.is_available():
            return False
        payload = [
            {
                "controllerId": v["vehicle_id"],
                "name": f"{v['variant_id']} ({v['vin_like']})",
                "description": f"CORA virtual cockpit {v['variant_id']}",
            }
            for v in vehicles
        ]
        _, code = self._req("POST", "/rest/v1/targets", payload)
        return code in (200, 201, 409)

    def create_staged_rollout(
        self,
        campaign_id: str,
        release_id: str,
        package_name: str,
        target_version: str,
        vehicle_ids: List[str],
    ) -> Tuple[str, str]:
        """
        Creates a Software Module, Distribution Set, and 2-group staged Rollout in hawkBit
        when reachable. Returns (hawkbit_rollout_id, mode).
        """
        if not self.is_available():
            logger.info("hawkBit not reachable at %s; using LOCAL_MIRROR mode for %s", self.base_url, campaign_id)
            return f"hb-local-{campaign_id}", "LOCAL_MIRROR"

        try:
            unique_ver = f"{target_version}-{campaign_id[-4:]}"
            # 1. Create Software Module
            sm_res, sm_code = self._req("POST", "/rest/v1/softwaremodules", [{
                "name": package_name,
                "version": unique_ver,
                "type": "application",
                "vendor": "Aurelia Motors",
                "description": f"CORA Release {release_id}",
            }])
            sm_id = sm_res[0]["id"] if sm_code in (200, 201) and isinstance(sm_res, list) and sm_res else None

            # 2. Create Distribution Set
            ds_payload = [{
                "name": f"aurelia-{release_id}",
                "version": unique_ver,
                "type": "app",
                "description": f"CORA Gate-Approved Release {release_id}",
                "modules": [{"id": sm_id}] if sm_id else [],
            }]
            ds_res, ds_code = self._req("POST", "/rest/v1/distributionsets", ds_payload)
            ds_id = ds_res[0]["id"] if ds_code in (200, 201) and isinstance(ds_res, list) and ds_res else None

            if not ds_id:
                return f"hb-local-{campaign_id}", "LOCAL_MIRROR"

            # 3. Create 2-group Rollout (10% canary -> 100% fleet)
            rollout_payload = {
                "name": f"CORA-{campaign_id}-{release_id}",
                "description": f"Staged 10% -> 100% rollout for {release_id}",
                "targetFilterQuery": "controllerId==*",
                "distributionSetId": ds_id,
                "groups": [
                    {
                        "name": "Group 1 (10% Canary)",
                        "targetPercentage": 10.0,
                        "successCondition": {"condition": "THRESHOLD", "expression": "100"},
                        "errorCondition": {"condition": "THRESHOLD", "expression": "50"},
                    },
                    {
                        "name": "Group 2 (100% Fleet)",
                        "targetPercentage": 100.0,
                        "successCondition": {"condition": "THRESHOLD", "expression": "100"},
                        "errorCondition": {"condition": "THRESHOLD", "expression": "50"},
                    },
                ],
            }
            ro_res, ro_code = self._req("POST", "/rest/v1/rollouts", rollout_payload)
            if ro_code in (200, 201) and isinstance(ro_res, dict) and ro_res.get("id"):
                rollout_id = str(ro_res["id"])
                self._req("POST", f"/rest/v1/rollouts/{rollout_id}/start")
                logger.info("Created & started live hawkBit rollout id=%s for %s", rollout_id, campaign_id)
                return rollout_id, "HAWKBIT_LIVE"
        except Exception as exc:
            logger.warning("hawkBit rollout sync failed (%s); falling back to LOCAL_MIRROR", exc)

        return f"hb-local-{campaign_id}", "LOCAL_MIRROR"

    def pause_rollout(self, hawkbit_rollout_id: Optional[str], mode: str):
        if mode == "HAWKBIT_LIVE" and hawkbit_rollout_id:
            self._req("POST", f"/rest/v1/rollouts/{hawkbit_rollout_id}/pause")

    def resume_rollout(self, hawkbit_rollout_id: Optional[str], mode: str):
        if mode == "HAWKBIT_LIVE" and hawkbit_rollout_id:
            self._req("POST", f"/rest/v1/rollouts/{hawkbit_rollout_id}/resume")
