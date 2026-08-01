"""
agent/conversation_log.py — 完整對話逐輪存檔（供後續使用者行為分析）
=====================================================
與既有兩層互補、各司其職：
  - audit_logger.py：合規審計（雜湊鏈、每一步工具與風控），偏「不可竄改稽核」。
  - memory_store.py：會『回讀進 context』的個人化記憶（偏好 + 交易日誌摘要）。
  - 本模組：純粹「完整對話逐輪」原始存檔，**不回讀進 context**，只為離線分析
    使用者行為（常問什麼、用哪些模型/角色/工具、回答多長、活躍時段）。

設計借鑑 Vibe-Trading 的 session persistence：
  - 每次 append 後 flush + os.fsync，機器崩潰也不易掉最後一筆。
  - 讀取時「跳過損毀的 JSON 行」，不因單行壞掉而整批讀取失敗。

存於 conversation_logs/conversations.jsonl（已在 .gitignore；屬使用者私有資料，不進版本庫）。
"""

import os
import re
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from loguru import logger

_TZ = timezone(timedelta(hours=8))  # 台北時間
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conversation_logs")
_FILE = os.path.join(_DIR, "conversations.jsonl")


def log_conversation_turn(
    model: str,
    persona: str,
    user_message: str,
    assistant_answer: str,
    tools_used: List[str] = None,
    risk_mode: str = None,
    session_id: str = "",
) -> None:
    """逐輪追加一筆對話記錄；flush + fsync 確保落盤。
    失敗僅記 warning、不拋出 —— 記錄動作絕不可影響對話本身。"""
    try:
        os.makedirs(_DIR, exist_ok=True)
        rec = {
            "ts": datetime.now(_TZ).isoformat(),
            "session_id": session_id or "",
            "model": model,
            "persona": persona,
            "risk_mode": risk_mode or os.getenv("RISK_MODE", "paper"),
            "user_message": user_message or "",
            "assistant_answer": assistant_answer or "",
            "assistant_len": len(assistant_answer or ""),
            "tools_used": tools_used or [],
        }
        with open(_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"對話記錄寫入失敗（已略過，不影響對話）: {e}")


def _iter_records() -> List[Dict[str, Any]]:
    """讀取所有記錄；跳過損毀的 JSON 行（crash 中斷寫入的殘行不會讓整批失敗）。"""
    out: List[Dict[str, Any]] = []
    if not os.path.exists(_FILE):
        return out
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.warning(f"對話記錄讀取失敗: {e}")
    return out


