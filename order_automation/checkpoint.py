"""Checkpoint/resume system for multi-step automation flows."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CheckpointState:
    flow_name: str
    completed_steps: list[str] = field(default_factory=list)
    started_at: str = ""
    last_updated: str = ""


class CheckpointManager:
    """Persists completed step IDs so failed runs can resume.

    Uses atomic writes (tmp file + rename) to avoid corruption.
    """

    def __init__(self, file_path: Path, flow_name: str) -> None:
        self._file = file_path
        self._flow_name = flow_name
        self._state = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_step_completed(self, step_id: str) -> bool:
        return step_id in self._state.completed_steps

    def mark_step_completed(self, step_id: str) -> None:
        if step_id not in self._state.completed_steps:
            self._state.completed_steps.append(step_id)
        self._state.last_updated = datetime.now(timezone.utc).isoformat()
        self._save()

    def get_completed_count(self) -> int:
        return len(self._state.completed_steps)

    def get_resume_index(self, all_step_ids: list[str]) -> int | None:
        """Return index of first uncompleted step, or None if all done."""
        completed = set(self._state.completed_steps)
        for i, sid in enumerate(all_step_ids):
            if sid not in completed:
                return i
        return None if not all_step_ids else len(all_step_ids)

    def prompt_resume(self, all_step_ids: list[str]) -> int:
        """If checkpoint exists, ask user whether to resume.

        Returns 0 (start from beginning) or the resume index.
        Auto-resumes in non-interactive terminals.
        """
        done = self.get_completed_count()
        total = len(all_step_ids)
        if done == 0:
            return 0
        if done >= total:
            logger.info("断点显示流程已完成，将重新执行。")
            self.clear()
            return 0

        logger.info(
            "发现断点 [%s]: %d/%d 步已完成",
            self._flow_name, done, total,
        )

        try:
            answer = input(
                f"是否从第 {done + 1} 步继续? (已跳过 {done} 步) [Y/n] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "y"

        if answer in ("", "y", "yes"):
            resume_idx = done
            logger.info("将从第 %d 步继续执行。", resume_idx + 1)
            return resume_idx
        else:
            logger.info("放弃断点，重新开始。")
            self.clear()
            return 0

    def clear(self) -> None:
        try:
            if self._file.exists():
                self._file.unlink()
        except OSError:
            pass
        self._state = CheckpointState(flow_name=self._flow_name)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> CheckpointState:
        if not self._file.exists():
            return CheckpointState(
                flow_name=self._flow_name,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return CheckpointState(
                flow_name=data.get("flow_name", self._flow_name),
                completed_steps=data.get("completed_steps", []),
                started_at=data.get("started_at", ""),
                last_updated=data.get("last_updated", ""),
            )
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning("断点文件损坏，将创建新的: %s", e)
            return CheckpointState(
                flow_name=self._flow_name,
                started_at=datetime.now(timezone.utc).isoformat(),
            )

    def _save(self) -> None:
        data = {
            "flow_name": self._state.flow_name,
            "completed_steps": self._state.completed_steps,
            "started_at": self._state.started_at,
            "last_updated": self._state.last_updated,
        }
        tmp = self._file.with_suffix(self._file.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(self._file))
        except OSError as e:
            logger.error("写入断点文件失败: %s", e)
