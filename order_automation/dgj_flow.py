from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import Page

from .helpers import (
    click_text,
    confirm_dialogs,
    confirm_input_contains,
    fill_filter_input,
    list_maybe_has_orders,
    run_step_with_retry,
    try_select_all,
    wait_for_text_hidden,
)

logger = logging.getLogger(__name__)

# -- Stable element IDs from real UI (layui/wu-* framework) ---------------
ID_QUERY = "#SeachConditions"
ID_RESET = "#ResetConditions"
ID_SELECT_ALL = "#allcheckorder"
ID_PROVINCE = "#selectToProvince"
ID_NOTE_AREA = "#txt_area_seller_remark_flag"
NAME_PRODUCT_CODE = "input[name='ProductCargoNumber'], [class*='ProductCargoNumberInput']"
NAME_PRODUCT_NAME = "input[name='ProductSubject'], [class*='ProductSubjectInput']"
NAME_ORDER_TYPE = "[name='AgentOrder']"
CLASS_FACTORY_SEARCH = ".selectWrap-search-input"
CLASS_FACTORY_OPTION = ".radio-label"
CLASS_DIALOG_CONFIRM = ".layui-layer-btn0"
CLASS_BATCH_SELLER_NOTE = "UpdateOrderSellerRemark"
CLASS_BATCH_ASSIGN_FACTORY = "ManualCheck"
CLASS_BATCH_REJECT = "CheckOrder"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


async def run_dgj_flow_part1(page: Page, cfg: dict[str, Any]) -> None:
    """店管家 Round 1: 待发货+自营 → 查询 → 批量退审 → 重置待审核."""
    lb: dict[str, str] = cfg["labels"]["dgj"]
    timeout = int(cfg.get("default_timeout_ms", 25000))

    await run_step_with_retry(
        page, "店管家-1 订单管理-所有订单",
        lambda: _nav_all_orders(page, lb, timeout),
    )
    await run_step_with_retry(
        page, "店管家-2 同步订单",
        lambda: _step_sync(page, lb, timeout),
    )
    await run_step_with_retry(
        page, "店管家-3 待发货+自营",
        lambda: _step_pending_self(page, lb, timeout),
    )
    await run_step_with_retry(
        page, "店管家-4 确认筛选并查询",
        lambda: _click_query(page),
    )
    await run_step_with_retry(
        page, "店管家-5 批量退审",
        lambda: _step_batch_reject(page, lb, timeout),
    )
    await run_step_with_retry(
        page, "店管家-6 重置并待审核",
        lambda: _step_reset_and_review(page, lb),
    )
    logger.info("店管家 dgj-1（Round 1）已结束")


async def run_dgj_flow_part2(page: Page, cfg: dict[str, Any]) -> None:
    """店管家 Round 2-3: -JD+省份 → 备注 → 分配陈坡 → 分配杨建."""
    lb: dict[str, str] = cfg["labels"]["dgj"]
    timeout = int(cfg.get("default_timeout_ms", 25000))

    await run_step_with_retry(
        page, "店管家-7 -JD+省份查询",
        lambda: _step_jd_province_query(page, lb),
    )
    await run_step_with_retry(
        page, "店管家-8 备注富硒蛋+分配陈坡",
        lambda: _step_note_and_assign(page, lb, lb["note_egg"],
                                       lb["factory_chenpo_label"], timeout),
    )
    await run_step_with_retry(
        page, "店管家-9 清省份查-JD",
        lambda: _step_clear_province_query(page),
    )
    await run_step_with_retry(
        page, "店管家-10 分配杨建",
        lambda: _step_assign_factory(page, lb, lb["factory_yangjian_label"], timeout),
    )
    logger.info("店管家 dgj-2（Round 2-3）已结束")


async def run_dgj_flow_part3(page: Page, cfg: dict[str, Any]) -> None:
    """店管家 Round 4-5: 商品编码陈坡 → 切回陈坡 → 商品名60g → 备注顺丰."""
    lb: dict[str, str] = cfg["labels"]["dgj"]
    timeout = int(cfg.get("default_timeout_ms", 25000))

    await run_step_with_retry(
        page, "店管家-11 重置查陈坡",
        lambda: _step_reset_and_code_query(page, lb["code_chenpo"]),
    )
    await run_step_with_retry(
        page, "店管家-12 分配陈坡(切回)",
        lambda: _step_assign_factory(page, lb, lb["factory_chenpo_label"], timeout),
    )
    await run_step_with_retry(
        page, "店管家-13 重置查60g",
        lambda: _step_reset_and_name_query(page, lb["name_60g"]),
    )
    await run_step_with_retry(
        page, "店管家-14 备注发顺丰",
        lambda: _step_note_sf(page, lb, timeout),
    )
    # Cleanup
    await run_step_with_retry(
        page, "店管家-15 重置查询(收尾)",
        lambda: _click_reset_and_query(page),
    )
    logger.info("店管家 dgj-3（Round 4-5）已结束")


