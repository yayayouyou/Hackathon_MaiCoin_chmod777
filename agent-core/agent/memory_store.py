"""
agent/memory_store.py — 分層使用者記憶 (Layered User Memory)
=====================================================
借鏡 OpenClaw 的分層記憶：與 audit_logger（不可變合規審計）互補，這一層是
「會被回讀進 context」的使用者記憶，讓 MAIA 有跨對話的連續性與個人化。

兩層：
  1. 偏好檔 profile.json — 使用者的持久事實/偏好（風險承受度、偏好交易所、只做現貨…）。
     由 remember_about_me() 工具寫入；每輪開頭注入 system prompt。
  2. 交易日誌 journal.jsonl — 每輪的精簡紀錄（問題、評級/決策、標的、工具、下單）。
     每輪結束自動追加；近期數筆注入 context，並可由 recall_history() 關鍵字搜尋。

檔案存於專案內 agent_memory/（已 gitignore；屬使用者私有資料，不進版本庫）。
"""
import os
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

_MEM_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent_memory"
)
_PROFILE = os.path.join(_MEM_DIR, "profile.json")
_JOURNAL = os.path.join(_MEM_DIR, "journal.jsonl")

_TZ = timezone(timedelta(hours=8))  # 台北時間


def _ensure_dir() -> None:
    os.makedirs(_MEM_DIR, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat()


def _today() -> str:
    return datetime.now(_TZ).strftime("%m-%d")


# ── 偏好檔 ─────────────────────────
def load_profile() -> Dict[str, Any]:
    if not os.path.exists(_PROFILE):
        return {"facts": []}
    try:
        with open(_PROFILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "facts" not in data:
            return {"facts": []}
        return data
    except Exception as e:  # noqa: BLE001
        logger.error(f"讀取偏好檔失敗: {e}")
        return {"facts": []}


def save_profile(profile: Dict[str, Any]) -> None:
    _ensure_dir()
    try:
        with open(_PROFILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        logger.error(f"寫入偏好檔失敗: {e}")


def remember_about_me(fact: str) -> Dict[str, Any]:
    """
    【LLM Tool - 記憶】記住一項關於使用者的持久偏好或事實（跨對話有效）。
    例如：使用者說「我只做現貨」「我風險承受度 2%」「我偏好 MAX 交易所」「我是新手」。

    Args:
        fact: 要記住的事實或偏好（精簡一句話）。
    """
    fact = (fact or "").strip()
    if not fact:
        return {"error": "沒有可記住的內容"}
    if len(fact) > 200:
        fact = fact[:200]
    profile = load_profile()
    existing = [f["fact"] for f in profile["facts"]]
    if fact in existing:
        return {"status": "已存在", "fact": fact}
    profile["facts"].append({"fact": fact, "ts": _now_iso()})
    # 上限 30 條，滿了汰換最舊
    profile["facts"] = profile["facts"][-30:]
    save_profile(profile)
    logger.info(f"記住使用者偏好: {fact}")
    return {"status": "已記住", "fact": fact, "total_facts": len(profile["facts"])}


def forget_about_me(keyword: str) -> Dict[str, Any]:
    """【LLM Tool - 記憶】忘記含指定關鍵字的偏好。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return {"error": "請提供要忘記的關鍵字"}
    profile = load_profile()
    before = len(profile["facts"])
    profile["facts"] = [f for f in profile["facts"] if keyword not in f["fact"]]
    save_profile(profile)
    return {"status": "已忘記", "removed": before - len(profile["facts"])}


# ── 交易日誌 ─────────────────────────
def _extract_rating(text: str) -> Optional[str]:
    """從最終決策文字擷取多空評級（若有）。"""
    m = re.search(r"(強烈買入|強烈賣出|買入|賣出|做多|做空|中性|觀望|降級|Strong\s*Buy|Strong\s*Sell|Buy|Sell|Neutral)", text or "", re.I)
    return m.group(1) if m else None


def append_journal(user_query: str, decision: str, tools: List[str],
                   order: Optional[Dict[str, Any]] = None) -> None:
    """每輪結束追加一筆精簡日誌。"""
    _ensure_dir()
    entry = {
        "ts": _now_iso(),
        "date": _today(),
        "query": (user_query or "")[:200],
        "rating": _extract_rating(decision),
        "summary": (decision or "").replace("\n", " ").strip()[:180],
        "tools": tools[:12],
        "order": order,
    }
    try:
        with open(_JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.error(f"寫入交易日誌失敗: {e}")


def _read_journal() -> List[Dict[str, Any]]:
    if not os.path.exists(_JOURNAL):
        return []
    out = []
    try:
        with open(_JOURNAL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:  # noqa: BLE001
        logger.error(f"讀取交易日誌失敗: {e}")
    return out


def recent_journal(n: int = 5) -> List[Dict[str, Any]]:
    return _read_journal()[-n:]


def recall_history(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool - 記憶】搜尋使用者過去的對話/交易紀錄（關鍵字比對）。
    例如使用者問「我上次問過 BTC 嗎？」「我之前的評級是什麼？」時使用。

    Args:
        query: 搜尋關鍵字（如幣種、評級、日期）。
        limit: 最多回傳幾筆。
    """
    query = (query or "").strip().lower()
    entries = _read_journal()
    if not query:
        hits = entries[-limit:]
    else:
        toks = [t for t in re.split(r"\s+", query) if t]
        hits = [e for e in entries
                if any(t in json.dumps(e, ensure_ascii=False).lower() for t in toks)][-limit:]
    return {"count": len(hits), "history": hits}


# ── 每輪 context 注入 ─────────────────────────
def build_memory_context() -> str:
    """組出要注入 system prompt 的 <user_memory> 區塊；無資料回空字串。"""
    profile = load_profile()
    facts = [f["fact"] for f in profile.get("facts", [])]
    recent = recent_journal(5)
    if not facts and not recent:
        return ""

    lines = ["<user_memory>", "以下是你對這位使用者已知的長期記憶，回答時應體貼地納入考量（但別生硬複述）："]
    if facts:
        lines.append("【記住的偏好與事實】")
        lines.extend(f"- {f}" for f in facts)
    if recent:
        lines.append("【近期對話紀錄】")
        for e in recent:
            r = f"（評級：{e['rating']}）" if e.get("rating") else ""
            od = ""
            if e.get("order"):
                o = e["order"]
                od = f"（下單：{o.get('side')} {o.get('volume')} {o.get('market')}）"
            lines.append(f"- [{e.get('date','')}] {e.get('query','')[:60]} → {e.get('summary','')[:60]}{r}{od}")
    lines.append("</user_memory>")
    return "\n".join(lines)


# ── LLM 工具 Schema ─────────────────────────
MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "remember_about_me",
            "description": (
                "記住一項關於『使用者本人』的持久偏好或事實，跨對話有效。"
                "當使用者表達長期偏好或自我描述時使用，例如：'我只做現貨'、'我風險承受度 2%'、"
                "'我偏好用 MAX'、'我是新手'、'我不碰迷因幣'、'記住我...'。只存偏好，不要拿來存一次性數據。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "要記住的偏好/事實，精簡一句話"}
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_history",
            "description": (
                "搜尋使用者過去的對話與交易紀錄（關鍵字比對）。當使用者問及過往時使用，"
                "例如：'我上次問過 BTC 嗎'、'我之前對 ETH 的評級'、'我最近下過哪些單'。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜尋關鍵字，如幣種/評級/日期"},
                    "limit": {"type": "integer", "description": "最多回傳幾筆，預設 5"},
                },
                "required": ["query"],
            },
        },
    },
]

MEMORY_CALLABLES = {
    "remember_about_me": remember_about_me,
    "recall_history": recall_history,
    "forget_about_me": forget_about_me,
}
