"""Record the Google Cloud Console, so the video shows the backend where it actually runs.

The rules ask for the backend visibly running on Google Cloud, and the Console is the most
legible evidence of that. It needs a signed-in session, which is why this runs in two steps:

    .venv/bin/python scripts/record_console.py login    # once: sign in, the profile persists
    .venv/bin/python scripts/record_console.py          # records every page

Real Chrome, not bundled Chromium, because Google frequently refuses sign-in from automation
builds. The profile lives in video/.chrome-profile and is gitignored: it holds a live session,
so it must never be committed.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "video/.chrome-profile"
OUT = ROOT / "video/assets/console"
W, H = 1920, 1080

C = "https://console.cloud.google.com"
# Each page earns its place: a service the project genuinely uses, and that a judge is told
# about in the narration. Seconds are per clip; the edit trims into them.
PAGES = [
    ("run-services",  f"{C}/run?project=concordat-alpha", 7,
     "Cloud Run: the three fleet services, deployed and serving"),
    ("run-logs",      f"{C}/run/detail/us-central1/bank-alpha/logs?project=concordat-alpha", 10,
     "Cloud Run logs: the fleet talking, live"),
    ("pubsub",        f"{C}/cloudpubsub/topic/list?project=concordat-alpha", 6,
     "Pub/Sub: every state transition is an event"),
    ("firestore",     f"{C}/firestore/databases/-default-/data?project=concordat-alpha", 6,
     "Firestore: case state, so any service can die mid-case"),
    ("bigquery",      f"{C}/bigquery?project=concordat-alpha", 7,
     "BigQuery: three isolated ledgers and the clean room"),
    ("agent-engine",  f"{C}/vertex-ai/agents/agent-engines?project=concordat-hack", 7,
     "Vertex AI Agent Engine: the fleet catalog on neutral ground"),
    ("iam",           f"{C}/iam-admin/serviceaccounts?project=concordat-alpha", 6,
     "One service account per bank, and the perimeter that 403 comes from"),
]


def launch(pw, record: bool):
    return pw.chromium.launch_persistent_context(
        str(PROFILE),
        channel="chrome",
        headless=False,
        viewport={"width": W, "height": H},
        args=["--hide-crash-restore-bubble", "--disable-features=Translate"],
        record_video_dir=str(OUT) if record else None,
        record_video_size={"width": W, "height": H} if record else None,
    )


def login() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = launch(pw, record=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{C}/run?project=concordat-alpha")
        print("\nSign in to Google in the window that opened, and land on the Cloud Run page.")
        print("Then come back here and press Enter.")
        input()
        ctx.close()
    print("Session saved. Now run without arguments to record.")


def record() -> None:
    if not PROFILE.exists():
        raise SystemExit("No session yet. Run:  .venv/bin/python scripts/record_console.py login")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    with sync_playwright() as pw:
        for name, url, secs, why in PAGES:
            ctx = launch(pw, record=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(9000)          # the Console fills in well after DOM ready
                if "sign" in page.url.lower() or "accounts.google" in page.url:
                    print(f"  {name}: NOT SIGNED IN, run the login step first")
                    ctx.close()
                    continue
                page.mouse.wheel(0, 220)             # a little life in the frame
                page.wait_for_timeout(secs * 1000)
            finally:
                ctx.close()
            vids = sorted(OUT.glob("*.webm"), key=lambda p: p.stat().st_mtime)
            if vids:
                vids[-1].rename(OUT / f"{name}.webm")
                print(f"  {name}.webm  {secs}s   {why}")
    print(f"\nclips in {OUT}")


if __name__ == "__main__":
    (login if len(sys.argv) > 1 and sys.argv[1] == "login" else record)()
