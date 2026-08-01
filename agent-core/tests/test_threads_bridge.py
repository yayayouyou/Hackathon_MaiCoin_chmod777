from __future__ import annotations

import pytest

from agent_ui import threads_bridge as bridge


def _use_json_store(monkeypatch, tmp_path):
    monkeypatch.delenv("DYNAMODB_DISCUSSION_POSTS_TABLE", raising=False)
    monkeypatch.delenv("DYNAMODB_DISCUSSION_SPACES_TABLE", raising=False)
    monkeypatch.setattr(bridge, "_STORE", tmp_path / "posts.json")
    monkeypatch.setattr(bridge, "_SPACE_STORE", tmp_path / "spaces.json")


def _simple_room(monkeypatch, tmp_path):
    """一間已經有 Threads 根文、可以直接收留言的討論室。"""
    _use_json_store(monkeypatch, tmp_path)
    bridge._save_spaces([{
        "id": "room", "archived": False,
        "threads_root_id": "root-thread", "discussion_root_threads_id": "root-thread",
    }])
    bridge._upsert("room", {
        "id": "platform-root", "room_id": "room", "threads_id": "root-thread",
        "author": "MAIA", "text": "開場", "source": "platform", "is_thread_root": True,
    })


def _threads_is_down(*_args, **_kwargs):
    raise RuntimeError("THREADS_ACCESS_TOKEN is not configured")


def test_default_reply_targets_the_actual_discussion_root(monkeypatch, tmp_path):
    _use_json_store(monkeypatch, tmp_path)
    bridge._save_spaces([{
        "id": "mention-room",
        "archived": False,
        "threads_root_id": "maia-acknowledgement",
        "source_threads_id": "user-original-post",
    }])
    source = {
        "id": "threads-user-original-post",
        "room_id": "mention-room",
        "threads_id": "user-original-post",
        "source": "threads",
        "is_thread_root": True,
    }
    acknowledgement = {
        "id": "platform-acknowledgement",
        "room_id": "mention-room",
        "threads_id": "maia-acknowledgement",
        "source": "platform",
        "kind": "bridge",
        "threads_parent_id": "user-original-post",
    }
    bridge._upsert("mention-room", source)
    bridge._upsert("mention-room", acknowledgement)
    monkeypatch.setattr(bridge, "publish_platform_post", lambda *_: {"threads_id": "maia-reply"})

    post = bridge.create_platform_post("mention-room", "Alice", "hello")

    assert post["threads_parent_id"] == "user-original-post"
    assert post["parent_post_id"] == "threads-user-original-post"


def test_reconcile_links_child_imported_before_its_parent(monkeypatch, tmp_path):
    _use_json_store(monkeypatch, tmp_path)
    bridge._upsert("room", {
        "id": "child", "room_id": "room", "threads_id": "child-thread",
        "threads_parent_id": "parent-thread",
    })
    bridge._upsert("room", {
        "id": "parent", "room_id": "room", "threads_id": "parent-thread",
    })

    assert bridge._reconcile_parent_links("room") == 1
    assert bridge.list_posts("room")[0]["parent_post_id"] == "parent"


def test_reconcile_skips_hidden_bridge_acknowledgement(monkeypatch, tmp_path):
    _use_json_store(monkeypatch, tmp_path)
    bridge._upsert("room", {"id": "source", "room_id": "room", "threads_id": "source-thread"})
    bridge._upsert("room", {
        "id": "bridge", "room_id": "room", "threads_id": "bridge-thread",
        "threads_parent_id": "source-thread", "kind": "bridge",
    })
    bridge._upsert("room", {
        "id": "reply", "room_id": "room", "threads_id": "reply-thread",
        "threads_parent_id": "bridge-thread",
    })

    bridge._reconcile_parent_links("room")

    reply = next(post for post in bridge.list_posts("room") if post["id"] == "reply")
    assert reply["parent_post_id"] == "source"


# ─────────────── 落庫先於發佈：Threads 不能決定一則留言存不存在 ───────────────

def test_post_survives_a_threads_outage(monkeypatch, tmp_path):
    """Threads 掛掉時留言仍要進 DB —— 這是整條 DB 整合的重點。"""
    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", _threads_is_down)

    post = bridge.create_platform_post("room", "Alice", "在嗎")

    assert post["sync_state"] == "local"
    assert "THREADS_ACCESS_TOKEN" in post["sync_error"]
    stored = [p for p in bridge.list_posts("room") if p["id"] == post["id"]]
    assert len(stored) == 1
    assert stored[0]["text"] == "在嗎"


def test_publishing_after_storing_does_not_duplicate_the_post(monkeypatch, tmp_path):
    """post_key 若隨 threads_id 重算，舊的那列會留著，討論串就會出現兩則一樣的留言。"""
    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", _threads_is_down)
    post = bridge.create_platform_post("room", "Alice", "在嗎")
    key_before = post["post_key"]
    before = len(bridge.list_posts("room"))

    monkeypatch.setattr(bridge, "publish_platform_post",
                        lambda *_: {"threads_id": "late-id", "published_text": "在嗎"})
    bridge._publish_pending("room", post)

    after = bridge.list_posts("room")
    assert len(after) == before
    published = next(p for p in after if p["id"] == post["id"])
    assert published["sync_state"] == "published"
    assert published["threads_id"] == "late-id"
    assert published["post_key"] == key_before      # 鍵不能跟著改


