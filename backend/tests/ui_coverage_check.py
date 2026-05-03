"""Isolated check on /projects/1/coverage — was it really broken or HMR noise?"""
import asyncio, json, sys
sys.path.insert(0, "/app/tests")
from ui_sweep import attach_listeners, login, ADMIN_USER, ADMIN_PASSWORD, FRONTEND
from playwright.async_api import async_playwright

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
        sink = {"console": [], "network": [], "rate_limited": []}
        await attach_listeners(page, sink)
        await login(page, ADMIN_USER, ADMIN_PASSWORD)

        # First load
        for i in range(3):
            sink["console"].clear(); sink["network"].clear(); sink["rate_limited"].clear()
            res = await page.goto(f"{FRONTEND}/projects/1/coverage", wait_until="networkidle", timeout=20000)
            print(json.dumps({
                "iteration": i + 1,
                "http": res.status,
                "final_url": page.url,
                "console": list(sink["console"]),
                "network_5xx": list(sink["network"]),
                "rate_limited": list(sink["rate_limited"]),
            }), flush=True)
            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
