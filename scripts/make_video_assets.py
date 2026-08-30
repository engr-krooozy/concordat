"""Generate the parts of the demo video that should be generated, and nothing else.

The demo itself is a screen recording of the real deployment, because the rules require the
backend to be visibly running on Google Cloud and because a fabricated UI would be a lie told
to a judge. What Veo and Lyria are for here:

  cold open  Veo 3    a person and a street, never the product. Fourteen seconds of context
                      that a screen recording cannot give and that no stock library can license
                      to us cleanly.
  score      Lyria 2  original music, which is how the "no unlicensed material" rule gets
                      satisfied rather than argued about.
  narration  Gemini   the script read aloud, so an edit can be cut before a mic is found.
                      Replace with a human read if there is time; it is better.

Everything lands in video/assets/ (gitignored). Re-runnable; skips what already exists.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT = "concordat-hack"
REGION = "us-central1"
BUCKET = "gs://concordat-hack-video"
OUT = Path(__file__).resolve().parent.parent / "video/assets"
SCRIPT = Path(__file__).resolve().parent.parent / "docs/video-script.md"
BASE = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}"

# Deliberately no product, no screens, no bank logos. Anything a judge might mistake for the
# real UI has to be the real UI.
COLD_OPEN = [
    ("cold-open-1",
     ("Handheld documentary shot, early morning in Lagos Nigeria. A woman in her "
     "thirties stands on a busy street holding a phone to her ear, her face falling as she "
     "listens. Warm low sun, shallow depth of field, muted colour grade. No text, no logos, "
     "no screens. Cinematic, 35mm.")),
    ("cold-open-2",
     ("Slow push in on a phone screen held in a woman's hand showing an abstract "
     "banking notification, deliberately blurred and unreadable, no brand marks. Morning light, "
     "shallow focus, documentary style. No legible text.")),
    ("cold-open-3",
     ("Wide static shot of a quiet modern bank hall interior at opening time, "
     "empty chairs, soft daylight through tall windows, no signage, no logos, no people's faces. "
     "Cool neutral grade, still and institutional. Cinematic.")),
]

SCORE = [
    ("score-tension",
     ("Sparse tense electronic underscore, low synth pulse, minimal percussion, "
     "restrained and unresolved, documentary thriller. No melody in the foreground, nothing "
     "triumphant. Steady 90 bpm.")),
    ("score-resolve",
     ("Calm warm ambient electronic instrumental, soft synthesizer pads and a gentle "
      "arpeggio, steady and understated, sits quietly under a speaking voice. 90 bpm.")),
]


def token() -> str:
    return subprocess.run(["gcloud", "auth", "print-access-token"],
                          capture_output=True, text=True, check=True).stdout.strip()


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def veo(name: str, prompt: str) -> None:
    """Veo is long-running: kick off, then poll the operation until the clip lands in GCS."""
    dest = OUT / f"{name}.mp4"
    if dest.exists():
        print(f"  {name}.mp4 already there, skipping")
        return
    r = requests.post(
        f"{BASE}/publishers/google/models/veo-3.0-generate-001:predictLongRunning",
        headers=headers(), timeout=60,
        json={"instances": [{"prompt": prompt}],
              "parameters": {"aspectRatio": "16:9", "sampleCount": 1,
                             "durationSeconds": 8, "generateAudio": False,
                             "storageUri": f"{BUCKET}/{name}/"}})
    if r.status_code != 200:
        print(f"  {name}: {r.status_code} {r.text[:200]}")
        return
    op = r.json()["name"]
    print(f"  {name}: generating", end="", flush=True)
    for _ in range(60):
        time.sleep(10)
        print(".", end="", flush=True)
        p = requests.post(f"{BASE}/publishers/google/models/veo-3.0-generate-001:fetchPredictOperation",
                          headers=headers(), json={"operationName": op}, timeout=60).json()
        if p.get("done"):
            err = p.get("error")
            if err:
                print(f" failed: {err.get('message','')[:160]}")
                return
            vids = p.get("response", {}).get("videos", [])
            if not vids:
                print(f" no video returned: {json.dumps(p.get('response', {}))[:200]}")
                return
            uri = vids[0].get("gcsUri")
            subprocess.run(["gsutil", "-q", "cp", uri, str(dest)], check=True)
            print(f" saved {dest.name}")
            return
    print(" timed out")


def lyria(name: str, prompt: str) -> None:
    dest = OUT / f"{name}.wav"
    if dest.exists():
        print(f"  {name}.wav already there, skipping")
        return
    r = requests.post(f"{BASE}/publishers/google/models/lyria-002:predict",
                      headers=headers(), timeout=300,
                      json={"instances": [{"prompt": prompt,
                                           "negative_prompt": "vocals, singing, lyrics"}],
                            "parameters": {"sample_count": 1}})
    if r.status_code != 200:
        print(f"  {name}: {r.status_code} {r.text[:200]}")
        return
    preds = r.json().get("predictions", [])
    if not preds:
        print(f"  {name}: no audio returned")
        return
    b64 = preds[0].get("bytesBase64Encoded") or preds[0].get("audioContent")
    dest.write_bytes(base64.b64decode(b64))
    print(f"  saved {dest.name}")


def narration_blocks() -> list[tuple[str, str]]:
    """Pull the quoted narration out of the shooting script, so the two never drift apart."""
    text = SCRIPT.read_text()
    blocks = []
    for m in re.finditer(r"^### (\d)\. ([^\n(]+).*?\n(.*?)(?=^### |\Z)", text, re.DOTALL | re.MULTILINE):
        spoken = " ".join(ln.lstrip("> ").strip()
                          for ln in m.group(3).splitlines() if ln.startswith(">"))
        spoken = re.sub(r"\s+", " ", spoken).strip()
        if spoken:
            blocks.append((f"vo-{m.group(1)}-{m.group(2).strip().lower().replace(' ', '-')}",
                           spoken))
    return blocks


def narrate(name: str, text: str) -> None:
    """Cloud TTS with a Gemini voice, which is the path make_voice_note.py already proved works.

    Charon is the steadiest of the Gemini narrator voices. en-GB because Gemini TTS has no
    en-NG, same compromise the customer voice note makes.
    """
    dest = OUT / f"{name}.mp3"
    if dest.exists():
        print(f"  {name}.mp3 already there, skipping")
        return
    r = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={**headers(), "x-goog-user-project": PROJECT}, timeout=180,
        json={"input": {"text": text},
              "voice": {"languageCode": "en-GB", "name": "Charon",
                        "model_name": "gemini-2.5-flash-tts"},
              "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.08}})
    payload = r.json()
    if "audioContent" not in payload:
        print(f"  {name}: {r.status_code} {json.dumps(payload)[:160]}")
        return
    dest.write_bytes(base64.b64decode(payload["audioContent"]))
    print(f"  saved {dest.name}  ({dest.stat().st_size/1024:.0f} KB)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"

    if what in ("all", "score"):
        print("Lyria: original score")
        for n, p in SCORE:
            lyria(n, p)

    if what in ("all", "vo"):
        print("Gemini TTS: narration, read from docs/video-script.md")
        for n, t in narration_blocks():
            narrate(n, t)

    if what in ("all", "veo"):
        print("Veo: cold open only, no product footage")
        for n, p in COLD_OPEN:
            veo(n, p)

    print(f"\nassets in {OUT}")


if __name__ == "__main__":
    main()
