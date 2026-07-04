"""Vultr Serverless Inference — OpenAI-compatible chat with deterministic fallback."""
import json
import urllib.error
import urllib.request

from greenlight import config


def chat(messages, *, model=None, max_tokens=512, tools=None):
    """Return assistant message dict {role, content, tool_calls?}. Uses fallback if no key."""
    model = model or config.MODEL_BRAIN
    key = config.inference_key()
    if not key or not config.USE_LIVE_LLM:
        return _fallback(messages, model)
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{config.VULTR_INFERENCE_API}/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, json.JSONDecodeError):
        return _fallback(messages, model)


def _fallback(messages, model):
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    return {
        "role": "assistant",
        "content": f"[offline fallback / {model}] Acknowledged: {user[:120]}…",
    }
