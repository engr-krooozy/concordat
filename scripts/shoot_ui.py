"""Screenshot mission control, and report anything the browser complains about.

Exists because "the JSON is correct" and "the page looks right" are different claims, and
only one of them is what a judge experiences. Runs headless Chromium via Playwright, which
ships its own browser — this machine's Node is broken and cannot drive one.

    .venv/bin/python -m scripts.shoot_ui                     # newest case
    .venv/bin/python -m scripts.shoot_ui case-aa6137f7 800   # a case, and settle time in ms
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://mission-control-fa7ntw3nkq-uc.a.run.app"
OUT = Path("docs/ui")


def main() -> None:
    case = sys.argv[1] if len(sys.argv) > 1 else None
    settle = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
    OUT.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100},
                                device_scale_factor=2)
        page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(settle)
        if case:
            page.click(f"button:has-text('{case}')")
            page.wait_for_timeout(settle)

        page.screenshot(path=OUT / "dashboard-top.png")
        graph = page.query_selector("#graph")
        if graph:
            graph.screenshot(path=OUT / "flow.png")
        page.screenshot(path=OUT / "dashboard-full.png", full_page=True)

        # what a viewer actually ends up reading
        for sel, name in [("#banner", "banner"), ("#negsummary", "negotiation"),
                          ("#finding", "finding")]:
            el = page.query_selector(sel)
            if el:
                text = " ".join(el.inner_text().split())
                print(f"  {name}: {text[:150]}")
        rows = page.query_selector_all("#audit .row")
        print(f"  audit rows rendered: {len(rows)}")
        dots = page.query_selector_all("#graph circle")
        paths = page.query_selector_all("#graph path")
        print(f"  graph: {len(dots)} nodes, {len(paths)} flow paths")
        browser.close()

    print("\n" + ("browser reported nothing" if not problems else "BROWSER COMPLAINTS:"))
    for p in dict.fromkeys(problems):
        print(f"  {p}")
    print(f"\nwrote {OUT}/dashboard-top.png, flow.png, dashboard-full.png")


if __name__ == "__main__":
    main()