def search_conversations(keyword: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    """關鍵字搜尋對話（同時比對使用者訊息與回答）；回傳最近 limit 筆。"""
    kw = (keyword or "").lower()
    recs = _iter_records()
    if kw:
        recs = [r for r in recs
                if kw in (r.get("user_message", "") + " " + r.get("assistant_answer", "")).lower()]
    return recs[-limit:]


def usage_summary() -> Dict[str, Any]:
    """使用者行為彙總：總輪數、各模型/角色/工具使用次數、平均回答長度、常見查詢詞、活躍時段。"""
    recs = _iter_records()
    if not recs:
        return {"total_turns": 0}
    models = Counter(r.get("model", "") for r in recs)
    personas = Counter(r.get("persona", "") for r in recs)
    tools = Counter(t for r in recs for t in (r.get("tools_used") or []))
    hours = Counter((r.get("ts", "")[11:13] for r in recs if len(r.get("ts", "")) >= 13))
    avg_len = round(sum(r.get("assistant_len", 0) for r in recs) / len(recs), 1)
    words: Counter = Counter()
    for r in recs:
        # 簡易中英斷詞：≥2 的連續英文字母，或 ≥2 的連續 CJK 字塊
        for tok in re.findall(r"[A-Za-z]{2,}|[一-鿿]{2,}", r.get("user_message", "")):
            words[tok.lower()] += 1
    return {
        "total_turns": len(recs),
        "by_model": dict(models.most_common()),
        "by_persona": dict(personas.most_common()),
        "top_tools": dict(tools.most_common(10)),
        "avg_answer_len": avg_len,
        "top_query_terms": dict(words.most_common(15)),
        "busiest_hours": dict(hours.most_common(5)),
        "first_ts": recs[0].get("ts"),
        "last_ts": recs[-1].get("ts"),
    }


# ──────────────────────────────────────────────
#  完整對話 Session 存檔（供「點歷史 → 重現整段對話 + 圖表」）
#  存於 conversation_logs/sessions/{id}.json；一檔一個 session（多輪 turns，
#  含 tool_result 的圖表數據），前端點擊時重播還原對話與圖表。
# ──────────────────────────────────────────────
_SESS_DIR = os.path.join(_DIR, "sessions")
_REPLAY_TYPES = {"persona", "tool_call", "tool_result", "final_answer"}   # 重播需要的 step（串流增量/狀態不存）
_SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")                            # 防路徑穿越


def _now() -> str:
    return datetime.now(_TZ).isoformat()


def _safe_sid(session_id: str) -> Optional[str]:
    return session_id if session_id and _SID_RE.match(session_id) else None


# ── 可插拔儲存後端 ─────────────────────────────────────────────
#  設了 S3_REPORTS_BUCKET → 存 S3（沿用報告端點同一個 bucket，sessions/ 前綴）；
#  否則存本地磁碟（dev 用）。部署到 AgentCore（容器 ephemeral 磁碟）時本地檔會隨
#  容器重啟消失，所以正式環境一定要走 S3。憑證由 IAM role / 環境提供，同報告端點。
def _s3_bucket() -> str:
    # 讀在函式內而非模組層，避免這支被 import 早於 load_dotenv 時抓不到值
    return (os.getenv("S3_REPORTS_BUCKET") or "").strip()


def _s3_prefix() -> str:
    return (os.getenv("S3_SESSIONS_PREFIX") or "sessions/").strip()


def _s3_client():
    import boto3
    region = os.getenv("AWS_DEFAULT_REGION") or os.getenv("BEDROCK_REGION") or None
    return boto3.client("s3", region_name=region)


def _s3_key(sid: str) -> str:
    return f"{_s3_prefix()}{sid}.json"


def _load_raw(sid: str) -> Optional[Dict[str, Any]]:
    """讀一個 session 的完整 dict（S3 或本地）；不存在/壞掉一律回 None。"""
    bucket = _s3_bucket()
    if bucket:
        try:
            obj = _s3_client().get_object(Bucket=bucket, Key=_s3_key(sid))
            return json.loads(obj["Body"].read())
        except Exception:  # noqa: BLE001 — NoSuchKey 或壞掉都當作沒有
            return None
    path = os.path.join(_SESS_DIR, f"{sid}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _store_raw(sid: str, sess: Dict[str, Any]) -> None:
    """寫一個 session 的完整 dict（S3 put_object 或本地原子寫入）。"""
    body = json.dumps(sess, ensure_ascii=False)
    bucket = _s3_bucket()
    if bucket:
        _s3_client().put_object(
            Bucket=bucket, Key=_s3_key(sid),
            Body=body.encode("utf-8"),
            ContentType="application/json; charset=utf-8",
            ServerSideEncryption="AES256",   # 與報告端點一致，bucket 維持私有加密
        )
        return
    os.makedirs(_SESS_DIR, exist_ok=True)
    path = os.path.join(_SESS_DIR, f"{sid}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)   # 原子替換，避免半寫檔


def _summarize(sess: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    return {
        "id": sess.get("id", fallback_id),
        "title": sess.get("title") or "（未命名）",
        "updated": sess.get("updated") or sess.get("created", ""),
        "turns": len(sess.get("turns", [])),
    }


def save_session_turn(session_id: str, user_message: str, steps: List[Dict[str, Any]],
                      model: str = "", persona: str = "") -> None:
    """把一輪對話（使用者訊息 + 可重播 steps）追加到該 session（S3 或本地）。失敗僅記 log 不拋。

    注意：這是 read-modify-write，同一 session 若並發寫入會 race —— 但單一使用者的對話
    是循序送出（前端等串流結束才送下一則），實務上不會踩到。"""
    sid = _safe_sid(session_id)
    if not sid:
        return
    try:
        sess = _load_raw(sid) or {"id": sid, "created": _now(), "title": "", "turns": []}
        replay = [s for s in (steps or []) if s.get("type") in _REPLAY_TYPES]
        sess.setdefault("turns", []).append({
            "ts": _now(), "user": user_message or "", "model": model, "persona": persona, "steps": replay,
        })
        if not sess.get("title"):
            sess["title"] = (user_message or "新對話")[:40]
        sess["updated"] = _now()
        _store_raw(sid, sess)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"session 存檔失敗（略過）: {e}")


def list_sessions(limit: int = 100) -> List[Dict[str, Any]]:
    """列出所有 session 摘要（id/title/updated/輪數），依更新時間新到舊。"""
    out: List[Dict[str, Any]] = []
    bucket = _s3_bucket()
    if bucket:
        # S3：list_objects_v2 拿 key，再逐一 GET 取摘要。demo 規模（數十個）可接受；
        # 真要規模化再改存物件 metadata 或改用 DynamoDB。
        try:
            client = _s3_client()
            prefix = _s3_prefix()
            token: Optional[str] = None
            keys: List[str] = []
            while True:
                kw: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
                if token:
                    kw["ContinuationToken"] = token
                resp = client.list_objects_v2(**kw)
                keys.extend(o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".json"))
                token = resp.get("NextContinuationToken")
                if not token:
                    break
            for key in keys:
                try:
                    s = json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())
                    out.append(_summarize(s, key[len(prefix):-5]))
                except Exception:  # noqa: BLE001
                    continue
        except Exception as e:  # noqa: BLE001
            logger.warning(f"list_sessions（S3）失敗: {e}")
    elif os.path.isdir(_SESS_DIR):
        for name in os.listdir(_SESS_DIR):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(_SESS_DIR, name), "r", encoding="utf-8") as f:
                    s = json.load(f)
                out.append(_summarize(s, name[:-5]))
            except (json.JSONDecodeError, OSError):
                continue
    out.sort(key=lambda x: x.get("updated", ""), reverse=True)
    return out[:limit]


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    """讀取完整 session（含每輪 steps 與圖表數據）供前端重播（S3 或本地）。"""
    sid = _safe_sid(session_id)
    if not sid:
        return None
    return _load_raw(sid)


