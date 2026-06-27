"""#4/#5 — LLM reasoning layer. Emits the fixed `Signal` schema.

The LLM is used for REASONING ONLY:
  - data shaping/validation is done upstream in preprocess.py (deterministic)
  - prompts are templates in findflow/prompts/, filled in Python
  - the model returns a small fixed JSON (tier + two-line description + actions);
    it is validated before it can affect a decision
  - it can only RAISE urgency above the deterministic floor, never lower it
  - any failure (no key / network / malformed output) -> safe floor fallback

Backends (selected at call time): mock > anthropic > openai-compatible > none.
"""
import json
import urllib.request

from . import config as C
from . import mock_llm
from . import prompts
from .alerting import (ESCALATION_ACTIONS, RANK_TIER, TIER_RANK, floor_tier,
                       risk_to_severity)
from .schema import Signal, TriageInput, VALID_TIERS


# ── helpers ───────────────────────────────────────────────────────────────────
def _strip_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0]
    return t.strip()


def _two_lines(text: str) -> str:
    """Normalize a description to exactly two non-empty lines."""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return "No description provided.\n—"
    if len(lines) == 1:
        return lines[0] + "\n—"
    return lines[0] + "\n" + " ".join(lines[1:])


# ── backends ──────────────────────────────────────────────────────────────────
def _chat(system: str, user: str, max_tokens: int = 500, temperature: float = 0.2):
    """OpenAI-compatible chat (DeepSeek V4 / vLLM / OpenRouter)."""
    if not C.LLM_API_KEY:
        return None
    body = {"model": C.LLM_MODEL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request(
        f"{C.LLM_BASE_URL}/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {C.LLM_API_KEY}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(json.loads(r.read())["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"    [OpenAI-compat error -> floor fallback: {type(e).__name__}: {e}]")
        return None


def _anthropic_chat(system: str, user: str, max_tokens: int = 600):
    """Claude Messages API. No `temperature` (rejected by Opus 4.7/4.8)."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=C.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=C.ANTHROPIC_MODEL, max_tokens=max_tokens,
            system=system, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return json.loads(_strip_json(text))
    except Exception as e:
        print(f"    [Anthropic error -> floor fallback: {type(e).__name__}: {e}]")
        return None


def _backend():
    if C.LLM_MOCK or C.LLM_PROVIDER == "mock":
        return mock_llm.mock_chat
    if C.LLM_PROVIDER in ("auto", "anthropic") and C.ANTHROPIC_API_KEY:
        return _anthropic_chat
    if C.LLM_PROVIDER in ("auto", "openai") and C.LLM_API_KEY:
        return _chat
    return None


def active_model() -> str:
    b = _backend()
    if b is mock_llm.mock_chat:
        return "mock"
    if b is _anthropic_chat:
        return C.ANTHROPIC_MODEL
    if b is _chat:
        return C.LLM_MODEL
    return "none"


def backend_mode() -> str:
    b = _backend()
    if b is mock_llm.mock_chat:
        return "MOCK"
    if b is _anthropic_chat:
        return f"LIVE(anthropic:{C.ANTHROPIC_MODEL})"
    if b is _chat:
        return f"LIVE(openai:{C.LLM_MODEL})"
    return "FALLBACK"


# ── output validation ─────────────────────────────────────────────────────────
def _valid_triage_output(d) -> bool:
    return (isinstance(d, dict)
            and d.get("urgency_tier") in VALID_TIERS
            and isinstance(d.get("description"), str) and d["description"].strip()
            and isinstance(d.get("actions", []), list))


# ── #4 triage  ->  Signal(type="alert") ───────────────────────────────────────
def triage(inp: TriageInput) -> Signal:
    floor = floor_tier(inp.age_band, inp.mins_open, inp.high_risk_ctx)
    backend = _backend()
    out = backend(
        prompts.load("triage_system.txt"),
        prompts.render("triage_user.txt",
                       floor_tier=floor, age_band=inp.age_band,
                       mins_open=int(inp.mins_open),
                       last_seen_location=inp.last_seen_location,
                       high_risk_ctx=inp.high_risk_ctx,
                       physical_description=inp.physical_description,
                       has_phone=inp.has_phone, language=inp.language,
                       status=inp.status,
                       warnings="; ".join(inp.warnings) or "none"),
    ) if backend else None

    if not _valid_triage_output(out):
        action = (ESCALATION_ACTIONS[floor] if floor in ESCALATION_ACTIONS
                  else "routine cross-booth search")
        return Signal(
            type="alert", ref=inp.case_id, severity=floor,
            description=_two_lines(
                f"Deterministic floor applied at {floor} (no LLM judgement available).\n"
                f"Handle per {floor} protocol and verify at the booth."),
            actions=[action], confidence=1.0, min_tier=floor, raised=False,
            model=active_model(), warnings=inp.warnings)

    final_rank = max(TIER_RANK[floor], TIER_RANK[out["urgency_tier"]])
    severity = RANK_TIER[final_rank]
    return Signal(
        type="alert", ref=inp.case_id, severity=severity,
        description=_two_lines(out["description"]),
        actions=out.get("actions", []),
        confidence=float(out.get("confidence", 0.0) or 0.0),
        min_tier=floor, raised=final_rank > TIER_RANK[floor],
        model=active_model(), warnings=inp.warnings)


# ── #5 predictive alarm  ->  Signal(type="prediction") ────────────────────────
def alarm_signal(zone_name: str, risk_score: float, live_signals: dict) -> Signal:
    severity = risk_to_severity(risk_score)
    backend = _backend()
    desc, actions, conf = None, [], None
    if backend:
        out = backend(
            prompts.load("alarm_system.txt"),
            prompts.render("alarm_user.txt", zone_name=zone_name,
                           risk_score=f"{risk_score:.2f}",
                           live_signals=str(live_signals)))
        if isinstance(out, dict) and isinstance(out.get("description"), str):
            desc, actions, conf = out["description"], out.get("actions", []), out.get("confidence")
    if desc is None:
        desc = (f"Predicted lost-person risk {risk_score:.2f} ({severity}) for {zone_name}.\n"
                f"Pre-position volunteers per the allocation table.")
        conf = 1.0
    return Signal(
        type="prediction", ref=zone_name, severity=severity,
        description=_two_lines(desc), actions=actions,
        confidence=float(conf or 0.0), min_tier=None, raised=False,
        model=active_model())
