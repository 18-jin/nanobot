"""Helpers for reusing OpenClaw OAuth credentials in nanobot."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_AUTH_PROFILES_PATH = Path("/config/.openclaw/agents/main/agent/auth-profiles.json")


class OpenClawOAuthError(RuntimeError):
    """Raised when OpenClaw OAuth credentials cannot be loaded."""


def load_openai_codex_access_token(auth_profiles_path: str | Path | None = None) -> str:
    """Load OpenAI Codex OAuth access token from OpenClaw auth-profiles store."""
    path = Path(auth_profiles_path) if auth_profiles_path else DEFAULT_AUTH_PROFILES_PATH
    if not path.exists():
        raise OpenClawOAuthError(f"OpenClaw auth profiles not found: {path}")

    try:
        data = json.loads(path.read_text())
    except Exception as e:  # pragma: no cover - defensive
        raise OpenClawOAuthError(f"Failed to read OpenClaw auth profiles: {e}") from e

    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise OpenClawOAuthError("Invalid auth-profiles format: missing profiles")

    # Preferred profile id for OpenAI Codex OAuth in OpenClaw.
    profile = profiles.get("openai-codex:default")
    if not isinstance(profile, dict):
        # Fallback: find any openai-codex profile.
        for value in profiles.values():
            if isinstance(value, dict) and value.get("provider") == "openai-codex":
                profile = value
                break

    if not isinstance(profile, dict):
        raise OpenClawOAuthError("No openai-codex OAuth profile found in OpenClaw auth store")

    token = profile.get("access")
    if not isinstance(token, str) or not token.strip():
        raise OpenClawOAuthError("OpenClaw profile has no access token")

    return token
