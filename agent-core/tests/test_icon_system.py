"""圖示建構系統的自動稽核。

一致性不是靠美感維持的，是靠約束。約束沒有強制力就會漂移 ——
半年後有人加一枚 1.5px 線寬、方端點、五個元素的圖示，整套就散了。
這支測試把建構規則變成機器可檢查的條件。

規則（與 agent_ui/static/icons.js 檔頭的宣告一致）：
  · 網格 24×24，所有座標落在 [0, 24]（留 2px 邊距 → 實際內容建議在 2~22）
  · 線寬 2、端點/轉角 round、無填充
  · 每個圖示最多 3 個造型元素
  · 不使用 <text> / <image> / 外部參照
"""
import re
from pathlib import Path

import pytest

ICONS_JS = Path(__file__).parent.parent / "agent_ui" / "static" / "icons.js"

GRID = 24
MAX_SHAPES = 3
BLEED = 0.5          # 容許極小的視覺溢出（圓端點會超出座標一點點）


def _icons():
    """從 icons.js 取出 {name: svg_body}。刻意用正規表示式讀原始碼而不是執行 JS：
    測試要驗的是「檔案裡寫了什麼」，不是「執行後變成什麼」。"""
    src = ICONS_JS.read_text(encoding="utf-8")
    body = src[src.index("const P = {"):src.index("const VB")]
    out = {}
    for m in re.finditer(r"^\s{4}([a-zA-Z_]+):\s*'(.*)',\s*$", body, re.M):
        out[m.group(1)] = m.group(2)
    return out


ICONS = _icons()


def test_registry_is_not_empty():
    assert len(ICONS) >= 30, f"只讀到 {len(ICONS)} 枚圖示，解析可能壞了"


@pytest.mark.parametrize("name", sorted(ICONS))
def test_shape_count_within_limit(name):
    """細節密度一致：有的很繁複、有的很空曠，看起來就不是同一套。"""
    svg = ICONS[name]
    shapes = len(re.findall(r"<(path|circle|rect|line|polyline|polygon)\b", svg))
    assert shapes <= MAX_SHAPES, f"{name} 有 {shapes} 個造型元素，超過上限 {MAX_SHAPES}"


@pytest.mark.parametrize("name", sorted(ICONS))
def test_no_inline_style_overrides(name):
    """線寬、端點、填充一律由 icon() 統一設定；圖示本體不得自己覆寫，
    否則就會出現『這一枚看起來比較粗』這種漂移。"""
    svg = ICONS[name]
    for attr in ("stroke-width", "stroke-linecap", "stroke-linejoin", "fill=", "style="):
        assert attr not in svg, f"{name} 自行覆寫了 {attr}，會破壞全系統一致性"


@pytest.mark.parametrize("name", sorted(ICONS))
def test_no_text_or_external_references(name):
    """<text> 會受字型影響、<image> 是外部資源（CSP 會擋），都不可用。"""
    svg = ICONS[name]
    for tag in ("<text", "<image", "url(", "xlink:", "<use"):
        assert tag not in svg, f"{name} 使用了 {tag}"


@pytest.mark.parametrize("name", sorted(ICONS))
def test_absolute_coordinates_stay_inside_the_grid(name):
    """絕對座標必須落在 24×24 網格內。

    只驗絕對指令（M/L 大寫）與幾何屬性（cx/cy/x/y/…）—— 路徑的相對指令
    （l/a/…）帶的是位移量不是座標，弧線旗標還會跟數字黏在一起
    （`a2 2 0 001.8 3`），拿去比大小會得到假警報。
    真正的邊界檢查靠瀏覽器實測 bbox（見 scripts/check_icon_bbox.py）。
    """
    svg = ICONS[name]
    nums = []
    for m in re.finditer(r'\b(?:cx|cy|r|x|y|width|height|x1|y1|x2|y2)="(-?\d+\.?\d*)"', svg):
        nums.append(float(m.group(1)))
    for m in re.finditer(r"[ML]\s*(-?\d+\.?\d*)[ ,](-?\d+\.?\d*)", svg):
        nums += [float(m.group(1)), float(m.group(2))]
    bad = [n for n in nums if n < -BLEED or n > GRID + BLEED]
    assert not bad, f"{name} 有超出 0~{GRID} 網格的絕對座標：{bad[:5]}"


@pytest.mark.parametrize("name", sorted(ICONS))
def test_icon_actually_draws_something(name):
    assert len(ICONS[name]) > 20, f"{name} 內容過短，可能是空的"


def test_icon_helper_sets_the_shared_constraints():
    """線寬 2 / round / 無填充 / currentColor 必須由 icon() 一處設定。
    一處設定 = 只有一個地方能改 = 不會出現半套。"""
    src = ICONS_JS.read_text(encoding="utf-8")
    for token in ('stroke-width="2"', 'stroke-linecap="round"',
                  'stroke-linejoin="round"', 'fill="none"', 'stroke="currentColor"'):
        assert token in src, f"icon() 沒有統一設定 {token}"


def test_unknown_icon_returns_empty_not_broken_markup():
    """打錯名字時要安靜地不輸出，而不是吐出壞掉的 SVG 讓版面爆掉。"""
    src = ICONS_JS.read_text(encoding="utf-8")
    assert "if (!d) return" in src


def test_trading_specific_icons_exist():
    """交易領域的概念開源套件沒有，必須自行提供 —— 少一個就會被迫退回 emoji，
    一致性就破一個洞。"""
    for n in ("liquidation", "funding", "reconcile", "position", "staking",
              "onchain", "orderbook", "flow", "sentiment", "wallet"):
        assert n in ICONS, f"缺少交易專屬圖示：{n}"


def test_no_emoji_leaked_into_the_icon_registry():
    src = ICONS_JS.read_text(encoding="utf-8")
    body = src[src.index("const P = {"):src.index("const VB")]
    emoji = re.findall(r"[\U0001F300-\U0001FAFF]", body)
    assert not emoji, f"圖示定義裡混入了 emoji：{emoji}"
