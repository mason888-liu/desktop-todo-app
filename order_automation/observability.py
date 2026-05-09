"""Step-level observability: screenshots, JSONL logs, failure artifacts."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    step_name: str
    index: int = 0
    status: str = "started"  # started, success, failed, skipped
    selector_used: str | None = None
    duration_ms: float = 0.0
    timestamp: str = ""
    error: str | None = None
    screenshot_path: str | None = None
    dom_snapshot_path: str | None = None
    page_url: str | None = None


class StepFailureError(Exception):
    """Wraps a step failure with paths to diagnostic artifacts."""

    def __init__(
        self,
        step_name: str,
        original_error: Exception,
        screenshot_path: str | None = None,
        dom_snapshot_path: str | None = None,
        page_url: str | None = None,
    ) -> None:
        super().__init__(str(original_error))
        self.step_name = step_name
        self.original_error = original_error
        self.screenshot_path = screenshot_path
        self.dom_snapshot_path = dom_snapshot_path
        self.page_url = page_url


class StepObserver:
    """Captures screenshots, DOM snapshots, and structured logs per step.

    All output goes to `run_logs/<timestamp>/` under the output directory.
    """

    def __init__(
        self,
        output_dir: Path,
        *,
        screenshot_on_step: bool = True,
        screenshot_on_failure: bool = True,
        json_log: bool = True,
    ) -> None:
        self._dir = output_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._screenshot_on_step = screenshot_on_step
        self._screenshot_on_failure = screenshot_on_failure
        self._json_log = json_log
        self._log_file = self._dir / "steps.jsonl" if json_log else None
        self._step_index = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_step_start(self, step_name: str) -> StepRecord:
        self._step_index += 1
        return StepRecord(
            step_name=step_name,
            index=self._step_index,
            status="started",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def on_step_success(
        self,
        record: StepRecord,
        *,
        page: Page | None = None,
        selector_used: str | None = None,
    ) -> None:
        """Record a successful step. Optionally take a screenshot."""
        record.status = "success"
        record.duration_ms = self._elapsed(record.timestamp)
        record.selector_used = selector_used
        if page:
            record.page_url = page.url
        if self._screenshot_on_step and page:
            record.screenshot_path = await self._screenshot(
                page, f"{record.index:02d}_{self._slug(record.step_name)}_ok"
            )
        if self._json_log:
            self._append_json(record)
        logger.info(
            "✓ 步骤完成 [%s] (%.1fs, 策略: %s)",
            record.step_name,
            record.duration_ms / 1000,
            selector_used or "N/A",
        )

    async def on_step_skipped(self, step_name: str, reason: str) -> None:
        """Record a skipped step (e.g., no orders)."""
        self._step_index += 1
        record = StepRecord(
            step_name=step_name,
            index=self._step_index,
            status="skipped",
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=reason,
        )
        if self._json_log:
            self._append_json(record)
        logger.info("⊘ 步骤跳过: %s (%s)", step_name, reason)

    async def on_step_failure(
        self, record: StepRecord, error: Exception, page: Page
    ) -> None:
        """Record failure with screenshot + DOM snapshot."""
        record.status = "failed"
        record.duration_ms = self._elapsed(record.timestamp)
        record.error = f"{type(error).__name__}: {error}"
        record.page_url = page.url

        base = f"{record.index:02d}_{self._slug(record.step_name)}_FAIL"

        if self._screenshot_on_failure:
            record.screenshot_path = await self._screenshot(page, base)
        try:
            dom_path = self._dir / f"{base}_dom.txt"
            content = await page.content()
            dom_path.write_text(content[:200_000], encoding="utf-8")
            record.dom_snapshot_path = str(dom_path)
        except Exception as e:
            logger.warning("DOM 快照失败: %s", e)

        if self._json_log:
            self._append_json(record)

        logger.error(
            "✗ 步骤失败: %s — %s", record.step_name, record.error,
        )

        raise StepFailureError(
            step_name=record.step_name,
            original_error=error,
            screenshot_path=record.screenshot_path,
            dom_snapshot_path=record.dom_snapshot_path,
            page_url=record.page_url,
        ) from error

    def on_flow_complete(
        self, total: int, passed: int, failed: int, skipped: int
    ) -> None:
        """Write summary.json with aggregate stats."""
        summary = {
            "total_steps": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts_dir": str(self._dir),
        }
        (self._dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            "流程结束: %d 步, 成功 %d, 跳过 %d, 失败 %d",
            total, passed, skipped, failed,
        )
        logger.info("产物目录: %s", self._dir)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _slug(name: str) -> str:
        return name.replace(" ", "_").replace("/", "-").replace("\\", "-")

    @staticmethod
    def _elapsed(iso_start: str) -> float:
        try:
            start = datetime.fromisoformat(iso_start)
            return (datetime.now(timezone.utc) - start).total_seconds() * 1000
        except Exception:
            return 0.0

    async def _screenshot(self, page: Page, name: str) -> str:
        path = self._dir / f"{name}.png"
        try:
            await page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception as e:
            logger.warning("截图失败: %s", e)
            return ""

    def _append_json(self, record: StepRecord) -> None:
        if not self._log_file:
            return
        data = {
            "index": record.index,
            "step": record.step_name,
            "status": record.status,
            "duration_ms": record.duration_ms,
            "selector_used": record.selector_used,
            "timestamp": record.timestamp,
            "error": record.error,
            "screenshot": record.screenshot_path,
            "dom_snapshot": record.dom_snapshot_path,
            "page_url": record.page_url,
        }
        try:
            with self._log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("JSON 日志写入失败: %s", e)
