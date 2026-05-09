"""诊断抖店首页 header 区域结构，定位店铺切换入口。"""
import asyncio
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

TABBIT_EXE = "C:/Users/Administrator/AppData/Local/Tabbit Browser/Application/Tabbit Browser.exe"
USER_DATA = "C:/Users/Administrator/AppData/Local/Tabbit Browser/User Data"
DOUYIN_HOME = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"


async def main():
    # Kill old Tabbit
    try:
        subprocess.run(["taskkill", "/F", "/IM", "Tabbit Browser.exe"],
                       timeout=8, capture_output=True)
    except Exception:
        pass
    await asyncio.sleep(3)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            USER_DATA,
            executable_path=TABBIT_EXE,
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("=" * 60)
        print("导航至抖店首页...")
        await page.goto(DOUYIN_HOME, wait_until="load", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(5000)

        title = await page.title()
        url = page.url
        print(f"页面标题: {title}")
        print(f"页面 URL: {url}")
        print(f"是否登录页: {'login' in url.lower() or 'passport' in url.lower()}")

        # Screenshot
        out_dir = Path("E:/first_cc")
        await page.screenshot(path=str(out_dir / "douyin_diag_home.png"), full_page=False)
        print("截图已保存: douyin_diag_home.png")

        # --- Strategy 1: Dump all elements in header-like containers ---
        print("\n" + "=" * 60)
        print("Header 区域元素 (tag + text + class + visible):")
        header_selectors = [
            "header", "[class*='header']", "[class*='Header']",
            "[class*='top-bar']", "[class*='topBar']", "[class*='nav']",
            "#header", "[role='banner']",
        ]
        seen = set()
        for hsel in header_selectors:
            container = page.locator(hsel).first
            if await container.count() == 0:
                continue
            # Get all descendents with text
            all_el = container.locator("*")
            count = await all_el.count()
            print(f"\n--- {hsel} (共 {count} 个子元素) ---")
            for i in range(min(count, 60)):
                el = all_el.nth(i)
                try:
                    tag = await el.evaluate("e => e.tagName")
                    text = (await el.inner_text()).replace("\n", " ").strip()[:80]
                    cls = (await el.get_attribute("class") or "")[:80]
                    vid = (await el.get_attribute("id") or "")
                    visible = await el.is_visible()
                    key = f"{tag}|{text}|{cls}"
                    if key in seen:
                        continue
                    seen.add(key)
                    if text or cls or vid:
                        print(f"  <{tag}> text='{text}' class='{cls}' id='{vid}' visible={visible}")
                except Exception:
                    pass

        # --- Strategy 2: Search for "切换" or "店铺" in any attribute ---
        print("\n" + "=" * 60)
        print("搜索含「切换」或「店铺」的元素:")
        for term in ("切换", "店铺", "组织"):
            for attr in ("text", "placeholder", "aria-label", "title"):
                try:
                    els = page.locator(f"[{attr}*='{term}']")
                    cnt = await els.count()
                    if cnt > 0:
                        for i in range(min(cnt, 5)):
                            el = els.nth(i)
                            tag = await el.evaluate("e => e.tagName")
                            txt = (await el.inner_text()).replace("\n", " ").strip()[:80]
                            print(f"  [{attr}*='{term}'] <{tag}> text='{txt}' visible={await el.is_visible()}")
                except Exception:
                    pass

        # --- Strategy 3: Check position-based click (top-right corner) ---
        print("\n" + "=" * 60)
        print("尝试 top-right 区域坐标点击...")
        # Move mouse to top-right and see what's there
        await page.mouse.move(1400, 25)
        await page.wait_for_timeout(1000)
        # Check what element is at this position
        el_at_pos = page.locator(":focus")
        print(f"  焦点元素: {await el_at_pos.count()}")

        # --- Strategy 4: List all elements with descTitle/descHeader-like classes ---
        print("\n" + "=" * 60)
        print("CSS class 模糊匹配 (descTitle / descHeader / intro):")
        for pattern in ("descTitle", "descHeader", "introName", "introDesc", "shop", "store"):
            els = page.locator(f"[class*='{pattern}']")
            cnt = await els.count()
            if cnt > 0:
                for i in range(min(cnt, 5)):
                    el = els.nth(i)
                    tag = await el.evaluate("e => e.tagName")
                    txt = (await el.inner_text()).replace("\n", " ").strip()[:100]
                    cls = (await el.get_attribute("class") or "")[:100]
                    print(f"  [class*='{pattern}'] <{tag}> text='{txt}' class='{cls}' visible={await el.is_visible()}")

        # --- Strategy 5: Dump page body text (first 500 chars) ---
        print("\n" + "=" * 60)
        print("页面 body text (前 500 字符):")
        try:
            body = await page.inner_text("body")
            print(body[:500])
        except Exception as e:
            print(f"  获取失败: {e}")

        print("\n" + "=" * 60)
        print("诊断完成。请保持浏览器打开，查看截图 douyin_diag_home.png")
        print("完成后按 Ctrl+C 退出。")
        await asyncio.Event().wait()  # keep browser open for inspection


if __name__ == "__main__":
    asyncio.run(main())
