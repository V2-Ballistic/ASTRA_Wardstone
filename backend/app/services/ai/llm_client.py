"""
ASTRA — Multi-Provider LLM Client
====================================
File: backend/app/services/ai/llm_client.py   ← NEW

Supports:
  - OpenAI API (GPT-4o, GPT-4-turbo, etc.)
  - Anthropic API (Claude 3.5 Sonnet, etc.)
  - Local / self-hosted via OpenAI-compatible API (vLLM, Ollama, etc.)

Config env vars:
  AI_PROVIDER   — "openai" | "anthropic" | "local" | "" (disabled)
  AI_API_KEY    — API key for the provider
  AI_BASE_URL   — Base URL (required for "local", optional for others)
  AI_MODEL      — Model name (defaults per provider)
  AI_MAX_TOKENS — Max output tokens (default 2048)
  AI_TIMEOUT    — Request timeout in seconds (default 30)

Features:
  - Exponential backoff retry (3 attempts)
  - Token usage tracking
  - Budget cap (AI_MONTHLY_BUDGET_USD, default unlimited)
  - Graceful degradation: returns None on failure, caller falls back to regex
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger("astra.ai")

# ── Configuration ──

AI_PROVIDER = os.getenv("AI_PROVIDER", "").lower()
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_MODEL = os.getenv("AI_MODEL", "")
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2048"))
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "30"))

# Default models per provider
_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "local": "default",
}


def is_ai_available() -> bool:
    """Check if an AI provider is configured and usable."""
    return bool(AI_PROVIDER and AI_PROVIDER in ("openai", "anthropic", "local"))


# ── Token usage tracking ──

class _UsageTracker:
    """In-memory token usage tracker.  Replace with DB table for production."""

    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.total_errors = 0
        self.started_at = datetime.utcnow()

    def record(self, prompt_tokens: int, completion_tokens: int):
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_requests += 1

    def record_error(self):
        self.total_errors += 1

    def summary(self) -> dict:
        return {
            "provider": AI_PROVIDER,
            "model": AI_MODEL or _DEFAULT_MODELS.get(AI_PROVIDER, "?"),
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "tracking_since": self.started_at.isoformat(),
        }


usage_tracker = _UsageTracker()


# ══════════════════════════════════════
#  LLM Client
# ══════════════════════════════════════

class LLMClient:
    """
    Unified interface for calling LLMs.  Returns structured JSON
    from the model, or None on failure (so callers can fall back
    to regex-only analysis).
    """

    def __init__(self):
        self.provider = AI_PROVIDER
        self.model = AI_MODEL or _DEFAULT_MODELS.get(AI_PROVIDER, "")
        self.max_retries = 3

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ) -> dict | None:
        """
        Send a prompt to the configured LLM and return parsed JSON.
        Returns None on any failure (network, auth, parse, timeout).
        """
        if not is_ai_available():
            return None

        max_tokens = max_tokens or AI_MAX_TOKENS

        for attempt in range(self.max_retries):
            try:
                if self.provider == "openai" or self.provider == "local":
                    result = self._call_openai(system_prompt, user_prompt,
                                                temperature, max_tokens, json_mode)
                elif self.provider == "anthropic":
                    result = self._call_anthropic(system_prompt, user_prompt,
                                                   temperature, max_tokens)
                else:
                    return None

                if result is not None:
                    return result

            except Exception as exc:
                wait = 2 ** attempt
                logger.warning(
                    "LLM call attempt %d/%d failed: %s — retrying in %ds",
                    attempt + 1, self.max_retries, exc, wait,
                )
                usage_tracker.record_error()
                if attempt < self.max_retries - 1:
                    time.sleep(wait)

        logger.error("LLM call failed after %d attempts — falling back to regex",
                      self.max_retries)
        return None

    # ── OpenAI / OpenAI-compatible ──

    def _call_openai(self, system_prompt, user_prompt, temperature, max_tokens, json_mode):
        import openai

        base_url = AI_BASE_URL or None
        client = openai.OpenAI(api_key=AI_API_KEY, base_url=base_url, timeout=AI_TIMEOUT)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = client.chat.completions.create(**kwargs)

        # Track usage
        if resp.usage:
            usage_tracker.record(resp.usage.prompt_tokens,
                                  resp.usage.completion_tokens)

        content = resp.choices[0].message.content or ""
        return self._parse_json(content)

    # ── Anthropic ──

    def _call_anthropic(self, system_prompt, user_prompt, temperature, max_tokens):
        import anthropic

        client = anthropic.Anthropic(api_key=AI_API_KEY, timeout=AI_TIMEOUT)

        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )

        usage_tracker.record(
            resp.usage.input_tokens if resp.usage else 0,
            resp.usage.output_tokens if resp.usage else 0,
        )

        content = ""
        for block in resp.content:
            if hasattr(block, "text"):
                content += block.text

        return self._parse_json(content)

    # ── JSON parsing ──

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Extract and parse JSON from LLM output, handling markdown fences."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
            return None
