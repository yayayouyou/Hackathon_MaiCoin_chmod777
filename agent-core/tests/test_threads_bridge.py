from __future__ import annotations

from agent_ui import threads_bridge as bridge


def _use_json_store(monkeypatch, tmp_path):
    monkeypatch.delenv("DYNAMODB_DISCUSSION_POSTS_TABLE", raising=False)
    monkeypatch.delenv("DYNAMODB_DISCUSSION_SPACES_TABLE", raising=False)
    monkeypatch.setattr(bridge, "_STORE", tmp_path / "posts.json")
    monkeypatch.setattr(bridge, "_SPACE_STORE", tmp_path / "spaces.json")


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
