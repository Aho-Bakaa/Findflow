"""Prompt loading & rendering.

Prompts live as plain-text files under `findflow/prompts/`. Variables are filled
deterministically in Python via `string.Template` ($var syntax) — chosen over
str.format so the JSON braces inside prompts don't need escaping.
"""
from pathlib import Path
from string import Template

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load(name: str) -> str:
    """Load a raw prompt file (e.g. 'triage_system.txt')."""
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def render(name: str, **variables) -> str:
    """Load a template and substitute $variables (missing ones left intact)."""
    return Template(load(name)).safe_substitute(**variables)
