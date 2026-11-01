#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weirdhost 唤醒 + sing-box 代理 + 强化 Turnstile 点击
"""

import os
import sys
import time
import random
import subprocess
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

# Turnstile 坐标探测 JS（来自 Bothosting 思路）
TS_COORDS_JS = """
function findWidget(root) {
    var els = root.querySelectorAll(
        'iframe[src*="challenges.cloudflare.com"], .cf-turnstile, [id*="cf-chl"]');
    for (var i = 0; i < els.length; i++) {
        var r = els[i].getBoundingClientRect();
        if (r.width > 50 && r.height > 20) return els[i];
    }
    var all = root.querySelectorAll('*');
    for (var j = 0; j < all.length; j++) {
        if (all[j].shadowRoot) {
            var f = findWidget(all[j].shadowRoot);
            if (f) return f;
        }
    }
    return null;
}
function boxFromTokenInput() {
    var el = document.querySelector('input[name="cf-turnstile-response"]');
    var cur = el ? el.parentElement : null;
    for (var k = 0; k < 6 && cur; k++) {
        var r = cur.getBoundingClientRect();
        if (r.width > 100 && r.width < 600 && r.height > 30 && r.height < 140) return cur;
        cur = cur.parentElement;
    }
    return null;
}
var hit = findWidget(document) || boxFromTokenInput();
if (!hit) return null;
var hr = hit.getBoundingClientRect();
return {cx: Math.round(hr.x + 30), cy: Math.round(hr.y + hr.height / 2)};
"""

TURNSTILE_TOKEN_JS = """
try {
  if (window.turnstile && window.turnstile.getResponse) {
    var t = window.turnstile.getResponse();
    if (t) return t;
  }
} catch (e) {}
var el = document.querySelector('input[name="cf-turnstile-response"]');
return el ? (el.value || '') : '';
"""


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


def js(sb, script, default=None):
    try:
        r = sb.execute_script(script)
        return default if r is None else r
    except Exception:
        return default


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
        "cf-turnstile", "turnstile", "attention required",
    ]
    return any(k in title or k in page for k in keys)


def _xdotool_click(x: int, y: int):
    try:
        subprocess.run(
            ["xdotool", "mousemove", "--sync", str(x), str(y)],
            timeout=3, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"[调试] xdotool 点击失败: {e}")
        return False


def click_turnstile(sb) -> bool:
    # 1) SeleniumBase 自带
    try:
        sb.uc_gui_click_captcha()
        time.sleep(2)
        if js(sb, TURNSTILE_TOKEN_JS, ""):
            return True
    except Exception as e:
        print(f"[调试] uc_gui_click_captcha: {e}")

    # 2) 坐标 + xdotool
    coords = js(sb, TS_COORDS_JS, None)
    if not coords:
        print("[调试] 未找到 Turnstile 坐标")
        return False

    try:
        wi = js(
            sb,
            "return '' + (window.screenX||0) + '|' + (window.screenY||0) + '|' + "
            "window.outerHeight + '|' + window.innerHeight;",
            "0|0|800|768",
        )
        parts = str(wi).split("|")
        sx, sy = int(parts[0] or 0), int(parts[1] or 0)
        bar = int(parts[2] or 800) - int(parts[3] or 768)
        ax = int(coords["cx"]) + sx
        ay = int(coords["cy"]) + sy + max(bar, 0)
        print(f"[信息] xdotool 点击 Turnstile ({ax}, {ay})")
        _xdotool_click(ax, ay)
        time.sleep(3)
        return True
    except Exception as e:
        print(f"[调试] 坐标点击失败: {e}")
        return False


def solve_turnstile(sb, timeout=75) -> bool:
    deadline = time.time() + timeout
    clicks = 0
    next_click = time.time() + 3
    while time.time() < deadline:
        if not is_cloudflare(sb):
            return True
        token = js(sb, TURNSTILE_TOKEN_JS, "")
        if token:
            print("[信息] 已获取 Turnstile token")
            return True
        if time.time() >= next_click:
            clicks += 1
            print(f"[信息] 第 {clicks} 次尝试点击 Turnstile...")
            click_turnstile(sb)
            next_click = time.time() + 8 + random.uniform(0, 2)
        time.sleep(2)
    return (not is_cloudflare(sb)) or bool(js(sb, TURNSTILE_TOKEN_JS, ""))


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
        print("[信息] 未启用代理")

    with SB(**sb_kwargs) as sb:
        try:
            try:
                ip = get_current_ip(PROXY_SERVER if IS_PROXY else "")
                print(f"[信息] 当前出口 IP: {ip}")
            except Exception as e:
                print(f"[警告] 获取出口 IP 失败: {e}")

            print("[信息] 打开域名并注入 Cookie...")
            sb.uc_open_with_reconnect(f"https://{DOMAIN}/", reconnect_time=5)
            random_delay(2, 3)

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
            sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=6)
            random_delay(3, 5)

            # 强化过 CF
            if is_cloudflare(sb):
                print("[信息] 检测到 Cloudflare，开始处理 Turnstile...")
                ok = solve_turnstile(sb, timeout=80)
                if not ok:
                    print("[信息] 首次未过，重连后再试...")
                    try:
                        sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=5)
                        random_delay(3, 4)
                        ok = solve_turnstile(sb, timeout=60)
                    except Exception as e:
                        print(f"[调试] 重连失败: {e}")
                if ok:
                    print("[信息] Cloudflare / Turnstile 已通过")
                else:
                    print("[警告] Turnstile 仍可能未通过")

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
                print("❌ 仍被 Cloudflare 拦截")
                print("   当前节点是机房 IP，CF 可能持续出验证码。")
                print("   建议换住宅代理 / 更干净的节点后再试。")
                sys.exit(4)

            # 点击唤醒
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