async def run_dgj_flow(page: Page, cfg: dict[str, Any]) -> None:
    await run_dgj_flow_part1(page, cfg)
    await run_dgj_flow_part2(page, cfg)
    await run_dgj_flow_part3(page, cfg)
    logger.info("店管家流程已全部执行完毕")


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


async def _nav_all_orders(page: Page, lb: dict[str, str], timeout: int) -> None:
    # Check if we landed on login page (cookies may have expired)
    login_btn = page.locator("#login_btn").first
    if await login_btn.count() > 0:
        logger.info("检测到登录页面，尝试自动登录...")
        try:
            await login_btn.click(timeout=10000)
            await page.wait_for_url("**/GeneralizeIndex/**", timeout=30000)
            logger.info("登录成功，已跳转至首页")
        except Exception:
            logger.warning("自动登录失败，请手动登录后按回车...")
            await asyncio.to_thread(input, "按回车继续 >>> ")
        await page.wait_for_timeout(1500)

    # Extract token from current URL for direct navigation to fxdd (tab-based view)
    token_match = re.search(r"token=([A-F0-9]+)", page.url)
    token = token_match.group(1) if token_match else ""
    fxdd_url = (
        "https://fxdd.dgjapp.com/NewOrder/AllOrder"
        f"?token={token}&FxPageType=1&IsCustomerOrder=false"
    )
    logger.info("导航至 fxdd 订单页: %s", fxdd_url)
    await page.goto(fxdd_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2500)  # allow full page load


async def _step_sync(page: Page, lb: dict[str, str], timeout: int) -> None:
    # The sync button toggles: "同步订单" (needs click) → "自动同步中" (running)
    # Try both texts — the clickable one is what we want
    for trigger in (lb["sync_trigger"], lb.get("sync_trigger_alt", "同步订单")):
        if await page.get_by_text(trigger, exact=False).first.count() > 0:
            await click_text(page, trigger, exact=False, timeout=timeout)
            break
    else:
        logger.warning("未找到同步按钮（可能已自动同步完成），跳过")
        await page.wait_for_timeout(1000)
        return

    # Wait for sync to complete: "同步订单中" disappears
    await page.wait_for_timeout(1000)
    await wait_for_text_hidden(page, lb["syncing_hint"], timeout_ms=600_000)


async def _step_pending_self(page: Page, lb: dict[str, str], timeout: int) -> None:
    # Wait for page to stabilize after sync
    await page.wait_for_timeout(1500)

    # Click "待发货" tab — use multiple strategies
    tab_text = lb["tab_pending_ship"]
    clicked = False
    for sel in (
        page.locator(".layui-nav .layui-nav-item").filter(has_text=tab_text).first,
        page.locator("[class*='nav'] li").filter(has_text=tab_text).first,
        page.get_by_text(tab_text, exact=False).first,
        page.locator(f":has-text('{tab_text}')").first,
    ):
        if await sel.count() > 0:
            try:
                await sel.first.click(timeout=10000) if await sel.count() > 1 else await sel.click(timeout=10000)
                clicked = True
                logger.info("已点击「%s」标签", tab_text)
                break
            except Exception:
                continue
    if not clicked:
        raise RuntimeError(f"无法点击「{tab_text}」标签")

    await page.wait_for_timeout(800)

    # Native <select name="AgentOrder">: pick "自营订单" option
    sel = page.locator(NAME_ORDER_TYPE).first
    if await sel.count() > 0:
        await sel.select_option(lb["order_type_self"], timeout=timeout)
        logger.info("已选择自营订单")
    else:
        logger.warning("未找到 <select name='AgentOrder'>，尝试备用方案")
        await click_text(page, lb.get("filter_all_orders_third", "全部订单"),
                         exact=False, timeout=timeout)
        await page.wait_for_timeout(400)
        await click_text(page, lb.get("self_operated", "自营订单"),
                         exact=False, timeout=timeout)
    await page.wait_for_timeout(400)


async def _click_query(page: Page) -> None:
    await page.locator(ID_QUERY).first.click(timeout=10000)
    await page.wait_for_timeout(1000)


async def _click_reset(page: Page) -> None:
    await page.locator(ID_RESET).first.click(timeout=10000)
    await page.wait_for_timeout(600)


async def _click_reset_and_query(page: Page) -> None:
    await _click_reset(page)
    await _click_query(page)


async def _step_batch_reject(page: Page, lb: dict[str, str], timeout: int) -> None:
    if not await list_maybe_has_orders(page):
        logger.info("无订单，跳过批量退审")
        return
    await try_select_all(page, lb.get("select_all", "全选"))
    logger.info("尝试批量退审...")
    await _click_batch_menu_item(page, CLASS_BATCH_REJECT, lb["batch_reject_review"], timeout)
    await page.wait_for_timeout(1200)  # wait for dialog animation
    await confirm_dialogs(page, timeout)
    logger.info("批量退审完成")


