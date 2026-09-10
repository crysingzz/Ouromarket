"""Optional browser verification: uv run --with playwright python scripts/ui_smoke.py."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parent.parent
output = root / ".state" / "ui"
output.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto("http://127.0.0.1:8787")
    page.get_by_label("Access token").fill((root / ".secrets/operator_token").read_text().strip())
    page.get_by_role("button", name="Connect workspace").click()
    expect(page.locator("#login-dialog")).not_to_be_visible()
    page.screenshot(
        path=str(output / "overview-desktop.png"), full_page=True, animations="disabled"
    )
    page.get_by_role("button", name="New research job").click()
    page.locator("#job-form").get_by_label("Research objective").fill(
        "Browser verification: test daily trend after transaction costs"
    )
    page.get_by_role("button", name="Create & run research").click()
    expect(page.locator("#job-dialog")).not_to_be_visible()
    expect(page.locator("#new-research")).to_be_enabled(timeout=45000)
    page.get_by_role("button", name="Inspect").first.click()
    page.wait_for_selector("#detail-dialog[open]")
    if "config_hash" not in page.locator("#detail-content").inner_text():
        raise RuntimeError("Experiment evidence did not render")
    with page.expect_download() as downloaded:
        page.get_by_role("button", name="Download reproduction bundle").click()
    downloaded.value.save_as(str(output / "reproduction-bundle.json"))
    page.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("button", name="Risk controls", exact=False).click()
    page.get_by_role("button", name="Halt execution").click()
    expect(page.locator("#control-state")).to_have_text("Execution halted")
    page.get_by_label("Operator reason").fill(
        "Browser verification completed; resume synthetic paper"
    )
    page.get_by_role("button", name="Resume after reconciliation").click()
    expect(page.locator("#control-state")).to_have_text("Pretrade controls active")
    page.get_by_role("button", name="Audit trail", exact=False).click()
    expect(page.locator("#audit-status")).to_have_text("HASH CHAIN VERIFIED")
    page.screenshot(path=str(output / "audit-desktop.png"), full_page=True, animations="disabled")
    page.get_by_role("button", name="Autonomous R&D", exact=False).click()
    expect(page.locator("#research-readiness")).to_contain_text("OpenAI key")
    expect(page.get_by_role("heading", name="Версии исследовательского агента")).to_be_visible()
    expect(page.locator("#forward-feed-status")).to_contain_text("Источник данных")
    page.get_by_role("button", name="Настроить OpenAI", exact=True).click()
    expect(page.locator("#provider-key")).to_have_attribute("type", "password")
    page.locator("#close-provider").click()
    page.get_by_role("button", name="Создать тестовые данные", exact=True).click()
    expect(page.locator("#dataset-list")).to_contain_text("synthetic demonstration")
    if page.locator("[data-campaign]").count():
        page.locator("[data-campaign]").first.click()
        expect(page.locator("#detail-dialog")).to_be_visible()
        expect(page.locator("#detail-content")).not_to_be_empty()
        page.locator("#close-detail").click()
    page.screenshot(
        path=str(output / "autonomous-desktop.png"), full_page=True, animations="disabled"
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(
        path=str(output / "autonomous-mobile.png"), full_page=True, animations="disabled"
    )
    if page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth"):
        raise RuntimeError("Autonomous mobile layout overflows horizontally")
    page.get_by_role("button", name="Overview", exact=False).click()
    page.get_by_role("button", name="Strategy registry", exact=False).click()
    expect(page.get_by_role("heading", name="Активные стратегии и претенденты")).to_be_visible()
    expect(page.get_by_role("heading", name="Артефакты Ouroboros")).to_be_visible()
    expect(page.locator("#lifecycle-strategies")).not_to_be_empty()
    page.screenshot(
        path=str(output / "lifecycle-mobile.png"), full_page=True, animations="disabled"
    )
    if page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth"):
        raise RuntimeError("Lifecycle mobile layout overflows horizontally")
    page.set_viewport_size({"width": 1440, "height": 1100})
    page.screenshot(
        path=str(output / "lifecycle-desktop.png"), full_page=True, animations="disabled"
    )
    page.get_by_role("button", name="Overview", exact=False).click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(output / "overview-mobile.png"), full_page=True, animations="disabled")
    if page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth"):
        raise RuntimeError("Mobile layout overflows horizontally")
    if failures:
        raise RuntimeError(f"Browser errors: {failures}")
    browser.close()
print(
    "PASS: login, research, evidence, halt/resume, audit, autonomous panels, masked provider setup, dataset creation, desktop/mobile; no JavaScript errors."
)
print(f"Screenshots: {output}")
