"""Central configuration: paths, model constants, domain priors."""
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Does not override existing env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

CASES_CSV       = DATA_DIR / "missing_persons.csv"
ZONES_CSV       = DATA_DIR / "zones.csv"
CAMERAS_CSV     = DATA_DIR / "cctv_locations.csv"
CCTV_KML        = DATA_DIR / "cctv.kml"
CHOKEPOINTS_KML = DATA_DIR / "chokepoints.kml"
POLICE_KML      = DATA_DIR / "police_stations.kml"

# ── Crowd movement model (dense Kumbh crowd) ──────────────────────────────────
RESPONDER_SPEED_MPS = 0.7      # volunteer pushing through crowd
WANDER_SPEED_MPS    = 0.4      # a lost child drifting
CROWD_PATH_FACTOR   = 1.4      # real walk dist vs straight-line

# ── Geographic sanity bounds (Nashik); drops bad coordinates ──────────────────
LAT_MIN, LAT_MAX = 19.85, 20.15

# ── Domain priors ─────────────────────────────────────────────────────────────
HIGH_RISK_LOCATIONS = {
    "Ramkund Ghat", "Panchavati Circle", "Kushavart Kund", "Gauri Patangan",
    "Dasak Ghat", "Nandur Ghat", "Laxmi Narayan Ghat",
}
# Highest-volume case days in the historic data (proxy for Shahi Snan)
SHAHI_SNAN_DATES = {"2027-07-29", "2027-08-08"}

# ── Reasoning LLM ─────────────────────────────────────────────────────────────
# Provider selection: auto picks anthropic > openai-compatible > none.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto")     # auto|anthropic|openai|mock

# Anthropic (Claude) backend
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL   = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

# OpenAI-compatible backend (DeepSeek V4 / self-hosted vLLM / OpenRouter)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL    = os.environ.get("LLM_MODEL", "deepseek-chat")
LLM_API_KEY  = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")

# LLM_MOCK=1 routes the reasoning layer to a deterministic stub (offline testing).
LLM_MOCK     = bool(os.environ.get("LLM_MOCK"))