async def _step_reset_and_review(page: Page, lb: dict[str, str]) -> None:
    await _click_reset(page)
    await click_text(page, lb["tab_pending_review"], exact=False)
    await _click_query(page)


async def _step_jd_province_query(page: Page, lb: dict[str, str]) -> None:
    # Fill product code "-JD"
    inp = page.locator(NAME_PRODUCT_CODE).first
    await inp.click(timeout=10000)
    await inp.fill("")
    await inp.fill(lb["code_jd_suffix"])
    await page.wait_for_timeout(300)
    # Verify directly on the locator we just filled
    try:
        v = await inp.input_value()
        if lb["code_jd_suffix"] not in v:
            logger.warning("产品编码输入框值校验失败: 期望含「%s」，实际「%s」", lb["code_jd_suffix"], v)
    except Exception:
        pass  # non-critical verification

    # Select province
    sel = page.locator(ID_PROVINCE).first
    if await sel.count() > 0:
        await sel.select_option(lb["province_heilongjiang"], timeout=10000)
    else:
        await click_text(page, lb.get("province_filter", "所有省份"), exact=False)
        await page.wait_for_timeout(350)
        await click_text(page, lb["province_heilongjiang"], exact=False)
    await page.wait_for_timeout(400)

    await _click_query(page)


async def _step_note_and_assign(
    page: Page, lb: dict[str, str], note: str, factory_label: str, timeout: int
) -> None:
    """Select all → batch seller note → Save, then select all → batch assign factory."""
    # -- Seller note --
    if await list_maybe_has_orders(page):
        await try_select_all(page, lb.get("select_all", "全选"))
        await _click_batch_menu_item(page, CLASS_BATCH_SELLER_NOTE, lb["batch_seller_note"], timeout)
        await page.wait_for_timeout(800)
        await _fill_note_dialog(page, note, timeout)
        await confirm_dialogs(page, timeout)  # clicks "保存"
        await page.wait_for_timeout(600)
    else:
        logger.info("无订单，跳过备注")

    # -- Assign factory --
    await _step_assign_factory(page, lb, factory_label, timeout)


async def _step_assign_factory(
    page: Page, lb: dict[str, str], factory_label: str, timeout: int
) -> None:
    """Select all → 批量指定厂家 → search → select → 确定."""
    if not await list_maybe_has_orders(page):
        logger.info("无订单，跳过分配厂家")
        return

    await try_select_all(page, lb.get("select_all", "全选"))

    # Click "批量指定厂家"
    await _click_batch_menu_item(page, CLASS_BATCH_ASSIGN_FACTORY, lb["batch_assign_factory"], timeout)
    await page.wait_for_timeout(600)

    # Inside layui dialog:
    # 1. Click "厂家供货" radio
    await click_text(page, lb["factory_radio_supplier"], exact=False, timeout=timeout)
    await page.wait_for_timeout(400)

    # 2. Open factory dropdown and search
    await click_text(page, lb["factory_dropdown_all"], exact=False, timeout=timeout)
    await page.wait_for_timeout(400)

    search = page.locator(CLASS_FACTORY_SEARCH).first
    await search.click(timeout=10000)
    await search.fill("")
    await search.fill(factory_label.split("(")[0] if "(" in factory_label else factory_label[:2])
    await page.wait_for_timeout(600)

    # 3. Select the factory option
    await click_text(page, factory_label, exact=False, timeout=timeout)

    # 4. Confirm
    await confirm_dialogs(page, timeout)  # clicks "确定"


async def _step_clear_province_query(page: Page) -> None:
    """Clear province filter (set to '所有省份') and query."""
    sel = page.locator(ID_PROVINCE).first
    if await sel.count() > 0:
        await sel.select_option("", timeout=10000)  # empty value = all provinces
    await page.wait_for_timeout(300)
    await _click_query(page)


async def _step_reset_and_code_query(page: Page, code: str) -> None:
    """Reset filters, then fill product code and query."""
    # Clear product code first (click to focus, clear)
    inp = page.locator(NAME_PRODUCT_CODE).first
    await inp.click(timeout=10000)
    await inp.fill("")
    await _click_reset(page)
    await _click_query(page)

    if code:
        await inp.click(timeout=10000)
        await inp.fill(code)
        await page.wait_for_timeout(300)
        await _click_query(page)


async def _step_reset_and_name_query(page: Page, name: str) -> None:
    """Reset filters, then fill product name and query."""
    await _click_reset(page)
    await _click_query(page)

    inp = page.locator(NAME_PRODUCT_NAME).first
    await inp.click(timeout=10000)
    await inp.fill(name)
    await page.wait_for_timeout(300)
    await _click_query(page)


