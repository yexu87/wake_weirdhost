#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weirdhost 服务器唤醒脚本（强化 Cloudflare 处理）
"""

import os
import sys
import time
import random
from urllib.parse import unquote
from datetime import datetime

from seleniumbase import SB

def get_env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val is None or not str(val).strip():
        return default
    return str(val).strip()

# ==================== 配置 ====================
SERVER_ID = get_env("SERVER_ID", "2932f1f7")
SERVER_URL = f"https://hub.weirdhost.xyz/server/{SERVER_ID}"
DOMAIN = "hub.weirdhost.xyz"

DEFAULT_COOKIE = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d=eyJpdiI6IlJZLzFDUnFKUnpQanJtQ1B6M2xMeVE9PSIsInZhbHVlIjoiNmdmQVYvOFduMy8rWjFuYlVUam95d3JycUxleFJLTHlDVHZydngvRjMwS0lSVG9wRDlZWjFha2QrVkkvaDNnNDFBU2lXeVF2QzlqYXpuSXNXdml0Nk9zdDlKOHZsUDBlUWkvanF5dWpUYmZHZ0JLUU5XWHRFQ2JFS1BGMVhKaHNaVUczOTAzb1FWZTl3R21wVGZJbkdRMXZHbFRFMy9nUjJoSmJrVTZtM3k3S2FscmdQMkorcGJUZzNOdFBUalFvczVqRFMvUC8raXd6cmx5QkMyYzBWNHgvejd4akNyLzRoZi9UV0VndmlpRT0iLCJtYWMiOiIxYmNhM2IyN2Q0ZTA4NWIzZTNlYzhhYjYzMDE4MjBkNTc1N2ZlY2Y5NWQwMjE2YmJkYTYyZjNkYjM4YjRkZWQzIiwidGFnIjoiIn0%3D"

COOKIE_RAW = get_env("WEIRDHOST_COOKIE", DEFAULT_COOKIE)

WAKE_BUTTON_TEXTS = ["지금 깨우기", "깨우기", "Wake", "Start"]

def parse_cookie(raw: str):
    raw = raw.strip()
    if "-----" in raw:
        raw = raw.split("-----", 1)[1].strip()
    if "=" not in raw:
        return None, None
    name, value = raw.split("=", 1)
    return name.strip(), unquote(value.strip())

def random_delay(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))

def main():
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[信息] 开始时间: {start_time}")
    print(f"[信息] 目标服务器: {SERVER_URL}")

    if not COOKIE_RAW:
        print("❌ 未设置 WEIRDHOST_COOKIE")
        sys.exit(1)

    name, value = parse_cookie(COOKIE_RAW)
    if not name or not name.startswith("remember_web"):
        print("❌ Cookie 格式错误")
        sys.exit(1)

    print(f"[调试] Cookie名称={name}")

    # headless=False + xvfb，UC 模式更容易过 Cloudflare
    with SB(uc=True, headless=False, locale_code="ko", maximize=True) as sb:
        try:
            # 1. 先打开域名并注入 Cookie
            print("[信息] 打开域名并注入 Cookie...")
            sb.uc_open_with_reconnect(f"https://{DOMAIN}/", reconnect_time=3)
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

            # 2. 打开服务器页面（带重连，利于过 CF）
            print("[信息] 打开服务器页面...")
            sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=4)
            random_delay(3, 5)

            # 3. 尝试处理 Cloudflare Turnstile
            for i in range(8):
                page = sb.get_page_source().lower()
                title = ""
                try:
                    title = sb.get_title().lower()
                except Exception:
                    pass

                if "just a moment" in title or "turnstile" in page or "cf-turnstile" in page or "checking your browser" in page:
                    print(f"[信息] Cloudflare 验证中... ({i+1}/8)")
                    try:
                        sb.uc_gui_click_captcha()
                    except Exception:
                        pass
                    time.sleep(4)
                else:
                    break

            # 4. 再等一会儿，确保页面加载完成
            random_delay(2, 4)
            sb.wait_for_ready_state_complete(timeout=15)

            # 5. 检查是否在休眠状态
            page = sb.get_page_source()
            print(f"[调试] 页面长度={len(page)}")

            is_sleeping = any(k in page for k in ["수면중", "지금 깨우기", "서버가 수면", "수면중이에요"])
            if is_sleeping:
                print("[信息] 检测到休眠状态，准备点击唤醒")
            else:
                print("[信息] 未直接检测到休眠文字，仍尝试找按钮")
                # 保存截图方便排查
                sb.save_screenshot("page_debug.png")
                print("[调试] 已保存 page_debug.png")

            # 6. 点击唤醒按钮
            clicked = False

            # 方式1：按文字找 button
            for text in WAKE_BUTTON_TEXTS:
                try:
                    xpath = f"//button[contains(normalize-space(.), '{text}')]"
                    if sb.is_element_visible(xpath, timeout=3):
                        sb.click(xpath)
                        print(f"[成功] 点击按钮：「{text}」")
                        clicked = True
                        break
                except Exception as e:
                    print(f"[调试] 文字「{text}」未点到: {e}")

            # 方式2：按常见 class / 颜色找蓝色按钮
            if not clicked:
                selectors = [
                    "button.bg-blue-500",
                    "button[class*='blue']",
                    "button.btn-primary",
                    "//button[contains(@class,'blue')]",
                    "div button:first-of-type",
                ]
                for sel in selectors:
                    try:
                        if sb.is_element_visible(sel, timeout=2):
                            sb.click(sel)
                            print(f"[成功] 点击兜底选择器: {sel}")
                            clicked = True
                            break
                    except Exception:
                        continue

            # 方式3：用 JS 强行点包含「깨우기」的按钮
            if not clicked:
                try:
                    js = """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].innerText.indexOf('깨우기') >= 0 ||
                            buttons[i].innerText.indexOf('Wake') >= 0) {
                            buttons[i].click();
                            return buttons[i].innerText;
                        }
                    }
                    return null;
                    """
                    result = sb.execute_script(js)
                    if result:
                        print(f"[成功] JS 点击了按钮: {result}")
                        clicked = True
                except Exception as e:
                    print(f"[调试] JS 点击失败: {e}")

            if not clicked:
                sb.save_screenshot("wake_fail.png")
                print("❌ 找不到唤醒按钮，已保存 wake_fail.png")
                # 再打印一点页面信息
                try:
                    print("[调试] 当前标题:", sb.get_title())
                    print("[调试] 页面是否含 수면중:", "수면중" in page)
                    print("[调试] 页面是否含 깨우기:", "깨우기" in page)
                except Exception:
                    pass
                sys.exit(2)

            # 7. 等待结果
            random_delay(5, 8)
            page2 = sb.get_page_source()

            if "수면중" not in page2 and "지금 깨우기" not in page2:
                print("✅ 唤醒成功！休眠遮罩已消失")
            else:
                print("⚠️ 已点击按钮，遮罩可能还在（服务器启动中）")
                sb.save_screenshot("after_click.png")

        except Exception as e:
            print(f"❌ 异常: {e}")
            try:
                sb.save_screenshot("error.png")
            except Exception:
                pass
            sys.exit(3)

if __name__ == "__main__":
    main()
