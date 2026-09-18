"""Computed-style acceptance for the cobalt-inspired local operator interface."""

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
output = root / ".state" / "ui"
output.mkdir(parents=True, exist_ok=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel=os.environ.get("ALPHA_BROWSER_CHANNEL"))
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    failures: list[str] = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto("http://127.0.0.1:8787")
    page.get_by_label("Access token").fill(
        (root / ".secrets" / "operator_token").read_text().strip()
    )
    page.get_by_role("button", name="Connect workspace").click()
    page.locator("#login-dialog").wait_for(state="hidden")
    desktop = page.evaluate(
        """() => {
          const style = selector => getComputedStyle(document.querySelector(selector));
          const box = selector => document.querySelector(selector).getBoundingClientRect();
          return {
            bodyBackground: style('body').backgroundColor,
            bodyFont: style('body').fontFamily,
            railPosition: style('.sidebar').position,
            railWidth: box('.sidebar').width,
            shellMargin: parseFloat(style('.shell').marginLeft),
            activeBackground: style('.nav-item.active').backgroundColor,
            activeColor: style('.nav-item.active').color,
            navCount: document.querySelectorAll('.nav-item').length,
            primaryBackground: style('.primary').backgroundColor,
            overflow: document.documentElement.scrollWidth - window.innerWidth,
          };
        }"""
    )
    require(desktop["bodyBackground"] == "rgb(0, 0, 0)", "Desktop canvas is not black")
    require("mono" in desktop["bodyFont"].lower(), "Monospace control typography is missing")
    require(desktop["railPosition"] == "fixed", "Desktop navigation rail is not fixed")
    require(abs(desktop["railWidth"] - 92) < 1, "Desktop navigation rail is not 92px")
    require(abs(desktop["shellMargin"] - 92) < 1, "Desktop canvas does not clear the rail")
    require(desktop["navCount"] == 7, "A navigation destination is missing")
    require(desktop["activeBackground"] == "rgb(233, 233, 229)", "Active rail tile is not light")
    require(desktop["activeColor"] == "rgb(17, 17, 17)", "Active rail tile text is not dark")
    require(desktop["primaryBackground"] == "rgb(233, 233, 229)", "Primary action is not light")
    require(desktop["overflow"] <= 0, "Desktop document overflows horizontally")
    page.screenshot(
        path=str(output / "cobalt-overview-desktop.png"), full_page=True, animations="disabled"
    )

    page.set_viewport_size({"width": 390, "height": 844})
    mobile = page.evaluate(
        """() => {
          const style = selector => getComputedStyle(document.querySelector(selector));
          const box = selector => document.querySelector(selector).getBoundingClientRect();
          const rail = box('.sidebar');
          return {
            railBottom: window.innerHeight - rail.bottom,
            railWidth: rail.width,
            railHeight: rail.height,
            shellMargin: parseFloat(style('.shell').marginLeft),
            bodyPaddingBottom: parseFloat(style('body').paddingBottom),
            columns: style('nav').gridTemplateColumns.split(' ').length,
            overflow: document.documentElement.scrollWidth - window.innerWidth,
          };
        }"""
    )
    require(abs(mobile["railBottom"]) < 1, "Mobile dock is not attached to the bottom")
    require(abs(mobile["railWidth"] - 390) < 1, "Mobile dock does not span the viewport")
    require(mobile["railHeight"] >= 70, "Mobile dock is too small for touch targets")
    require(mobile["shellMargin"] == 0, "Mobile canvas still reserves desktop rail space")
    require(mobile["bodyPaddingBottom"] >= 70, "Mobile content is not clear of the dock")
    require(mobile["columns"] == 7, "Mobile dock does not retain all destinations")
    require(mobile["overflow"] <= 0, "Mobile document overflows horizontally")
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    page.get_by_role("button", name="Strategy registry").click()
    page.get_by_role("heading", name="Активные стратегии и претенденты").wait_for()
    require(page.evaluate("() => window.scrollY") == 0, "Section navigation did not return to top")
    page.screenshot(
        path=str(output / "cobalt-strategies-mobile.png"), full_page=False, animations="disabled"
    )
    require(not failures, f"Browser errors: {failures}")
    browser.close()

print("PASS: cobalt-inspired desktop and mobile layout; no overflow or JavaScript errors.")
print(f"Screenshots: {output}")
