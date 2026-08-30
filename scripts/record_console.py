"""Capture the Google Cloud Console for the demo video, from a genuinely signed-in browser.

Google refuses sign-in in a Playwright-launched Chrome: the automation flags trip its "this
browser or app may not be secure" check, and no amount of flag-tweaking reliably beats it.

So Playwright never launches the browser here. Step one starts ordinary Chrome with a debugging
port and no automation flags, and you sign in exactly as you always do. Step two attaches to
that already-authenticated browser over CDP and drives it. Attaching adds no automation flags,
so the session stays trusted.

    .venv/bin/python scripts/record_console.py open      # 1. Chrome opens, you sign in
    .venv/bin/python scripts/record_console.py           # 2. captures every page

Chrome 136+ refuses a debugging port on the default profile, so this uses its own profile
directory. That is also why you sign in once: it is a fresh profile, not your everyday one.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "video/.chrome-profile"
OUT = ROOT / "video/assets/console"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9222
C = "https://console.cloud.google.com"

# Each page is a service the project genuinely uses and the narration names out loud.
# Logs go through Logs Explorer rather than the Cloud Run logs tab: that tab's URL 404s, and
# Logs Explorer shows actual log lines, which is what the rules ask to see.
LOGS_Q = ('resource.type%3D%22cloud_run_revision%22%0A'
          'resource.labels.service_name%3D%22bank-alpha%22')

PAGES = [
    ("run-services", f"{C}/run?project=concordat-alpha",
     "Cloud Run: three fleet services, each under its own identity"),
    ("run-detail", f"{C}/run/detail/us-central1/bank-alpha/metrics?project=concordat-alpha",
     "bank-alpha: the service itself, deployed and serving"),
    ("run-logs", f"{C}/logs/query;query={LOGS_Q};duration=P7D?project=concordat-alpha",
     "Logs Explorer: the fleet talking, live"),
    ("pubsub", f"{C}/cloudpubsub/topic/list?project=concordat-alpha",
     "Pub/Sub: every state transition is an event"),
    ("firestore", f"{C}/firestore/databases/-default-/data?project=concordat-alpha",
     "Firestore: case state, so a service can die mid-case"),
    ("bigquery", f"{C}/bigquery?project=concordat-alpha",
     "BigQuery: three isolated ledgers and the clean room"),
    ("agent-engine", f"{C}/vertex-ai/agents/agent-engines?project=concordat-hack",
     "Vertex AI Agent Engine: the catalog, on neutral ground"),
    ("iam", f"{C}/iam-admin/serviceaccounts?project=concordat-alpha",
     "One service account per bank: where the 403 comes from"),
]


def open_browser() -> None:
    """Ordinary Chrome, no automation flags, so Google treats the sign-in as a real one."""
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [CHROME, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
         "--no-first-run", "--no-default-browser-check",
         f"{C}/run?project=concordat-alpha"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("\nChrome is opening. In that window:")
    print("  1. sign in as adekunlemustapha2001@gmail.com")
    print("  2. wait until you can see the bank-alpha service on the Cloud Run page")
    print("\nLeave Chrome open, then run:")
    print("  .venv/bin/python scripts/record_console.py")


def capture() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(f"http://localhost:{PORT}")
        except Exception as exc:                      # noqa: BLE001 - message matters more
            raise SystemExit(
                f"Could not attach to Chrome on port {PORT}: {exc}\n"
                "Run this first, and leave that Chrome window open:\n"
                "  .venv/bin/python scripts/record_console.py open") from None

        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # Attaching to a running browser means no device_scale_factor to set at construction,
        # so override the metrics over CDP instead: same 1920x1080 layout, rendered at 2x.
        cdp = ctx.new_cdp_session(page)
        cdp.send("Emulation.setDeviceMetricsOverride",
                 {"width": 1920, "height": 1080, "deviceScaleFactor": 2, "mobile": False})

        bad = []
        for name, url, why in PAGES:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            if page.locator("text=/Sign in|Choose an account/i").count():
                raise SystemExit("Chrome is not signed in. Sign in, then re-run.")

            # The Console renders its shell immediately and fills in much later, so waiting for
            # the DOM proves nothing. Wait for the spinners to go instead, then settle.
            for _ in range(40):
                time.sleep(1)
                spinners = page.locator(
                    "[role=progressbar], .mat-progress-spinner, .loading-spinner").count()
                if not spinners:
                    break
            time.sleep(9)
            page.screenshot(path=str(OUT / f"{name}.png"), scale="device")

            # A 404 or an empty frame is still a screenshot, so say so rather than let it
            # reach the cut unnoticed.
            note = ""
            if page.locator("text=/URL not found|Page not found/i").count():
                note, _ = "  <- 404, PAGE NOT CAPTURED", bad.append(name)
            elif (OUT / f"{name}.png").stat().st_size < 200_000:
                note, _ = "  <- looks empty, check it", bad.append(name)
            print(f"  {name}.png   {why}{note}")

        if bad:
            print("\nThese need attention: " + ", ".join(bad))
        browser.close()
    print(f"\n{len(PAGES)} frames in {OUT}")
    print("Now rebuild:  .venv/bin/python scripts/assemble_video.py")


if __name__ == "__main__":
    (open_browser if len(sys.argv) > 1 and sys.argv[1] == "open" else capture)()
