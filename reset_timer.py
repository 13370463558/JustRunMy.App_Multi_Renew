#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import subprocess
import requests
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
DOMAIN    = "justrunmy.app"

# ============================================================
#  环境变量与全局变量
# ============================================================
EMAIL        = os.environ.get("EML")
PASSWORD     = os.environ.get("EMLP")   # 注意：PWD 是 shell 保留变量(工作目录)，会冲突，故改名 EMLP
TG_BOT_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_ID")

if not EMAIL or not PASSWORD:
    print("致命错误：未找到 EML 或 EMLP 环境变量！")
    print("请检查 GitHub Repository Secrets 是否配置正确（EML_1, EMLP）。")
    sys.exit(1)

# 全局变量，用于动态保存网页上抓取到的应用名称
DYNAMIC_APP_NAME = "未知应用"

# ============================================================
#  截图模块：每个重要步骤都保存一张截图
#  （存入 screenshots/ 目录，文件名带时间戳，避免互相覆盖）
# ============================================================
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
SHOT_SEQ = 0  # 递增序号，保证截图顺序

def init_shot_dir():
    os.makedirs(SHOT_DIR, exist_ok=True)

def shot(sb, tag: str):
    """保存一张截图。tag 为步骤说明（如 login_page、login_ok）。"""
    global SHOT_SEQ
    SHOT_SEQ += 1
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(SHOT_DIR, f"{SHOT_SEQ:02d}_{ts}_{tag}.png")
    try:
        sb.save_screenshot(path)
        print(f"  📸 截图已保存: {path}")
    except Exception as e:
        print(f"  ⚠️ 截图失败({tag}): {e}")

def list_shots():
    print("\n========================================")
    print("本次运行生成的截图清单:")
    print("========================================")
    try:
        files = sorted(os.listdir(SHOT_DIR))
        for f in files:
            print(f"  {os.path.join(SHOT_DIR, f)}")
    except Exception as e:
        print(f"  读取截图目录失败: {e}")

# ============================================================
#  Telegram 推送模块
# ============================================================
def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 TG_TOKEN 或 TG_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    text = (
        f"{DYNAMIC_APP_NAME}\n"
        f"{status_icon} {status_text}\n"
        f"剩余: {time_left}\n"
        f"时间: {current_time_str}"
    )

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("  Telegram 通知发送成功！")
        else:
            print(f"  Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  Telegram 通知发送异常: {e}")

# ============================================================
#  页面注入脚本 (Turnstile 辅助)
# ============================================================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

# 从 FREE APP TIMER 卡片的文本里提取倒计时数值（如 "1 day 11:59" 或 "19:08"）
# 不依赖具体 CSS class，基于语义定位，页面改版也不易失效。
_COUNTDOWN_JS = """
(function(){
    var els = document.querySelectorAll('*');
    for (var i = 0; i < els.length; i++) {
        var t = (els[i].textContent || '').replace(/\\s+/g, ' ').trim();
        if (t.indexOf('FREE APP TIMER') >= 0 && t.indexOf('until automatic stop') >= 0) {
            var m = t.match(/(\\d+\\s+d[a-z]*\\b[^,]*|\\d{1,2}:\\d{2})/i);
            if (m) return m[0];
        }
    }
    return '';
})()
"""

def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
        
    bar = wi["oh"] - wi["ih"]
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"  物理级点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    
    if sb.execute_script(_SOLVED_JS):
        print("  已静默通过")
        return True

    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"  Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)
        
        _click_turnstile(sb)
        
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"  Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  第 {attempt + 1} 次未通过，重试...")

    print("  Turnstile 6 次均失败")
    return False

