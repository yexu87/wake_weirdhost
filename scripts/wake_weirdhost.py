#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weirdhost 服务器唤醒脚本（支持 Telegram 通知）
适用于 GitHub Actions 定时运行
"""

import os
import sys
import time
import random
import asyncio
import aiohttp
from urllib.parse import unquote
from datetime import datetime

from seleniumbase import SB

# ==================== 配置 ====================
SERVER_ID = os.environ.get("SERVER_ID", "2932f1f7").strip()
SERVER_URL = f"https://hub.weirdhost.xyz/server/{SERVER_ID}"
DOMAIN = "hub.weirdhost.xyz"

COOKIE_RAW = os.environ.get("WEIRDHOST_COOKIE", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()

WAKE_BUTTON_TEXTS = ["지금 깨우기", "깨우기", "Wake", "Start"]

# ==================== 工具函数 ====================
def parse_cookie(raw: str):
    raw = raw.strip()
    if "-----" in raw:
        raw = raw.split("-----", 1)[1].strip()
    if "=" not in raw:
        return None, None
    name, value = raw.split("=", 1)
    return name.strip(), unquote(value.strip())

def random_delay(a=0.8, b=2.0):
    time.sleep(random.uniform(a, b))

async def tg_send(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[信息] 未配置 Telegram，跳过通知")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            })
    except Exception as e:
        print(f"[错误] Telegram 发送失败: {e}")

def notify(text: str):
    asyncio.run(tg_send(text))

# ==================== 主逻辑 ====================
def main():
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[信息] 开始时间: {start_time}")
    print(f"[信息] 目标服务器: {SERVER_URL}")

    if not COOKIE_RAW:
        msg = "❌ <b>Weirdhost 唤醒失败</b>\n原因: 未设置 WEIRDHOST_COOKIE"
        print(msg)
        notify(msg)
        sys.exit(1)

    name, value = parse_cookie(COOKIE_RAW)
    if not name or not name.startswith("remember_web"):
        msg = "❌ <b>Weirdhost 唤醒失败</b>\n原因: Cookie 格式错误（必须以 remember_web_ 开头）"
        print(msg)
        notify(msg)
        sys.exit(1)

    success = False
    result_msg = ""

    try:
        with SB(uc=True, headless=True, locale_code="ko") as sb:
            # 1. 打开域名并注入 Cookie
            sb.open(f"https://{DOMAIN}/")
            random_delay()

            sb.driver.add_cookie({
                "name": name,
                "value": value,
                "domain": DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": True,
            })
            print("[信息] Cookie 已注入")

            # 2. 进入服务器页面
            sb.open(SERVER_URL)
            random_delay(2.5, 4)

            # 处理 Cloudflare
            for _ in range(12):
                src = sb.get_page_source().lower()
                if "turnstile" in src or "cf-turnstile" in src:
                    print("[信息] 检测到 Cloudflare，等待...")
                    time.sleep(3)
                else:
                    break

            page = sb.get_page_source()

            # 3. 判断状态
            is_sleeping = any(k in page for k in ["수면중", "지금 깨우기", "서버가 수면"])
            if is_sleeping:
                print("[信息] 服务器处于休眠状态，准备唤醒")
            else:
                print("[信息] 未检测到休眠遮罩，服务器可能已在线")

            # 4. 点击唤醒按钮
            clicked = False
            for text in WAKE_BUTTON_TEXTS:
                try:
                    xpath = f"//button[contains(., '{text}')]"
                    if sb.is_element_visible(xpath, timeout=4):
                        sb.click(xpath)
                        print(f"[成功] 已点击「{text}」")
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                # 兜底
                try:
                    sb.click("button.bg-blue-500, button[class*='blue']")
                    clicked = True
                    print("[成功] 已点击兜底按钮")
                except Exception:
                    pass

            if not clicked:
                sb.save_screenshot("wake_fail.png")
                result_msg = (
                    f"❌ <b>Weirdhost 唤醒失败</b>\n"
                    f"服务器: <code>{SERVER_ID}</code>\n"
                    f"原因: 找不到「지금 깨우기」按钮\n"
                    f"时间: {start_time}"
                )
                print(result_msg)
                notify(result_msg)
                sys.exit(2)

            # 5. 等待结果
            random_delay(4, 7)
            page2 = sb.get_page_source()

            if "수면중" not in page2 and "지금 깨우기" not in page2:
                success = True
                result_msg = (
                    f"✅ <b>Weirdhost 唤醒成功</b>\n"
                    f"服务器: <code>{SERVER_ID}</code>\n"
                    f"时间: {start_time}\n"
                    f"状态: 休眠遮罩已消失，服务器正在启动"
                )
            else:
                result_msg = (
                    f"⚠️ <b>Weirdhost 唤醒结果不确定</b>\n"
                    f"服务器: <code>{SERVER_ID}</code>\n"
                    f"时间: {start_time}\n"
                    f"状态: 已点击按钮，但遮罩仍在（可能需要更长时间）"
                )

            print(result_msg)
            notify(result_msg)

    except Exception as e:
        result_msg = (
            f"❌ <b>Weirdhost 唤醒异常</b>\n"
            f"服务器: <code>{SERVER_ID}</code>\n"
            f"错误: <code>{str(e)[:200]}</code>\n"
            f"时间: {start_time}"
        )
        print(result_msg)
        notify(result_msg)
        sys.exit(3)

    if success:
        print("[完成] 唤醒成功")
    else:
        print("[完成] 已执行，结果见上方通知")

if __name__ == "__main__":
    main()
