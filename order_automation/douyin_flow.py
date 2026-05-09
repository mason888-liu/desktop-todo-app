from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .helpers import (
    click_text,
    confirm_dialogs,
    list_maybe_has_orders,
    run_step_with_retry,
    try_select_all,
)

logger = logging.getLogger(__name__)

# -- URLs -------------------------------------------------------------------
DOUYIN_HOMEPAGE = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"
DROPSHIP_URL = "https://fxg.jinritemai.com/ffa/morder/dropshiping"

# -- Stable selectors from douyin recording (auxo-* framework) ---------------
SEL_SHOP_SWITCHER = "切换组织/店铺"
SEL_SHIP_CENTER = "发货中心"
SEL_FACTORY_DROPSHIP = "厂商代发"
SEL_PRODUCT_INPUT = "input[placeholder='请输入商品名/ID']"
SEL_QUERY_BTN = "查询"
SEL_ONLY_REMARK = "仅展示有备注的订单"
SEL_BATCH_ASSIGN = "批量分配"
SEL_ASSIGN_SHOP_SEARCH = "#distr_shop_id"
SEL_ASSIGN_CONFIRM = "分配"
SEL_RECENT_UNASSIGNED = "近7日未分配"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


async def run_douyin_flow_part1(page: Page, cfg: dict[str, Any]) -> None:
    """抖店 Part 1: 豫南缘 → 代发订单 → 60g → 分配我老家."""
    lb: dict[str, str] = cfg["labels"]["douyin"]
    timeout = int(cfg.get("default_timeout_ms", 25000))

    await run_step_with_retry(
        page, "抖店-1 切换豫南缘",
        lambda: _switch_shop(page, lb["shop_yunan"], timeout),
    )
    await run_step_with_retry(
        page, "抖店-2 进入代发订单",
        lambda: _navigate_dropship(page, timeout),
    )
    await run_step_with_retry(
        page, "抖店-3 搜60g+仅备注+查询",
        lambda: _search_product(page, lb["name_60g"], timeout),
    )
    await run_step_with_retry(
        page, "抖店-4 勾选仅展示有备注",
        lambda: _toggle_only_remark(page, timeout),
    )
    await run_step_with_retry(
        page, "抖店-5 分配我老家",
        lambda: _batch_assign(page, lb["factory_wojia"], timeout),
    )
    logger.info("抖店 Part 1（豫南缘）已结束")


async def run_douyin_flow_part2(page: Page, cfg: dict[str, Any]) -> None:
    """抖店 Part 2: 百姓安心蛋 → 代发订单 → 可生吞谷物蛋 → 分配燕归谷."""
    lb: dict[str, str] = cfg["labels"]["douyin"]
    timeout = int(cfg.get("default_timeout_ms", 25000))

    await run_step_with_retry(
        page, "抖店-6 切换百姓安心蛋",
        lambda: _switch_shop(page, lb["shop_baixing"], timeout),
    )
    await run_step_with_retry(
        page, "抖店-7 进入代发订单",
        lambda: _navigate_dropship(page, timeout),
    )
    await run_step_with_retry(
        page, "抖店-8 搜可生吞谷物蛋",
        lambda: _search_product(page, lb["long_product_title"], timeout),
    )
    await run_step_with_retry(
        page, "抖店-9 分配燕归谷",
        lambda: _batch_assign(page, lb["factory_yangui"], timeout),
    )
    logger.info("抖店 Part 2（百姓安心蛋）已结束")


async def run_douyin_flow(page: Page, cfg: dict[str, Any]) -> None:
    await run_douyin_flow_part1(page, cfg)
    await run_douyin_flow_part2(page, cfg)
    logger.info("抖店流程已全部执行完毕")


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


