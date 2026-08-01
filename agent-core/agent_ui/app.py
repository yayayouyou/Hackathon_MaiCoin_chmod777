"""
agent_ui/app.py

AI Crypto Trading Agent Web 展示與測試服務後端 (FastAPI)
=====================================================
"""

import os
import sys
import json
import time
import secrets
import threading
import requests
from dotenv import load_dotenv
from loguru import logger
from fastapi import FastAPI, Request, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Local/demo launches commonly invoke uvicorn directly. Load the project
# configuration before importing modules that choose their storage backend.
# Existing deployment environment variables keep precedence.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# 將專案根路徑加入 sys.path 以便加載 skills 與 agent 模組
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 開啟路由決策記錄（P3）：實際使用時把每題的意圖/工具/信心分數寫入 routing_log.jsonl，
# 供事後分析「漏工具/低信心」的題。可設 ROUTING_LOG=0 關閉。
os.environ.setdefault("ROUTING_LOG", "1")

from agent.ollama_agent import run_agent_turn
from agent.ollama_config import resolve_host, resolve_auth, DEFAULT_OLLAMA_HOST
from agent.personas import list_personas
from agent_ui import auth, store

app = FastAPI(title="MAIA · MAX AI Trading Copilot")

# PWA 靜態資源（圖示等）
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/manifest.webmanifest")
def get_manifest():
    """PWA manifest（用正確 content-type 讓瀏覽器接受安裝）。"""
    return FileResponse(os.path.join(_STATIC_DIR, "manifest.webmanifest"),
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def get_service_worker():
    """Service worker 必須從根路徑供應，scope 才涵蓋整個 app（/static/sw.js 的 scope 只有 /static）。"""
    return FileResponse(os.path.join(_STATIC_DIR, "sw.js"),
                        media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

# 核准端點 CSRF/來源防護：每次啟動產生一次性密鑰，僅透過『同源』/api/config 交給前端；
# 跨源 CSRF 頁面因同源政策讀不到此值、也無法送自訂標頭（會觸發被拒的 CORS 預檢）。
_APPROVAL_SECRET = secrets.token_urlsafe(24)
_THREADS_SYNC_STOP = threading.Event()
_THREADS_SYNC_THREAD: Optional[threading.Thread] = None
_INSIGHTS_STOP = threading.Event()
_INSIGHTS_THREAD: Optional[threading.Thread] = None


def _threads_sync_interval() -> int:
    raw = os.getenv("THREADS_SYNC_INTERVAL_SECONDS", "300")
    try:
        return max(60, int(raw))
    except ValueError:
        logger.warning("THREADS_SYNC_INTERVAL_SECONDS={!r} is invalid; using 300 seconds", raw)
        return 300


def _community_insights_check_interval() -> int:
    raw = os.getenv("COMMUNITY_INSIGHTS_CHECK_INTERVAL_SECONDS", "300")
    try:
        return max(60, int(raw))
    except ValueError:
        logger.warning("COMMUNITY_INSIGHTS_CHECK_INTERVAL_SECONDS={!r} is invalid; using 300 seconds", raw)
        return 300


def _threads_auto_sync_loop() -> None:
    """Low-frequency polling for the hackathon demo; manual sync remains available."""
    interval = _threads_sync_interval()
    while not _THREADS_SYNC_STOP.is_set():
        try:
            from agent_ui.threads_bridge import list_spaces, sync_mentions_to_spaces, sync_threads
            sync_mentions_to_spaces()
            for space in list_spaces():
                sync_threads(space["id"])
        except Exception:
            logger.exception("Threads background sync failed; will retry later")
        if _THREADS_SYNC_STOP.wait(interval):
            break


def _community_insights_auto_loop() -> None:
    """Keep the current Taipei day's insight fresh, retrying after failures."""
    interval = _community_insights_check_interval()
    while not _INSIGHTS_STOP.is_set():
        try:
            from agent_ui.community_insights import generate_daily_insights, today_taipei
            # The generator compares source counts and is a no-op when nothing
            # changed.  This also repairs the startup race where a Threads sync
            # finishes just after an initially empty daily insight was stored.
            generate_daily_insights(today_taipei())
        except Exception:
            logger.exception("Community insight generation failed; will retry later")
        if _INSIGHTS_STOP.wait(interval):
            break


@app.on_event("startup")
def start_threads_auto_sync() -> None:
    global _THREADS_SYNC_THREAD
    if os.getenv("THREADS_AUTO_SYNC", "false").strip().lower() not in {"1", "true", "yes"}:
        return
    if not os.getenv("THREADS_ACCESS_TOKEN") or (_THREADS_SYNC_THREAD and _THREADS_SYNC_THREAD.is_alive()):
        return
    _THREADS_SYNC_STOP.clear()
    _THREADS_SYNC_THREAD = threading.Thread(target=_threads_auto_sync_loop, name="threads-auto-sync", daemon=True)
    _THREADS_SYNC_THREAD.start()


@app.on_event("startup")
def start_community_insights_auto_generation() -> None:
    global _INSIGHTS_THREAD
    if os.getenv("COMMUNITY_INSIGHTS_AUTO_GENERATE", "false").strip().lower() not in {"1", "true", "yes"}:
        return
    if _INSIGHTS_THREAD and _INSIGHTS_THREAD.is_alive():
        return
    _INSIGHTS_STOP.clear()
    _INSIGHTS_THREAD = threading.Thread(
        target=_community_insights_auto_loop,
        name="community-insights-auto-generation",
        daemon=True,
    )
    _INSIGHTS_THREAD.start()


@app.on_event("startup")
def start_strategy_bot_runner() -> None:
    """策略機器人 paper runner：一支 daemon 迴圈自動評估各 running bot 並模擬成交（全 paper，不下真單）。"""
    if os.getenv("STRATEGY_BOT_RUNNER", "1").strip().lower() in {"0", "false", "no"}:
        return
    from agent import strategy_bots
    strategy_bots.start_runner()


@app.on_event("shutdown")
def stop_threads_auto_sync() -> None:
    _THREADS_SYNC_STOP.set()
    _INSIGHTS_STOP.set()
    try:
        from agent import strategy_bots
        strategy_bots.stop_runner()
    except Exception:  # noqa: BLE001
        pass


def _require_approval_secret(x_approval_secret: Optional[str] = Header(default=None)) -> None:
    """核准/拒絕端點的來源驗證：需帶正確的 X-Approval-Secret 標頭，否則 403（擋瀏覽器 CSRF）。"""
    # 以 bytes 比對（compare_digest 對含非 ASCII 的 str 會拋 TypeError → 應回 403 而非 500）
    if not x_approval_secret or not secrets.compare_digest(
            str(x_approval_secret).encode("utf-8"), _APPROVAL_SECRET.encode("utf-8")):
        raise HTTPException(status_code=403, detail="核准請求未通過來源驗證（缺少或錯誤的核准密鑰）。")


# 頂部行情列的市場清單與快取（10 秒），避免每個前端輪詢都直打 MAX 公開 API
TICKER_MARKETS = ["btctwd", "ethtwd", "usdttwd", "soltwd", "xrptwd", "dogetwd",
                  "adatwd", "bnbtwd", "ltctwd", "linktwd"]
_ticker_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
# 完整市場清單 + 報價（60 秒快取），供前端現貨交易面板的交易對列表
_markets_cache: Dict[str, Any] = {"ts": 0.0, "data": None}

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    model: str
    host: Optional[str] = None
    persona: Optional[str] = "default"
    session_id: Optional[str] = None   # 前端每個對話的 id，用來把整段對話存成可重播 session


class OrderApprovalRequest(BaseModel):
    token: str


class OrderPreviewRequest(BaseModel):
    """前端下單表單送出的意圖。**它不會下單**，只產生一份待核准的凍結計畫。"""
    market: str
    side: str                          # buy / sell
    volume: float
    # limit / market / post_only（只掛單：會立即成交的話交易所整筆拒絕）
    ord_type: str = "limit"
    price: Optional[float] = None      # 市價單留空；limit 與 post_only 必填
    exchange: str = "max"


class ExportRequest(BaseModel):
    strategy_name: str
    params: Optional[Dict[str, Any]] = None
    format: str = "pine"              # pine | csv
    symbol: str = "BTC/USDT"
    backtest_result: Optional[Dict[str, Any]] = None   # csv 匯出需帶上一次回測結果


class ReportUploadRequest(BaseModel):
    """要保存到 S3 的 MAIA 分析快照。"""
    title: str
    report: Dict[str, Any]
    source: str = "maia-demo"


class AuthRequest(BaseModel):
    """註冊／登入。"""
    username: str
    password: str


class ProgressRequest(BaseModel):
    """世界進度。四欄都可選 —— 前端改暱稱時不該被迫連收藏一起送。"""
    nickname: Optional[str] = None
    character: Optional[str] = None
    stance: Optional[str] = None
    favorites: Optional[List[str]] = None


class ThreadsDiscussionPostRequest(BaseModel):
    """A Threads-bridged reply. Author and publication policy come from session role."""
    text: str
    parent_post_id: Optional[str] = None


class DiscussionSpaceRequest(BaseModel):
    title: str
    opening_text: str


class DeleteThreadsRootRequest(BaseModel):
    confirmation: str

@app.get("/", response_class=HTMLResponse)
def get_index():
    """載入精美的前端聊天介面 HTML"""
    # 我們將網頁放在 templates/index.html，如果沒有就直接拋錯
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    # no-store：開發期每次都拿最新頁面，避免瀏覽器沿用舊 CSS/JS
    return HTMLResponse(content=html_content, headers={"Cache-Control": "no-store, must-revalidate"})

@app.get("/analytics", response_class=HTMLResponse)
def get_analytics():
    """使用者行為分析儀表板（讀取 conversation_logs 對話存檔）。"""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "analytics.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-store, must-revalidate"})

