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

USE_LIVE_LLM = os.getenv("GREENLIGHT_LIVE_LLM", "0") == "1"


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
