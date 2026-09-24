"""玩家帳號：密碼雜湊、session 生命週期、以及三條帳戶端點的登入牆。

store 一律換成記憶體假物件 —— 這些測試不該需要 AWS 憑證或 DynamoDB Local，
否則 CI 與「剛 clone 完的組員」都跑不動。DynamoDB 真正的行為由
scripts/create_tables.py + 手動端到端驗證負責。
"""
import time

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient

from agent_ui import auth, store
from agent_ui.app import app


# ─────────────────── 純函式 ───────────────────

def test_password_roundtrip():
    h, salt, iters = auth.hash_password("hunter2xyz")
    player = {"password_hash": h, "salt": salt, "iterations": iters}
    assert auth.verify_password("hunter2xyz", player)
    assert not auth.verify_password("hunter2xy", player)


def test_same_password_gets_different_hash():
    """salt 要真的隨機：兩個人用同一組密碼，雜湊必須不同，否則彩虹表一次打穿全部。"""
    h1, _, _ = auth.hash_password("samepassword")
    h2, _, _ = auth.hash_password("samepassword")
    assert h1 != h2


def test_verify_uses_stored_iteration_count():
    """疊代次數從玩家紀錄讀 —— 日後調高常數時舊帳號仍要驗得過。"""
    h, salt, _ = auth.hash_password("hunter2xyz", iterations=1000)
    assert auth.verify_password("hunter2xyz", {
        "password_hash": h, "salt": salt, "iterations": 1000,
    })


def test_verify_rejects_malformed_player():
    assert not auth.verify_password("x", {})
    assert not auth.verify_password("x", {"password_hash": "a", "salt": "zz", "iterations": "?"})


def test_username_is_normalized():
    assert auth.normalize_username("  AliCe ") == "alice"


@pytest.mark.parametrize("username", ["ab", "a" * 25, "Alice", "有中文", "a b", ""])
def test_bad_usernames_rejected(username):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        auth.validate_credentials(username, "longenoughpw")


def test_short_password_rejected():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        auth.validate_credentials("alice", "short")


def test_public_player_never_leaks_password_fields():
    out = auth.public_player({
        "username": "alice", "password_hash": "DEADBEEF", "salt": "CAFE", "iterations": 1,
    })
    assert "DEADBEEF" not in str(out) and "CAFE" not in str(out)
    assert set(out) == {"username", "nickname", "character", "stance", "favorites",
                        "created_at", "role"}


# ─────────────────── session 過期 ───────────────────

class _FakeTable:
    def __init__(self, item=None):
        self.item = item

    def get_item(self, Key):  # noqa: N803  (boto3 的參數就是大寫)
        return {"Item": self.item} if self.item else {}


def test_expired_session_is_treated_as_absent(monkeypatch):
    """DynamoDB TTL 的刪除是背景批次（官方說法「通常 48 小時內」），
    所以過期判斷必須由程式碼自己做，不能靠表沒資料。"""
    expired = {"token": "t", "username": "alice", "expires_at": int(time.time()) - 1}
    monkeypatch.setattr(store, "_sessions", lambda: _FakeTable(expired))
    assert store.get_session("t") is None

    fresh = {"token": "t", "username": "alice", "expires_at": int(time.time()) + 60}
    monkeypatch.setattr(store, "_sessions", lambda: _FakeTable(fresh))
    assert store.get_session("t")["username"] == "alice"


# ─────────────────── 端到端（假 store） ───────────────────

@pytest.fixture
def client(monkeypatch):
    players: dict = {}
    sessions: dict = {}

    def create_player(item):
        if item["username"] in players:
            return False
        players[item["username"]] = dict(item)
        return True

    def update_progress(username, progress):
        allowed = ("nickname", "character", "stance", "favorites")
        players[username].update({k: v for k, v in progress.items() if k in allowed})

    def create_session(token, username, ttl):
        sessions[token] = {"token": token, "username": username,
                           "expires_at": int(time.time()) + ttl}

    def get_session(token):
        s = sessions.get(token)
        if not s or s["expires_at"] <= int(time.time()):
            return None
        return s

    monkeypatch.setattr(store, "get_player", players.get)
    monkeypatch.setattr(store, "create_player", create_player)
    monkeypatch.setattr(store, "update_progress", update_progress)
    monkeypatch.setattr(store, "create_session", create_session)
    monkeypatch.setattr(store, "get_session", get_session)
    monkeypatch.setattr(store, "delete_session", lambda t: sessions.pop(t, None))

    with TestClient(app) as c:
        yield c


