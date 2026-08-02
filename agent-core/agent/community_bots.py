"""
agent/community_bots.py — 把 MAIA 帶到 LINE / Telegram（零新套件）

MAIA 的大腦（run_agent_turn）原封不動複用；這一層只做「傳輸」：
從聊天平台收訊息 → 丟給 agent → 把答案送回去。LINE 與 Telegram 共用
同一個 `agent_reply()`，差別只在傳輸層。

Telegram：**long polling**（getUpdates）。刻意不用 webhook —— 不需要公開
網址，本機 localhost 就能跑（跟 strategy_bots 的 runner 同一種 daemon 迴圈），
部署後背景執行緒照樣能跑。env 開關 `TELEGRAM_BOT_TOKEN`，沒設就不啟動。

LINE：見同專案 app.py 的 `/api/webhook/line`（LINE 只能 webhook，需公開網址）。
本檔的 `agent_reply()` 兩邊共用。
"""
import os
import base64
import hashlib
import hmac
import threading
from typing import Optional

import requests
from loguru import logger

_TG_API = "https://api.telegram.org/bot{token}/{method}"
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_HTTP_TIMEOUT = 65   # long poll 伺服器端最多 hold 50s，這裡留緩衝


# ── 共用大腦 ────────────────────────────────────────────────
def agent_reply(text: str, persona: str = "default") -> str:
    """把一段文字丟給 MAIA 的大腦，收斂成最終回覆字串。LINE / Telegram 共用。"""
    from agent.ollama_agent import run_agent_turn
    final = ""
    try:
        for step in run_agent_turn(
            history_messages=[{"role": "user", "content": text}],
            model_name=os.getenv("AGENT_MODEL", ""),
            persona_key=persona,
        ):
            if step.get("type") == "final_answer":
                final = step.get("content", "") or final
    except Exception as e:  # noqa: BLE001
        logger.error(f"[bot] agent_reply 失敗：{e}")
        return "抱歉，MAIA 這次沒能回覆（內部錯誤），請再試一次。"
    return final or "（MAIA 沒有產生回覆）"


# ── Telegram（long polling）─────────────────────────────────
def _tg(method: str, token: str, **params):
    try:
        r = requests.post(_TG_API.format(token=token, method=method), json=params, timeout=_HTTP_TIMEOUT)
        return r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[telegram] {method} 失敗：{e}")
        return {"ok": False, "error": str(e)}


def _handle_tg_update(upd: dict, token: str) -> None:
    msg = upd.get("message") or upd.get("edited_message")
    if not isinstance(msg, dict):
        return
    chat = (msg.get("chat") or {}).get("id")
    text = msg.get("text")
    if not chat or not text:
        return
    if text.strip() in ("/start", "/help"):
        _tg("sendMessage", token, chat_id=chat,
            text="嗨，我是 MAIA 🤖 你的加密貨幣交易副駕。\n"
                 "問我行情、做分析、回測策略，或叫我把策略打包成自動機器人都可以。")
        return
    _tg("sendChatAction", token, chat_id=chat, action="typing")
    reply = agent_reply(text)
    # Telegram 單則上限 4096 字元，超過就分段送
    for i in range(0, len(reply), 4000):
        _tg("sendMessage", token, chat_id=chat, text=reply[i:i + 4000])


def _tg_loop(token: str) -> None:
    logger.info("[telegram] polling 已啟動")
    _tg("deleteWebhook", token, drop_pending_updates=False)  # 有殘留 webhook 會讓 getUpdates 409
    offset = None
    while not _stop.is_set():
        params = {"timeout": 50, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        data = _tg("getUpdates", token, **params)
        if not data.get("ok"):
            _stop.wait(3)   # 出錯緩衝，不狂打 API
            continue
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            try:
                _handle_tg_update(upd, token)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[telegram] 處理訊息失敗：{e}")
    logger.info("[telegram] polling 已停止")


def start_telegram_bot() -> bool:
    """啟動 Telegram polling daemon。沒設 TELEGRAM_BOT_TOKEN 就跳過（回 False）。"""
    global _thread
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.info("[telegram] 未設 TELEGRAM_BOT_TOKEN，略過")
        return False
    if _thread and _thread.is_alive():
        return True
    _stop.clear()
    _thread = threading.Thread(target=_tg_loop, args=(token,), daemon=True, name="telegram-bot")
    _thread.start()
    return True


def stop_telegram_bot() -> None:
    _stop.set()


# ── LINE（webhook）──────────────────────────────────────────
_LINE_REPLY = "https://api.line.me/v2/bot/message/reply"


def verify_line_signature(body: bytes, signature: str) -> bool:
    """驗證 X-Line-Signature：用 channel secret 對**原始 body bytes** 做 HMAC-SHA256 再 base64。"""
    secret = os.getenv("LINE_CHANNEL_SECRET", "").encode("utf-8")
    if not secret or not signature:
        return False
    digest = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _line_reply(reply_token: str, text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token or not reply_token:
        return
    text = text or "（MAIA 沒有產生回覆）"
    # LINE 單則上限 5000 字、單次最多 5 則
    chunks = [text[i:i + 4800] for i in range(0, len(text), 4800)][:5] or [text]
    try:
        requests.post(
            _LINE_REPLY,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": c} for c in chunks]},
            timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[line] reply 失敗：{e}")


def _process_line_event(event: dict) -> None:
    if event.get("type") != "message":
        return
    msg = event.get("message") or {}
    if msg.get("type") != "text":
        return
    text = (msg.get("text") or "").strip()
    reply_token = event.get("replyToken")
    if not reply_token or not text:
        return
    if text in ("/start", "/help", "help", "？", "?"):
        _line_reply(reply_token,
                    "嗨，我是 MAIA 🤖 你的加密貨幣交易副駕。\n"
                    "問我行情、做分析、回測策略，或叫我把策略打包成自動機器人都可以。")
        return
    _line_reply(reply_token, agent_reply(text))


def handle_line_events(events: list) -> None:
    """在背景執行緒處理 LINE 事件（agent 很慢，webhook 端點要先回 200，回覆才不會逾時）。"""
    for ev in events or []:
        try:
            _process_line_event(ev)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[line] 事件處理失敗：{e}")
