"""
Module 4 Artefact Hashing & Cryptographic Signing (Spec §4 M4-FR3).
Generates and verifies SHA-256 digests and HMAC-SHA256 release signatures
(cloud phase swaps key source to Google Cloud KMS).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Tuple

# Local POC signing key (Cloud phase: fetched from Cloud KMS / Secret Manager per Spec §3)
_POC_SIGNING_SECRET = os.environ.get("CORA_OTA_SIGNING_KEY", "ferfier-cora-poc-ota-signing-key-2026").encode("utf-8")


def compute_sha256(file_path: str) -> str:
    """Computes hex-encoded SHA-256 digest of an APK artefact."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_artefact(file_path: str) -> Tuple[str, str]:
    """Returns (sha256_hex, signature_hex) for the given artefact file."""
    digest = compute_sha256(file_path)
    sig = hmac.new(_POC_SIGNING_SECRET, digest.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest, sig


def verify_artefact(file_path: str, expected_sha256: str, expected_signature: str) -> Tuple[bool, str]:
    """
    Verifies both file integrity (SHA-256) and authenticity (signature).
    Implements M4-FR3: Reject artefacts failing hash or signature check with exact reason.
    """
    if not os.path.isfile(file_path):
        return False, f"ARTEFACT_MISSING: File not found at {file_path}"

    actual_sha256 = compute_sha256(file_path)
    if not hmac.compare_digest(actual_sha256.lower(), expected_sha256.lower()):
        return False, f"HASH_MISMATCH: expected={expected_sha256[:16]}... actual={actual_sha256[:16]}..."

    expected_computed_sig = hmac.new(_POC_SIGNING_SECRET, actual_sha256.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_computed_sig.lower(), expected_signature.lower()):
        return False, "SIGNATURE_INVALID: Cryptographic signature verification failed"

    return True, "VERIFIED"
