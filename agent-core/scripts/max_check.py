#!/usr/bin/env python3
"""
scripts/max_check.py — MAX 金鑰端到端檢查（金鑰形狀 → 公開 API → 簽章 → 逐一端點 → 後端）。

為什麼需要：像素世界右側的「我的帳戶」區整區都靠 MAX 私有 API。當它整片空白時，
六種原因的表徵**一模一樣**（前端拿到空陣列），而且 `/api/dashboard` 是 HTTP 200
回 `has_account:false`，連錯誤碼都沒有：

    1. 金鑰根本沒設                → EnvironmentError
    2. 金鑰是佔位值 / 貼錯         → The access key does not exist
    3. 金鑰有效但沒開 API 權限     → 401/403
    4. 綁了 IP 白名單、這台不在內   → 401（訊息與 3 幾乎一樣）
    5. 金鑰有效但該端點要更高權限   → 單一端點 403，其他正常
    6. 本機時鐘偏移 → nonce 被拒   → nonce is invalid

這支腳本把六者分開報，並且**逐一測右側面板實際會用到的每一支端點** ——
因為 MAX 的權限是逐端點勾選的，「餘額讀得到」不等於「成交紀錄讀得到」。

用法：
    python scripts/max_check.py                 # 全部檢查
    python scripts/max_check.py --public-only   # 只驗公開 API（不需金鑰）
    python scripts/max_check.py --no-backend    # 跳過打 agent-core 的端到端檢查
    python scripts/max_check.py --backend http://127.0.0.1:8000

離開碼：0 = 右側面板該有的資料都拿得到；1 = 有紅燈。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OK, FAIL, WARN, INFO, SKIP = "[ OK ]", "[FAIL]", "[WARN]", "[INFO]", "[SKIP]"
_failed = False


def say(tag: str, msg: str) -> None:
    global _failed
    if tag == FAIL:
        _failed = True
    print(f"{tag} {msg}", flush=True)


def _load_env() -> None:
    """讀 agent-core/.env。已經在環境裡的值優先，不覆蓋。"""
    try:
        from dotenv import load_dotenv
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(root, ".env"), override=False)
    except ImportError:
        say(WARN, "沒有 python-dotenv，只讀環境變數（若金鑰只寫在 .env 裡會誤判成沒設）")


# ── ① 金鑰形狀 ──────────────────────────────────────────────

def step_shape() -> bool:
    """金鑰有沒有設、長度像不像真的。

    真實的 MAX 金鑰是 32 個字元的英數字串。這一步不打網路，但它能在
    「明明是貼了佔位值」的情況下省下後面五步的困惑 —— 那正是本專案
    2026-08-01 的實際狀況（21/24 字元，MAX 回 access key does not exist）。
    """
    key = os.getenv("MAX_API_KEY", "").strip()
    sec = os.getenv("MAX_API_SECRET", "").strip()

    if not key or not sec:
        missing = [n for n, v in (("MAX_API_KEY", key), ("MAX_API_SECRET", sec)) if not v]
        say(FAIL, f"{' 與 '.join(missing)} 沒有設定。到 https://max.maicoin.com/apikeys 申請一組"
                  f"**唯讀**金鑰（勾 read 相關權限即可，不要勾下單/提領），寫進 agent-core/.env")
        return False

    say(INFO, f"MAX_API_KEY 長度 {len(key)}、MAX_API_SECRET 長度 {len(sec)}")
    if len(key) < 30 or len(sec) < 30:
        say(WARN, "金鑰長度短於 30 字元。MAX 實際發的是 32 字元英數字串 —— "
                  "這組很可能是佔位值或複製時被截斷，下一步大機率會回 "
                  "`The access key does not exist`")
    else:
        say(OK, "金鑰長度符合 MAX 的 32 字元格式")
    return True


# ── ② 公開 API（不需金鑰）─────────────────────────────────

def step_public() -> bool:
    """先確認「不是網路壞了、也不是 MAX 掛了」，否則後面每一格都會紅得沒有意義。"""
    try:
        from skills.max_exchange.max_public import _max_public_request
        raw = _max_public_request("/api/v3/tickers", {"markets[]": ["btctwd"]})
        last = None
        for t in (raw if isinstance(raw, list) else []):
            if str(t.get("market")) == "btctwd":
                last = t.get("last")
        if last is None:
            say(FAIL, f"公開行情端點回了非預期內容：{str(raw)[:120]}")
            return False
        say(OK, f"公開 API 可達（btctwd last = {last}）")
        return True
    except Exception as e:  # noqa: BLE001
        say(FAIL, f"連公開 API 都打不到 —— 先查網路/DNS/防火牆，不是金鑰的問題：{str(e)[:140]}")
        return False


# ── ③ 簽章與身分 ────────────────────────────────────────────

def _classify(msg: str) -> str:
    """把 MAX 的錯誤訊息翻成「該去做什麼」。"""
    m = msg.lower()
    if "access key does not exist" in m or "invalid access key" in m:
        return ("金鑰不存在 —— 這組 key 不是 MAX 發的、已被刪除、或貼錯/貼到別的交易所的。"
                "到 https://max.maicoin.com/apikeys 重新產一組並整串複製")
    if "nonce" in m:
        return ("nonce 被拒 —— 通常是本機時鐘偏移。Windows：設定 → 時間與語言 → 立即同步；"
                "或這把金鑰正被另一支程式同時使用（nonce 必須遞增）")
    if "ip" in m and ("not allow" in m or "restrict" in m or "white" in m):
        return "IP 白名單擋掉 —— 這台機器的對外 IP 不在金鑰的允許清單裡，去 apikeys 頁面加上或清空白名單"
    if "permission" in m or "forbidden" in m or "unauthorized" in m or "scope" in m:
        return "權限不足 —— 這把金鑰沒有勾選對應的讀取權限，回 apikeys 頁面補勾（唯讀即可）"
    if "signature" in m:
        return "簽章不符 —— MAX_API_SECRET 貼錯或前後有多餘空白/換行"
    return ""


def step_identity() -> bool:
    """③ 最基本的一支私有端點。它過了才代表「金鑰＋簽章」這條路是通的。"""
    try:
        from skills.max_exchange.max_private import get_max_member_info
        info = get_max_member_info()
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        say(FAIL, f"私有 API 簽章/身分驗證失敗：{msg[:160]}")
        hint = _classify(msg)
        if hint:
            say(INFO, f"→ {hint}")
        return False

    if not isinstance(info, dict) or info.get("error"):
        say(FAIL, f"身分端點回了錯誤：{str(info)[:160]}")
        return False

    kyc = info.get("account_kyc_level")
    vip = info.get("vip_tier")
    say(OK, f"金鑰有效。KYC 等級 Lv{kyc} · VIP {vip} · "
            f"maker {info.get('maker_fee_pct')}% / taker {info.get('taker_fee_pct')}%")
    if isinstance(kyc, int) and kyc < 2:
        say(WARN, f"KYC 只有 Lv{kyc}。餘額與成交紀錄通常仍讀得到，但部分資金端點需要 Lv2")
    return True


# ── ④ 右側面板逐一端點 ─────────────────────────────────────
#
# MAX 的權限是**逐端點**勾的，所以「餘額讀得到」完全不保證「成交紀錄讀得到」。
# 這張表照抄右側三個站點實際會用到的資料，一支一支測，紅的那支直接對應到
# 畫面上會空掉的哪一塊 —— 不必等做完面板才發現。

CHECKS = [
    ("現貨餘額",     "持倉艙位 · 錢包餘額",
     lambda: __import__("skills.max_exchange.max_private", fromlist=["x"]).get_max_accounts()),
    ("成交紀錄",     "損益對帳 · 已實現損益 · 近期交易統計 · 損益卡",
     lambda: __import__("skills.max_exchange.max_private", fromlist=["x"]).get_max_my_trades(limit=20)),
    ("入金紀錄",     "資金流 · 入金鏈上溯源",
     lambda: __import__("skills.max_exchange.max_private", fromlist=["x"]).get_max_fund_transactions("deposit", limit=5)),
    ("出金紀錄",     "資金流 · 提幣白名單",
     lambda: __import__("skills.max_exchange.max_private", fromlist=["x"]).get_max_fund_transactions("withdrawal", limit=5)),
    ("融資維持率",   "持倉艙位 · M-Wallet 風險",
     lambda: __import__("skills.max_exchange.max_private", fromlist=["x"]).get_max_ad_ratio()),
    ("閃兌紀錄",     "資金流 · 閃兌",
     lambda: __import__("skills.max_exchange.max_private", fromlist=["x"]).get_max_converts(limit=5)),
]


def step_endpoints() -> None:
    """④ 逐一端點。單支失敗不中斷 —— 目的正是要知道**哪幾支**壞了。"""
    for name, used_by, fn in CHECKS:
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            say(FAIL, f"{name}：{msg[:110]}   ← 會讓「{used_by}」空掉")
            hint = _classify(msg)
            if hint:
                say(INFO, f"   → {hint}")
            continue

        n = len(r) if isinstance(r, (list, dict)) else 0
        if isinstance(r, list) and not r:
            say(WARN, f"{name}：讀得到但**是空的**（帳戶沒有這類紀錄）   ← 「{used_by}」會顯示空狀態")
        else:
            say(OK, f"{name}：{n} 筆   → 供「{used_by}」")


# ── ⑤ 後端端到端 ────────────────────────────────────────────

def step_backend(base: str) -> None:
    """⑤ 前端實際打的是 agent-core 的端點，不是 MAX。這一步驗完整那條路。

    分開測的理由：金鑰對、但後端沒重啟（還抱著舊的環境變數）是很常見的一種
    「明明改好了畫面還是空的」。
    """
    try:
        import requests
    except ImportError:
        say(SKIP, "沒有 requests，跳過後端檢查")
        return

    try:
        d = requests.get(f"{base}/api/dashboard", timeout=90).json()
    except Exception as e:  # noqa: BLE001
        say(SKIP, f"打不到 agent-core（{base}）—— 後端沒開就跳過：{str(e)[:90]}")
        return

    if d.get("has_account"):
        say(OK, f"後端 /api/dashboard：{len(d.get('balances') or [])} 種資產 · "
                f"總估值 {d.get('total_value_twd')} TWD")
    else:
        err = d.get("account_error") or "（無錯誤訊息）"
        say(FAIL, f"後端 /api/dashboard 仍拿不到帳戶：{str(err)[:120]}")
        say(INFO, "   → 若上面第③④步是綠的，代表**後端沒有重新啟動**，還在用舊的環境變數。"
                  "重啟 agent-core 後再跑一次")

    try:
        p = requests.get(f"{base}/api/positions", timeout=180).json()
        pos = p.get("positions") or []
        tot = (p.get("totals") or {}).get("total_value_twd")
        if pos:
            say(OK, f"後端 /api/positions：{len(pos)} 檔艙位 · 市值 {tot} TWD · "
                    f"已實現 {(p.get('realized') or {}).get('total_twd')}")
        else:
            say(WARN, "後端 /api/positions：帳本是空的 —— FIFO 艙位卡、對帳、已實現損益都會空。"
                      "帳本靠成交紀錄建立，若第④步的『成交紀錄』是空的，這裡就一定是空的")
    except Exception as e:  # noqa: BLE001
        say(WARN, f"/api/positions 檢查略過：{str(e)[:90]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="MAX 金鑰端到端檢查")
    ap.add_argument("--public-only", action="store_true", help="只驗公開 API，不碰金鑰")
    ap.add_argument("--no-backend", action="store_true", help="跳過 agent-core 端到端檢查")
    ap.add_argument("--backend", default="http://127.0.0.1:8000", help="agent-core 位址")
    args = ap.parse_args()

    _load_env()

    print("── ① 金鑰形狀 ───────────────────────────────")
    has_key = step_shape() if not args.public_only else (say(SKIP, "--public-only"), False)[1]

    print("── ② 公開 API ──────────────────────────────")
    if not step_public():
        return 1                      # 網路都不通，後面全部沒有意義

    if args.public_only:
        return 1 if _failed else 0

    print("── ③ 簽章與身分 ────────────────────────────")
    if not has_key or not step_identity():
        print("\n金鑰這一關沒過，後面的端點檢查略過（結果只會是同一個錯誤重複六次）。")
        return 1

    print("── ④ 右側面板要用的端點 ────────────────────")
    step_endpoints()

    if not args.no_backend:
        print("── ⑤ 後端端到端 ────────────────────────────")
        step_backend(args.backend.rstrip("/"))

    print()
    print("全部通過 —— 右側「我的帳戶」區可以開工了。" if not _failed
          else "有紅燈，照上面的 → 提示處理完再跑一次。")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
