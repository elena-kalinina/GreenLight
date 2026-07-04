"""Paths, env, and model IDs."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LINE_PATH = DATA / "line" / "aw26_line.json"
EVENT_LOG = DATA / "events.jsonl"

VULTR_INFERENCE_API = "https://api.vultrinference.com/v1"

MODEL_BRAIN = "moonshotai/Kimi-K2.6"
MODEL_RAG = "deepseek-ai/DeepSeek-V4-Flash"
MODEL_STRUCTURED = "Qwen/Qwen3.6-27B"


def load_env():
    env = dict(os.environ)
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def inference_key():
    return load_env().get("INFERENCE_API_KEY", "").strip()


def _flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name)
    if v is None:
        v = load_env().get(name, default)
    return str(v).strip() == "1"


def use_live_llm() -> bool:
    return _flag("GREENLIGHT_LIVE_LLM")


def use_agent() -> bool:
    """Agent mode: Kimi tool-calling loop (required for Vultr Statement Two track)."""
    if _flag("GREENLIGHT_AGENT"):
        return True
    return use_live_llm() and bool(inference_key())


# Back-compat alias — prefer use_live_llm()
def USE_LIVE_LLM():
    return use_live_llm()