async def _step_note_sf(page: Page, lb: dict[str, str], timeout: int) -> None:
    """Select all → batch seller note → fill '发顺丰' → Save."""
    if not await list_maybe_has_orders(page):
        logger.info("无订单，跳过备注发顺丰")
        return
    await try_select_all(page, lb.get("select_all", "全选"))
    await _click_batch_menu_item(page, CLASS_BATCH_SELLER_NOTE, lb["batch_seller_note"], timeout)
    await page.wait_for_timeout(800)
    await _fill_note_dialog(page, lb["note_sf"], timeout)
    await confirm_dialogs(page, timeout)  # clicks "保存"


# ---------------------------------------------------------------------------
# Dialog helpers
# ---------------------------------------------------------------------------


async def _click_batch_menu_item(page: Page, class_name: str, text: str, timeout: int) -> None:
    """Click a hidden batch-operation menu item by first expanding the dropdown.

    The batch menu items live inside a collapsible toolbar dropdown.
    We first click "批量操作" to expand the menu, then click the target LI.
    If the LI is still hidden, we dispatch a JS click directly on the element
    to trigger its onclick handler regardless of visibility.
    """
    # Click "批量操作" to expand the dropdown
    batch_toggle = page.locator(".new-export-btnShow").first
    if await batch_toggle.count() > 0:
        try:
            await batch_toggle.click(timeout=timeout)
            await page.wait_for_timeout(600)
        except Exception:
            pass
    else:
        # Fallback: click "批量操作" text
        await click_text(page, "批量操作", exact=False, timeout=timeout)
        await page.wait_for_timeout(600)

    # Try to click the LI by its unique operation class
    li = page.locator(f"li.{class_name}").first
    if await li.count() > 0:
        try:
            await li.click(timeout=timeout)
            logger.info("已点击批量菜单项: %s (class=%s)", text, class_name)
            return
        except Exception:
            pass
        # If still hidden, dispatch JS click to trigger onclick directly
        try:
            await li.evaluate("el => el.click()")
            logger.info("已通过 JS 点击批量菜单项: %s (class=%s)", text, class_name)
            return
        except Exception as e:
            logger.warning("JS 点击也失败(%s), 尝试文本点击: %s", e, text)

    # Last resort: click by text
    await click_text(page, text, exact=False, timeout=timeout)
    logger.info("已通过文本点击批量菜单项: %s", text)


async def _fill_note_dialog(page: Page, text: str, timeout: int) -> None:
    """Fill the seller-note textarea in the layui dialog."""
    await page.wait_for_timeout(2500)

    # Strategy 1: iframes first
    for frame in page.frames:
        ta = frame.locator("#txt_area_seller_remark_flag").first
        if await ta.count() > 0 and await ta.is_visible():
            try:
                await ta.click(timeout=timeout)
                await ta.fill("")
                await ta.fill(text)
                logger.info("备注已填入(iframe): %s", text)
                return
            except Exception as e:
                logger.debug("iframe fill 失败: %s", e)

    # Strategy 2: main page stable ID
    ta = page.locator("#txt_area_seller_remark_flag").first
    if await ta.count() > 0:
        if await ta.is_visible():
            try:
                await ta.click(timeout=timeout)
                await ta.fill("")
                await ta.fill(text)
                logger.info("备注已填入: %s", text)
                return
            except Exception as e:
                logger.debug("fill 失败: %s", e)
        else:
            try:
                await ta.click(force=True, timeout=timeout)
                await page.wait_for_timeout(300)
                await ta.fill("")
                await ta.fill(text, force=True)
                logger.info("备注已填入(force): %s", text)
                return
            except Exception as e:
                logger.debug("force 失败: %s", e)

    # Strategy 3: any visible textarea in dialog
    for s in (".layui-layer textarea", "textarea:visible"):
        for frame in (page,) + tuple(page.frames):
            loc = frame.locator(s) if isinstance(frame, Page) else frame.locator(s)
            for i in range(await loc.count()):
                ta_el = loc.nth(i)
                try:
                    await ta_el.click(timeout=5000)
                    await ta_el.fill("")
                    await ta_el.fill(text)
                    logger.info("备注已填入(fallback %s[%d]): %s", s, i, text)
                    return
                except Exception:
                    continue

    # Last resort: force-fill any textarea on page
    any_ta = page.locator("textarea").first
    if await any_ta.count() > 0:
        try:
            await any_ta.click(force=True, timeout=timeout)
            await any_ta.fill("")
            await any_ta.fill(text, force=True)
            logger.info("备注已填入(last-resort): %s", text)
            return
        except Exception as e:
            logger.debug("last-resort 失败: %s", e)

    raise RuntimeError("未找到可见的备注输入框")
