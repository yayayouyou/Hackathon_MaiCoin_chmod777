"""
skills/analytics/position_ledger.py — 事件帳本 + 對帳（艙位/損益的地基）

為什麼需要：交易所只給「餘額快照」＋分散在多支 API 的流水，沒有艙位概念。
實測證明只用成交紀錄推算持倉，5 個幣種全部對不上——因為餘額還來自
閃兌、質押獎勵、入出金、錢包互轉。本模組把所有「會動到餘額」的事件正規化成
統一帳本（append-only、增量同步、依 uid 去重），並提供對帳報告。
**沒有對帳，後面算出來的損益都不可信。**

去重要點（實測）：站內轉帳(internal_transfers) 與 入/出金(fund_transactions) 是
同一批事件（20 筆入金 vs 17 筆站內轉入，交集 16）→ 只採 fund_transactions，
否則會重複計算。
"""
import os
import json
from typing import Dict, Any, List, Optional
from loguru import logger

_LEDGER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "conversation_logs", "position_ledger.jsonl",
)
_markets_cache: Optional[Dict[str, tuple]] = None


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _markets() -> Dict[str, tuple]:
    """market id → (base, quote)。必須用 API 的 base_unit/quote_unit —— 字串裁切會出錯
    （例：'usdttwd' 去掉 twd/usdt 會變空字串）。"""
    global _markets_cache
    if _markets_cache is None:
        try:
            from skills.max_exchange.max_public import get_max_markets
            _markets_cache = {m["id"]: (str(m.get("base_unit", "")).upper(),
                                        str(m.get("quote_unit", "")).upper())
                              for m in (get_max_markets() or [])}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"取得 markets 失敗，base/quote 解析降級：{e}")
            _markets_cache = {}
    return _markets_cache


def _fetch_all(path: str, params: Dict[str, Any], ts_field: str = "created_at",
               max_pages: int = 20) -> List[Dict[str, Any]]:
    """分頁抓滿：API 單次上限 1000，用 timestamp 往更早翻頁直到沒有新紀錄。
    （實測：獎勵有 815 筆，只抓 500 會漏；成交 176 筆已是全部。）"""
    from skills.max_exchange.max_private import _max_private_request
    out: List[Dict[str, Any]] = []
    seen: set = set()
    cursor = None
    for _ in range(max_pages):
        p = dict(params)
        p["limit"] = 1000
        if cursor:
            p["timestamp"] = cursor
        try:
            batch = _max_private_request(path, p)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{path} 分頁抓取失敗：{e}")
            break
        if not isinstance(batch, list) or not batch:
            break
        new = 0
        for r in batch:
            rid = str(r.get("id") or r.get("sn") or r.get("uuid") or "")
            if rid and rid in seen:
                continue
            seen.add(rid)
            out.append(r)
            new += 1
        if new == 0:
            break
        try:
            oldest = min(int(r.get(ts_field) or 0) for r in batch)
        except (TypeError, ValueError):
            break
        if not oldest or oldest == cursor:
            break
        cursor = oldest
    return out


def _ev(uid, ts, source, currency, delta, disposal=False, price=None,
        quote=None, quote_amount=None, note="") -> Dict[str, Any]:
    return {"uid": uid, "ts": int(ts or 0), "source": source,
            "currency": str(currency).upper(), "delta": round(float(delta), 12),
            "disposal": bool(disposal), "price": price, "quote": quote,
            "quote_amount": quote_amount, "note": note}


