#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weirdhost 服务器唤醒（支持 sing-box / NODE_LINK 代理过 CF）
"""

import os
import sys
import time
import random
import requests
from urllib.parse import unquote
from datetime import datetime

from seleniumbase import SB


def get_env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val is None or not str(val).strip():
        return default
    return str(val).strip()


SERVER_ID = get_env("SERVER_ID", "2932f1f7")
SERVER_URL = f"https://hub.weirdhost.xyz/server/{SERVER_ID}"
DOMAIN = "hub.weirdhost.xyz"

DEFAULT_COOKIE = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d=eyJpdiI6IlJZLzFDUnFKUnpQanJtQ1B6M2xMeVE9PSIsInZhbHVlIjoiNmdmQVYvOFduMy8rWjFuYlVUam95d3JycUxleFJLTHlDVHZydngvRjMwS0lSVG9wRDlZWjFha2QrVkkvaDNnNDFBU2lXeVF2QzlqYXpuSXNXdml0Nk9zdDlKOHZsUDBlUWkvanF5dWpUYmZHZ0JLUU5XWHRFQ2JFS1BGMVhKaHNaVUczOTAzb1FWZTl3R21wVGZJbkdRMXZHbFRFMy9nUjJoSmJrVTZtM3k3S2FscmdQMkorcGJUZzNOdFBUalFvczVqRFMvUC8raXd6cmx5QkMyYzBWNHgvejd4akNyLzRoZi9UV0VndmlpRT0iLCJtYWMiOiIxYmNhM2IyN2Q0ZTA4NWIzZTNlYzhhYjYzMDE4MjBkNTc1N2ZlY2Y5NWQwMjE2YmJkYTYyZjNkYjM4YjRkZWQzIiwidGFnIjoiIn0%3D"

COOKIE_RAW = get_env("WEIRDHOST_COOKIE", DEFAULT_COOKIE)
IS_PROXY = get_env("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = get_env("PROXY_SERVER", "http://127.0.0.1:1080")

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


def get_current_ip(proxy: str = "") -> str:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
    r.raise_for_status()
    return r.text.strip()


def is_cloudflare(sb) -> bool:
    try:
        title = sb.get_title().lower()
    except Exception:
        title = ""
    try:
        page = sb.get_page_source().lower()
    except Exception:
        page = ""
    keys = [
        "just a moment", "잠시만 기다리", "checking your browser",
        "cf-turnstile", "turnstile", "cloudflare", "attention required",
    ]
    return any(k in title or k in page for k in keys)


def main():
    print(f"[信息] 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[信息] 目标服务器: {SERVER_URL}")

    if not COOKIE_RAW:
        print("❌ 未设置 WEIRDHOST_COOKIE")
        sys.exit(1)

    name, value = parse_cookie(COOKIE_RAW)
    if not name or not name.startswith("remember_web"):
        print("❌ Cookie 格式错误")
        sys.exit(1)

    print(f"[调试] Cookie名称={name}")

    sb_kwargs = {
        "uc": True,
        "headless": False,
        "locale_code": "ko",
        "maximize": True,
    }

    if IS_PROXY:
        print(f"[信息] 使用代理: {PROXY_SERVER}")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("[信息] 未启用代理（直连，易被 CF 拦截）")

    with SB(**sb_kwargs) as sb:
        try:
            try:
                ip = get_current_ip(PROXY_SERVER if IS_PROXY else "")
                print(f"[信息] 当前出口 IP: {ip}")
            except Exception as e:
                print(f"[警告] 获取出口 IP 失败: {e}")

            print("[信息] 打开域名并注入 Cookie...")
            sb.uc_open_with_reconnect(f"https://{DOMAIN}/", reconnect_time=4)
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

            print("[信息] 打开服务器页面...")
            sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=5)
            random_delay(3, 5)

            for i in range(12):
                if not is_cloudflare(sb):
                    print("[信息] Cloudflare 已通过")
                    break
                print(f"[信息] Cloudflare 验证中... ({i+1}/12)")
                try:
                    sb.uc_gui_click_captcha()
                except Exception as e:
                    print(f"[调试] captcha: {e}")
                if i in (3, 7):
                    try:
                        sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=4)
                    except Exception:
                        pass
                time.sleep(4)
            else:
                print("[警告] Cloudflare 可能仍未通过")

            random_delay(2, 3)
            try:
                sb.wait_for_ready_state_complete(timeout=15)
            except Exception:
                pass

            page = sb.get_page_source()
            title = ""
            try:
                title = sb.get_title()
            except Exception:
                pass
            print(f"[调试] 标题: {title}")
            print(f"[调试] 含 수면중: {'수면중' in page}, 含 깨우기: {'깨우기' in page}")

            if is_cloudflare(sb):
                sb.save_screenshot("cf_blocked.png")
                print("❌ 仍被 Cloudflare 拦截，检查节点是否可用")
                sys.exit(4)

            clicked = False
            for text in WAKE_BUTTON_TEXTS:
                xpath = f"//button[contains(normalize-space(.), '{text}')]"
                try:
                    try:
                        sb.wait_for_element_visible(xpath, timeout=5)
                    except TypeError:
                        if not sb.is_element_visible(xpath):
                            continue
                    sb.click(xpath)
                    print(f"[成功] 点击：「{text}」")
                    clicked = True
                    break
                except Exception as e:
                    print(f"[调试] 「{text}」: {e}")

            if not clicked:
                try:
                    result = sb.execute_script("""
                        var buttons = document.querySelectorAll('button');
                        for (var i = 0; i < buttons.length; i++) {
                            var t = buttons[i].innerText || '';
                            if (t.indexOf('깨우기') >= 0 || t.indexOf('Wake') >= 0) {
                                buttons[i].click();
                                return t;
                            }
                        }
                        return null;
                    """)
                    if result:
                        print(f"[成功] JS 点击: {result}")
                        clicked = True
                except Exception as e:
                    print(f"[调试] JS 失败: {e}")

            if not clicked:
                sb.save_screenshot("wake_fail.png")
                print("❌ 找不到唤醒按钮")
                sys.exit(2)

            random_delay(5, 8)
            page2 = sb.get_page_source()
            if "수면중" not in page2 and "지금 깨우기" not in page2:
                print("✅ 唤醒成功！休眠遮罩已消失")
            else:
                print("⚠️ 已点击，遮罩可能还在（启动中）")
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
