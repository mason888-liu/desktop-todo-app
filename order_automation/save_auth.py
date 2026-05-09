"""
一次性保存登录态，供 config.yaml 的 storage_state 使用。

用法（在项目根目录 e:\\first_cc）:
  pip install -r order_automation/requirements.txt
  playwright install chromium
  python -m order_automation.save_auth

浏览器打开后手动登录店管家与抖店，回车后会把 cookie 存到 order_automation/auth.json
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

from .helpers import load_config


def _config_path() -> Path:
    env = os.environ.get("ORDER_AUTOMATION_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "config.yaml"


async def _run() -> None:
    cfg_path = _config_path()
    if not cfg_path.is_file():
        print(f"缺少 {cfg_path}，请先复制 config.example.yaml")
        return
    cfg = load_config(cfg_path)
    out = Path(__file__).resolve().parent / "auth.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=0)
        context = await browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
        p1 = await context.new_page()
        p2 = await context.new_page()
        await p1.goto(cfg["dgj_url"], wait_until="domcontentloaded", timeout=120_000)
        await p2.goto(cfg["douyin_url"], wait_until="domcontentloaded", timeout=120_000)
        input("在两个标签中分别登录完成后，按回车保存 auth.json …")
        await context.storage_state(path=str(out))
        await browser.close()
    print(f"已写入: {out}\n请在 config.yaml 设置 storage_state: \"{out.as_posix()}\"")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