CREDS = {"username": "alice", "password": "hunter2xyz"}


def test_register_then_me(client):
    assert client.post("/api/auth/register", json=CREDS).status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["player"]["username"] == "alice"


def test_duplicate_registration_conflicts(client):
    client.post("/api/auth/register", json=CREDS)
    r = client.post("/api/auth/register", json=CREDS)
    assert r.status_code == 409


def test_registration_is_case_insensitive(client):
    client.post("/api/auth/register", json=CREDS)
    r = client.post("/api/auth/register", json={"username": "ALICE", "password": "otherpassword"})
    assert r.status_code == 409, "Alice 與 alice 必須是同一個帳號"


def test_login_with_wrong_password(client):
    client.post("/api/auth/register", json=CREDS)
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "alice", "password": "wrongpassword"})
    assert r.status_code == 401


def test_unknown_account_and_wrong_password_are_indistinguishable(client):
    """訊息不同等於送對方一支帳號列舉工具。"""
    client.post("/api/auth/register", json=CREDS)
    client.post("/api/auth/logout")
    a = client.post("/api/auth/login", json={"username": "alice", "password": "wrongpassword"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "wrongpassword"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_logout_clears_session(client):
    client.post("/api/auth/register", json=CREDS)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_progress_roundtrip(client):
    client.post("/api/auth/register", json=CREDS)
    r = client.put("/api/auth/progress", json={
        "nickname": "小明", "character": "hoodie", "favorites": ["lobby"],
    })
    assert r.status_code == 200
    player = client.get("/api/auth/me").json()["player"]
    assert player["nickname"] == "小明"
    assert player["character"] == "hoodie"
    assert player["favorites"] == ["lobby"]


def test_progress_cannot_overwrite_password(client):
    """白名單防線：把 password_hash 塞進進度更新不該生效。"""
    client.post("/api/auth/register", json=CREDS)
    client.put("/api/auth/progress", json={"nickname": "小明", "password_hash": "pwned"})
    client.post("/api/auth/logout")
    # 原密碼仍然可用 = 雜湊沒被蓋掉
    assert client.post("/api/auth/login", json=CREDS).status_code == 200


@pytest.mark.parametrize("path", ["/api/dashboard", "/api/positions", "/api/account_activity"])
def test_account_endpoints_require_login(client, path):
    """這三條是本次改動的主要目的：公開網址不能再直吐真實帳戶餘額與損益。"""
    assert client.get(path).status_code == 401


def test_chat_requires_login(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}],
                                       "model": "x"})
    assert r.status_code == 401


def test_public_endpoints_stay_open(client):
    """行情與設定不需要登入 —— 世界在登入前就要能顯示行情條。"""
    assert client.get("/api/config").status_code == 200


# ─────────────────── 角色：一般使用者 vs 官方帳號 ───────────────────

def test_role_defaults_to_user_for_legacy_records():
    """role 是後加的欄位。既有帳號的紀錄裡沒有它，讀不到必須降級成一般使用者 ——
    反過來（讀不到當官方）會讓所有舊帳號在某次部署後同時變成管理員。"""
    assert auth.role_of({}) == auth.ROLE_USER
    assert auth.role_of({"username": "alice"}) == auth.ROLE_USER


def test_unknown_role_value_degrades_to_user():
    """認不得的角色不該獲得比一般使用者更多的權限。"""
    assert auth.role_of({"role": "superadmin"}) == auth.ROLE_USER
    assert auth.role_of({"role": ""}) == auth.ROLE_USER
    assert auth.role_of({"role": auth.ROLE_OFFICIAL}) == auth.ROLE_OFFICIAL


def test_registration_creates_a_regular_user(client):
    client.post("/api/auth/register", json=CREDS)
    assert client.get("/api/auth/me").json()["player"]["role"] == auth.ROLE_USER


