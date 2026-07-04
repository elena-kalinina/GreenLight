#!/usr/bin/env python3
"""Generate the demo voiceover with Gradium TTS.

Reads demo/narration.json (the versioned VO script) and synthesizes audio via
Gradium's REST TTS endpoint (auth: x-api-key). Audio is written to demo/voiceover/
(gitignored — it's a regenerable build artifact).

Usage:
  python3 scripts/gradium_tts.py               # all beats in narration.voice_id -> per-beat WAVs + full.wav
  python3 scripts/gradium_tts.py --voice <id>  # override the voice for this run
  python3 scripts/gradium_tts.py --beat 03_wow # just one beat
  python3 scripts/gradium_tts.py --samples     # synthesize one beat across candidate voices to compare

Never prints the API key.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
NARRATION = ROOT / "demo" / "narration.json"
OUT_DIR = ROOT / "demo" / "voiceover"
TTS_URL = "https://api.gradium.ai/api/post/speech/tts"

# A curated shortlist of Gradium flagship voices for the narrator A/B test.
CANDIDATE_VOICES = {
    "john_us_m": ("KWJiFWu2O9nMPYcR", "Warm low-pitched US male, classic radio broadcaster"),
    "emma_us_f": ("YTpq7expH9539ERJ", "Pleasant smooth US female"),
    "sydney_us_f": ("jtEKaLYNn6iif5PR", "Joyful airy US female, corporate-friendly"),
    "eva_gb_f": ("ubuXFxVQwVYnZQhy", "Lively British female"),
    "jack_gb_m": ("m86j6D7UZpGzHsNu", "Pleasant British male, good for narration"),
}


def load_key():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("GRADIUM_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("GRADIUM_API_KEY not found in .env")


def synth(api_key, text, voice_id, output_format="wav"):
    body = json.dumps({
        "text": text, "voice_id": voice_id,
        "output_format": output_format, "only_audio": True,
    }).encode()
    req = urllib.request.Request(
        TTS_URL, data=body, method="POST",
        headers={"x-api-key": api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            ctype = r.headers.get("Content-Type", "")
            data = r.read()
            if "audio" not in ctype:
                raise RuntimeError(f"unexpected content-type {ctype}: {data[:160]!r}")
            return data
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]!r}")


def concat_wavs(paths, out_path, gap_seconds=0.45):
    """Stitch same-format WAVs into one, with a short silence between beats.

    Gradium's WAVs carry a placeholder frame count (2^31-1) in the header, so we
    set the output format fresh and let writeframes recompute the true length.
    """
    with wave.open(str(paths[0]), "rb") as w0:
        nch, sw, fr = w0.getnchannels(), w0.getsampwidth(), w0.getframerate()
    silence = b"\x00" * (int(fr * gap_seconds) * sw * nch)
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(nch)
        out.setsampwidth(sw)
        out.setframerate(fr)
        for i, p in enumerate(paths):
            with wave.open(str(p), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            if i != len(paths) - 1:
                out.writeframes(silence)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", help="override voice_id")
    ap.add_argument("--beat", help="synthesize only this beat id")
    ap.add_argument("--samples", action="store_true",
                    help="synthesize the wow beat across candidate voices for comparison")
    args = ap.parse_args()

    api_key = load_key()
    cfg = json.loads(NARRATION.read_text())
    fmt = cfg.get("output_format", "wav")

    if args.samples:
        sample_dir = OUT_DIR / "samples"
        sample_dir.mkdir(parents=True, exist_ok=True)
        wow = next(b for b in cfg["beats"] if b["id"] == "03_wow")
        print("Synthesizing the '03_wow' beat in each candidate voice:\n")
        for name, (vid, desc) in CANDIDATE_VOICES.items():
            audio = synth(api_key, wow["text"], vid, fmt)
            out = sample_dir / f"{name}.{fmt}"
            out.write_bytes(audio)
            print(f"  {out}  ({len(audio):,} bytes) — {desc}")
        print("\nListen, then set \"voice_id\" in demo/narration.json (or rerun with --voice <id>).")
        return

    voice_id = args.voice or cfg["voice_id"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    beats = [b for b in cfg["beats"] if (not args.beat or b["id"] == args.beat)]
    if not beats:
        sys.exit(f"no beat matching {args.beat!r}")

    written = []
    for b in beats:
        audio = synth(api_key, b["text"], voice_id, fmt)
        out = OUT_DIR / f"{b['id']}.{fmt}"
        out.write_bytes(audio)
        written.append(out)
        print(f"  {out}  ({len(audio):,} bytes)  [{b.get('time','')}]")

    if not args.beat and len(written) > 1 and fmt == "wav":
        full = OUT_DIR / "full.wav"
        concat_wavs(written, full)
        print(f"\n  Stitched full track -> {full}")


if __name__ == "__main__":
    main()
