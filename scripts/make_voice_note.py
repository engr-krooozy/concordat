"""Synthesize the demo voice note. Synthetic in every sense: a synthetic customer, reading
a synthetic complaint about synthetic money, in a synthesized voice.

Regenerate only if the wording changes — the mp3 is committed so the demo is reproducible
without a Text-to-Speech quota.

    CLOUDSDK_ACTIVE_CONFIG_NAME=concordat .venv/bin/python -m scripts.make_voice_note
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import httpx

OUT = Path("data/intake/fraud-report.mp3")
BUCKET = "gs://concordat-alpha-intake"
PROJECT = "concordat-alpha"

SCRIPT = (
    "Good afternoon. I want to report a fraud on my account, please. Yesterday afternoon, "
    "around two o'clock, I got an alert that two point four million naira left my account "
    "through a web transfer. My account number is A L P nine million and one. I did not "
    "authorise it. I was at work the whole afternoon, I never made any transfer. Please, "
    "you have to trace where this money went. That money is everything I have."
)


def token() -> str:
    import os

    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
    return subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout.strip()


def main() -> None:
    response = httpx.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={"Authorization": f"Bearer {token()}", "x-goog-user-project": PROJECT},
        json={
            "input": {"text": SCRIPT},
            # Gemini TTS voices need their model named explicitly, and they do not offer
            # en-NG — en-GB is the closest available for a Lagos retail caller.
            "voice": {
                "languageCode": "en-GB",
                "name": "Achernar",
                "model_name": "gemini-2.5-flash-tts",
            },
            "audioConfig": {"audioEncoding": "MP3"},
        },
        timeout=120,
    )
    payload = response.json()
    if "audioContent" not in payload:
        raise SystemExit(f"synthesis failed: {json.dumps(payload)[:300]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(base64.b64decode(payload["audioContent"]))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")

    subprocess.run(
        ["gcloud", "storage", "cp", str(OUT), f"{BUCKET}/fraud-report.mp3"],
        check=True,
        env={**__import__("os").environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"},
    )
    print(f"uploaded to {BUCKET}/fraud-report.mp3")


if __name__ == "__main__":
    main()
