"""
skills/analytics/pnl_card.py — 損益對帳單卡（share-safe SVG）
=====================================================
從成交紀錄用 FIFO 配對算「已實現損益」，產生可分享的對帳單卡（SVG）。
- share-safe：預設只放『百分比 / 勝率 / 筆數 / 各市場報酬%』，不放真實餘額、金額、地址。
- 零依賴：純字串組 SVG（中文由瀏覽器字型渲染，完美）；前端可用 canvas 轉 PNG 供 Threads 等發布。
"""
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

_TZ = timezone(timedelta(hours=8))


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def compute_pnl_summary(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """FIFO 配對算已實現損益（依市場，各市場自己的計價幣）。回 share-safe 摘要。"""
    by_mkt: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in (trades or []):
        m = str(t.get("market", "")).upper()
        if m:
            by_mkt[m].append(t)

    markets: List[Dict[str, Any]] = []
    tot_wins = tot_closed = 0
    for mkt, ts in by_mkt.items():
        ts.sort(key=lambda x: x.get("created_at") or x.get("time_ms") or 0)
        lots: deque = deque()          # 未平的買入批次 [price, vol]
        realized = cost = 0.0
        wins = closed = 0
        for t in ts:
            side = str(t.get("side", "")).lower()
            price, vol = _f(t.get("price")), _f(t.get("volume"))
            if price <= 0 or vol <= 0:
                continue
            if side in ("buy", "bid"):
                lots.append([price, vol])
            else:                       # 賣出 → FIFO 配對
                rem = vol
                while rem > 1e-12 and lots:
                    bp, bv = lots[0]
                    m = min(rem, bv)
                    realized += (price - bp) * m
                    cost += bp * m
                    closed += 1
                    wins += 1 if price >= bp else 0
                    rem -= m
                    if bv - m <= 1e-12:
                        lots.popleft()
                    else:
                        lots[0][1] = bv - m
        if closed:
            markets.append({"market": mkt, "pct": round(realized / cost * 100, 2) if cost else 0.0,
                            "closed": closed, "wins": wins})
            tot_wins += wins
            tot_closed += closed

    markets.sort(key=lambda x: x["pct"], reverse=True)
    return {
        "markets": markets,
        "win_rate": round(tot_wins / tot_closed * 100, 1) if tot_closed else 0.0,
        "closed_trades": tot_closed,
        "best": markets[0] if markets else None,
        "worst": markets[-1] if markets else None,
        "generated": datetime.now(_TZ).strftime("%Y-%m-%d"),
        "note": "已實現損益（FIFO 配對、依可得成交）；統計觀察、非投資建議。",
    }


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_pnl_card_svg(summary: Dict[str, Any], handle: str = "", up_is_green: bool = True) -> str:
    """把摘要渲染成 share-safe 對帳單卡 SVG（480x600，深色品牌）。"""
    UP, DOWN = ("#2EBD85", "#F6465D") if up_is_green else ("#F6465D", "#2EBD85")
    W, H = 480, 600
    win = summary.get("win_rate", 0.0)
    n = summary.get("closed_trades", 0)
    mkts = (summary.get("markets") or [])[:5]
    best = summary.get("best")

    def color(p):
        return UP if p >= 0 else DOWN

    rows = ""
    y = 322
    maxabs = max((abs(m["pct"]) for m in mkts), default=1.0) or 1.0
    for m in mkts:
        p = m["pct"]
        bw = int(min(abs(p) / maxabs, 1.0) * 150)
        rows += (
            f'<text x="40" y="{y}" fill="#C9D4E8" font-size="17" font-weight="700">{_esc(m["market"])}</text>'
            f'<rect x="150" y="{y-13}" width="{bw}" height="16" rx="3" fill="{color(p)}" opacity="0.85"/>'
            f'<text x="440" y="{y}" fill="{color(p)}" font-size="17" font-weight="800" text-anchor="end">'
            f'{"+" if p>=0 else ""}{p:.1f}%</text>'
        )
        y += 42

    if not mkts:
        rows = f'<text x="240" y="340" fill="#7C8AA5" font-size="15" text-anchor="middle">尚無已平倉的成交可統計</text>'

    hd = f'@{_esc(handle)} · ' if handle else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,'PingFang TC','Noto Sans TC','Microsoft JhengHei',sans-serif">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#141F35"/><stop offset="1" stop-color="#0E1626"/></linearGradient></defs>
  <rect width="{W}" height="{H}" rx="28" fill="url(#bg)"/>
  <rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="28" fill="none" stroke="#2E4592" stroke-opacity="0.5"/>
  <!-- header -->
  <circle cx="46" cy="52" r="16" fill="#2E4592"/>
  <text x="46" y="58" fill="#fff" font-size="17" font-weight="800" text-anchor="middle">M</text>
  <text x="72" y="49" fill="#EAF0FA" font-size="19" font-weight="800">MAIA · 交易對帳單</text>
  <text x="72" y="69" fill="#7C8AA5" font-size="13">{_esc(summary.get("generated",""))} · 已實現損益 (FIFO)</text>
  <!-- 勝率大字 -->
  <text x="40" y="150" fill="#7C8AA5" font-size="14">勝率</text>
  <text x="40" y="205" fill="#EAF0FA" font-size="58" font-weight="800">{win:.0f}<tspan font-size="30">%</tspan></text>
  <text x="440" y="150" fill="#7C8AA5" font-size="14" text-anchor="end">已平倉筆數</text>
  <text x="440" y="205" fill="#EAF0FA" font-size="58" font-weight="800" text-anchor="end">{n}</text>
  {'<text x="40" y="248" fill="'+color(best["pct"])+'" font-size="15" font-weight="700">最佳 '+_esc(best["market"])+' '+("+" if best["pct"]>=0 else "")+f'{best["pct"]:.1f}%</text>' if best else ''}
  <line x1="40" y1="272" x2="440" y2="272" stroke="#243350" stroke-width="1"/>
  <text x="40" y="300" fill="#7C8AA5" font-size="14">各市場已實現報酬</text>
  {rows}
  <!-- footer -->
  <line x1="40" y1="{H-70}" x2="440" y2="{H-70}" stroke="#243350" stroke-width="1"/>
  <text x="40" y="{H-42}" fill="#5D6B85" font-size="12">{hd}統計觀察 · 非投資建議</text>
  <text x="440" y="{H-42}" fill="#5D6B85" font-size="12" text-anchor="end">made with MAIA</text>
  <text x="40" y="{H-22}" fill="#41506E" font-size="11">share-safe：僅顯示百分比/勝率，未含餘額或金額</text>
</svg>'''