@app.get("/api/models")
def get_models(host: Optional[str] = None):
    """
    回傳前端模型下拉選單。
    - OpenRouter 模式：回傳雲端 OpenRouter 模型 id 清單（可直接被後端採用）。
    - Ollama 模式：動態讀取 Ollama 伺服器上的可用模型列表。
    """
    if os.getenv("LLM_PROVIDER", "ollama").strip().lower() == "openrouter":
        default = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
        curated = [
            default,
            "google/gemini-2.5-flash",       # 便宜快、1M context、中文佳（預設）
            "anthropic/claude-sonnet-4.5",   # 決策品質最強、agentic 工具最穩
            "deepseek/deepseek-chat-v3.1",   # 最省、中文佳
            "openai/gpt-4.1-mini",           # OpenAI 平價選項
        ]
        seen, models = set(), []
        for m in curated:                     # 去重保序，default 置頂
            if m and m not in seen:
                seen.add(m)
                models.append(m)
        return {"status": "SUCCESS", "models": models}

    url = f"{resolve_host(host)}/api/tags"
    try:
        resp = requests.get(url, auth=resolve_auth(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("name") for m in data.get("models", [])]
        return {"status": "SUCCESS", "models": models}
    except Exception as e:
        # 當無法連線時，返回常用預設名單
        return {
            "status": "FALLBACK",
            "models": ["gemma4:12b-mlx", "gemma4:26b-mlx", "gemma4:e4b-mlx", "qwen2.5:7b"],
            "error": str(e)
        }

@app.get("/api/config")
def get_config():
    """
    回傳前端啟動時需要的非機密設定（目前為預設 Ollama host）。
    注意：不回傳 OLLAMA_USER/PASSWORD 等機密，認證由後端處理。
    """
    from agent.trade_approval import _APPROVAL_TTL_SEC
    return {
        "default_host": resolve_host(),
        # paper = 紙上模擬（安全預設）；live = 實盤。前端以此顯示風險徽章。
        "risk_mode": os.getenv("RISK_MODE", "paper").strip().lower(),
        # 核准端點來源密鑰（同源前端讀取；跨源 CSRF 頁面因同源政策無法讀取此回應）
        "approval_secret": _APPROVAL_SECRET,
        # 待核准訂單存活秒數（前端顯示倒數）
        "approval_ttl_sec": _APPROVAL_TTL_SEC,
    }


# ══════════════════════ 玩家帳號 ══════════════════════
# session cookie 成立的前提是**前後端同源**（開發走 vite 的 /api proxy，部署走
# CloudFront 的 /api/* behavior）。跨源會需要 SameSite=None + CORS，而
# tests/test_app_security.py 有一條測試明文擋著 CORSMiddleware —— 那不是疏漏，
# 是核准端點的 CSRF 防線所依賴的前提。

def _cookie_secure(request: Request) -> bool:
    """這次回應的 cookie 該不該帶 Secure。

    未設定 MAIA_COOKIE_SECURE 時看請求本身是不是 https —— 本機 http 開發自動關掉
    （否則瀏覽器根本不會回傳 cookie，症狀是「登入成功但每一次請求都說沒登入」），
    正式環境走 CloudFront 必為 https 自動打開，不需要任何人記得改設定。

    ⚠️ 後端在反向代理後面時，要用 `uvicorn --proxy-headers` 啟動，
    `request.url.scheme` 才會反映 X-Forwarded-Proto。
    """
    override = os.getenv("MAIA_COOKIE_SECURE", "").strip().lower()
    if override in ("1", "true", "yes"):
        return True
    if override in ("0", "false", "no"):
        return False
    return request.url.scheme == "https"


def _issue_session(username: str, request: Request, response: Response) -> None:
    token = auth.new_session_token()
    store.create_session(token, username, auth.SESSION_TTL_SEC)
    response.set_cookie(
        auth.COOKIE_NAME, token,
        max_age=auth.SESSION_TTL_SEC,
        httponly=True,                       # JS 讀不到 → XSS 偷不走 session
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


@app.post("/api/auth/register")
def auth_register(req: AuthRequest, request: Request, response: Response):
    """註冊並直接登入。"""
    username = auth.normalize_username(req.username)
    auth.validate_credentials(username, req.password)

    pw_hash, salt, iterations = auth.hash_password(req.password)
    created = store.create_player({
        "username": username,
        "password_hash": pw_hash,
        "salt": salt,
        "iterations": iterations,
        "created_at": store.now_iso(),
        "updated_at": store.now_iso(),
        "nickname": "", "character": "", "stance": "", "favorites": [],
        # 註冊一律是一般使用者。官方身分只能由 scripts/grant_official.py 授予
        "role": auth.ROLE_USER,
    })
    if not created:
        raise HTTPException(status_code=409, detail="這個帳號已經有人用了。")

    _issue_session(username, request, response)
    return {"player": auth.public_player(store.get_player(username) or {})}


@app.post("/api/auth/login")
def auth_login(req: AuthRequest, request: Request, response: Response):
    username = auth.normalize_username(req.username)
    player = store.get_player(username)
    # 帳號不存在與密碼錯誤回同一句話：分開講等於送給對方一支帳號列舉工具
    if not player or not auth.verify_password(req.password, player):
        raise HTTPException(status_code=401, detail="帳號或密碼不正確。")

    _issue_session(username, request, response)
    return {"player": auth.public_player(player)}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    """登出。沒登入也回 200 —— 登出是冪等的，對已經登出的人報錯沒有意義。"""
    token = request.cookies.get(auth.COOKIE_NAME)
    if token:
        store.delete_session(token)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(username: str = Depends(auth.require_session)):
    """目前登入的玩家與世界進度。未登入回 401（前端據此決定要不要顯示登入畫面）。"""
    player = store.get_player(username)
    if not player:
        # session 有效但玩家被刪了。這是不一致狀態，當作未登入處理
        raise HTTPException(status_code=401, detail="找不到這個帳號。")
    return {"player": auth.public_player(player)}


@app.put("/api/auth/progress")
def auth_progress(req: ProgressRequest, username: str = Depends(auth.require_session)):
    """儲存世界進度（暱稱／角色／立場／收藏）。"""
    store.update_progress(username, req.model_dump(exclude_none=True))
    return {"ok": True}


def _public_discussion_post(post: Dict[str, Any]) -> Dict[str, Any]:
    """挑出可以送到瀏覽器的討論室貼文欄位。

    白名單而非黑名單，理由同 auth.public_player：這個端點不需登入就讀得到，
    而貼文紀錄裡有 username（登入帳號）與 Threads 的內部 id。用黑名單的話，
    之後任何人往貼文多加一個欄位就會預設外流。
    """
    return {
        "id": post.get("id", ""),
        "author": post.get("author", ""),
        "author_role": post.get("author_role"),
        "text": post.get("text", ""),
        "source": post.get("source", "platform"),
        "source_author": post.get("source_author"),
        "created_at": post.get("created_at", ""),
        "permalink": post.get("permalink"),
        "parent_post_id": post.get("parent_post_id"),
        "sync_state": post.get("sync_state"),
    }


@app.get("/api/tickers")
def get_tickers():
    """
    頂部行情列：MAX 公開 API 即時報價（帶 10 秒伺服器端快取）。
    """
    now = time.time()
    if _ticker_cache["data"] is not None and now - _ticker_cache["ts"] < 10:
        return {"status": "SUCCESS", "tickers": _ticker_cache["data"], "cached": True}
    try:
        from skills.max_exchange.max_public import _max_public_request
        raw = _max_public_request("/api/v3/tickers", {"markets[]": TICKER_MARKETS})
        tickers = []
        for t in raw if isinstance(raw, list) else []:
            try:
                last = float(t.get("last") or 0)
                open_ = float(t.get("open") or 0)
                tickers.append({
                    "market": t.get("market", ""),
                    "symbol": t.get("market", "").replace("twd", "").upper(),
                    "last": last,
                    "pct": (last / open_ - 1) * 100 if open_ else 0.0,
                })
            except (TypeError, ValueError):
                continue
        # 依原始清單順序排序
        order = {m: i for i, m in enumerate(TICKER_MARKETS)}
        tickers.sort(key=lambda x: order.get(x["market"], 99))
        _ticker_cache.update(ts=now, data=tickers)
        return {"status": "SUCCESS", "tickers": tickers, "cached": False}
    except Exception as e:
        return {"status": "ERROR", "tickers": [], "error": str(e)}

@app.get("/api/personas")
def get_personas():
    """
    返回所有可用的投資大師人格列表。
    """
    return {"personas": list_personas()}


def _agg_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把近期成交彙整成統計（筆數 / 買賣比 / TWD 交易額 / 最常交易市場）。"""
    from collections import Counter
    n = len(trades)
    if not n:
        return {"count": 0}
    buy = sum(1 for t in trades if str(t.get("side", "")).lower() in ("buy", "bid"))
    mkts = Counter((t.get("market") or "").upper() for t in trades if t.get("market"))
    funds = 0.0
    for t in trades:
        try:
            funds += float(t.get("funds", 0) or 0)
        except (TypeError, ValueError):
            pass
    return {
        "count": n, "buy": buy, "sell": n - buy, "twd_volume": round(funds, 0),
        "top_markets": [{"market": m, "count": c} for m, c in mkts.most_common(5)],
    }


@app.get("/api/dashboard", dependencies=[Depends(auth.require_session)])
def get_dashboard():
    """使用者總覽儀表板：帳戶狀態 + 餘額 + 近期交易統計 + 記憶特質（缺 MAX 金鑰時優雅降級）。"""
    out: Dict[str, Any] = {
        "risk_mode": os.getenv("RISK_MODE", "paper").strip().lower(),
        "trade_approval": (os.getenv("TRADE_APPROVAL", "always") or "always").strip().lower(),
    }
    try:
        from skills.max_exchange.max_private import get_max_accounts
        accts = get_max_accounts()
        out["balances"] = [{
            "currency": str(a.get("currency", "")).upper(),
            "balance": float(a.get("balance", 0) or 0),
            "locked": float(a.get("locked", 0) or 0),
            "staked": float(a.get("staked", 0) or 0),   # 質押中（如 MAX 質押）— 之前漏掉導致資產顯示不全
        } for a in (accts if isinstance(accts, list) else [])][:12]
        out["has_account"] = bool(out["balances"])
    except Exception as e:  # noqa: BLE001
        out["has_account"] = False
        out["balances"] = []
        out["account_error"] = str(e)[:100]
    # 為每個餘額換算 TWD 價值（供前端畫「資產分佈」圓環圖；抓不到報價的資產 value_twd=None）
    try:
        bals = out.get("balances", [])
        markets = [f"{b['currency'].lower()}twd" for b in bals if b["currency"].lower() != "twd"]
        price = {"twd": 1.0}
        if markets:
            from skills.max_exchange.max_public import _max_public_request
            raw = _max_public_request("/api/v3/tickers", {"markets[]": markets})
            for t in (raw if isinstance(raw, list) else []):
                m = str(t.get("market", ""))
                if m.endswith("twd"):
                    try:
                        price[m[:-3]] = float(t.get("last") or 0)
                    except (TypeError, ValueError):
                        pass
        total = 0.0
        for b in bals:
            p = price.get(b["currency"].lower())
            amt = b["balance"] + b.get("locked", 0) + b.get("staked", 0)   # 含質押 → 資產估值完整
            b["value_twd"] = round(amt * p, 2) if p else None
            if b["value_twd"]:
                total += b["value_twd"]
        out["total_value_twd"] = round(total, 2)
    except Exception:  # noqa: BLE001
        pass
    # 融資 M-Wallet：把淨值(asset-debt)併入總資產 + 維持率風險；空錢包/無部位時不輸出 margin，前端就不顯示
    try:
        from skills.max_exchange.max_private import get_max_accounts as _m_accts, get_max_ad_ratio
        m_bals = _m_accts("m")
        ad = get_max_ad_ratio()
        asset_u = ad.get("asset_in_usdt") or 0.0
        debt_u = ad.get("debt_in_usdt") or 0.0
        if m_bals or asset_u > 1e-9 or debt_u > 1e-9:      # 有部位才處理
            usdt_twd = 0.0
            try:
                from skills.max_exchange.max_public import _max_public_request as _pub
                for t in (_pub("/api/v3/tickers", {"markets[]": ["usdttwd"]}) or []):
                    if str(t.get("market")) == "usdttwd":
                        usdt_twd = float(t.get("last") or 0)
            except Exception:  # noqa: BLE001
                pass
            net_usdt = asset_u - debt_u
            net_twd = round(net_usdt * usdt_twd, 2) if usdt_twd else None
            out["margin"] = {
                "ad_ratio": ad.get("ad_ratio"),
                "asset_in_usdt": round(asset_u, 4),
                "debt_in_usdt": round(debt_u, 4),
                "net_equity_usdt": round(net_usdt, 4),
                "net_equity_twd": net_twd,
                "balances": m_bals,
            }
            if net_twd:
                out["total_value_twd"] = round(out.get("total_value_twd", 0.0) + net_twd, 2)
    except Exception:  # noqa: BLE001
        pass
    # 幣種 metadata：把「可質押」標到持有的幣（前端顯示質押機會，如持有 MAX/SOL 可質押賺獎勵）
    try:
        from skills.max_exchange.max_public import get_max_currencies
        cur = get_max_currencies() or {}
        for b in out.get("balances", []):
            meta = cur.get(b["currency"])
            if meta:
                b["stakeable"] = bool(meta.get("stakeable"))
    except Exception:  # noqa: BLE001
        pass
    # 質押/持有等獎勵摘要（MAX 質押常領 holding_reward；供帳戶總覽「鎖倉質押 & 獎勵」展示）
    try:
        from collections import defaultdict
        from skills.max_exchange.max_private import _max_private_request
        rw = _max_private_request("/api/v3/rewards", {"limit": 200})
        if isinstance(rw, list) and rw:
            by_type: Dict[str, float] = defaultdict(float)
            by_cur: Dict[str, float] = defaultdict(float)
            for x in rw:
                try:
                    amt = float(x.get("amount", 0) or 0)
                except (TypeError, ValueError):
                    continue
                by_type[str(x.get("type", ""))] += amt
                by_cur[str(x.get("currency", "")).upper()] += amt
            out["rewards"] = {
                "count": len(rw),
                "by_type": {k: round(v, 8) for k, v in by_type.items() if v > 0},
                "by_currency": {k: round(v, 8) for k, v in by_cur.items() if v > 0},
                "recent": [{"type": x.get("type"), "currency": str(x.get("currency", "")).upper(),
                            "amount": x.get("amount")} for x in rw[:6]],
            }
        else:
            out["rewards"] = None
    except Exception:  # noqa: BLE001
        out["rewards"] = None
    try:
        from skills.max_exchange.max_private import get_max_my_trades
        trades = get_max_my_trades(limit=100)
        out["trade_stats"] = _agg_trades(trades) if isinstance(trades, list) else None
    except Exception:  # noqa: BLE001
        out["trade_stats"] = None
    # 使用者特質：優先用 LLM 語意摘要的快取（無則退回 profile 明確記憶）；並在背景刷新（陳舊才重算，不阻塞本次載入）
    try:
        from agent.conversation_log import load_cached_traits, refresh_traits_if_stale
        traits = load_cached_traits()
        if not traits:
            from agent import memory_store
            facts = memory_store.load_profile().get("facts", [])
            traits = [(f.get("fact") if isinstance(f, dict) else str(f)) for f in facts][:10]
        out["traits"] = traits or []

        def _bg_traits():
            try:
                from agent.llm.factory import get_provider
                refresh_traits_if_stale(get_provider(model_name=os.getenv("TRAITS_MODEL", "gemma4:12b")))
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=_bg_traits, daemon=True).start()
    except Exception:  # noqa: BLE001
        out["traits"] = []
    return out


def _mask_addr(a):
    """遮蔽區塊鏈地址中段（僅顯示頭 6 尾 4），避免完整地址暴露在畫面/紀錄。"""
    if not a or not isinstance(a, str) or len(a) < 12:
        return a
    return a[:6] + "…" + a[-4:]


_POS_LOCK = __import__("threading").Lock()


@app.get("/api/positions", dependencies=[Depends(auth.require_session)])
def positions(sync: int = 0, method: str = "fifo", reward_basis: str = "market"):
    """艙位成本 + 未實現/已實現損益 + 對帳狀態（唯讀、lazy 載入）。

    三份結果共用同一次 build_lots（各自重算會多花一倍時間）。帳本超過 30 分鐘沒更新
    或檔案不存在時自動同步；sync=1 強制同步（前端「重新整理」按鈕用）。
    """
    import os as _os
    import time as _time
    out: Dict[str, Any] = {"ok": False}
    try:
        from skills.analytics import position_ledger as pl
        from skills.analytics import lot_engine as le

        method = method if method in ("fifo", "average") else "fifo"
        reward_basis = reward_basis if reward_basis in ("market", "zero") else "market"

        stale = True
        try:
            stale = (_time.time() - _os.path.getmtime(pl._LEDGER)) > 1800
        except OSError:
            stale = True                       # 檔案不存在 → 一定要先同步，否則帳本是空的
        if sync or stale:
            # 帳本是 append-only 檔案，去重靠讀檔當下的 uid 集合 —— 兩個併發請求
            # 會各自讀到舊集合、各自寫入，造成重複事件。上鎖並在鎖內重驗新鮮度。
            with _POS_LOCK:
                try:
                    still_stale = (_time.time() - _os.path.getmtime(pl._LEDGER)) > 1800
                except OSError:
                    still_stale = True
                if sync or still_stale:
                    out["synced"] = pl.sync_ledger()

        book = le.build_lots(method=method, reward_basis=reward_basis)
        pos = le.summarize_positions(book)
        rea = le.summarize_realized(book, limit=30)
        rec = pl.reconcile()

        out.update({
            "ok": True, "method": method, "reward_basis": reward_basis,
            "positions": pos["positions"],
            "totals": {k: pos.get(k) for k in (
                "total_cost_twd", "total_value_twd",
                "total_unrealized_pnl_twd", "total_unrealized_pnl_pct")},
            "adjustments": pos.get("adjustments", []),
            "unmatched_qty": pos.get("unmatched_qty", {}),
            "realized": {"total_twd": rea["total_realized_pnl_twd"],
                         "closes": rea["closes"], "by_currency": rea["by_currency"],
                         "recent": rea["recent"], "fee_cost_twd": rea.get("fee_cost_twd", {})},
            "reconcile": {k: rec.get(k) for k in
                          ("confidence", "matched", "currencies", "mismatched", "rows", "note")},
            "ledger_events": rec.get("events"),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"/api/positions 失敗：{e}")
        out["error"] = str(e)
    return out


@app.get("/api/behavior")
def behavior(method: str = "fifo"):
    """交易行為分析（Shadow Account）。lazy 載入 —— 需重播整本帳本，約數秒。"""
    try:
        from skills.analytics.shadow_account import analyze_trading_behavior
        return analyze_trading_behavior(method=method if method in ("fifo", "average") else "fifo")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"/api/behavior 失敗：{e}")
        return {"error": str(e)}


@app.get("/api/trading_guard")
def trading_guard(limit: int = 20):
    """實盤防線狀態：生效模式、授權、累計曝險、停止開關、下單決策台帳。"""
    try:
        from skills.execution.live_guard import ledger_summary
        return ledger_summary(limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"/api/trading_guard 失敗：{e}")
        return {"error": str(e)}


@app.get("/api/account_activity", dependencies=[Depends(auth.require_session)])
def account_activity():
    """個人帳戶資金動態（唯讀、lazy 載入，不拖慢主儀表板）：入金/出金/互轉合併時間軸 +
    閃兌記錄 + 提幣白名單（地址一律遮蔽中段）。缺金鑰或失敗時回 ok=False 讓前端優雅隱藏。"""
    out: Dict[str, Any] = {"ok": False}
    try:
        from skills.max_exchange.max_private import (
            get_max_fund_transactions, get_max_converts, get_max_withdraw_addresses, get_max_my_trades,
            _norm_ts_ms)
        try:
            tr = get_max_my_trades(limit=12)
            out["trades"] = [{
                "market": str(t.get("market", "")).upper(), "side": t.get("side"),
                "price": t.get("price"), "volume": t.get("volume"), "funds": t.get("funds"),
                # ⚠ 走 _norm_ts_ms（與 flow / converts 同一套），不要自己乘 1000。
                #   MAX v3 的成交紀錄回的是 `created_at` 且**已經是毫秒**，沒有
                #   `created_at_in_ms` 這個欄位 —— 舊寫法取不到它就掉進 `created_at * 1000`
                #   的 fallback，時間戳整整大 1000 倍。前端 fmtT() 算出來的 diff 是大負數，
                #   落進「未滿一小時」那一支再被 Math.max(1, …) 夾住，於是每一筆成交
                #   都顯示「1 分前」—— 不會看起來壞掉，只是安靜地說謊。
                "time_ms": _norm_ts_ms(t.get("created_at_in_ms") or t.get("created_at")),
            } for t in (tr if isinstance(tr, list) else [])]
        except Exception:  # noqa: BLE001
            out["trades"] = []
        deps = get_max_fund_transactions("deposit", limit=10)
        wds = get_max_fund_transactions("withdrawal", limit=10)
        trs = get_max_fund_transactions("transfer", limit=10)
        for w in wds:                                   # 出金地址遮蔽
            w["to_address"] = _mask_addr(w.get("to_address"))
        out["flow"] = sorted(deps + wds + trs, key=lambda r: r.get("time_ms") or 0, reverse=True)[:12]
        out["converts"] = get_max_converts(limit=8)
        # 提幣白名單：只查「實際出金過」的幣種（最多 3 種），地址遮蔽
        wd_curs: List[str] = []
        for w in wds:
            c = w.get("currency")
            if c and c not in wd_curs:
                wd_curs.append(c)
        addrs: List[Dict[str, Any]] = []
        for c in wd_curs[:3]:
            try:
                for a in get_max_withdraw_addresses(c, limit=20):
                    a["address"] = _mask_addr(a.get("address"))
                    addrs.append(a)
            except Exception:  # noqa: BLE001
                continue
        out["withdraw_addresses"] = addrs
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:120]
    return out


@app.get("/api/deposit_sources")
def deposit_sources():
    """入金鏈上來源溯源（lazy；對站外加密入金查發送地址+具名標籤）。地址已遮蔽。"""
    try:
        from skills.market_data.chain_trace import trace_deposit_source
        return trace_deposit_source(limit=15)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:120]}


@app.get("/api/pnl_card.svg")
def pnl_card(handle: str = "", up_is_green: int = 1, limit: int = 200):
    """損益對帳單卡（share-safe SVG）：FIFO 算已實現損益、只放百分比/勝率，不含餘額金額。
    前端可將此 SVG 用 canvas 轉 PNG 後分享/發文。"""
    try:
        from skills.max_exchange.max_private import get_max_my_trades
        from skills.analytics.pnl_card import compute_pnl_summary, render_pnl_card_svg
        trades = get_max_my_trades(limit=min(500, max(20, limit)))
        summary = compute_pnl_summary(trades if isinstance(trades, list) else [])
        svg = render_pnl_card_svg(summary, handle=handle[:20], up_is_green=bool(up_is_green))
        return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})
    except Exception as e:  # noqa: BLE001
        err = (f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="120">'
               f'<rect width="480" height="120" fill="#141F35"/>'
               f'<text x="24" y="64" fill="#7C8AA5" font-size="14">損益卡產生失敗：{str(e)[:60]}</text></svg>')
        return Response(content=err, media_type="image/svg+xml")


@app.get("/api/orderbook")
def get_orderbook(market: str = "btctwd", limit: int = 14):
    """即時訂單簿（MAX 公開深度）— 供 dock『訂單簿』分頁輪詢。"""
    try:
        from skills.max_exchange.max_public import get_max_depth
        return get_max_depth(market, limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:120], "bids": [], "asks": []}


# MAX 支援的 K 線週期（分鐘）。前端的時間軸切換只能從這裡挑，
# 送別的數字 MAX 會退件。
_KLINE_PERIODS = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}
# 依 (market, period, limit) 分別快取 15 秒。K 線最短週期是 1 分鐘，
# 15 秒的舊資料對圖形沒有可見影響，但能擋掉縮放/平移時的連續重抓。
_kline_cache: Dict[str, Any] = {}


@app.get("/api/klines")
def get_klines(market: str = "btctwd", timeframe: str = "1h", limit: int = 300):
    """K 線歷史（MAX 公開資料）— 供前端價格圖。

    回傳已正規化成物件並**把秒級時間戳補成毫秒**：MAX 的 /api/v3/k 回的是
    `[秒, o, h, l, c, v]`，前端 `new Date(秒)` 會得到 1970 年。這種錯不會讓
    畫面壞掉，只會讓時間軸安靜地全錯 —— 在後端轉一次，前端就沒有機會轉錯。
    """
    tf = (timeframe or "1h").strip().lower()
    period = _KLINE_PERIODS.get(tf)
    if period is None:
        return {"status": "ERROR", "candles": [],
                "error": f"不支援的週期 {timeframe}；可用：{', '.join(_KLINE_PERIODS)}"}
    limit = max(10, min(1000, int(limit)))

    key = f"{market.lower()}|{period}|{limit}"
    now = time.time()
    hit = _kline_cache.get(key)
    if hit and now - hit["ts"] < 15:
        return {"status": "SUCCESS", "market": market, "timeframe": tf,
                "candles": hit["data"], "cached": True}
    try:
        from skills.max_exchange.max_public import get_max_klines
        raw = get_max_klines(market, limit=limit, period_minutes=period)
        candles = []
        for row in (raw if isinstance(raw, list) else []):
            if not isinstance(row, list) or len(row) < 6:
                continue
            try:
                ts = int(row[0])
                candles.append({
                    # 秒 → 毫秒（超過 1e11 視為已是毫秒，防 MAX 之後改格式）
                    "t": ts * 1000 if ts < 100_000_000_000 else ts,
                    "o": float(row[1]), "h": float(row[2]),
                    "l": float(row[3]), "c": float(row[4]), "v": float(row[5]),
                })
            except (TypeError, ValueError):
                continue
        candles.sort(key=lambda k: k["t"])
        if len(_kline_cache) > 40:      # 上限：每個交易對 × 週期都會佔一格
            _kline_cache.clear()
        _kline_cache[key] = {"ts": now, "data": candles}
        return {"status": "SUCCESS", "market": market, "timeframe": tf,
                "candles": candles, "cached": False}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"/api/klines 失敗：{e}")
        return {"status": "ERROR", "candles": [], "error": str(e)[:120]}


# 一併關進登入牆：公開網址上的無認證 LLM 端點是實際的帳單風險（每一輪最多 8 步、
# 每步都是一次 Bedrock 呼叫）。代價是評審要先註冊，約 10 秒。
@app.post("/api/chat", dependencies=[Depends(auth.require_session)])
async def chat_endpoint(req: ChatRequest):
    """
    聊天與決策推理端點。使用 Server-Sent Events (SSE) 實時串流大腦的思考與 Tool 執行日誌。
    """
    def event_generator():
        # 取本輪使用者訊息（history 最後一則 user）；沿途累積工具與最終答案供記錄
        user_msg = next((m.get("content", "") for m in reversed(req.messages)
                         if m.get("role") == "user"), "")
        persona_name = req.persona or "default"
        tools_used, final_answer, replay_steps = [], "", []
        generator = run_agent_turn(
            history_messages=req.messages,
            model_name=req.model,
            host=req.host,
            persona_key=req.persona or "default"
        )
        for step in generator:
            stype = step.get("type")
            if stype == "tool_call":
                tools_used.append(step.get("name"))
            elif stype == "final_answer":
                final_answer = step.get("content", "")
            elif stype == "persona":
                persona_name = step.get("name", persona_name)
            # 收集可重播的 step（含 tool_result 圖表數據）供 session 存檔；串流增量/狀態不收
            if stype in ("persona", "tool_call", "tool_result", "final_answer"):
                replay_steps.append(step)
            # SSE 格式: "data: <JSON>\n\n"
            yield f"data: {json.dumps(step, ensure_ascii=False)}\n\n"
        # 串流結束 → (1) 逐輪摘要供離線分析 (2) 完整 session 存檔供點擊重播（皆 try/except，不影響對話）
        from agent.conversation_log import log_conversation_turn, save_session_turn
        log_conversation_turn(
            model=req.model, persona=persona_name, user_message=user_msg,
            assistant_answer=final_answer, tools_used=tools_used,
        )
        save_session_turn(
            req.session_id or "", user_msg, replay_steps, model=req.model, persona=persona_name,
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/usage_summary")
def get_usage_summary():
    """使用者行為彙總（離線分析用）：總輪數、模型/角色/工具分佈、常見查詢詞、活躍時段。"""
    from agent.conversation_log import usage_summary
    return usage_summary()


@app.get("/api/conversations")
def get_conversations(q: str = "", limit: int = 50):
    """搜尋/列出歷史對話（供前端歷史側欄）。q 為關鍵字（比對問答內容），空則回最近 limit 筆。"""
    from agent.conversation_log import search_conversations
    return {"conversations": search_conversations(q, limit)}


@app.get("/api/sessions")
def get_sessions(limit: int = 100):
    """列出所有可重播的對話 session 摘要（id/title/updated/輪數），供左側歷史側欄。"""
    from agent.conversation_log import list_sessions
    return {"sessions": list_sessions(limit)}


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    """讀取完整 session（含每輪 steps 與圖表數據）供前端點擊重播還原。"""
    from agent.conversation_log import load_session
    s = load_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="找不到該對話 session")
    return s


@app.post("/api/export_strategy")
def export_strategy_endpoint(req: ExportRequest):
    """匯出策略：format='pine' → TradingView Pine Script v6；'csv' → 交易明細 CSV。"""
    from skills.analytics.strategy_export import export_strategy
    return export_strategy(req.strategy_name, req.params, req.format, req.symbol, req.backtest_result)


@app.post("/api/reports/upload")
def upload_report_to_s3(
    req: ReportUploadRequest,
    _: None = Depends(_require_approval_secret),
):
    """將一份分析報告私有保存至 S3，並回傳 15 分鐘有效的下載連結。

    S3 bucket 必須由 ``S3_REPORTS_BUCKET`` 指定。端點需要與下單相同的
    same-origin approval secret，避免公開部署後被任意使用者拿來寫入 bucket。
    """
    bucket = (os.getenv("S3_REPORTS_BUCKET") or "").strip()
    if not bucket:
        raise HTTPException(status_code=503, detail="尚未設定 S3_REPORTS_BUCKET")

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="S3 功能需要 boto3") from exc

    now = time.gmtime()
    key = (
        f"reports/{time.strftime('%Y/%m/%d', now)}/"
        f"maia-{secrets.token_urlsafe(9)}.json"
    )
    payload = {
        "schema_version": 1,
        "title": req.title[:160],
        "source": req.source[:80],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", now),
        "report": req.report,
    }

    try:
        # 預設會簽出 SigV2 + 全域端點（s3.amazonaws.com）的連結，對非 us-east-1 的 bucket
        # 會 307 重導；presigned 簽章綁定 host，重導後必然失效 —— 必須指定 s3v4 + 虛擬主機定址。
        client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
            ContentDisposition="attachment; filename=maia-report.json",
            ServerSideEncryption="AES256",
        )
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=900,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("S3 報告上傳失敗")
        raise HTTPException(status_code=502, detail="S3 報告上傳失敗") from exc

    return {
        "ok": True,
        "bucket": bucket,
        "key": key,
        "download_url": url,
        "expires_in_seconds": 900,
    }


# ── 語音轉文字（Amazon Transcribe 批次）────────────────────────
def _audio_format(content_type: str) -> str:
    """瀏覽器 MediaRecorder 的 mimeType → Transcribe MediaFormat。"""
    ct = (content_type or "").lower()
    if "webm" in ct:
        return "webm"
    if "ogg" in ct or "opus" in ct:
        return "ogg"
    if "mp4" in ct or "m4a" in ct or "aac" in ct:
        return "mp4"
    if "wav" in ct or "wave" in ct:
        return "wav"
    if "flac" in ct:
        return "flac"
    if "mpeg" in ct or "mp3" in ct:
        return "mp3"
    return "webm"  # Chrome MediaRecorder 預設是 audio/webm;codecs=opus


def _run_transcribe(audio: bytes, content_type: str) -> Dict[str, Any]:
    """（在 threadpool 執行；boto3 與輪詢皆阻塞）音檔 → S3 → Transcribe job → 文字。

    批次沒有『送 blob 同步回文字』的 API，job 只吃 s3:// 物件，所以一定先 put_object。
    憑證由環境/IAM 提供（同 Bedrock/S3）。轉完把音檔刪掉（隱私）。
    """
    import urllib.request
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    bucket = (os.getenv("S3_REPORTS_BUCKET") or "").strip()
    region = os.getenv("AWS_DEFAULT_REGION") or os.getenv("BEDROCK_REGION") or None
    lang = (os.getenv("TRANSCRIBE_LANGUAGE") or "zh-TW").strip()
    fmt = _audio_format(content_type)
    job = "maia-stt-" + secrets.token_urlsafe(9)
    key = f"stt/{time.strftime('%Y/%m/%d', time.gmtime())}/{job}.{fmt}"

    s3 = boto3.client("s3", region_name=region)
    tx = boto3.client("transcribe", region_name=region)
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=audio,
                      ContentType=content_type or f"audio/{fmt}", ServerSideEncryption="AES256")
        tx.start_transcription_job(
            TranscriptionJobName=job, LanguageCode=lang, MediaFormat=fmt,
            Media={"MediaFileUri": f"s3://{bucket}/{key}"})
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Transcribe 起始失敗")
        raise HTTPException(status_code=502, detail="語音轉文字啟動失敗") from exc

    text, failed = "", None
    for _ in range(40):  # 上限 ~32 秒
        try:
            info = tx.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]
        except (BotoCoreError, ClientError):
            break
        st = info["TranscriptionJobStatus"]
        if st == "COMPLETED":
            try:
                data = json.loads(urllib.request.urlopen(info["Transcript"]["TranscriptFileUri"], timeout=15).read())
                text = data["results"]["transcripts"][0]["transcript"]
            except Exception:  # noqa: BLE001
                text = ""
            break
        if st == "FAILED":
            failed = info.get("FailureReason")
            logger.warning(f"Transcribe job FAILED: {failed}")
            break
        time.sleep(0.8)

    for fn in (lambda: tx.delete_transcription_job(TranscriptionJobName=job),
               lambda: s3.delete_object(Bucket=bucket, Key=key)):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass

    if failed:
        raise HTTPException(status_code=422, detail=f"轉錄失敗：{failed}")
    return {"text": text, "language": lang}


@app.post("/api/transcribe")
async def transcribe(request: Request, _: None = Depends(_require_approval_secret)):
    """語音轉文字：前端錄音的 raw blob → Amazon Transcribe（批次）→ 回 {text}。

    與下單相同的 same-origin approval secret 守衛，避免公開部署後被人拿去狂刷帳單。
    前端只送音檔、拿文字；AWS 憑證一律留在後端（同 Bedrock/S3）。
    """
    if not (os.getenv("S3_REPORTS_BUCKET") or "").strip():
        raise HTTPException(status_code=503, detail="尚未設定 S3_REPORTS_BUCKET（批次轉錄需先把音檔放 S3）")
    audio = await request.body()
    if not audio or len(audio) < 256:
        raise HTTPException(status_code=400, detail="音檔為空或過短")
    if len(audio) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="音檔過大（上限 12MB）")
    return await run_in_threadpool(_run_transcribe, audio, request.headers.get("content-type") or "")


@app.get("/api/markets")
def get_markets(quote: str = ""):
    """可交易市場清單 + 當前報價（供前端現貨交易面板的交易對列表）。

    為什麼不用 /api/tickers：那一支只回頂部跑馬燈的 10 個白名單市場。
    交易面板要能選到帳戶裡真正持有的任何幣，清單必須是完整的。

    帶 60 秒快取 —— 市場清單一天也不會變幾次，但報價要夠新，
    所以取兩者的折衷：清單與報價一起快取，前端自己每幾秒重抓。
    """
    now = time.time()
    q = (quote or "").strip().lower()
    if _markets_cache["data"] is not None and now - _markets_cache["ts"] < 60:
        rows = _markets_cache["data"]
        return {"status": "SUCCESS", "markets": [r for r in rows if not q or r["quote"] == q], "cached": True}
    try:
        from skills.max_exchange.max_public import get_max_markets, _max_public_request
        mkts = [m for m in (get_max_markets() or []) if m.get("id")]
        ids = [str(m["id"]).lower() for m in mkts]

        # ⚠ /api/v3/tickers **必須**帶 markets[]，不帶會回 400（不是回全部）。
        #   市場數量上百，一次塞進 query string 會過長 → 分批打。
        px: Dict[str, Dict[str, Any]] = {}
        CHUNK = 60
        for i in range(0, len(ids), CHUNK):
            try:
                for t in (_max_public_request("/api/v3/tickers", {"markets[]": ids[i:i + CHUNK]}) or []):
                    m = str(t.get("market") or "")
                    if m:
                        px[m] = t
            except Exception:  # noqa: BLE001
                continue          # 某一批壞掉不該讓整份清單消失，那一批就是沒有報價

        rows: List[Dict[str, Any]] = []
        for m in mkts:
            mid = str(m["id"]).lower()
            t = px.get(mid) or {}
            try:
                last = float(t.get("last") or 0)
                open_ = float(t.get("open") or 0)
            except (TypeError, ValueError):
                last, open_ = 0.0, 0.0
            rows.append({
                "id": mid,
                "name": m.get("name"),
                "base": str(m.get("base_unit") or "").upper(),
                "quote": str(m.get("quote_unit") or "").lower(),
                "last": last,
                "pct": (last / open_ - 1) * 100 if open_ else 0.0,
                "vol": float(t.get("vol") or 0) if t.get("vol") else 0.0,
                # 下單表單靠這幾個做前端驗證，不然只能等後端退件才知道打錯。
                # 欄位名對齊 get_max_markets() 的輸出（它已經改過名，不是 MAX 原始欄位）
                "min_base_amount": m.get("min_base_amount"),
                "base_precision": m.get("base_precision"),
                "quote_precision": m.get("quote_precision"),
            })
        rows.sort(key=lambda r: -(r["vol"] * (r["last"] or 0)))
        _markets_cache.update(ts=now, data=rows)
        return {"status": "SUCCESS", "markets": [r for r in rows if not q or r["quote"] == q], "cached": False}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"/api/markets 失敗：{e}")
        return {"status": "ERROR", "markets": [], "error": str(e)[:120]}


@app.post("/api/order_preview")
def order_preview(req: OrderPreviewRequest, _: None = Depends(_require_approval_secret)):
    """把前端下單表單的意圖轉成一份**待核准的凍結計畫**，回 token 給前端確認用。

    ⚠ 這一支**不會下單**。它與模型走的是同一條互鎖：先產生計畫、凍結模式與
      參數、登記成 pending，真正送出一定要再打 /api/approve_order 帶 token。
      多這一跳的理由是「使用者在畫面上核准的，必須就是實際送出的那一筆」——
      表單值在確認框開著的時候還可能被改，凍結計畫讓那件事不可能發生。

    ⚠ 模式在這裡就凍住（paper / live）。核准之後 approve_and_execute 依凍結
      的 mode 執行、不重讀環境變數 —— 否則「在模擬盤按下核准、送出前有人把
      .env 改成 live」就會變成真單。
    """
    from agent import trade_approval as ta
    from agent.trade_approval import _APPROVAL_TTL_SEC
    from skills.execution.live_guard import effective_risk_mode, exposure_window
    from skills.execution.risk_guard import validate_order

    market = (req.market or "").replace("/", "").replace("_", "").lower()
    side = (req.side or "").lower()
    ord_type = (req.ord_type or "limit").lower()

    # 取當前市價：市價單用它估算名目金額，限價單用它讓使用者看到偏離多少
    latest = 0.0
    try:
        from skills.max_exchange.max_public import _max_public_request
        for t in (_max_public_request("/api/v3/tickers", {"markets[]": [market]}) or []):
            if str(t.get("market")) == market:
                latest = float(t.get("last") or 0)
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "error": f"取不到 {market} 的市價：{str(e)[:80]}"}
    if latest <= 0:
        return {"status": "ERROR", "error": f"取不到 {market} 的市價，無法估算金額"}

    ok, why = validate_order(market, side, req.volume, req.price or 0.0, ord_type, latest)
    if not ok:
        return {"status": "ERROR", "error": why}

    mode, mode_note = effective_risk_mode()
    plan = ta.build_order_plan(
        {"exchange_id": req.exchange, "market": market, "side": side,
         "volume": req.volume, "price": req.price, "ord_type": ord_type},
        latest, mode,
    )
    token, plan_h = ta.register_pending(plan)
    return {
        "status": "SUCCESS",
        "token": token,
        "hash": plan_h,
        "summary": ta.human_summary(plan),
        "plan": plan,
        "mode": mode,
        "mode_note": mode_note,
        # 讓確認框能顯示「這一筆會用掉多少額度」，而不是送出被擋才知道
        "exposure": exposure_window(),
        "ttl_sec": _APPROVAL_TTL_SEC,
    }


@app.get("/api/discussions/{room_id}")
def get_discussion(room_id: str):
    """Return MAIA discussion posts, including imported Threads content."""
    from agent_ui.threads_bridge import get_space, list_posts
    space = get_space(room_id)
    if not space or space.get("archived"):
        raise HTTPException(status_code=404, detail="discussion space was not found")
    posts = [post for post in list_posts(room_id) if post.get("kind") != "bridge" and post.get("text") != "此討論已同步至 MAIA 平台；可直接回覆本串。"]
    return {"posts": [_public_discussion_post(post) for post in posts]}


@app.get("/api/discussion-spaces")
def get_discussion_spaces(include_archived: bool = False):
    from agent_ui.threads_bridge import list_spaces
    return {"spaces": list_spaces(include_archived)}


@app.post("/api/discussion-spaces")
def create_discussion_space(req: DiscussionSpaceRequest, username: str = Depends(auth.require_session)):
    if not req.title.strip() or not req.opening_text.strip():
        raise HTTPException(status_code=422, detail="title and opening_text are required")
    try:
        from agent_ui.threads_bridge import create_space
        player = store.get_player(username) or {}
        author = str(player.get("nickname") or username)
        # 角色從 DynamoDB 即時查，不從 cookie 或請求主體讀 —— 撤銷官方身分要立即生效
        return {"space": create_space(req.title.strip(), author, req.opening_text.strip(),
                                      username, auth.role_of(player))}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/discussion-spaces/{room_id}")
def archive_discussion_space(room_id: str, _: str = Depends(auth.require_official)):
    from agent_ui.threads_bridge import archive_space, get_space
    space = get_space(room_id)
    if not space:
        raise HTTPException(status_code=404, detail="discussion space not found")
    if space.get("archived"):
        raise HTTPException(status_code=409, detail="discussion space is already archived")
    if not archive_space(room_id):
        raise HTTPException(status_code=409, detail="discussion space could not be archived")
    return {"ok": True, "archived": True, "room_id": room_id}


@app.post("/api/discussions/{room_id}")
def create_discussion_post(
    room_id: str,
    req: ThreadsDiscussionPostRequest,
    username: str = Depends(auth.require_session),
):
    """Create a MAIA post and publish the authenticated author's reply to Threads."""
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="text is required")
    try:
        from agent_ui.threads_bridge import create_platform_post
        player = store.get_player(username)
        if not player:
            raise HTTPException(status_code=401, detail="找不到這個帳號。")
        author = str(player.get("nickname") or username)
        # 角色從 DynamoDB 即時查，不從 cookie 或請求主體讀 —— 撤銷官方身分要立即生效
        post = create_platform_post(room_id, author, req.text.strip(), True, req.parent_post_id,
                                    username, auth.role_of(player))
        return {"post": _public_discussion_post(post)}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/discussions/{room_id}/sync")
def sync_discussion_from_threads(
    room_id: str,
    _: str = Depends(auth.require_official),
):
    """Import mentions and replies from the official account's tracked Threads branches."""
    try:
        from agent_ui.threads_bridge import sync_threads
        return {"ok": True, "imported": sync_threads(room_id)}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/threads/sync-mentions")
def sync_threads_mentions(_: str = Depends(auth.require_official)):
    """Create one MAIA discussion space for every new @official Threads post."""
    try:
        from agent_ui.threads_bridge import sync_mentions_to_spaces
        return {"ok": True, **sync_mentions_to_spaces()}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/community-insights/lobby")
def get_lobby_community_insight(date: Optional[str] = None):
    """Return the generated all-room insight for one Taipei calendar day."""
    from agent_ui.community_insights import get_insight
    try:
        insight = get_insight("lobby", date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not insight:
        raise HTTPException(status_code=404, detail="community insight has not been generated yet")
    return {"insight": insight}


@app.get("/api/community-insights/rooms/{room_id}")
def get_room_community_insight(room_id: str, date: Optional[str] = None):
    """Return one discussion space's generated daily insight."""
    from agent_ui.community_insights import get_insight
    try:
        insight = get_insight("room", date, room_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not insight:
        raise HTTPException(status_code=404, detail="community insight has not been generated yet")
    return {"insight": insight}


@app.post("/api/admin/community-insights/generate")
def generate_community_insights(date: Optional[str] = None, _: str = Depends(auth.require_official)):
    """Generate room insights first, then the lobby roll-up; official accounts only."""
    from agent_ui.community_insights import generate_daily_insights
    try:
        return {"ok": True, **generate_daily_insights(date, force=True)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        status = 409 if "already running" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.post("/api/admin/discussion-spaces/{room_id}/delete-threads-root")
def delete_official_threads_root(
    room_id: str,
    req: DeleteThreadsRootRequest,
    _: str = Depends(auth.require_official),
):
    """High-risk official action: delete MAIA's remote root and archive locally."""
    if req.confirmation != "DELETE":
        raise HTTPException(status_code=422, detail="confirmation must equal DELETE")
    try:
        from agent_ui.threads_bridge import delete_threads_root
        return {"ok": True, **delete_threads_root(room_id)}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/approve_order")
def approve_order(req: OrderApprovalRequest, _: None = Depends(_require_approval_secret)):
    """
    人工核准並執行一筆待核准訂單。以「凍結計畫」執行，模型無法在核准後竄改參數。
    """
    from agent import trade_approval as ta
    from skills.execution.order_executor import create_order

    def executor(plan: Dict[str, Any]) -> Dict[str, Any]:
        if plan.get("kind") == "cancel_all":
            # 核准後才執行的全帳戶撤單（confirm 由受信任的執行器提供，模型無法自行放行）
            from skills.execution.order_executor import cancel_all_orders
            return cancel_all_orders(plan["exchange"], market=None, confirm_all_markets=True)
        return create_order(
            exchange_id=plan["exchange"],
            market=plan["market"],
            side=plan["side"],
            volume=plan["volume"],
            price=plan["price"],
            ord_type=plan["ord_type"],
            mode=plan.get("mode"),   # 依凍結計畫的模式執行，不重讀環境（防 paper 核准被當 live 送出）
        )

    return ta.approve_and_execute(req.token, executor)


@app.post("/api/reject_order")
def reject_order(req: OrderApprovalRequest, _: None = Depends(_require_approval_secret)):
    """使用者取消一筆待核准訂單。"""
    from agent import trade_approval as ta
    return ta.reject(req.token)


# ── 策略機器人（Paper 模擬盤 MVP）────────────────────────────
# MVP 刻意全域、免登入：bots 全程 paper（模擬盤、不下真單），沒有真錢風險，
# 也不觸「一律人工確認」那道實盤安全牆。per-user 歸屬與 live 授權留待後續。
class BotCreateRequest(BaseModel):
    name: str
    strategy_type: str                 # ma_crossover | rsi_reversal
    params: Optional[Dict[str, Any]] = None
    market: str = "btctwd"
    period_minutes: int = 5
    initial_capital: float = 100_000.0


@app.get("/api/bots")
def list_strategy_bots():
    from agent import strategy_bots
    return {"bots": strategy_bots.list_bots()}


@app.post("/api/bots")
def create_strategy_bot(req: BotCreateRequest):
    from agent import strategy_bots
    res = strategy_bots.create_bot(
        name=req.name, strategy_type=req.strategy_type, params=req.params,
        market=req.market, period_minutes=req.period_minutes, initial_capital=req.initial_capital,
    )
    if isinstance(res, dict) and "error" in res:
        raise HTTPException(status_code=422, detail=res["error"])
    return {"bot": res}


@app.get("/api/bots/{bot_id}")
def get_strategy_bot(bot_id: str):
    from agent import strategy_bots
    bot = strategy_bots.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="找不到這支策略機器人。")
    return {"bot": bot}


@app.post("/api/bots/{bot_id}/start")
def start_strategy_bot(bot_id: str):
    from agent import strategy_bots
    bot = strategy_bots.start_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="找不到這支策略機器人。")
    return {"bot": bot}


@app.post("/api/bots/{bot_id}/stop")
def stop_strategy_bot(bot_id: str):
    from agent import strategy_bots
    bot = strategy_bots.stop_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="找不到這支策略機器人。")
    return {"bot": bot}


@app.delete("/api/bots/{bot_id}")
def delete_strategy_bot(bot_id: str):
    from agent import strategy_bots
    if not strategy_bots.delete_bot(bot_id):
        raise HTTPException(status_code=404, detail="找不到這支策略機器人。")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    # 本地啟動服務在 8000 端口
    uvicorn.run(app, host="127.0.0.1", port=8000)
