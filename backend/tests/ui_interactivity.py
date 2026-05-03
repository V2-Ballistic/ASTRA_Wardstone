"""
UI interactivity probe — for each route that previously rendered clean,
exercise the safe interactive elements:
  - tab switches (any element with role=tab or .tab-button class)
  - modal open + close (buttons with text matching Add/Create/Upload/New
    that open a dialog with role=dialog)
  - dropdown / select toggles
We DO NOT click:
  - Delete / Remove / Trash buttons
  - Submit buttons inside forms (may have backend side effects)
  - Logout / Sign out
  - Approve / Reject (state-mutating)

Run after `ui_sweep.py` proves the harness no longer cascades.
"""
from __future__ import annotations
import asyncio
import json
import sys
sys.path.insert(0, "/app/tests")
from ui_sweep import (
    attach_listeners, login, ADMIN_USER, ADMIN_PASSWORD, FRONTEND,
    ROUTE_DELAY_S, _is_noise,
)
from playwright.async_api import async_playwright, Page

# Routes to probe interactively. Drawn from the route inventory.
ROUTES = [
    ("/", "home"),
    ("/parts-library", "parts_library"),
    ("/parts-library/pending-imports", "parts_library_pending"),
    ("/catalog", "catalog"),
    ("/projects/1", "project_dashboard"),
    ("/projects/1/requirements", "project_requirements"),
    ("/projects/1/traceability", "project_traceability"),
    ("/projects/1/baselines", "project_baselines"),
    ("/projects/1/parts", "project_parts"),
    ("/projects/1/mechanical-interfaces", "project_mech_interfaces"),
    ("/projects/1/system-architecture", "project_system_arch"),
    ("/projects/1/interfaces", "project_interfaces"),
    ("/projects/1/interfaces/auto-requirements", "project_interfaces_auto_req"),
    ("/projects/1/coverage", "project_coverage"),
    ("/projects/1/audit", "project_audit"),
    ("/projects/1/settings", "project_settings"),
    ("/projects/1/verification", "project_verification"),
    ("/projects/1/reports", "project_reports"),
    ("/projects/1/req-sync", "project_req_sync"),
    ("/projects/1/impact", "project_impact"),
]

# Don't click these.
DESTRUCTIVE_TEXT = (
    "Delete", "Remove", "Trash", "Sign out", "Logout", "Cancel",
    "Submit", "Save", "Approve", "Reject", "Force",
)
# These are safe — they open modals or switch views.
OPEN_TEXT = (
    "Add", "Create", "Upload", "New", "Open", "Show", "View",
    "Filter", "Edit",  # edit usually opens a panel, doesn't auto-save
)


async def probe_interactive(page: Page, label: str, path: str, sink: dict) -> dict:
    sink["console"].clear()
    sink["network"].clear()
    if "rate_limited" in sink:
        sink["rate_limited"].clear()

    actions: list[str] = []
    response = await page.goto(
        f"{FRONTEND}{path}", wait_until="networkidle", timeout=20000,
    )
    http = response.status if response else None
    final_url = page.url
    # Reauth + retry-once on rate-limit-driven bounce.
    if "/login" in final_url and path != "/login":
        await asyncio.sleep(30)
        await login(page, ADMIN_USER, ADMIN_PASSWORD)
        sink["console"].clear()
        sink["network"].clear()
        if "rate_limited" in sink:
            sink["rate_limited"].clear()
        response = await page.goto(
            f"{FRONTEND}{path}", wait_until="networkidle", timeout=20000,
        )
        http = response.status if response else None
        final_url = page.url
        if "/login" in final_url and path != "/login":
            return {
                "label": label, "path": path, "http": http,
                "actions": ["BOUNCED_TO_LOGIN_AFTER_REAUTH"],
                "console_errors": list(sink["console"]),
                "network_5xx": list(sink["network"]),
            }
        actions.append("reauth_succeeded")

    # 1. Tab switching — any role=tab not in selected state
    tabs = page.locator('[role="tab"]:not([aria-selected="true"]):visible')
    n_tabs = await tabs.count()
    for i in range(min(n_tabs, 3)):
        try:
            tab = tabs.nth(i)
            label_text = (await tab.inner_text())[:30].replace("\n", " ")
            await tab.click(timeout=3000)
            await asyncio.sleep(0.4)
            actions.append(f"tab_clicked:{label_text}")
        except Exception as exc:
            actions.append(f"tab_click_error:{type(exc).__name__}")
            break

    # 2. Modal open + close — find a button with safe-open text
    modal_opened = False
    for safe in OPEN_TEXT:
        candidates = page.get_by_role("button", name=safe, exact=False)
        n = await candidates.count()
        if n == 0:
            continue
        # Filter out destructive ones (e.g. "Add and delete")
        for i in range(min(n, 3)):
            try:
                btn = candidates.nth(i)
                if not await btn.is_visible():
                    continue
                btn_text = (await btn.inner_text())[:40]
                if any(d.lower() in btn_text.lower() for d in DESTRUCTIVE_TEXT):
                    continue
                await btn.click(timeout=3000)
                actions.append(f"opened:{btn_text}")
                modal_opened = True
                # If a dialog appeared, close it.
                await asyncio.sleep(0.5)
                dialog = page.locator('[role="dialog"]:visible').first
                if await dialog.count() > 0:
                    # Try to close: ESC, then × button, then Cancel
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                    if await dialog.count() > 0 and await dialog.is_visible():
                        cancel_btn = page.get_by_role("button", name="Cancel").first
                        if await cancel_btn.count() > 0 and await cancel_btn.is_visible():
                            await cancel_btn.click(timeout=2000)
                            await asyncio.sleep(0.3)
                    if await dialog.count() > 0 and await dialog.is_visible():
                        actions.append("modal_close_failed")
                    else:
                        actions.append("modal_closed")
                break
            except Exception as exc:
                actions.append(f"open_error:{safe}:{type(exc).__name__}")
                continue
        if modal_opened:
            break

    return {
        "label": label, "path": path, "http": http,
        "actions": actions,
        "console_errors": list(sink["console"]),
        "network_5xx": list(sink["network"]),
        "rate_limited": list(sink.get("rate_limited", [])),
    }


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--host-resolver-rules=MAP localhost:3000 astra-frontend-1:3000",
                "--no-sandbox",
            ],
        )
        ctx = await browser.new_context()
        page = await ctx.new_page()
        sink: dict = {"console": [], "network": [], "rate_limited": []}
        await attach_listeners(page, sink)
        await login(page, ADMIN_USER, ADMIN_PASSWORD)
        for path, label in ROUTES:
            res = await probe_interactive(page, label, path, sink)
            print(json.dumps(res), flush=True)
            await asyncio.sleep(ROUTE_DELAY_S)
            if res.get("rate_limited"):
                await asyncio.sleep(15)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