def click_by_text(sb, candidates, timeout=8, exact_only=False):
    """忽略大小写地点击文本匹配的按钮/链接/role=button。

    candidates : 候选文本列表(字符串)。优先精确匹配，再子串匹配。
    exact_only : 为 True 时只做精确匹配(忽略大小写)。
    返回 True 表示已点击；否则返回 False。会把页面元素文本打印到日志方便排查。
    """
    import time as _t
    cands = [str(c).lower() for c in candidates]
    selectors = ["button", "a", "[role='button']", "input[type='button']", "input[type='submit']"]

    def _collect():
        els = []
        for sel in selectors:
            try:
                els.extend(sb.find_elements(sel))
            except Exception:
                continue
        return els

    def _text(el):
        try:
            return (el.text or "").strip()
        except Exception:
            return ""

    end = _t.time() + timeout
    while _t.time() < end:
        els = _collect()
        texts = [t for t in (_text(e) for e in els) if t]
        if texts:
            print(f"  页面元素文本: {texts}")
        # 精确匹配
        for el in els:
            t = _text(el)
            if t and t.lower() in cands:
                try:
                    el.click()
                    print(f"  ✅ 点击成功: [{t}]")
                    return True
                except Exception as e:
                    print(f"  点击 [{t}] 失败: {e}")
        # 子串匹配
        if not exact_only:
            for el in els:
                t = _text(el)
                if t and any(c in t.lower() for c in cands):
                    try:
                        el.click()
                        print(f"  ✅ 点击成功(子串): [{t}]")
                        return True
                    except Exception as e:
                        print(f"  点击 [{t}] 失败: {e}")
        _t.sleep(0.5)
    return False


