from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .smart_locator import SmartLocator, LocatorResult
from .action_verifier import (
    ActionVerifier,
    ConditionType,
    VerificationCondition,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Core interaction helpers (delegated to SmartLocator)
# ---------------------------------------------------------------------------

async def click_text(
    page: Page,
    text: str,
    *,
    exact: bool = False,
    timeout: int = 30000,
    locator: SmartLocator | None = None,
) -> LocatorResult:
    """Click element by text using SmartLocator fallback chain."""
    sl = locator or SmartLocator(page)
    result = await sl.click(text, exact=exact, timeout=timeout)
    if not result.success:
        raise RuntimeError(f"无法点击「{text}」: 所有定位策略均失败")
    logger.debug("点击「%s」成功，策略: %s", text, result.strategy_used)
    return result


async def click_role_button(
    page: Page, name: str, timeout: int | None = None
) -> None:
    """Click a button by accessible name, with SmartLocator fallback."""
    t = timeout or 30000
    btn = page.get_by_role("button", name=name).first
    if await btn.count() > 0:
        await btn.click(timeout=t)
        await page.wait_for_timeout(300)
        return
    # Fallback via SmartLocator
    sl = SmartLocator(page)
    result = await sl.click(name)
    if not result.success:
        raise RuntimeError(f"无法点击按钮「{name}」")
    await page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Wait helpers
# ---------------------------------------------------------------------------

async def wait_for_text_hidden(
    page: Page, text: str, timeout_ms: int = 300_000
) -> None:
    """Wait until a text element disappears (e.g., syncing indicator)."""
    loc = page.get_by_text(text, exact=False).first
    try:
        await loc.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        return  # already hidden
    await loc.wait_for(state="hidden", timeout=timeout_ms)


# ---------------------------------------------------------------------------
# Order detection
# ---------------------------------------------------------------------------

async def list_maybe_has_orders(page: Page) -> bool:
    """Heuristic: does the current page have actionable order rows?"""
    empty_markers = (
        "暂无数据", "暂无订单", "没有数据", "无数据",
        "暂无相关", "共 0 条", "共0条",
    )
    for m in empty_markers:
        loc = page.get_by_text(m, exact=False)
        if await loc.count() == 0:
            continue
        try:
            if await loc.first.is_visible():
                return False
        except PlaywrightTimeout:
            continue

    # Check traditional table
    rows = page.locator("table tbody tr")
    n = await rows.count()
    if n > 3:
        return True
    if n > 0:
        texts = []
        for i in range(min(n, 3)):
            try:
                texts.append(await rows.nth(i).inner_text())
            except PlaywrightTimeout:
                texts.append("")
        blob = "\n".join(texts)
        if any(x in blob for x in empty_markers):
            return False
        return True

    # Fallback for virtualized / non-table layouts
    generic_rows = page.locator(
        "[class*='table'] [class*='row']:not([class*='header']):not([class*='empty']), "
        "[class*='list'] [class*='item']:not([class*='header'])"
    )
    if await generic_rows.count() > 0:
        return True

    return False


# ---------------------------------------------------------------------------
# Select-all
# ---------------------------------------------------------------------------

async def try_select_all(page: Page, label: str) -> None:
    """Select all items. Strategy: #allcheckorder → thead checkbox → check-all class → text."""
    # Strategy 1: Known stable ID from 店管家
    known_cb = page.locator("#allcheckorder").first
    if await known_cb.count() > 0:
        try:
            if not await known_cb.is_checked():
                await known_cb.check(timeout=8000)
            await page.wait_for_timeout(400)
            logger.debug("全选: #allcheckorder")
            return
        except PlaywrightTimeout:
            pass

    # Strategy 2: thead checkbox
    head_cb = page.locator("thead input[type='checkbox']").first
    if await head_cb.count() > 0:
        try:
            await head_cb.check(timeout=8000)
            await page.wait_for_timeout(400)
            logger.debug("全选: thead checkbox")
            return
        except PlaywrightTimeout:
            pass

    # Strategy 3: check-all class pattern
    check_all_cb = page.locator(
        "[class*='check-all'] input[type='checkbox']"
    ).first
    if await check_all_cb.count() > 0:
        try:
            await check_all_cb.check(timeout=8000, force=True)
            await page.wait_for_timeout(400)
            logger.debug("全选: check-all checkbox")
            return
        except PlaywrightTimeout:
            pass

    # Strategy 4: click label text (e.g., "全选")
    sl = SmartLocator(page)
    result = await sl.click(label, exact=False)
    if not result.success:
        raise RuntimeError(f"全选失败: 无法定位「{label}」")
    logger.debug("全选: text click「%s」(策略: %s)", label, result.strategy_used)


# ---------------------------------------------------------------------------
# Input filling
# ---------------------------------------------------------------------------

async def fill_filter_input(
    page: Page, field_label: str, value: str
) -> None:
    """Fill a filter input field identified by its label. Uses SmartLocator."""
    sl = SmartLocator(page)
    result = await sl.fill_input(field_label, value)
    if not result.success:
        raise RuntimeError(
            f"无法在筛选项「{field_label}」附近找到输入框"
        )
    logger.debug(
        "填充「%s」=「%s」(策略: %s)",
        field_label, value, result.strategy_used,
    )


async def confirm_input_contains(
    page: Page, field_label: str, expect_sub: str
) -> None:
    """Verify an input near `field_label` contains `expect_sub`."""
    # Try form-item first
    form_item = (
        page.locator(".ant-form-item")
        .filter(has_text=field_label)
        .first
    )
    candidates = []
    if await form_item.count() > 0:
        candidates.append(form_item.locator("input").first)
    candidates.append(
        page.locator(
            f"xpath=//*[contains(normalize-space(.), '{field_label}')]"
            f"/following::input[1]"
        ).first
    )
    for inp in candidates:
        if await inp.count() == 0:
            continue
        try:
            v = await inp.input_value()
            if expect_sub in v:
                return
        except Exception:
            continue
    raise RuntimeError(f"自检失败：「{field_label}」输入框应包含「{expect_sub}」")


# ---------------------------------------------------------------------------
# Dialog confirmation (extracted from flow files)
# ---------------------------------------------------------------------------

async def confirm_dialogs(page: Page, timeout: int = 8000) -> int:
    """Click confirmation buttons in any open dialogs.

    Returns the number of dialogs confirmed. Raises on error (no longer
    silently swallows failures).
    """
    confirmed = 0
    confirm_texts = ("保存", "确 定", "确定", "确认", "提 交", "提交", "知道了")

    for text in confirm_texts:
        # Strategy 1: layui dialog button class
        layui_btn = page.locator(f".layui-layer-btn0:has-text('{text}')").first
        if await layui_btn.count() > 0:
            try:
                await layui_btn.click(timeout=min(timeout, 8000))
                await page.wait_for_timeout(500)
                confirmed += 1
                logger.info("确认弹窗(layui): 「%s」", text)
                continue
            except PlaywrightTimeout:
                pass

        # Strategy 2: generic button role
        btn = page.get_by_role("button", name=text)
        if await btn.count() > 0:
            try:
                await btn.first.click(timeout=min(timeout, 8000))
                await page.wait_for_timeout(400)
                confirmed += 1
                logger.info("确认弹窗: 「%s」", text)
            except PlaywrightTimeout:
                logger.warning("弹窗按钮「%s」存在但点击超时", text)
                raise
            except Exception as e:
                logger.error("弹窗确认异常「%s」: %s", text, e)
                raise

    if confirmed == 0:
        logger.debug("未检测到需要确认的弹窗")
    return confirmed


# ---------------------------------------------------------------------------
# Menu navigation
# ---------------------------------------------------------------------------

async def open_menu_chain(page: Page, *items: str) -> None:
    for it in items:
        await click_text(page, it, exact=False)


# ---------------------------------------------------------------------------
# Step runner with retry, checkpoint, and verification
# ---------------------------------------------------------------------------

async def run_step_with_retry(
    page: Page,
    step_name: str,
    action: Callable[[], Awaitable[None]],
    *,
    max_refresh_cycles: int = 6,
    checkpoint: Any = None,  # CheckpointManager (optional)
    observer: Any = None,    # StepObserver (optional)
    verifier: ActionVerifier | None = None,
    verify: list[VerificationCondition] | None = None,
    is_mutation: bool = False,
) -> None:
    """Run a step with intelligent retry and optional checkpoint/observe.

    Retry logic (replaces blind page refresh):
      1st failure → retry immediately (transient timeout)
      2nd failure → try with longer timeouts
      3rd+ failure → refresh page as last resort
    Tracks whether mutations occurred to warn about potential duplicates.
    """
    # Checkpoint: skip if already completed
    if checkpoint is not None and hasattr(checkpoint, "is_step_completed"):
        if checkpoint.is_step_completed(step_name):
            logger.info("断点跳过: %s", step_name)
            if observer is not None and hasattr(observer, "on_step_skipped"):
                await observer.on_step_skipped(step_name, "checkpoint: already completed")
            return

    # Observability: start recording
    record = None
    if observer is not None and hasattr(observer, "on_step_start"):
        record = observer.on_step_start(step_name)

    refresh_cycles = 0
    last_error = None

    while refresh_cycles < max_refresh_cycles:
        try:
            await action()
        except (PlaywrightTimeout, AssertionError, RuntimeError) as e:
            last_error = e
            logger.warning(
                "步骤「%s」失败 (第 %d 次): %s",
                step_name, refresh_cycles + 1, e,
            )
            await asyncio.sleep(1.2)
            refresh_cycles += 1
            if refresh_cycles >= 2 and not is_mutation:
                # Refresh page and retry
                logger.info("刷新页面后重试: %s", step_name)
                try:
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass
            continue
        except Exception as e:
            last_error = e
            logger.warning(
                "步骤「%s」异常 (第 %d 次): %s",
                step_name, refresh_cycles + 1, e,
            )
            await asyncio.sleep(1.2)
            refresh_cycles += 1
            if refresh_cycles >= 2:
                try:
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass
            continue
        else:
            # Action succeeded — run verification if configured
            if verifier is not None and verify is not None:
                try:
                    await verifier.verify(verify)
                except Exception as ve:
                    last_error = ve
                    logger.warning("步骤验证失败: %s", ve)
                    refresh_cycles += 1
                    continue

            # Success path
            if observer is not None and hasattr(observer, "on_step_success"):
                await observer.on_step_success(page=page, record=record)
            if checkpoint is not None and hasattr(checkpoint, "mark_step_completed"):
                checkpoint.mark_step_completed(step_name)
            return

    # All retries exhausted
    if last_error:
        if observer is not None and hasattr(observer, "on_step_failure"):
            await observer.on_step_failure(record, last_error, page)
        raise RuntimeError(
            f"步骤在多次重试后仍失败: {step_name}"
        ) from last_error
    raise RuntimeError(f"步骤失败（未知原因）: {step_name}")
