"""Action verification: confirm expected state changes after actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class ConditionType(Enum):
    ELEMENT_VISIBLE = "element_visible"
    ELEMENT_HIDDEN = "element_hidden"
    URL_CONTAINS = "url_contains"
    URL_CHANGED = "url_changed"
    INPUT_VALUE_CONTAINS = "input_contains"
    TABLE_HAS_ROWS = "table_has_rows"


@dataclass
class VerificationCondition:
    condition_type: ConditionType
    target: str
    timeout_ms: int = 10000
    description: str = ""


class VerificationError(Exception):
    """Raised when a verification condition is not met."""

    def __init__(self, message: str, condition: VerificationCondition) -> None:
        super().__init__(message)
        self.condition = condition


class ActionVerifier:
    """Verify expected state changes after UI actions."""

    def __init__(self, page: Page | None, default_timeout_ms: int = 10000) -> None:
        self._page = page
        self._before_url: str | None = None
        self.default_timeout_ms = default_timeout_ms

    def set_page(self, page: Page) -> None:
        self._page = page

    def record_before_url(self) -> None:
        if self._page:
            self._before_url = self._page.url

    async def verify(
        self, conditions: list[VerificationCondition]
    ) -> bool:
        if not self._page:
            raise RuntimeError("ActionVerifier has no page reference")
        for cond in conditions:
            if not await self._verify_single(cond):
                desc = cond.description or str(cond)
                msg = (
                    f"验证失败: {desc} "
                    f"(条件: {cond.condition_type.value}, "
                    f"目标: '{cond.target}', "
                    f"超时: {cond.timeout_ms}ms)"
                )
                raise VerificationError(msg, cond)
        return True

    async def _verify_single(self, cond: VerificationCondition) -> bool:
        timeout = cond.timeout_ms or self.default_timeout_ms
        ct = cond.condition_type

        if ct == ConditionType.ELEMENT_VISIBLE:
            return await self._check_visible(cond.target, timeout)
        elif ct == ConditionType.ELEMENT_HIDDEN:
            return await self._check_hidden(cond.target, timeout)
        elif ct == ConditionType.URL_CONTAINS:
            return await self._check_url_contains(cond.target, timeout)
        elif ct == ConditionType.URL_CHANGED:
            return await self._check_url_changed(timeout)
        elif ct == ConditionType.INPUT_VALUE_CONTAINS:
            return await self._check_input_contains(cond.target, timeout)
        elif ct == ConditionType.TABLE_HAS_ROWS:
            return await self._check_table_rows(int(cond.target or "1"), timeout)
        return False

    async def _check_visible(self, text: str, timeout: int) -> bool:
        try:
            loc = self._page.get_by_text(text, exact=False).first
            await loc.wait_for(state="visible", timeout=timeout)
            return True
        except PlaywrightTimeout:
            return False

    async def _check_hidden(self, text: str, timeout: int) -> bool:
        try:
            loc = self._page.get_by_text(text, exact=False).first
            await loc.wait_for(state="hidden", timeout=timeout)
            return True
        except PlaywrightTimeout:
            return False

    async def _check_url_contains(self, fragment: str, timeout: int) -> bool:
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            if fragment in self._page.url:
                return True
            await asyncio.sleep(0.3)
        return False

    async def _check_url_changed(self, timeout: int) -> bool:
        import asyncio

        if self._before_url is None:
            return False
        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            if self._page.url != self._before_url:
                return True
            await asyncio.sleep(0.3)
        return False

    async def _check_input_contains(self, expected: str, timeout: int) -> bool:
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            inputs = self._page.locator("input")
            count = await inputs.count()
            for i in range(min(count, 20)):
                try:
                    val = await inputs.nth(i).input_value()
                    if expected in val:
                        return True
                except Exception:
                    continue
            await asyncio.sleep(0.4)
        return False

    async def _check_table_rows(self, min_rows: int, timeout: int) -> bool:
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            rows = self._page.locator(
                "table tbody tr:not([class*='empty']), "
                "[class*='table'] [class*='row']:not([class*='header']):not([class*='empty']), "
                "[class*='list'] [class*='item']:not([class*='header'])"
            )
            if await rows.count() >= min_rows:
                return True
            await asyncio.sleep(0.5)
        return False

    async def wait_for_navigation(self, timeout_ms: int = 15000) -> bool:
        try:
            await self._page.wait_for_url("**", timeout=timeout_ms)
            return True
        except PlaywrightTimeout:
            return False