def login(sb) -> bool:
    print(f"打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(4)

    shot(sb, "02_登录页加载")

    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
    except Exception:
        print("页面未加载出登录表单")
        shot(sb, "03_登录表单加载失败")
        return False

    print("关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print(f"填写邮箱...")
    js_fill_input(sb, 'input[name="Email"]', EMAIL)
    time.sleep(0.3)
    
    print("填写密码...")
    js_fill_input(sb, 'input[name="Password"]', PASSWORD)
    time.sleep(1)
    shot(sb, "04_已填写邮箱密码")

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("登录界面的 Turnstile 验证失败")
            shot(sb, "05_登录turnstile失败")
            return False
        shot(sb, "05_登录turnstile通过")
    else:
        print("未检测到 Turnstile")
        shot(sb, "05_无turnstile直接提交")

    print("敲击回车提交表单...")
    sb.press_keys('input[name="Password"]', '\n')

    print("等待登录跳转...")
    for _ in range(12):
        time.sleep(1)
        if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
            break

    if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
        print("登录成功！")
        shot(sb, "06_登录成功")
        return True
        
    print("登录失败，页面没有跳转。")
    shot(sb, "07_登录失败")
    return False

def renew(sb) -> bool:
    global DYNAMIC_APP_NAME
    print("\n" + "="*50)
    print("   开始自动续期流程")
    print("="*50)
    
    print("进入控制面板: https://justrunmy.app/panel")
    shot(sb, "08_打开控制面板")
    sb.open("https://justrunmy.app/panel")
    time.sleep(5)
    shot(sb, "09_控制面板加载")

    print("自动读取应用名称...")
    retry_count = 3
    found = False
    for attempt in range(1, retry_count + 1):
        try:
            sb.wait_for_element('h3.font-semibold', timeout=15)
            DYNAMIC_APP_NAME = sb.get_text('h3.font-semibold')
            print(f"成功抓取到应用名称: {DYNAMIC_APP_NAME}")
            shot(sb, "10_应用卡片定位")
            
            sb.click('h3.font-semibold')
            time.sleep(3)
            print(f"成功进入应用详情页: {sb.get_current_url()}")
            shot(sb, "11_应用详情页")
            found = True
            break
        except Exception as e:
            if attempt < retry_count:
                print(f"第 {attempt} 次尝试获取应用卡片失败，刷新页面重试...")
                sb.refresh()
                time.sleep(5)
    
    if not found:
        shot(sb, "50_找不到应用卡片")
        send_tg_message("[X]", "续期失败(找不到应用)", "未知")
        return False

    print("点击 Reset Timer 按钮...")
    try:
        shot(sb, "12_点击ResetTimer前")
        if not click_by_text(sb, ["Reset timer", "Reset Timer", "reset timer", "Reset"], timeout=8):
            raise Exception("未匹配到 Reset timer 按钮")
        time.sleep(3)
        shot(sb, "13_点击ResetTimer后")
    except Exception as e:
        print(f"找不到 Reset Timer 按钮: {e}")
        shot(sb, "51_找不到ResetTimer按钮")
        send_tg_message("[X]", "续期失败(找不到按钮)", "未知")
        return False

    print("检查续期弹窗内是否需要 CF 验证...")
    shot(sb, "14_续期弹窗")
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("弹窗内的 Turnstile 验证失败")
            shot(sb, "52_弹窗turnstile失败")
            send_tg_message("[X]", "续期失败(人机验证未过)", "未知")
            return False
        shot(sb, "15_弹窗turnstile通过")

    print("点击 Just Reset 确认续期...")
    try:
        shot(sb, "16_确认弹窗打开")
        if not click_by_text(sb, ["Just Reset", "Just reset", "just reset", "Confirm", "Reset"], timeout=8, exact_only=True):
            # 精确匹配失败，退回到子串匹配（更宽松）
            if not click_by_text(sb, ["just reset", "confirm", "reset"], timeout=5):
                raise Exception("未匹配到 Just Reset 确认按钮")
        print("提交续期请求，等待服务器处理...")
        time.sleep(5)
        shot(sb, "17_已提交续期")
    except Exception as e:
        print(f"找不到 Just Reset 按钮: {e}")
        shot(sb, "53_找不到确认按钮")
        send_tg_message("[X]", "续期失败(无法确认)", "未知")
        return False

    print("验证最终倒计时状态...")
    try:
        # 不 refresh：提交后页面已自动更新倒计时(截图可见)。
        # 直接轮询抓取，等 FREE APP TIMER 卡片渲染完成，避免 SPA 刷新后的骨架屏。
        timer_text = ""
        for attempt in range(12):
            timer_text = sb.execute_script(_COUNTDOWN_JS) or ""
            if timer_text:
                break
            time.sleep(1)
        print(f"当前应用剩余时间: {timer_text}")

        # 成功标准：倒计时已重置到"天"级（如 1 day 11:59 / 3 days），
        # 而续期前是"小时:分钟"级（如 19:08），因此出现 day 即代表续期成功。
        if re.search(r"\b\d+\s+d[a-z]*\b", timer_text, re.IGNORECASE):
            print("续期任务圆满完成！")
            shot(sb, "99_续期成功_OK")
            send_tg_message("[OK]", "续期完成", timer_text)
            return True
        else:
            print("倒计时似乎没有重置到天级，请人工检查截图。")
            shot(sb, "98_倒计时异常警告")
            send_tg_message("[!]", "续期异常(请检查)", timer_text)
            return True
    except Exception as e:
        print(f"读取倒计时失败，但流程已执行完毕: {e}")
        shot(sb, "97_倒计时读取失败")
        send_tg_message("[!]", "读取剩余时间失败", "未知")
        return False

def main():
    print("=" * 50)
    print("   JustRunMy.app 自动登录与续期脚本")
    print("=" * 50)
    
    init_shot_dir()
    
    proxy_url_env = os.environ.get("PROXY_URL", "").strip()
    sb_kwargs = {"uc": True, "test": True, "headless": False}
    
    if proxy_url_env:
        local_proxy = "http://127.0.0.1:8080"
        print(f"检测到代理配置，挂载本地通道: {local_proxy}")
        sb_kwargs["proxy"] = local_proxy
    
    with SB(**sb_kwargs) as sb:
        print("浏览器已启动")
        shot(sb, "00_浏览器已启动")
        try:
            sb.open("https://api.ipify.org/?format=json")
            print(f"当前出口 IP: {sb.get_text('body')}")
            shot(sb, "01_出口IP")
        except Exception:
            pass

        if login(sb):
            renew(sb)
        else:
            print("\n登录环节失败，终止后续续期操作。")
            shot(sb, "70_登录失败_终止")
            send_tg_message("[X]", "登录失败", "未知")
    
    list_shots()

if __name__ == "__main__":
    main()
