#!/usr/bin/env python3
"""
scripts/contrast_audit.py — 用真實瀏覽器量測介面的文字對比（WCAG AA）

為什麼要用瀏覽器而不是讀 CSS：實際對比取決於「疊起來之後」的顏色，
包含半透明背景、color-mix、繼承、以及 CSS 變數在不同主題下的解析結果。
單看原始碼算不出來。

**這支腳本本身踩過的坑，寫下來以免重蹈：**
色彩字串不可以用正規表示式解析。瀏覽器可能回傳 `rgb()`、`rgba()`、
或 `color(srgb 0.78 0.145 0.235 / 0.12)` —— 最後這種的數值是 0~1，
用 `match(/[\\d.]+/g)` 抓出來當成 0~255 會得到完全錯誤的亮度，
進而誤報一堆不存在的對比問題（實測誤報成 3.75:1，真值是 4.62:1）。
正確做法是把顏色丟給 canvas 讓瀏覽器自己解析，再逐層做 alpha 合成。

用法：
    .venv/bin/python scripts/contrast_audit.py                 # 深淺兩主題
    .venv/bin/python scripts/contrast_audit.py --theme light
    .venv/bin/python scripts/contrast_audit.py --url http://127.0.0.1:8000/
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

AUDIT_JS = r"""(() => {
  const cv = document.createElement('canvas').getContext('2d', {willReadFrequently: true});
  // 讓瀏覽器解析任何色彩語法 —— 不要自己寫 parser
  const parse = (s) => {
    cv.clearRect(0, 0, 1, 1); cv.fillStyle = '#000'; cv.fillStyle = s;
    cv.clearRect(0, 0, 1, 1); cv.fillRect(0, 0, 1, 1);
    const d = cv.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const over = (fg, bg) => [0, 1, 2].map(i => fg[3] * fg[i] + (1 - fg[3]) * bg[i]);
  const lum = (c) => {
    const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  // 有漸層/圖片背景時無法用單一顏色代表 —— 回報「無法判定」而非誤判成失敗。
  // 品牌圓標與 wordmark 都是這種情況，硬算會得到 1:1 的假警報。
  const hasImageBg = (el) => {
    let e = el;
    while (e && e !== document.documentElement) {
      const bi = getComputedStyle(e).backgroundImage;
      if (bi && bi !== 'none') return true;
      e = e.parentElement;
    }
    return false;
  };
  const bgOf = (el) => {                     // 由最上層往下合成，直到不透明
    const stack = []; let e = el;
    while (e && e !== document.documentElement) { stack.push(parse(getComputedStyle(e).backgroundColor)); e = e.parentElement; }
    stack.push(parse(getComputedStyle(document.documentElement).backgroundColor || '#fff'));
    stack.push([255, 255, 255, 1]);
    let cur = null;
    for (let i = stack.length - 1; i >= 0; i--) cur = cur ? over(stack[i], cur) : [stack[i][0], stack[i][1], stack[i][2]];
    return cur;
  };
  const out = [], skipped = [];
  document.querySelectorAll('body *').forEach((el) => {
    if (!el.offsetParent || el.children.length) return;      // 只看葉節點的可見文字
    const t = (el.textContent || '').trim();
    if (!t || t.length > 60) return;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || +st.opacity === 0) return;
    if (hasImageBg(el)) { skipped.push(t.slice(0, 30)); return; }   // 漸層背景：無法判定
    const fs = parseFloat(st.fontSize);
    const fg = parse(st.color), bg = bgOf(el);
    const l1 = lum(over(fg, bg)), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const need = (fs >= 18 || (fs >= 14 && +st.fontWeight >= 700)) ? 3 : 4.5;   // AA 大字/內文
    if (ratio < need - 0.05) out.push({text: t.slice(0, 30), ratio: +ratio.toFixed(2), need, size: Math.round(fs)});
  });
  const seen = new Set();
  return {
    fails: out.filter(r => { const k = r.text + r.ratio; if (seen.has(k)) return false; seen.add(k); return true; }),
    undetermined: [...new Set(skipped)],
  };
})()"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/")
    ap.add_argument("--theme", choices=["dark", "light", "both"], default="both")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--wait", type=float, default=13.0, help="等待頁面初始化的秒數")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    try:
        from cdp import ws_connect, call            # noqa
    except ImportError:
        print("需要 scripts/cdp.py（極簡 CDP 客戶端）", file=sys.stderr)
        return 2

    prof = f"/tmp/contrast-audit-{a.port}"
    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={a.port}", f"--user-data-dir={prof}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(5)
        req = urllib.request.Request(f"http://127.0.0.1:{a.port}/json/new?{a.url}", method="PUT")
        tab = json.load(urllib.request.urlopen(req))
        ws = ws_connect(tab["webSocketDebuggerUrl"])
        n = [0]

        def ev(expr):
            n[0] += 1
            r = call(ws, n[0], "Runtime.evaluate",
                     {"expression": expr, "returnByValue": True, "awaitPromise": True}).get("result", {})
            return r.get("result", {}).get("value")

        for m in ("Page.enable", "Runtime.enable"):
            n[0] += 1
            call(ws, n[0], m, {})
        n[0] += 1
        call(ws, n[0], "Emulation.setDeviceMetricsOverride",
             {"width": 1400, "height": 950, "deviceScaleFactor": 1, "mobile": False})
        time.sleep(a.wait)

        themes = ["dark", "light"] if a.theme == "both" else [a.theme]
        failed = 0
        for th in themes:
            ev(f"document.documentElement.setAttribute('data-theme','{th}')")
            time.sleep(1.0)
            res = ev(AUDIT_JS) or {}
            real = res.get("fails") or []
            und = res.get("undetermined") or []
            print(f"\n=== {th} 主題 ===")
            if not real:
                print("  ✅ 全部通過 WCAG AA")
            else:
                failed += len(real)
                for r in real:
                    print(f"  ❌ {r['ratio']}:1（需 {r['need']}）{r['size']}px  {r['text']}")
            if und:
                print(f"  ○ 無法自動判定 {len(und)} 項（漸層背景，需目視）："
                      + "、".join(und[:6]))
        return 1 if failed else 0
    finally:
        chrome.terminate()


if __name__ == "__main__":
    sys.exit(main())
