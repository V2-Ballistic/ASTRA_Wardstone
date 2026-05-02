"""
ASTRA — UI sweep harness (one-shot, ad-hoc; not a regression test).

Usage:
    docker exec astra-backend-1 python /app/tests/ui_sweep.py [routes...]

For each route:
  - load it in headless chromium with admin auth
  - capture HTTP status, console errors, network 5xx responses
  - dump primary interactive elements (buttons, links inside <main>)
  - quick auth-gate probe: same route with no token → expect /login redirect

Output is JSON on stdout for easy ingestion by the test log writer.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from typing import Any

from playwright.async_api import async_playwright, Page, BrowserContext

FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3000")
BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
# Inside the backend container, localhost:8000 IS the backend (same
# container). For localhost:3000 we point chromium at the frontend
# container via --host-resolver-rules below.

ADMIN_USER = "smoke_test"
ADMIN_PASSWORD = "SmokeTest123"
DEV_USER = "ui_dev_test"
DEV_PASSWORD = "DevTest123"


# Routes that require auth — keys are paths, values are the URL to test
DEFAULT_ROUTES: list[tuple[str, str]] = [
    # (label, path)
    ("home", "/"),
    ("login", "/login"),
    ("traceability_global", "/traceability"),
    ("catalog", "/catalog"),
    ("catalog_part_new", "/catalog/parts/new"),
    ("catalog_supplier_new", "/catalog/suppliers/new"),
    ("parts_library", "/parts-library"),
    ("parts_library_pending", "/parts-library/pending-imports"),
    ("projects_new", "/projects/new"),
    ("project_dashboard", "/projects/1"),
    ("project_ai", "/projects/1/ai"),
    ("project_audit", "/projects/1/audit"),
    ("project_baselines", "/projects/1/baselines"),
    ("project_coverage", "/projects/1/coverage"),
    ("project_impact", "/projects/1/impact"),
    ("project_import", "/projects/1/import"),
    ("project_interfaces", "/projects/1/interfaces"),
    ("project_interfaces_auto_req", "/projects/1/interfaces/auto-requirements"),
    ("project_interfaces_connect", "/projects/1/interfaces/connect"),
    ("project_interfaces_import", "/projects/1/interfaces/import"),
    ("project_mech_interfaces", "/projects/1/mechanical-interfaces"),
    ("project_parts", "/projects/1/parts"),
    ("project_reports", "/projects/1/reports"),
    ("project_req_sync", "/projects/1/req-sync"),
    ("project_requirements", "/projects/1/requirements"),
    ("project_req_new", "/projects/1/requirements/new"),
    ("project_settings", "/projects/1/settings"),
    ("project_system_arch", "/projects/1/system-architecture"),
    ("project_traceability", "/projects/1/traceability"),
    ("project_verification", "/projects/1/verification"),
]


_TOKEN_CACHE: dict[str, str] = {}

async def login(page: Page, username: str, password: str) -> str:
    """Log in via the API once per username, return the JWT, and seed it
    into localStorage. Cached so we don't hit the rate-limiter.
    """
    import urllib.request, urllib.parse, time
    if username not in _TOKEN_CACHE:
        body = urllib.parse.urlencode(
            {"username": username, "password": password}
        ).encode()
        for attempt in range(5):
            try:
                req = urllib.request.Request(
                    f"{BACKEND}/api/v1/auth/login",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                _TOKEN_CACHE[username] = data["access_token"]
                break
            except Exception as exc:
                if attempt == 4:
                    raise
                time.sleep(2 + attempt * 3)  # 2,5,8,11s backoff
    token = _TOKEN_CACHE[username]
    # Seed localStorage so AuthGate sees a logged-in user on next load
    await page.goto(f"{FRONTEND}/login", wait_until="domcontentloaded")
    await page.evaluate(f"localStorage.setItem('astra_token', '{token}')")
    return token


NOISE_PATTERNS = ("/auth/providers", "/auth/me")
def _is_noise(text: str) -> bool:
    if not any(n in text for n in NOISE_PATTERNS):
        return False
    return any(
        marker in text
        for marker in ("404", "401", "429", "ERR_FAILED", "CORS")
    )


async def attach_listeners(page: Page, sink: dict[str, list[str]]) -> None:
    """Wire console / network listeners to a page once. Probes reset the
    sink between tests to scope errors to one probe."""
    def _on_console(msg):
        if msg.type in ("error", "warning") and not _is_noise(msg.text):
            sink["console"].append(f"[{msg.type}] {msg.text}")
    def _on_pageerror(exc):
        sink["console"].append(f"[pageerror] {exc}")
    def _on_response(resp):
        if resp.status >= 500:
            sink["network"].append(f"{resp.status} {resp.url}")
    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)
    page.on("response", _on_response)


async def probe_route(
    context: BrowserContext, label: str, path: str, *, authed: bool,
    page: Page | None = None, sink: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Test a single route. If `page` is provided, reuse it (avoids re-running
    AuthContext bootstrap which floods /auth/me). Otherwise opens its own page."""
    own_page = page is None
    if page is None:
        page = await context.new_page()
        sink = {"console": [], "network": []}
        await attach_listeners(page, sink)
    if sink is None:
        sink = {"console": [], "network": []}
        await attach_listeners(page, sink)
    sink["console"].clear()
    sink["network"].clear()

    try:
        response = await page.goto(
            f"{FRONTEND}{path}", wait_until="networkidle", timeout=20000,
        )
        http_status = response.status if response else None
        final_url = page.url

        # If unauth'd and route is gated, AppShell redirects to /login.
        # Detect by parsing final URL.
        redirected_to_login = "/login" in final_url and path != "/login"

        # Count primary interactive elements inside main content
        # (avoid sidebar buttons which are global).
        main_buttons = await page.locator(
            'main button:visible, [role="main"] button:visible'
        ).count()
        main_links = await page.locator(
            'main a:visible, [role="main"] a:visible'
        ).count()
        # Fall back: whole-page button/link count (some pages don't use <main>)
        all_buttons = await page.locator("button:visible").count()

        # Extract <h1> for sanity check
        h1_text = ""
        try:
            h1 = page.locator("h1").first
            if await h1.count() > 0:
                h1_text = (await h1.inner_text())[:120]
        except Exception:
            pass

        result = {
            "label": label,
            "path": path,
            "authed": authed,
            "http": http_status,
            "final_url": final_url,
            "redirected_to_login": redirected_to_login,
            "h1": h1_text,
            "main_buttons": main_buttons,
            "main_links": main_links,
            "all_buttons": all_buttons,
            "console_errors": list(sink["console"]),
            "network_5xx": list(sink["network"]),
        }
    except Exception as exc:
        result = {
            "label": label,
            "path": path,
            "authed": authed,
            "error": f"{type(exc).__name__}: {exc}",
            "console_errors": list(sink["console"]),
            "network_5xx": list(sink["network"]),
        }
    finally:
        if own_page:
            await page.close()
    return result