def test_user_cannot_promote_self_via_progress(client):
    """進度更新的白名單擋掉 role —— 否則一個 PUT 就能自己升成官方帳號。"""
    client.post("/api/auth/register", json=CREDS)
    client.put("/api/auth/progress", json={"nickname": "小明", "role": auth.ROLE_OFFICIAL})
    assert client.get("/api/auth/me").json()["player"]["role"] == auth.ROLE_USER


def test_require_official_rejects_regular_user(client, monkeypatch):
    """已登入但非官方要回 403 而不是 401：401 會讓前端跳登入視窗，
    但這個人已經登入了，再登一次也不會變成官方。"""
    from fastapi import HTTPException
    client.post("/api/auth/register", json=CREDS)

    class _Req:
        cookies = {auth.COOKIE_NAME: list(client.cookies.values())[0]}

    with pytest.raises(HTTPException) as e:
        auth.require_official(_Req())
    assert e.value.status_code == 403


def test_require_official_accepts_official(client, monkeypatch):
    client.post("/api/auth/register", json=CREDS)
    player = store.get_player("alice")
    player["role"] = auth.ROLE_OFFICIAL          # 模擬 scripts/grant_official.py 授予後

    class _Req:
        cookies = {auth.COOKIE_NAME: list(client.cookies.values())[0]}

    assert auth.require_official(_Req()) == "alice"


# ─────────────────── 本機免登入（MAIA_LOCAL_NO_LOGIN） ───────────────────

def _req(host, headers=None):
    from starlette.requests import Request
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (host, 50000)})


@pytest.fixture
def no_login(monkeypatch):
    monkeypatch.setenv("MAIA_LOCAL_NO_LOGIN", "1")


def test_local_no_login_is_off_by_default(monkeypatch):
    """沒明確打開就跟以前一樣要登入。app import 時會載入 .env，所以這裡主動清掉再驗。"""
    monkeypatch.delenv("MAIA_LOCAL_NO_LOGIN", raising=False)
    assert not auth.local_no_login(_req("127.0.0.1"))


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_local_no_login_allows_loopback_without_touching_store(no_login, monkeypatch, host):
    """放行時不查 session —— DynamoDB 沒開也要能 demo。"""
    def boom(_token):
        raise AssertionError("本機放行不該查 session")
    monkeypatch.setattr(store, "get_session", boom)
    assert auth.require_session_or_local(_req(host)) == auth.LOCAL_USERNAME


def test_local_no_login_rejects_remote_client(no_login):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        auth.require_session_or_local(_req("203.0.113.7"))
    assert e.value.status_code == 401


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "X-Real-IP"])
def test_local_no_login_rejects_forwarded_requests(no_login, header):
    """部署時 uvicorn 跑 --forwarded-allow-ips *，request.client 取的是 XFF 最左邊 ——
    客戶端自己填得了 127.0.0.1。帶任何轉發標頭就不算本機，偽造也沒用。"""
    assert not auth.local_no_login(_req("127.0.0.1", {header: "127.0.0.1"}))


@pytest.fixture
def local_client(no_login):
    # 不用 `with`：不跑 startup（策略機器人 runner、Telegram polling）
    return TestClient(app, client=("127.0.0.1", 50000))


def test_local_no_login_opens_chat(local_client):
    """body 故意缺 model：過了登入牆才輪到 body 驗證 → 422 而不是 401，也不會真的呼叫 LLM。"""
    assert local_client.post("/api/chat", json={"messages": []}).status_code == 422


def test_local_no_login_keeps_identity_endpoints_strict(local_client):
    """免登入只開「能不能用」的端點；身分相關的（我是誰、進度、發文、官方操作）仍要真的登入。"""
    assert local_client.get("/api/auth/me").status_code == 401


def test_local_no_login_opens_exactly_the_expected_routes():
    """逐條打會打到 MAX 真實 API，改檢查接線：放行的就是這六條，不多不少。"""
    opened = {
        (m, r.path)
        for r in app.routes if hasattr(r, "dependant")
        for m in r.methods
        if auth.require_session_or_local in {d.call for d in r.dependant.dependencies}
    }
    assert opened == {
        ("GET", "/api/dashboard"), ("GET", "/api/positions"), ("GET", "/api/account_activity"),
        ("POST", "/api/chat"), ("GET", "/api/orders"), ("POST", "/api/cancel_order"),
    }