# ──────────────────────────────────────────────
#  使用者特質（LLM 語意摘要 + 快取）
#  取代舊的關鍵字統計：用一次 LLM 讀近期對話摘出語意化特質，快取到檔；
#  只有對話輪數比上次摘要多 min_new_turns 以上才重算 → 顧效能、非每次都跑。
# ──────────────────────────────────────────────
_TRAITS_CACHE = os.path.join(_DIR, "traits_cache.json")


def load_cached_traits() -> Optional[List[str]]:
    """讀取快取的使用者特質（供儀表板即時顯示，無 LLM 成本）。"""
    if not os.path.exists(_TRAITS_CACHE):
        return None
    try:
        with open(_TRAITS_CACHE, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("traits")
    except (json.JSONDecodeError, OSError):
        return None


def refresh_traits_if_stale(provider, min_new_turns: int = 5) -> Optional[List[str]]:
    """對話輪數比上次摘要多 min_new_turns 以上（或無快取）才用 LLM 重新摘要特質並快取。
    回傳特質清單；失敗保留舊快取。設計為可在背景執行緒呼叫，不阻塞請求。"""
    recs = _iter_records()
    total = len(recs)
    cached_raw = None
    if os.path.exists(_TRAITS_CACHE):
        try:
            with open(_TRAITS_CACHE, "r", encoding="utf-8") as f:
                cached_raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            cached_raw = None
    if cached_raw and (total - cached_raw.get("turns_at_gen", 0)) < min_new_turns:
        return cached_raw.get("traits")          # 還新鮮，不重算
    if total < 2 or provider is None:
        return cached_raw.get("traits") if cached_raw else None

    recent = [r.get("user_message", "") for r in recs[-30:] if r.get("user_message")]
    summ = usage_summary()
    prompt = (
        "根據以下使用者與加密交易助理的對話與統計，用繁體中文摘要出 4~6 條『使用者特質』"
        "（交易風格、關注標的、偏好的分析角度、風險偏好、常用功能等），每條 8~16 字、精煉具體、避免空泛。\n"
        f"常用工具：{list(summ.get('top_tools', {}).keys())[:8]}\n"
        f"常用角色：{list(summ.get('by_persona', {}).keys())[:5]}\n"
        "近期提問：\n- " + "\n- ".join(recent[-20:])
    )
    try:
        resp = provider.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            format={"type": "object",
                    "properties": {"traits": {"type": "array", "items": {"type": "string"}}},
                    "required": ["traits"]},
        )
        traits = (json.loads(resp.content or "{}") or {}).get("traits") or []
        traits = [str(t)[:40] for t in traits[:6] if str(t).strip()]
        if traits:
            os.makedirs(_DIR, exist_ok=True)
            tmp = _TRAITS_CACHE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"generated": _now(), "turns_at_gen": total, "traits": traits}, f, ensure_ascii=False)
            os.replace(tmp, _TRAITS_CACHE)
            logger.info(f"使用者特質已重新摘要（{total} 輪）：{traits}")
            return traits
    except Exception as e:  # noqa: BLE001
        logger.warning(f"特質 LLM 摘要失敗，保留舊快取：{e}")
    return cached_raw.get("traits") if cached_raw else None
