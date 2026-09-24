"""
agent_ui/auth.py — 帳密雜湊與 session 驗證

全部走標準庫（hashlib / secrets / hmac），**零新增相依**。

注意這裡處理的是「應用層的玩家帳號」，跟交易所金鑰是兩回事。專案鐵律
「交易所 API 金鑰永遠不進瀏覽器」仍然成立且沒有被這支檔案動搖 ——
MAX 金鑰依舊只活在後端的環境變數／Secrets Manager 裡。
"""

import hashlib
import os
import re
import secrets
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request

from agent_ui import store

COOKIE_NAME = "maia_session"
SESSION_TTL_SEC = 7 * 24 * 3600

# 角色。一般使用者是預設值，官方帳號要另外授予（scripts/grant_official.py）。
ROLE_USER = "user"
ROLE_OFFICIAL = "official"

# PBKDF2-HMAC-SHA256。OWASP 目前建議 600k，但那在登入時大約要 0.3～0.5 秒，
# 現場 demo 按下去要等半秒是看得出來的。210k 是刻意取的折衷：對離線暴力破解
# 仍有實質成本，對互動延遲則落在感覺不到的範圍。
PBKDF2_ITERATIONS = 210_000

_USERNAME_RE = re.compile(r"^[a-z0-9_-]{3,24}$")


def normalize_username(raw: str) -> str:
    """帳號一律小寫。

    不做正規化的話 `Alice` 與 `alice` 會是兩個帳號，而使用者完全預期它們是同一個 ——
    這種帳號會在「我明明註冊過卻登不進去」的形式下才被發現。
    """
    return (raw or "").strip().lower()


def validate_credentials(username: str, password: str) -> None:
    """格式檢查。不合格直接 400，錯誤訊息要能直接顯示給使用者。"""
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="帳號需為 3–24 個字元，只能用小寫英文、數字、底線或連字號。",
        )
    if len(password or "") < 8:
        raise HTTPException(status_code=400, detail="密碼至少 8 個字元。")


def hash_password(password: str, salt_hex: Optional[str] = None,
                  iterations: int = PBKDF2_ITERATIONS) -> Tuple[str, str, int]:
    """回傳 (雜湊 hex, salt hex, 疊代次數)。salt 不給就隨機產生。"""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex(), salt.hex(), iterations


def verify_password(password: str, player: Dict[str, Any]) -> bool:
    """驗證密碼。

    疊代次數從玩家紀錄裡讀而不是用常數：之後調高 PBKDF2_ITERATIONS 時，
    早期註冊的帳號仍然驗得過（否則所有舊使用者會在某次部署後同時登不進來）。
    """
    try:
        expected = str(player["password_hash"])
        salt_hex = str(player["salt"])
        iterations = int(player["iterations"])
    except (KeyError, TypeError, ValueError):
        return False
    actual, _, _ = hash_password(password, salt_hex, iterations)
    # 定時比較：避免用回應時間逐字元試出雜湊值
    return secrets.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def require_session(request: Request) -> str:
    """FastAPI 依賴：驗證 session cookie，回傳 username。

    形狀刻意跟 app.py 既有的 `_require_approval_secret` 一致 —— 同一個檔案裡兩種
    不同風格的驗證會讓人以為它們的保證強度也不同。
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="請先登入。")
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="登入已過期，請重新登入。")
    return str(session["username"])


# ─────────────── 本機免登入（opt-in，只給自己這台機器 demo 用）───────────────
LOCAL_USERNAME = "local"
_LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
# 部署在 CloudFront → ALB 後面時 ALB 一定會補 X-Forwarded-For；而 Dockerfile.api 用
# `--forwarded-allow-ips *`，此時 request.client 取的是 XFF **最左邊**那個 —— 客戶端自己
# 填得了 127.0.0.1。所以「IP 是本機」不能單獨當依據：只要帶任何轉發標頭就不算本機。
_FORWARD_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip")


def local_no_login(request: Request) -> bool:
    """這個請求能不能免登入：`.env` 明確開 MAIA_LOCAL_NO_LOGIN，且是直接從本機連進來的。

    預設關閉 —— 登入牆擋的是 LLM 帳單與真實帳戶（餘額、成交、撤單），公開網址上不能拆。
    """
    if os.getenv("MAIA_LOCAL_NO_LOGIN", "").strip().lower() not in ("1", "true", "yes"):
        return False
    host = request.client.host if request.client else ""
    if host not in _LOOPBACK_HOSTS:
        return False
    return not any(h in request.headers for h in _FORWARD_HEADERS)


def require_session_or_local(request: Request) -> str:
    """帳戶、對話、掛單端點用的登入牆；本機免登入模式下放行本機請求。

    本機放行時回傳 LOCAL_USERNAME，而且先判斷本機、不去查 session ——
    這幾條端點只要「能不能用」、不用知道是誰，DynamoDB 沒開也照樣能 demo。
    身分相關的端點（/api/auth/me、進度、發文、官方操作）仍然走 require_session。
    """
    if local_no_login(request):
        return LOCAL_USERNAME
    return require_session(request)


def role_of(player: Dict[str, Any]) -> str:
    """讀玩家角色。

    缺欄位一律當一般使用者：role 是後來才加的，既有帳號的紀錄裡沒有這個欄位，
    而「讀不到就當官方」會讓所有舊帳號在某次部署後同時變成管理員。
    值不在白名單內也一樣降級 —— 認不得的角色不該獲得比一般使用者更多的權限。
    """
    role = str((player or {}).get("role") or ROLE_USER)
    return role if role in (ROLE_USER, ROLE_OFFICIAL) else ROLE_USER


def require_official(request: Request) -> str:
    """FastAPI 依賴：必須是**已登入的官方帳號**，回傳 username。

    未登入回 401（去登入），已登入但非官方回 403（登入也沒用）—— 兩者對前端
    是不同的動作，混成同一個狀態碼會讓「該跳登入視窗還是該顯示無權限」分不出來。
    """
    username = require_session(request)
    player = store.get_player(username)
    if not player or role_of(player) != ROLE_OFFICIAL:
        raise HTTPException(status_code=403, detail="這個操作限官方帳號。")
    return username


def public_player(player: Dict[str, Any]) -> Dict[str, Any]:
    """挑出可以送到瀏覽器的欄位。

    白名單而不是「刪掉密碼欄位」：日後有人在玩家紀錄上加欄位時，黑名單會**預設外洩**，
    白名單則預設不外洩。
    """
    return {
        "username": player.get("username", ""),
        "nickname": player.get("nickname", ""),
        "character": player.get("character", ""),
        "stance": player.get("stance", ""),
        "favorites": list(player.get("favorites") or []),
        "created_at": player.get("created_at", ""),
        # 前端據此顯示官方徽章／官方專屬介面。這只是顯示用，權限判斷一律在後端
        # 走 require_official —— 前端拿到什麼值都不影響它能不能呼叫官方端點。
        "role": role_of(player),
    }
