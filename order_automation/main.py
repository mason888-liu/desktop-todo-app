from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from .dgj_flow import run_dgj_flow, run_dgj_flow_part1, run_dgj_flow_part2, run_dgj_flow_part3
from .douyin_flow import run_douyin_flow, run_douyin_flow_part1, run_douyin_flow_part2
from .helpers import load_config
from .checkpoint import CheckpointManager
from .observability import StepObserver
from .action_verifier import ActionVerifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("order_automation")


def _config_path() -> Path:
    env = os.environ.get("ORDER_AUTOMATION_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "config.yaml"


# Ordered step IDs for checkpoint/resume
ALL_DGJ_STEPS = [
    "店管家-1 订单管理-所有订单",
    "店管家-2 同步订单",
    "店管家-3 待发货+自营",
    "店管家-4 确认筛选并查询",
    "店管家-5 批量退审",
    "店管家-6 重置并待审核",
    "店管家-7 -JD+省份查询",
    "店管家-8 备注富硒蛋+分配陈坡",
    "店管家-9 清省份查-JD",
    "店管家-10 分配杨建",
    "店管家-11 重置查陈坡",
    "店管家-12 分配陈坡(切回)",
    "店管家-13 重置查60g",
    "店管家-14 备注发顺丰",
    "店管家-15 重置查询(收尾)",
]

ALL_DOUYIN_STEPS = [
    "抖店-1 切换豫南缘",
    "抖店-2 进入代发订单",
    "抖店-3 搜60g+仅备注+查询",
    "抖店-4 勾选仅展示有备注",
    "抖店-5 分配我老家",
    "抖店-6 切换百姓安心蛋",
    "抖店-7 进入代发订单",
    "抖店-8 搜可生吞谷物蛋",
    "抖店-9 分配燕归谷",
]


async def _amain(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config) if args.config else _config_path()
    if not cfg_path.is_file():
        logger.error(
            "未找到配置文件: %s（可复制 config.example.yaml 为 config.yaml）",
            cfg_path,
        )
        return 2

    cfg = load_config(cfg_path)
    headless = bool(cfg.get("headless", False))
    slow_mo = int(cfg.get("slow_mo", 0))
    nav_timeout = int(cfg.get("navigation_timeout_ms", 60_000))
    storage = (cfg.get("storage_state") or "").strip()

    # ------------------------------------------------------------------
    # Initialize infrastructure modules
    # ------------------------------------------------------------------
    pkg_dir = Path(__file__).resolve().parent

    run_dir = pkg_dir / "run_logs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    observer = StepObserver(
        run_dir,
        screenshot_on_step=cfg.get("screenshot_on_step", True),
        screenshot_on_failure=cfg.get("screenshot_on_failure", True),
        json_log=cfg.get("json_log", True),
    )
    logger.info("运行日志目录: %s", run_dir)

    dgj_checkpoint = CheckpointManager(pkg_dir / ".checkpoint_dgj.json", flow_name="dgj")
    douyin_checkpoint = CheckpointManager(pkg_dir / ".checkpoint_douyin.json", flow_name="douyin")

    verifier = ActionVerifier(None, default_timeout_ms=cfg.get("verify_timeout_ms", 10000))

    # ------------------------------------------------------------------
    # Checkpoint resume prompting
    # ------------------------------------------------------------------
    rnd = args.round
    resume_dgj = 0
    resume_douyin = 0

    if rnd in ("all",) and not args.douyin_only:
        resume_dgj = dgj_checkpoint.prompt_resume(ALL_DGJ_STEPS)
    if rnd in ("all",) and not args.dgj_only:
        resume_douyin = douyin_checkpoint.prompt_resume(ALL_DOUYIN_STEPS)

    # ------------------------------------------------------------------
    # Launch browser
    # ------------------------------------------------------------------
    tabbit_cfg: dict = cfg.get("tabbit", {}) or {}
    use_tabbit = bool(tabbit_cfg.get("enabled", False))

    async with async_playwright() as p:
        if use_tabbit:
            # Kill existing Tabbit to release user data dir lock
            import subprocess
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "Tabbit Browser.exe"],
                    timeout=8, capture_output=True,
                )
            except Exception:
                pass
            await asyncio.sleep(3)  # wait for OS to release lock

            tabbit_exe = tabbit_cfg.get("executable", "")
            tabbit_ud = tabbit_cfg.get("user_data_dir", "")
            if not tabbit_exe or not tabbit_ud:
                logger.error("tabbit 配置缺少 executable 或 user_data_dir")
                return 2
            logger.info("使用 Tabbit 浏览器: %s", tabbit_exe)
            context = await p.chromium.launch_persistent_context(
                tabbit_ud,
                executable_path=tabbit_exe,
                headless=headless,
                slow_mo=slow_mo,
                locale="zh-CN",
                viewport={"width": 1440, "height": 900},
            )
            browser = None  # persistent context has no separate browser handle
        else:
            browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
            ctx_kwargs: dict = {
                "locale": "zh-CN",
                "viewport": {"width": 1440, "height": 900},
            }
            if storage and Path(storage).is_file():
                ctx_kwargs["storage_state"] = storage
                logger.info("已加载登录态: %s", storage)
            context = await browser.new_context(**ctx_kwargs)

        context.set_default_timeout(int(cfg.get("default_timeout_ms", 25000)))

        if use_tabbit:
            dgj_page = context.pages[0] if context.pages else await context.new_page()
            dy_page = await context.new_page()
        else:
            dgj_page = await context.new_page()
            dy_page = await context.new_page()

        verifier.set_page(dgj_page)

        # Navigate only to needed platforms
        if not args.douyin_only:
            await dgj_page.goto(cfg["dgj_url"], wait_until="domcontentloaded", timeout=nav_timeout)
        if not args.dgj_only:
            await dy_page.goto(cfg["douyin_url"], wait_until="domcontentloaded", timeout=nav_timeout)

        # Pause for manual login if needed (skipped for Tabbit — login is persisted)
        if not use_tabbit and (args.pause or (not storage and not args.no_pause)):
            logger.info(
                "请在两个标签中完成登录并确保能进入订单模块，然后按回车继续…"
            )
            await asyncio.to_thread(input, "按回车开始自动执行 >>> ")

        # ------------------------------------------------------------------
        # Execute flows
        # ------------------------------------------------------------------
        total_steps = 0
        passed = 0
        failed = 0
        skipped = 0

        try:
            if not args.douyin_only:
                verifier.set_page(dgj_page)
                if rnd == "all":
                    await run_dgj_flow(dgj_page, cfg)
                elif rnd == "dgj-1":
                    # Skip steps already completed if resuming
                    if resume_dgj > 0:
                        for step in ALL_DGJ_STEPS[: min(resume_dgj, 6)]:
                            dgj_checkpoint.mark_step_completed(step)
                    await run_dgj_flow_part1(dgj_page, cfg)
                elif rnd == "dgj-2":
                    await run_dgj_flow_part2(dgj_page, cfg)
                elif rnd == "dgj-3":
                    await run_dgj_flow_part3(dgj_page, cfg)

            if not args.dgj_only:
                verifier.set_page(dy_page)
                if rnd == "all":
                    await run_douyin_flow(dy_page, cfg)
                elif rnd == "dy-1":
                    await run_douyin_flow_part1(dy_page, cfg)
                elif rnd == "dy-2":
                    await run_douyin_flow_part2(dy_page, cfg)

        except Exception as e:
            logger.error("流程执行出错: %s", e)
            # Log artifact paths if available
            if hasattr(e, "screenshot_path") and e.screenshot_path:
                logger.error("  失败截图: %s", e.screenshot_path)
            if hasattr(e, "dom_snapshot_path") and e.dom_snapshot_path:
                logger.error("  DOM 快照: %s", e.dom_snapshot_path)
            if hasattr(e, "page_url") and e.page_url:
                logger.error("  页面 URL: %s", e.page_url)
            failed += 1
            return 3

        # ------------------------------------------------------------------
        # Cleanup on full completion
        # ------------------------------------------------------------------
        if rnd == "all":
            dgj_checkpoint.clear()
            douyin_checkpoint.clear()
            logger.info("断点文件已清理")

        observer.on_flow_complete(
            total=len(ALL_DGJ_STEPS) + len(ALL_DOUYIN_STEPS),
            passed=passed,
            failed=failed,
            skipped=skipped,
        )

        # Close all tabs to avoid accumulation (user feedback)
        for p in context.pages:
            try:
                await p.close()
            except Exception:
                pass

        await context.close()
        if browser is not None:
            await browser.close()

    logger.info("全部步骤执行结束")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="店管家 + 抖店 订单处理自动化（Playwright）")
    parser.add_argument(
        "--config", "-c",
        help="config.yaml 路径，默认环境变量 ORDER_AUTOMATION_CONFIG 或包内 config.yaml",
    )
    parser.add_argument(
        "--pause", action="store_true",
        help="即使有 storage_state 也在开始前暂停等待回车",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="无 storage_state 也不暂停（不推荐）",
    )
    parser.add_argument("--dgj-only", action="store_true", help="只跑店管家")
    parser.add_argument("--douyin-only", action="store_true", help="只跑抖店")
    parser.add_argument(
        "--round", "-r",
        choices=("all", "dgj-1", "dgj-2", "dgj-3", "dy-1", "dy-2"),
        default="all",
        help="指定执行轮次（默认 all 全流程）",
    )
    args = parser.parse_args()
    if args.dgj_only and args.douyin_only:
        logger.error("不能同时指定 --dgj-only 与 --douyin-only")
        sys.exit(2)
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
