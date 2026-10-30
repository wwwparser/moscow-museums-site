"""LLM access policy for the museum project.

External LLM providers are intentionally unavailable. Admission work is queued
for internal Luna and applied by a separate, evidence-validating script.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ExternalLLMDisabled(RuntimeError):
    pass


def load_env(path=None):
    """Retained as a no-op compatibility function; never reads secrets."""
    return None


def config(provider):
    raise ExternalLLMDisabled(
        f"External LLM provider {provider!r} is disabled; prepare a Luna queue instead"
    )


def extract_json(prompt, provider=None, max_tokens=6000, use_cache=True):
    raise ExternalLLMDisabled(
        "External LLM requests are disabled before network access; use internal Luna"
    )


def choose_provider():
    raise ExternalLLMDisabled(
        "Provider selection and balance checks are disabled; use internal Luna queue"
    )