async def main(routes: list[tuple[str, str]]):
    async with async_playwright() as p:
        # MAP localhost:3000 → frontend container so Origin stays
        # `localhost:3000` (the only origin in backend CORS).
        # localhost:8000 already resolves to the backend container
        # itself (we're running inside it), so no mapping needed there.
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--host-resolver-rules=MAP localhost:3000 astra-frontend-1:3000",
                "--no-sandbox",
            ],
        )

        # Authed pass — admin user. Single page, navigate through all
        # routes — AuthContext only bootstraps once so /auth/me fires once.
        ctx_admin = await browser.new_context()
        admin_page = await ctx_admin.new_page()
        admin_sink: dict[str, list[str]] = {"console": [], "network": []}
        await attach_listeners(admin_page, admin_sink)
        await login(admin_page, ADMIN_USER, ADMIN_PASSWORD)
        admin_results = []
        for label, path in routes:
            res = await probe_route(
                ctx_admin, label, path, authed=True,
                page=admin_page, sink=admin_sink,
            )
            admin_results.append(res)
            print(json.dumps({"phase": "admin", **res}), flush=True)
            await asyncio.sleep(0.3)
        await admin_page.close()

        # Unauthed pass — every protected route should redirect to /login
        ctx_anon = await browser.new_context()
        anon_page = await ctx_anon.new_page()
        anon_sink: dict[str, list[str]] = {"console": [], "network": []}
        await attach_listeners(anon_page, anon_sink)
        anon_results = []
        for label, path in routes:
            if path == "/login":
                continue
            res = await probe_route(
                ctx_anon, label, path, authed=False,
                page=anon_page, sink=anon_sink,
            )
            anon_results.append(res)
            print(json.dumps({"phase": "anon", **res}), flush=True)
            await asyncio.sleep(0.3)
        await anon_page.close()

        # Wrong-persona pass — developer hits role-gated routes
        ctx_dev = await browser.new_context()
        dev_page = await ctx_dev.new_page()
        dev_sink: dict[str, list[str]] = {"console": [], "network": []}
        await attach_listeners(dev_page, dev_sink)
        await login(dev_page, DEV_USER, DEV_PASSWORD)
        # Routes that should bounce or render restricted-access for non-admins.
        # Per the codebase, RBAC is mostly backend-enforced; we just spot-check
        # whether the page loads without crashing.
        dev_routes = [
            ("dev_project_settings", "/projects/1/settings"),
            ("dev_project_audit", "/projects/1/audit"),
            ("dev_catalog_part_new", "/catalog/parts/new"),
            ("dev_parts_library", "/parts-library"),
            ("dev_project_parts", "/projects/1/parts"),
        ]
        dev_results = []
        for label, path in dev_routes:
            res = await probe_route(
                ctx_dev, label, path, authed=True,
                page=dev_page, sink=dev_sink,
            )
            dev_results.append(res)
            print(json.dumps({"phase": "dev", **res}), flush=True)
            await asyncio.sleep(0.3)
        await dev_page.close()

        await browser.close()

    # Summary
    summary = {
        "admin_total": len(admin_results),
        "admin_pass": sum(
            1 for r in admin_results
            if r.get("http") in (200, 304)
            and not r.get("console_errors")
            and not r.get("network_5xx")
            and not r.get("error")
        ),
        "anon_redirected_to_login": sum(
            1 for r in anon_results if r.get("redirected_to_login")
        ),
        "dev_loaded_without_crash": sum(
            1 for r in dev_results
            if r.get("http") in (200, 304) and not r.get("error")
        ),
    }
    print(json.dumps({"phase": "summary", **summary}), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Take subset of routes by label or path
        wanted = set(sys.argv[1:])
        sub = [(l, p) for (l, p) in DEFAULT_ROUTES if l in wanted or p in wanted]
        asyncio.run(main(sub or DEFAULT_ROUTES))
    else:
        asyncio.run(main(DEFAULT_ROUTES))