async def _switch_shop(page: Page, shop_name: str, timeout: int) -> None:
    """Click '切换组织/店铺' then select the target shop by name."""
    # Ensure we're on the homepage
    if "homepage" not in page.url:
        logger.info("导航至抖店首页...")
        await page.goto(DOUYIN_HOMEPAGE, wait_until="load", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(5000)

    # Check for login
    if "login" in page.url.lower() or "passport" in page.url.lower():
        logger.warning("抖店需要登录，请在浏览器中完成登录后按回车...")
        await asyncio.to_thread(input, "按回车继续 >>> ")
        await page.wait_for_timeout(2000)
        await page.goto(DOUYIN_HOMEPAGE, wait_until="load", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(5000)

    # The shop switcher is in a hover-triggered dropdown at the top-right.
    # Based on diagnostics, the element's CSS module class is
    # `index_descTitle__IpE5P` (stable per-build).
    # We first hover over the shop-name area to reveal the dropdown,
    # then click "切换组织/店铺".
    logger.info("悬停右上角触发店铺菜单...")
    vp = page.viewport_size or {"width": 1440, "height": 900}

    # Hover at the top-right corner where the user avatar/shop name lives
    await page.mouse.move(vp["width"] - 80, 25)
    await page.wait_for_timeout(1000)

    # Try to click the shop switcher — use the exact class from diagnostics
    # plus a text filter as fallback
    logger.info("查找店铺切换入口...")
    for sel in (
        ".index_descTitle__IpE5P",
        "[class*='descTitle']",
    ):
        loc = page.locator(sel)
        cnt = await loc.count()
        if cnt > 0:
            # Find the one with "切换组织/店铺" text
            for i in range(cnt):
                el = loc.nth(i)
                try:
                    txt = (await el.inner_text()).strip()
                    if SEL_SHOP_SWITCHER in txt and await el.is_visible():
                        await el.click(timeout=timeout)
                        logger.info("已点击「%s」(selector: %s[%d])", SEL_SHOP_SWITCHER, sel, i)
                        await page.wait_for_timeout(1200)
                        # Click target shop in the dropdown
                        await click_text(page, shop_name, exact=False, timeout=timeout)
                        await page.wait_for_timeout(1500)
                        logger.info("已切换至店铺: %s", shop_name)
                        return
                except Exception:
                    continue

    raise RuntimeError(
        f"未找到可见的「{SEL_SHOP_SWITCHER}」—— "
        f"请确认浏览器已登录抖店，且页面加载完成"
    )


async def _navigate_dropship(page: Page, timeout: int) -> None:
    """Navigate to the dropship orders page.

    Tries direct URL navigation first (faster and more reliable),
    then falls back to clicking through the menu.
    """
    # Try direct URL navigation
    try:
        await page.goto(DROPSHIP_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)  # douyin loads slowly
        # Verify we landed on the right page
        if "dropshiping" in page.url:
            logger.info("已直接导航至代发订单页")
            return
    except Exception:
        pass

    # Fallback: click through navigation menu
    logger.info("通过菜单导航至代发订单...")
    await click_text(page, SEL_SHIP_CENTER, exact=False, timeout=timeout)
    await page.wait_for_timeout(1500)
    await click_text(page, SEL_FACTORY_DROPSHIP, exact=False, timeout=timeout)
    await page.wait_for_timeout(2000)
    logger.info("已通过菜单进入代发订单页")


async def _search_product(page: Page, keyword: str, timeout: int) -> None:
    """Enter product search keyword and click query."""
    inp = page.locator(SEL_PRODUCT_INPUT).first
    if await inp.count() > 0:
        await inp.click(timeout=10000)
        await page.wait_for_timeout(500)
        await inp.fill("")
        await inp.fill(keyword)
        await page.wait_for_timeout(400)
        logger.info("已输入搜索词: %s", keyword)
    else:
        logger.warning("未找到商品搜索输入框")

    await click_text(page, SEL_QUERY_BTN, exact=False, timeout=timeout)
    await page.wait_for_timeout(2000)  # wait for results


async def _toggle_only_remark(page: Page, timeout: int) -> None:
    """Toggle the '仅展示有备注的订单' checkbox."""
    # Click the label text first (common pattern in auxo framework)
    await click_text(page, SEL_ONLY_REMARK, exact=False, timeout=timeout)
    await page.wait_for_timeout(500)

    # Also try clicking the checkbox directly if it's not already checked
    cb = page.locator(".auxo-checkbox-input").first
    if await cb.count() > 0:
        try:
            if not await cb.is_checked():
                await cb.check(timeout=8000)
                logger.info("已勾选「仅展示有备注的订单」")
        except Exception:
            logger.debug("checkbox 操作跳过（可能已勾选）")
    await page.wait_for_timeout(300)


async def _batch_assign(page: Page, factory: str, timeout: int) -> None:
    """Select all orders → 批量分配 → search shop → select → 分配."""
    if not await list_maybe_has_orders(page):
        logger.info("无订单，跳过批量分配")
        return

    # Select all visible orders
    await _try_select_orders(page, timeout)
    await page.wait_for_timeout(400)

    # Click "批量分配"
    await click_text(page, SEL_BATCH_ASSIGN, exact=False, timeout=timeout)
    await page.wait_for_timeout(1200)  # dialog animation

    # Search for the target shop in the assign dialog
    search = page.locator(SEL_ASSIGN_SHOP_SEARCH).first
    if await search.count() > 0:
        try:
            await search.wait_for(state="visible", timeout=10000)
            await search.click(timeout=timeout)
            await search.fill("")
            await search.fill(factory)
            await page.wait_for_timeout(800)
            logger.info("已搜索厂家: %s", factory)
        except Exception as e:
            logger.warning("厂家搜索框操作失败: %s", e)

    # Select the shop from dropdown results
    await click_text(page, factory, exact=False, timeout=timeout)
    await page.wait_for_timeout(500)

    # Click "分配" to confirm
    await click_text(page, SEL_ASSIGN_CONFIRM, exact=False, timeout=timeout)
    await page.wait_for_timeout(800)

    # Confirm any dialogs
    await confirm_dialogs(page, timeout)
    logger.info("批量分配完成: %s", factory)


async def _try_select_orders(page: Page, timeout: int) -> None:
    """Select orders using the auxo checkbox pattern."""
    # Strategy 1: Click a "全选" text if available
    try:
        await try_select_all(page, "全选")
        return
    except Exception:
        pass

    # Strategy 2: Click first checkbox in the table
    cb = page.locator(".auxo-checkbox-input").first
    if await cb.count() > 0:
        try:
            if not await cb.is_checked():
                await cb.check(timeout=timeout)
                logger.info("已勾选首行订单")
                return
        except Exception:
            pass

    logger.warning("未能勾选订单，继续执行...")
