"""Screen-record the live dashboard with Playwright, one clip per shot in the cue sheet.

This is real footage of the deployed product, captured from the public URL in a real browser.
Nothing here is generated or mocked: if the site is down, the clips are empty, which is the
correct failure. Durations come from docs/video-script.md so picture matches the narration.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

UI = "https://mission-control-fa7ntw3nkq-uc.a.run.app"
OUT = Path(__file__).resolve().parent.parent / "video/assets/clips"
# Record 4K of a page that still lays out at 1920x1080.
#
# device_scale_factor does NOT do this: Playwright renders the viewport at CSS size and paints
# it into the top-left of whatever record_video_size asks for, leaving the rest grey. Zoom is
# the lever that works. A 3840x2160 viewport zoomed 2x has a layout viewport of exactly
# 1920x1080, so composition and every scroll target are unchanged, at four times the pixels.
W, H = 3840, 2160
ZOOM = 2.0

# (name, seconds, what the camera does). Seconds are the cue-sheet durations, plus a little
# handle at each end so the edit has something to trim into.
SHOTS = [
    ("s2-dashboard", 19, "hold_top"),
    ("s3-intake", 19, "scroll_steps"),
    ("s4-negotiation", 31, "scroll_negotiation"),
    ("s5-finding", 35, "scroll_finding"),
    ("s9-close", 21, "hold_top"),
]


def glide(page, to: int, ms: int) -> None:
    """Ease-in-out scroll. A linear scroll reads as a machine; this reads as a camera."""
    page.evaluate(
        """([to, ms]) => new Promise(done => {
             const from = window.scrollY, t0 = performance.now();
             const ease = p => p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p+2, 3)/2;
             (function step(now){
               const p = Math.min(1, (now - t0) / ms);
               window.scrollTo(0, from + (to - from) * ease(p));
               p < 1 ? requestAnimationFrame(step) : done();
             })(t0);
           })""",
        [to, ms],
    )


def move(page, kind: str, secs: int) -> None:
    if kind == "hold_top":
        page.wait_for_timeout(secs * 1000)
    elif kind == "scroll_steps":
        page.wait_for_timeout(2500)
        glide(page, 700, (secs - 5) * 1000)
        page.wait_for_timeout(2500)
    elif kind == "scroll_negotiation":
        glide(page, 1180, 2500)
        page.wait_for_timeout(3000)
        glide(page, 1700, (secs - 10) * 1000)
        page.wait_for_timeout(4500)
    elif kind == "scroll_finding":
        glide(page, 1900, 2500)
        page.wait_for_timeout(4000)
        glide(page, 2600, (secs - 12) * 1000)
        page.wait_for_timeout(5500)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    only = sys.argv[1] if len(sys.argv) > 1 else None

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, secs, kind in SHOTS:
            if only and only != name:
                continue
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(OUT),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            page.goto(UI, wait_until="load")
            page.evaluate(f"document.documentElement.style.zoom = '{ZOOM}'")
            page.wait_for_timeout(6000)  # the fleet panels fill in after first paint
            move(page, kind, secs)
            ctx.close()  # flushes the webm
            src = max(OUT.glob("*.webm"), key=lambda p: p.stat().st_mtime)
            src.rename(OUT / f"{name}.webm")
            print(f"  {name}.webm  {secs}s")
        browser.close()
    print(f"\nclips in {OUT}")


if __name__ == "__main__":
    main()
