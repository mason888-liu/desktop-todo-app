"""Multi-strategy element locator with ordered fallback chain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


@dataclass
class LocatorResult:
    success: bool
    strategy_used: str | None = None
    locator: Locator | None = None


class SmartLocator:
    """Multi-strategy locator: stable selectors first, text last.

    Priority chain (configurable):
      1. data-testid / data-test attribute
      2. data-* attributes (data-value, data-key, data-label, data-name)
      3. ARIA role + accessible name
      4. CSS class patterns from common UI frameworks
      5. Text content (last resort, most fragile)
    """

    DEFAULT_STRATEGIES = [
        ("data-testid", 3000),
        ("data-attr", 3000),
        ("aria-role", 4000),
        ("css-class", 4000),
        ("text-content", 5000),
    ]

    def __init__(
        self,
        page: Page,
        strategies: list[tuple[str, int]] | None = None,
    ) -> None:
        self._page = page
        self._strategies = strategies or self.DEFAULT_STRATEGIES
        self._last_strategy: str | None = None

    @property
    def last_strategy(self) -> str | None:
        return self._last_strategy

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    async def _try_data_testid(self, text: str) -> Locator | None:
        for attr in ("data-testid", "data-test", "data-test-id"):
            loc = self._page.locator(f"[{attr}*='{text}' i]").first
            if await loc.count() > 0:
                try:
                    await loc.wait_for(state="visible", timeout=3000)
                    return loc
                except PlaywrightTimeout:
                    continue
        return None

    async def _try_data_attr(self, text: str) -> Locator | None:
        for attr in ("data-value", "data-key", "data-label", "data-name", "data-id"):
            loc = self._page.locator(f"[{attr}*='{text}' i]").first
            if await loc.count() > 0:
                try:
                    await loc.wait_for(state="visible", timeout=3000)
                    return loc
                except PlaywrightTimeout:
                    continue
        return None

    async def _try_aria_role(self, text: str) -> Locator | None:
        for role in ("button", "link", "option", "tab", "menuitem", "listitem"):
            loc = self._page.get_by_role(role, name=text).first
            if await loc.count() > 0:
                try:
                    await loc.wait_for(state="visible", timeout=4000)
                    return loc
                except PlaywrightTimeout:
                    continue
        # try checkbox separately (often has label not name)
        loc = self._page.get_by_role("checkbox", name=text).first
        if await loc.count() > 0:
            try:
                await loc.wait_for(state="visible", timeout=4000)
                return loc
            except PlaywrightTimeout:
                pass
        return None

    async def _try_css_class(self, text: str) -> Locator | None:
        patterns = (
            f"[class*='btn']:has-text('{text}')",
            f"[class*='tab']:has-text('{text}')",
            f"[class*='item']:has-text('{text}')",
            f"[class*='option']:has-text('{text}')",
            f"[class*='nav']:has-text('{text}')",
            f"[class*='menu']:has-text('{text}')",
            f"a:has-text('{text}')",
            f"button:has-text('{text}')",
            f"label:has-text('{text}')",
            f"span:has-text('{text}')",
        )
        for pat in patterns:
            loc = self._page.locator(pat).first
            if await loc.count() > 0:
                try:
                    await loc.wait_for(state="visible", timeout=4000)
                    return loc
                except PlaywrightTimeout:
                    continue
        return None

    async def _try_text_content(self, text: str, exact: bool = False) -> Locator | None:
        if exact:
            loc = self._page.get_by_text(text, exact=True).first
        else:
            loc = self._page.get_by_text(text, exact=False).first
        if await loc.count() > 0:
            try:
                await loc.wait_for(state="visible", timeout=5000)
                return loc
            except PlaywrightTimeout:
                pass
        # loose :has-text fallback
        loc = self._page.locator(f":has-text('{text}')").first
        if await loc.count() > 0:
            try:
                await loc.wait_for(state="visible", timeout=5000)
                return loc
            except PlaywrightTimeout:
                pass
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def click(
        self, text: str, *, exact: bool = False, timeout: int | None = None
    ) -> LocatorResult:
        strategy_funcs = {
            "data-testid": lambda: self._try_data_testid(text),
            "data-attr": lambda: self._try_data_attr(text),
            "aria-role": lambda: self._try_aria_role(text),
            "css-class": lambda: self._try_css_class(text),
            "text-content": lambda: self._try_text_content(text, exact),
        }

        for name, _ in self._strategies:
            if name not in strategy_funcs:
                continue
            try:
                loc = await strategy_funcs[name]()
                if loc is not None:
                    await loc.click(timeout=timeout or 5000)
                    self._last_strategy = name
                    logger.debug("点击「%s」成功，策略: %s", text, name)
                    return LocatorResult(True, strategy_used=name, locator=loc)
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        logger.warning("所有定位策略均失败: 「%s」", text)
        return LocatorResult(False)

    async def find(
        self, text: str, *, exact: bool = False
    ) -> LocatorResult:
        """Locate without clicking. Useful for verification."""
        strategy_funcs = {
            "data-testid": lambda: self._try_data_testid(text),
            "data-attr": lambda: self._try_data_attr(text),
            "aria-role": lambda: self._try_aria_role(text),
            "css-class": lambda: self._try_css_class(text),
            "text-content": lambda: self._try_text_content(text, exact),
        }

        for name, _ in self._strategies:
            if name not in strategy_funcs:
                continue
            try:
                loc = await strategy_funcs[name]()
                if loc is not None:
                    self._last_strategy = name
                    return LocatorResult(True, strategy_used=name, locator=loc)
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        return LocatorResult(False)

    async def fill_input(
        self, field_label: str, value: str
    ) -> LocatorResult:
        """Find input near a label and fill it. Multi-strategy fallback."""

        # Strategy 1: Ant Design form item
        form_item = self._page.locator(
            ".ant-form-item, .ecom-form-item, .auxo-form-item"
        ).filter(has_text=field_label).first
        if await form_item.count() > 0:
            inp = form_item.locator("input").first
            if await inp.count() > 0:
                await inp.click(timeout=5000)
                await inp.fill("")
                await inp.fill(value)
                self._last_strategy = "ant-form-item"
                return LocatorResult(True, "ant-form-item", inp)

        # Strategy 2: Label followed by input (XPath)
        xp = (
            f"//*[contains(normalize-space(.), '{field_label}')]"
            f"/following::input[1]"
        )
        inp = self._page.locator(xp).first
        if await inp.count() > 0:
            try:
                await inp.wait_for(state="visible", timeout=4000)
                await inp.click(timeout=5000)
                await inp.fill("")
                await inp.fill(value)
                self._last_strategy = "xpath-following"
                return LocatorResult(True, "xpath-following", inp)
            except PlaywrightTimeout:
                pass

        # Strategy 3: Input with matching placeholder
        for trial in (field_label, field_label.replace(" ", "")):
            ph_input = self._page.locator(
                f"input[placeholder*='{trial}' i]"
            ).first
            if await ph_input.count() > 0:
                await ph_input.click(timeout=5000)
                await ph_input.fill("")
                await ph_input.fill(value)
                self._last_strategy = "placeholder"
                return LocatorResult(True, "placeholder", ph_input)

            aria_input = self._page.locator(
                f"input[aria-label*='{trial}' i]"
            ).first
            if await aria_input.count() > 0:
                await aria_input.click(timeout=5000)
                await aria_input.fill("")
                await aria_input.fill(value)
                self._last_strategy = "aria-label"
                return LocatorResult(True, "aria-label", aria_input)

        # Strategy 4: Find textarea near label
        ta = self._page.locator(
            f"//*[contains(normalize-space(.), '{field_label}')]"
            f"/following::textarea[1]"
        ).first
        if await ta.count() > 0:
            try:
                await ta.wait_for(state="visible", timeout=4000)
                await ta.click(timeout=5000)
                await ta.fill("")
                await ta.fill(value)
                self._last_strategy = "xpath-textarea"
                return LocatorResult(True, "xpath-textarea", ta)
            except PlaywrightTimeout:
                pass

        logger.warning("fill_input 所有策略均失败: 「%s」", field_label)
        return LocatorResult(False)

    async def select_option(
        self, field_label: str, option_text: str
    ) -> LocatorResult:
        """Open a dropdown by label, then click the option."""

        # Strategy 1: Framework form-item with select
        row = (
            self._page.locator(
                ".ant-form-item, .ecom-form-item, .auxo-form-item"
            )
            .filter(has_text=field_label)
            .first
        )
        if await row.count() > 0:
            sel = row.locator(
                ".ant-select, .auxo-select, [class*='select']"
            ).first
            if await sel.count() > 0:
                await sel.click(timeout=5000)
                await self._page.wait_for_timeout(350)
                result = await self.click(option_text)
                if result.success:
                    result.strategy_used = f"framework-select → {result.strategy_used}"
                    return result

        # Strategy 2: Click label text, then option
        label_result = await self.click(field_label)
        if label_result.success:
            await self._page.wait_for_timeout(350)
            opt_result = await self.click(option_text)
            if opt_result.success:
                opt_result.strategy_used = f"text-click → {opt_result.strategy_used}"
                return opt_result

        return LocatorResult(False)

    async def check_checkbox(self, label_text: str) -> LocatorResult:
        """Check a checkbox by its label text."""

        # Strategy 1: Find label, then associated checkbox
        label = self._page.get_by_text(label_text, exact=False).first
        if await label.count() > 0:
            parent = label.locator("..")
            cb = parent.locator("input[type='checkbox']").first
            if await cb.count() > 0:
                if not await cb.is_checked():
                    await cb.check(timeout=5000)
                self._last_strategy = "label-parent-checkbox"
                return LocatorResult(True, "label-parent-checkbox", cb)
            # Strategy 1b: label is itself the wrapper
            cb2 = label.locator("input[type='checkbox']").first
            if await cb2.count() > 0:
                if not await cb2.is_checked():
                    await cb2.check(timeout=5000)
                self._last_strategy = "label-wrapper-checkbox"
                return LocatorResult(True, "label-wrapper-checkbox", cb2)

        # Strategy 2: Find wrapping label element
        wrapper = self._page.locator("label").filter(has_text=label_text).first
        if await wrapper.count() > 0:
            cb = wrapper.locator("input[type='checkbox']").first
            if await cb.count() > 0:
                if not await cb.is_checked():
                    await cb.check(timeout=5000)
                self._last_strategy = "label-filter-checkbox"
                return LocatorResult(True, "label-filter-checkbox", cb)
            # click label anyway
            try:
                await wrapper.click(timeout=5000)
                self._last_strategy = "label-click"
                return LocatorResult(True, "label-click", wrapper)
            except PlaywrightTimeout:
                pass

        # Strategy 3: Just click the text
        result = await self.click(label_text)
        if result.success:
            result.strategy_used = f"checkbox-text → {result.strategy_used}"
            return result

        return LocatorResult(False)