def fetch_events(limit: int = 1000) -> List[Dict[str, Any]]:
    """從各來源抓取並正規化成統一事件（只涵蓋現貨錢包；站內轉帳不重複計入）。"""
    from skills.max_exchange.max_private import (
        get_max_my_trades, get_max_converts, get_max_fund_transactions, _max_private_request)
    ev: List[Dict[str, Any]] = []
    mk = _markets()

    # 1) 成交（只取現貨錢包；base/quote/手續費 三個方向）
    try:
        for t in (get_max_my_trades(limit=limit) or []):
            if str(t.get("wallet_type", "spot")).lower() not in ("spot", ""):
                continue
            mid = str(t.get("market", "")).lower()
            base, quote = mk.get(mid, ("", ""))
            if not base:
                continue
            tid, ts = t.get("id"), t.get("created_at")
            buy = str(t.get("side", "")).lower() in ("buy", "bid")
            vol, funds, price = _f(t.get("volume")), _f(t.get("funds")), _f(t.get("price"))
            ev.append(_ev(f"trade:{tid}:base", ts, "trade", base, vol if buy else -vol,
                          disposal=not buy, price=price, quote=quote, quote_amount=funds,
                          note=f"{'買' if buy else '賣'} {mid}"))
            ev.append(_ev(f"trade:{tid}:quote", ts, "trade", quote, -funds if buy else funds,
                          disposal=(buy and quote != "TWD"), price=None, note=f"{mid} 計價幣"))
            fee, fcur = _f(t.get("fee")), str(t.get("fee_currency", "")).upper()
            if fee > 0 and fcur:
                ev.append(_ev(f"trade:{tid}:fee", ts, "fee", fcur, -fee, note="成交手續費"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"成交事件抓取失敗：{e}")

    # 2) 閃兌（不在成交紀錄裡！from 端為處分）
    try:
        for c in (get_max_converts(limit=200) or []):
            sn, ts = c.get("sn"), c.get("time_ms")
            fa, ta = _f(c.get("from_amount")), _f(c.get("to_amount"))
            fc, tc = c.get("from_currency"), c.get("to_currency")
            if fc and fa:
                # 賣出腿的「賣得多少」＝換到的 to_amount（不帶這個就算不出閃兌的已實現損益）
                ev.append(_ev(f"convert:{sn}:from", ts, "convert", fc, -fa, disposal=(fc != "TWD"),
                              price=(ta / fa if fa else None), quote=tc, quote_amount=ta,
                              note=f"閃兌 {fc}→{tc}"))
            if tc and ta:
                ev.append(_ev(f"convert:{sn}:to", ts, "convert", tc, ta,
                              price=(fa / ta if ta else None), quote=fc, quote_amount=fa,
                              note=f"閃兌 {fc}→{tc}"))
            fee, fcur = _f(c.get("fee")), str(c.get("fee_currency", "")).upper()
            if fee > 0 and fcur:
                ev.append(_ev(f"convert:{sn}:fee", ts, "fee", fcur, -fee, note="閃兌手續費"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"閃兌事件抓取失敗：{e}")

    # 3) 獎勵（白拿 → 無成本基礎，P2 依政策定價）※ 實測 815 筆，需分頁抓滿
    try:
        for r in (_fetch_all("/api/v3/rewards", {}) or []):
            amt = _f(r.get("amount"))
            if amt:
                ev.append(_ev(f"reward:{r.get('uuid')}", r.get("created_at"), "reward",
                              r.get("currency"), amt, note=f"獎勵 {r.get('type','')}"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"獎勵事件抓取失敗：{e}")

    # 4) 入金 / 出金（出金是「轉移」不是處分；含提幣手續費）
    for kind, sign in (("deposit", 1), ("withdrawal", -1)):
        try:
            for d in (get_max_fund_transactions(kind, limit=200) or []):
                amt = _f(d.get("amount"))
                if amt:
                    ev.append(_ev(f"{kind}:{d.get('sn')}", d.get("time_ms"), kind,
                                  d.get("currency"), sign * amt,
                                  note=("入金" if sign > 0 else "出金/提幣（轉移非處分）")))
                fee = _f(d.get("fee"))
                fcur = str(d.get("fee_currency") or d.get("currency") or "").upper()
                if kind == "withdrawal" and fee > 0 and fcur:
                    ev.append(_ev(f"{kind}:{d.get('sn')}:fee", d.get("time_ms"), "fee",
                                  fcur, -fee, note="提幣手續費"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{kind} 事件抓取失敗：{e}")

    # 5) 現貨↔融資互轉（只影響現貨側）
    try:
        for t in (get_max_fund_transactions("transfer", limit=200) or []):
            amt = _f(t.get("amount"))
            frm, to = str(t.get("from", "")).lower(), str(t.get("to", "")).lower()
            if not amt or "spot" not in (frm, to):
                continue
            delta = amt if to == "spot" else -amt
            ev.append(_ev(f"transfer:{t.get('sn')}", t.get("time_ms"), "transfer",
                          t.get("currency"), delta, note=f"錢包互轉 {frm}→{to}"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"互轉事件抓取失敗：{e}")

    # 註：internal_transfers 與 入/出金為同一批事件（實測交集 16/20）→ 不重複計入
    return ev


def load_events() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.exists(_LEDGER):
        return out
    with open(_LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def sync_ledger(limit: int = 1000, repair: bool = False) -> Dict[str, Any]:
    """抓取並增量併入本地帳本（依 uid 去重）。歷史只會越存越完整，突破 API 分頁上限。

    repair=True：同 uid 的既有事件用新版欄位覆寫後整檔重寫（正規化邏輯修正時用），
    但**只保留仍抓得到的事件之外的舊事件**，不會丟掉 API 已經給不出的歷史。"""
    existing = load_events()
    seen = {e.get("uid") for e in existing}
    fetched = fetch_events(limit=limit)
    if repair:
        by_uid = {e.get("uid"): e for e in existing}
        by_uid.update({e.get("uid"): e for e in fetched})   # 新版覆寫舊版，抓不到的保留
        merged = sorted(by_uid.values(), key=lambda x: x.get("ts") or 0)
        os.makedirs(os.path.dirname(_LEDGER), exist_ok=True)
        with open(_LEDGER, "w", encoding="utf-8") as f:
            for e in merged:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        added = len(by_uid) - len(existing)
        logger.info(f"帳本修補重寫：總計 {len(merged)}、新增 {added}")
        return {"added": added, "total": len(merged), "repaired": True, "path": _LEDGER}
    fresh = [e for e in fetched if e.get("uid") not in seen]
    if fresh:
        os.makedirs(os.path.dirname(_LEDGER), exist_ok=True)
        with open(_LEDGER, "a", encoding="utf-8") as f:
            for e in fresh:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                f.flush()
        os.fsync
    logger.info(f"帳本同步：新增 {len(fresh)}、既有 {len(existing)}")
    return {"added": len(fresh), "total": len(existing) + len(fresh), "path": _LEDGER}


def replay(events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, float]:
    """重播帳本 → 各幣種淨數量。"""
    pos: Dict[str, float] = {}
    for e in (events if events is not None else load_events()):
        pos[e["currency"]] = pos.get(e["currency"], 0.0) + _f(e.get("delta"))
    return {k: round(v, 10) for k, v in pos.items()}


def reconcile(tolerance: float = 1e-6) -> Dict[str, Any]:
    """對帳：帳本重播數量 vs 交易所實際餘額；差異即「資料不完整」的警訊。"""
    from skills.max_exchange.max_private import get_max_accounts
    events = load_events()
    calc = replay(events)
    try:
        actual = {a["currency"]: _f(a.get("total")) for a in (get_max_accounts() or [])}
    except Exception as e:  # noqa: BLE001
        return {"error": f"取得餘額失敗：{e}"}

    # 各幣種的來源組成（歸因用）
    contrib: Dict[str, Dict[str, float]] = {}
    for e in events:
        contrib.setdefault(e["currency"], {}).setdefault(e["source"], 0.0)
        contrib[e["currency"]][e["source"]] += _f(e.get("delta"))

    rows, matched = [], 0
    for cur in sorted(set(calc) | set(actual)):
        c, a = calc.get(cur, 0.0), actual.get(cur, 0.0)
        gap = a - c
        ok = abs(gap) <= max(tolerance, abs(a) * 1e-6)
        matched += 1 if ok else 0
        if ok:
            dx = "相符"
        elif c < -tolerance:
            dx = "🚩 帳本為負（現貨不可能）→ 缺更早的取得紀錄（API 歷史起點之前）"
        elif gap > 0:
            dx = "缺『取得』紀錄：實際比帳本多，有未涵蓋的入帳來源"
        else:
            dx = "缺『支出』紀錄：帳本比實際多，有未涵蓋的出帳（平台扣款/未公開流水）"
        rows.append({"currency": cur, "ledger_qty": round(c, 10), "actual_qty": round(a, 10),
                     "gap": round(gap, 10), "ok": ok, "diagnosis": dx,
                     "sources": {k: round(v, 8) for k, v in (contrib.get(cur) or {}).items()}})
    return {
        "events": len(events), "currencies": len(rows),
        "matched": matched, "mismatched": len(rows) - matched,
        "confidence": "high" if matched == len(rows) else ("partial" if matched else "low"),
        "rows": rows,
        "note": "差異＝帳本未涵蓋的來源或歷史不完整。已知成因：① API 成交歷史有起點（更早的買入抓不到）"
                "② 平台有未公開流水的通道（如定期定額/機器人，MAX 無對應 API）。損益可信度以此為準。",
    }


def reconcile_holdings(sync: bool = True) -> Dict[str, Any]:
    """工具入口：（可選）同步最新流水後做資金對帳，回傳差異與成因診斷。"""
    out: Dict[str, Any] = {}
    if sync:
        try:
            out["synced"] = sync_ledger()
        except Exception as e:  # noqa: BLE001
            out["sync_error"] = str(e)
    out.update(reconcile())
    return out


def get_cost_basis_positions() -> Dict[str, Any]:
    """工具入口：目前持倉的成本可追溯度。"""
    return build_reconciled_positions()


def build_reconciled_positions(tolerance: float = 1e-6) -> Dict[str, Any]:
    """把對帳差異補成『期初/未知來源部位』，讓數量與交易所一致 —— 但明確標記該部分
    **成本基礎未知**，供 P2 算損益時排除或依政策定價。誠實優於假裝精確。"""
    rec = reconcile(tolerance=tolerance)
    if rec.get("error"):
        return rec
    positions = {}
    for row in rec["rows"]:
        cur, gap, actual = row["currency"], row["gap"], row["actual_qty"]
        known = max(0.0, actual - max(0.0, gap))       # 可追溯成本的數量
        unknown = round(actual - known, 10)             # 期初/未知來源數量
        if actual <= tolerance:
            continue        # 已清空的幣種沒有未實現損益；其歷史差異看 reconcile()
        positions[cur] = {
            "qty": actual,                              # 以交易所實際餘額為準
            "qty_known_basis": round(known, 10),
            "qty_unknown_basis": unknown,
            "basis_coverage_pct": round(known / actual * 100, 1) if actual else 0.0,
            "diagnosis": row["diagnosis"],
        }
    cov = [p["basis_coverage_pct"] for p in positions.values() if p["qty"] > 0]
    return {
        "positions": positions,
        "avg_basis_coverage_pct": round(sum(cov) / len(cov), 1) if cov else 0.0,
        "reconcile_confidence": rec["confidence"],
        "note": "qty 以交易所餘額為準；qty_unknown_basis 為無法追溯成本的部分（期初或未公開通道），"
                "計算損益時應標示或排除，不可當作零成本。",
    }