def test_sync_publishes_posts_left_local(monkeypatch, tmp_path):
    """沒有這條補發路徑，local 就只是一個永遠不會消失的標籤。"""
    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", _threads_is_down)
    bridge.create_platform_post("room", "Alice", "在嗎")

    monkeypatch.setattr(bridge, "publish_platform_post", lambda *_: {"threads_id": "recovered"})
    monkeypatch.setattr(bridge, "_get_all_pages", lambda *_a, **_k: [])
    result = bridge.sync_threads("room")

    assert result["published"] == 1
    assert result["publish_errors"] == 0
    assert all(p.get("sync_state") != "local" for p in bridge.list_posts("room"))


def test_failed_republish_is_counted_not_raised(monkeypatch, tmp_path):
    """發不出去的留言（例如字數超限）不能讓整個同步中斷。"""
    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", _threads_is_down)
    bridge.create_platform_post("room", "Alice", "在嗎")
    monkeypatch.setattr(bridge, "_get_all_pages", lambda *_a, **_k: [])

    result = bridge.sync_threads("room")

    assert result["published"] == 0
    assert result["publish_errors"] == 1


# ─────────────────── 貼文要記下是哪個帳號、什麼身分發的 ───────────────────

def test_post_records_the_platform_account(monkeypatch, tmp_path):
    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", lambda *_: {"threads_id": "x"})

    bridge.create_platform_post("room", "小明", "哈囉", True, None, "alice", "official")

    stored = next(p for p in bridge.list_posts("room") if p["text"] == "哈囉")
    assert stored["username"] == "alice"
    assert stored["author_role"] == "official"
    assert stored["author"] == "小明"          # 顯示用的暱稱快照仍在


def test_author_role_is_snapshotted_at_post_time(monkeypatch, tmp_path):
    """撤銷官方身分後，先前以官方名義發的貼文不該追溯變成一般發言 ——
    那會跟已經同步出去的 Threads 貼文對不上。"""
    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", lambda *_: {"threads_id": "x"})
    bridge.create_platform_post("room", "小明", "官方公告", True, None, "alice", "official")
    monkeypatch.setattr(bridge, "publish_platform_post", lambda *_: {"threads_id": "y"})
    bridge.create_platform_post("room", "小明", "之後的發言", True, None, "alice", "user")

    roles = {p["text"]: p["author_role"] for p in bridge.list_posts("room") if p.get("author_role")}
    assert roles == {"官方公告": "official", "之後的發言": "user"}


# ─────────────────── 建立討論區維持 fail-fast（S7 的邊界） ───────────────────

def test_space_is_not_created_when_threads_rejects_the_opening_post(monkeypatch, tmp_path):
    """沒有 Threads 根文的討論區收不了任何留言，存下來只是製造一個壞掉的房間。"""
    _use_json_store(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", _threads_is_down)

    with pytest.raises(RuntimeError):
        bridge.create_space("題目", "小明", "開場白")

    assert bridge.list_spaces(True) == []


# ─────────────────── 端點層：使用者看到什麼、瀏覽器拿到什麼 ───────────────────

@pytest.fixture
def api(monkeypatch, tmp_path):
    """已登入的 TestClient，討論室走 JSON store、Threads 一律失敗。"""
    import time

    from fastapi.testclient import TestClient

    from agent_ui import store
    from agent_ui.app import app

    _simple_room(monkeypatch, tmp_path)
    monkeypatch.setattr(bridge, "publish_platform_post", _threads_is_down)

    players = {"alice": {"username": "alice", "nickname": "小明", "role": "user"}}
    sessions = {"tok": {"token": "tok", "username": "alice", "expires_at": int(time.time()) + 600}}
    monkeypatch.setattr(store, "get_player", players.get)
    monkeypatch.setattr(store, "get_session", sessions.get)

    with TestClient(app) as client:
        client.cookies.set("maia_session", "tok")
        yield client


def test_endpoint_reports_success_when_threads_is_down(api):
    """Threads 掛掉不是使用者的錯，也不該讓他以為留言沒送出 —— 留言確實已經進 DB。"""
    response = api.post("/api/discussions/room", json={"text": "在嗎"})

    assert response.status_code == 200
    assert response.json()["post"]["sync_state"] == "local"


def test_endpoint_never_exposes_the_login_account(api):
    """這個端點不需登入就讀得到，username 外流等於公開所有人的帳號。"""
    api.post("/api/discussions/room", json={"text": "在嗎"})

    created = api.post("/api/discussions/room", json={"text": "還在"}).json()["post"]
    listed = api.get("/api/discussions/room").json()["posts"]

    for post in [created, *listed]:
        assert "username" not in post
        assert "sync_error" not in post
        assert "raw_text" not in post
    assert bridge.list_posts("room")[-1]["username"] == "alice"   # DB 裡有，只是不外流
