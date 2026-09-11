"""Browser recovery workflow with explicit API fixtures, never real mutations."""

from playwright.sync_api import expect


def check_recovery(page):
    strategy = {
        "candidate_id": "recovery-fixture",
        "name": "Browser recovery fixture",
        "symbol": "SPY",
        "status": "DEMOTED",
        "version": 5,
        "forward_eligible": False,
        "validation_after": "2026-09-01T00:00:00Z",
    }
    calls = []

    def overview(route):
        route.fulfill(
            json={
                "strategies": [strategy],
                "unregistered": [],
                "comparisons": [],
                "transitions": [],
                "mode": "internal-paper",
                "capital_eligible": False,
            }
        )

    def mutate(route):
        body = route.request.post_data_json
        if (
            route.request.method != "POST"
            or body["expected_version"] != strategy["version"]
            or len(body["reason"]) < 8
            or not body["request_id"]
        ):
            raise RuntimeError("Invalid browser recovery request")
        if route.request.url.endswith("/revalidate"):
            if set(body) != {"expected_version", "reason", "request_id"}:
                raise RuntimeError("Revalidation must not submit a target or verdict")
            calls.append("REVALIDATE")
            route.fulfill(json={"status": "PASS", "capital_eligible": False})
        else:
            target = body["target"]
            calls.append(target)
            strategy.update(
                status=target,
                version=strategy["version"] + 1,
                forward_eligible=target in {"SHADOW", "PAPER"},
            )
            route.fulfill(json=strategy)

    page.route("**/api/lifecycle", overview)
    page.route("**/api/lifecycle/recovery-fixture/*", mutate)
    page.locator("#refresh").click()
    card = page.locator("#lifecycle-strategies .strategy-card").filter(has_text=strategy["name"])
    for label in (
        "Вернуть на исследование",
        "Повторная проверка",
        "Лаборатория пройдена →",
        "Наблюдение →",
        "Бумажная торговля →",
    ):
        card.get_by_role("button", name=label, exact=True).click()
        expect(page.locator("#lifecycle-dialog")).to_be_visible()
        page.locator("#lifecycle-reason").fill("Browser fixture: verify explicit recovery decision")
        page.locator("#lifecycle-form").get_by_role("button", name="Сохранить решение").click()
        expect(page.locator("#lifecycle-dialog")).not_to_be_visible()
    if calls != ["RESEARCH", "REVALIDATE", "LAB_VALIDATED", "SHADOW", "PAPER"]:
        raise RuntimeError("Incomplete browser recovery workflow")
    expect(card.get_by_role("button", name="Претендент →", exact=True)).to_be_visible()
    page.unroute("**/api/lifecycle", overview)
    page.unroute("**/api/lifecycle/recovery-fixture/*", mutate)
    page.locator("#refresh").click()
