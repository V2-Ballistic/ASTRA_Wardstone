"""Test individual dynamic-id routes in isolation, with cooldown between."""
import asyncio
import json
import sys
sys.path.insert(0, "/app/tests")
from ui_sweep import probe_route, attach_listeners, login, BACKEND, ADMIN_USER, ADMIN_PASSWORD
from playwright.async_api import async_playwright


EXTRA_ROUTES = [
    ("parts_library_detail", "/parts-library/5"),    # use(params) was buggy here
    ("pending_import_detail", "/parts-library/pending-imports/1"),  # buggy here too
    ("catalog_part_detail", "/catalog/parts/5"),
    ("supplier_detail", "/catalog/suppliers/5"),
    ("requirement_detail", "/projects/1/requirements/1"),
    ("system_detail", "/projects/1/interfaces/system/1"),
    ("project_requirements", "/projects/1/requirements"),
    ("project_traceability", "/projects/1/traceability"),
    ("project_baselines", "/projects/1/baselines"),
    ("project_settings", "/projects/1/settings"),
]


async def run_one(label: str, path: str):
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
        sink = {"console": [], "network": []}
        await attach_listeners(page, sink)
        await login(page, ADMIN_USER, ADMIN_PASSWORD)
        res = await probe_route(
            ctx, label, path, authed=True, page=page, sink=sink,
            reauth_username=ADMIN_USER, reauth_password=ADMIN_PASSWORD,
        )
        print(json.dumps({"phase": "admin", **res}), flush=True)
        await browser.close()


async def main():
    for i, (label, path) in enumerate(EXTRA_ROUTES):
        await run_one(label, path)
        if i < len(EXTRA_ROUTES) - 1:
            # Big cooldown to avoid rate limit
            await asyncio.sleep(35)


if __name__ == "__main__":
    asyncio.run(main())
