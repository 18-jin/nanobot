"""Provider that proxies prompts through local Codex CLI (OAuth-backed)."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from nanobot.providers.base import LLMProvider, LLMResponse


class CodexCliProvider(LLMProvider):
    def __init__(self, default_model: str = "openai/gpt-5.3-codex"):
        super().__init__(api_key=None, api_base=None)
        self.default_model = default_model

    def _model_arg(self, model: str | None) -> str:
        m = (model or self.default_model).strip()
        if "/" in m:
            return m.split("/", 1)[1]
        return m

    def _build_prompt(self, messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for m in messages[-24:]:
            role = str(m.get("role", "user")).upper()
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(str(x) for x in content)
            lines.append(f"[{role}]\n{content or ''}\n")
        lines.append("\nReply to the latest user request directly.")
        return "\n".join(lines)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        _ = (tools, max_tokens, temperature)
        prompt = self._build_prompt(messages)
        model_name = self._model_arg(model)

        with tempfile.NamedTemporaryFile(prefix="nanobot-codex-", suffix=".txt", delete=False) as tf:
            out_path = Path(tf.name)

        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--model",
            model_name,
            "--output-last-message",
            str(out_path),
            "-",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(prompt.encode("utf-8"))

        if proc.returncode != 0:
            err = (stderr or stdout).decode("utf-8", errors="ignore")
            return LLMResponse(content=f"Error calling Codex CLI: {err.strip()}", finish_reason="error")

        try:
            content = out_path.read_text(encoding="utf-8").strip()
        except Exception:
            content = ""
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass

        if not content:
            content = (stdout or b"").decode("utf-8", errors="ignore").strip()

        return LLMResponse(content=content or "(empty response)")

    def get_default_model(self) -> str:
        return self.default_model
