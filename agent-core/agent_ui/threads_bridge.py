"""Small, safe Threads bridge for the hackathon demo.

External content is stored as data only.  It is never passed to the trading
executor.  Production uses DynamoDB for shared discussion spaces/posts;
atomic JSON files remain available as a self-contained local fallback.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from pathlib import Path
from typing import Any

import requests

API_ROOT = "https://graph.threads.net"
_LOCK = threading.Lock()
_MENTION_SYNC_LOCK = threading.Lock()
_STORE = Path(os.getenv("DISCUSSION_STORE_PATH", "agent_memory/discussions.json"))
_SPACE_STORE = Path(os.getenv("DISCUSSION_SPACE_STORE_PATH", "agent_memory/discussion_spaces.json"))


def _ddb_table(env_name: str):
    name = (os.getenv(env_name) or "").strip()
    if not name:
        return None
    import boto3
    return boto3.resource("dynamodb", region_name=os.getenv("DYNAMODB_REGION") or None).Table(name)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _mentions_not_before() -> datetime | None:
    """Optional UTC cutoff that prevents historical @MAIA posts being re-imported."""
    raw = (os.getenv("THREADS_MENTIONS_NOT_BEFORE") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("THREADS_MENTIONS_NOT_BEFORE must be an ISO-8601 timestamp, e.g. 2026-08-01T00:00:00Z") from exc
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)


def _is_before_cutoff(timestamp: Any, cutoff: datetime | None) -> bool:
    if not cutoff:
        return False
    try:
        value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        value = value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    except ValueError:
        # A timestamp is required for a cutoff to be meaningful; reject unknown-age input.
        return True
    return value < cutoff


def _post_key(post: dict[str, Any]) -> str:
    """The sort key a post is filed under, computed once at insertion.

    Never recompute this for a post that is already stored.  A post that is
    published after being stored gains a ``threads_id`` and would land on a
    different key, and ``_save`` only puts — the row under the old key would
    survive and the discussion would show the message twice.
    """
    return "T#" + str(post["threads_id"]) if post.get("threads_id") else "P#" + str(post["id"])


def _load() -> dict[str, list[dict[str, Any]]]:
    table = _ddb_table("DYNAMODB_DISCUSSION_POSTS_TABLE")
    if table:
        rows, start = [], None
        while True:
            page = table.scan(**({"ExclusiveStartKey": start} if start else {}))
            rows.extend(page.get("Items", [])); start = page.get("LastEvaluatedKey")
            if not start: break
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            # post_key deliberately stays on the record so it survives a
            # round trip unchanged.  See _post_key.
            result.setdefault(row["space_id"], []).append(row)
        return result
    if not _STORE.exists():
        return {}
    try:
        value = json.loads(_STORE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(value: dict[str, list[dict[str, Any]]]) -> None:
    table = _ddb_table("DYNAMODB_DISCUSSION_POSTS_TABLE")
    if table:
        with table.batch_writer() as batch:
            for space_id, posts in value.items():
                for post in posts:
                    item = dict(post); item["space_id"] = space_id
                    item["post_key"] = post.get("post_key") or _post_key(post)
                    batch.put_item(Item=item)
        return
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    temp = _STORE.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(_STORE)


def _load_spaces() -> list[dict[str, Any]]:
    table = _ddb_table("DYNAMODB_DISCUSSION_SPACES_TABLE")
    if table:
        rows, start = [], None
        while True:
            page = table.scan(**({"ExclusiveStartKey": start} if start else {}))
            rows.extend(page.get("Items", [])); start = page.get("LastEvaluatedKey")
            if not start: break
        for row in rows:
            row["id"] = row.pop("space_id")
        return rows
    if not _SPACE_STORE.exists():
        return []
    try:
        value = json.loads(_SPACE_STORE.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_spaces(value: list[dict[str, Any]]) -> None:
    table = _ddb_table("DYNAMODB_DISCUSSION_SPACES_TABLE")
    if table:
        with table.batch_writer() as batch:
            for space in value:
                item = dict(space); item["space_id"] = item.pop("id")
                batch.put_item(Item=item)
        return
    _SPACE_STORE.parent.mkdir(parents=True, exist_ok=True)
    temp = _SPACE_STORE.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(_SPACE_STORE)


def list_spaces(include_archived: bool = False) -> list[dict[str, Any]]:
    with _LOCK:
        spaces = _load_spaces()
    visible = spaces if include_archived else [space for space in spaces if not space.get("archived")]
    return sorted(visible, key=lambda space: str(space.get("created_at") or ""), reverse=True)


def get_space(room_id: str) -> dict[str, Any] | None:
    """Return one discussion space, including archived spaces for state checks."""
    with _LOCK:
        space = next((item for item in _load_spaces() if item.get("id") == room_id), None)
    return dict(space) if space else None


def _require_active_space(room_id: str) -> dict[str, Any]:
    space = get_space(room_id)
    if not space:
        raise RuntimeError("discussion space was not found")
    if space.get("archived"):
        raise RuntimeError("discussion space is archived")
    if space.get("threads_deleted_at"):
        raise RuntimeError("the official Threads root has been deleted")
    return space


def create_space(title: str, creator: str, opening_text: str,
                 username: str | None = None, author_role: str | None = None) -> dict[str, Any]:
    room_id = f"topic-{secrets.token_urlsafe(6)}"
    space = {"id": room_id, "title": title[:120], "creator": creator[:60], "created_at": _now(), "archived": False}
    # The opening message is the official Threads root. The title names the
    # MAIA discussion room only, so both surfaces begin with the same content.
    #
    # Unlike a reply, this one must not fall back to a local-only record: every
    # later message hangs off this Threads id, so a room without it can never
    # accept a post.  Storing a room we know is broken helps nobody.
    remote = publish_platform_post(creator[:60], opening_text)
    root = {
        "id": f"topic-root-{secrets.token_urlsafe(8)}", "room_id": room_id,
        "author": creator[:60], "source_author": creator[:60], "text": opening_text,
        "username": username, "author_role": author_role,
        "source": "platform", "created_at": _now(), "threads_id": remote["threads_id"],
        "permalink": None, "sync_state": "published", "is_thread_root": True,
        "thread_root_id": None, "parent_post_id": None, "threads_parent_id": None, "kind": "topic",
    }
    _upsert(room_id, root)
    # Keep the discussion root separate from the MAIA-owned post used for
    # administrative deletion.  They happen to be the same for a room made
    # in MAIA, but differ for a room imported from a Threads mention.
    space["threads_root_id"] = root["threads_id"]
    space["discussion_root_threads_id"] = root["threads_id"]
    with _LOCK:
        spaces = _load_spaces()
        spaces.append(space)
        _save_spaces(spaces)
    return space


def archive_space(room_id: str) -> bool:
    with _LOCK:
        spaces = _load_spaces()
        for space in spaces:
            if space.get("id") == room_id:
                if space.get("archived"):
                    return False
                space["archived"] = True
                space["archived_at"] = _now()
                _save_spaces(spaces)
                return True
    return False


def delete_threads_root(room_id: str) -> dict[str, Any]:
    """Delete only MAIA's root post; caller must enforce official-admin access."""
    with _LOCK:
        spaces = _load_spaces()
        space = next((item for item in spaces if item.get("id") == room_id), None)
    if not space or not space.get("threads_root_id"):
        raise RuntimeError("discussion space or its Threads root was not found")
    deleted = _api("DELETE", f"/{space['threads_root_id']}")
    if deleted.get("success") is not True:
        raise RuntimeError(f"Threads did not confirm deletion: {deleted}")
    with _LOCK:
        spaces = _load_spaces()
        for item in spaces:
            if item.get("id") == room_id:
                item["threads_deleted_at"] = _now()
                item["archived"] = True
                _save_spaces(spaces)
                break
    return {"room_id": room_id, "threads_root_id": space["threads_root_id"], "archived": True}


def list_posts(room_id: str) -> list[dict[str, Any]]:
    # Also repair legacy records when the room is opened.  This is a no-op once
    # the links are correct and lets old, flat MAIA views recover without a
    # manual database migration.
    _reconcile_parent_links(room_id)
    with _LOCK:
        return sorted(_load().get(room_id, []), key=lambda post: str(post.get("created_at") or ""))


def _upsert(room_id: str, post: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    # _LOCK only serializes writers inside one process.  Reading the whole
    # store, mutating it and writing it back is therefore safe for a single
    # container only — two instances accepting posts concurrently would each
    # overwrite the other's message with no error.  Deploy one instance, or
    # move to per-item writes first.
    with _LOCK:
        store = _load()
        posts = store.setdefault(room_id, [])
        remote_id = post.get("threads_id")
        if remote_id:
            for current in posts:
                if current.get("threads_id") == remote_id:
                    return current, False
        post.setdefault("post_key", _post_key(post))
        posts.append(post)
        _save(store)
        return post, True


def update_post(room_id: str, post_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    """Persist a change to one stored post.

    _load() rebuilds every record from storage, so mutating the dict a caller
    happens to be holding never reaches the database.
    """
    with _LOCK:
        store = _load()
        for post in store.get(room_id, []):
            if post.get("id") == post_id:
                post.update(patch)
                _save(store)
                return post
    return None


def _reconcile_parent_links(room_id: str) -> int:
    """Repair parent ids once all pages of a Threads conversation are present.

    Threads may return a child before its parent.  Persisting a missing parent
    at import time made the MAIA view permanently flat because later syncs
    deduplicated that child.  Resolve links from the durable Threads ids after
    every import instead.
    """
    with _LOCK:
        store = _load()
        posts = store.get(room_id, [])
        by_threads_id = {str(post.get("threads_id")): post for post in posts if post.get("threads_id")}
        changed = 0
        for post in posts:
            parent_threads_id = str(post.get("threads_parent_id") or "")
            parent = by_threads_id.get(parent_threads_id)
            # The acknowledgement created for a mentioned post is hidden in
            # MAIA.  Its children must therefore attach to the first visible
            # ancestor, otherwise the UI has no parent to render.
            seen_parent_ids: set[str] = set()
            while parent and parent.get("kind") == "bridge":
                parent_id = str(parent.get("threads_id") or "")
                if not parent_id or parent_id in seen_parent_ids:
                    parent = None
                    break
                seen_parent_ids.add(parent_id)
                parent = by_threads_id.get(str(parent.get("threads_parent_id") or ""))
            if parent and parent is not post and post.get("parent_post_id") != parent.get("id"):
                post["parent_post_id"] = parent["id"]
                changed += 1
        if changed:
            _save(store)
        return changed


def _token() -> str:
    token = (os.getenv("THREADS_ACCESS_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("THREADS_ACCESS_TOKEN is not configured")
    return token


def _api(method: str, path: str, *, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        request_fn = {"GET": requests.get, "POST": requests.post, "DELETE": requests.delete}.get(method.upper())
        if request_fn is None:
            raise RuntimeError(f"unsupported Threads method: {method}")
        headers = {"Authorization": f"Bearer {_token()}"}
        body = data
        if method.upper() == "POST" and data is not None:
            # Explicit UTF-8 avoids Windows console / default form encoding corrupting Chinese text.
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
            body = urlencode(data, encoding="utf-8", errors="strict").encode("utf-8")
        response = request_fn(f"{API_ROOT}{path}", headers=headers, params=params, data=body, timeout=15)
    except requests.RequestException as exc:
        raise RuntimeError(f"Threads API network error: {exc}") from exc
    if not response.ok:
        raise RuntimeError(f"Threads API HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def _get_all_pages(path: str, *, fields: str, page_size: int = 50, extra_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read every cursor page from a Threads collection without looping forever."""
    params: dict[str, Any] = {"fields": fields, "limit": min(max(page_size, 1), 50)}
    if extra_params:
        params.update(extra_params)
    items: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()
    while True:
        page = _api("GET", path, params=params)
        data = page.get("data", [])
        if isinstance(data, list):
            items.extend(item for item in data if isinstance(item, dict))
        cursor = str(((page.get("paging") or {}).get("cursors") or {}).get("after") or "")
        if not data or not cursor or cursor in seen_cursors:
            return items
        seen_cursors.add(cursor)
        params["after"] = cursor


def publish_platform_post(author: str, text: str, reply_to_id: str | None = None) -> dict[str, Any]:
    """Publish a root post or a reply as the official account."""
    prefix = f"[MAIA 平台｜{author}]\n"
    available = 500 - len(prefix)
    if available < 1 or len(text) > available:
        raise RuntimeError(f"Threads 內容最多可輸入 {max(available, 0)} 字（已包含 MAIA 署名）")
    body = prefix + text
    payload: dict[str, Any] = {"media_type": "TEXT", "text": body}
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id
    creation = _api("POST", "/me/threads", data=payload)
    creation_id = creation.get("id")
    if not creation_id:
        raise RuntimeError("Threads did not return a creation id")
    # Threads containers are eventually consistent. Publishing immediately can
    # return subcode 4279009 (container/media not found) even though creation
    # succeeded. Retry only that known readiness race; other API errors remain
    # fail-fast so invalid tokens and permissions are not hidden.
    published = None
    for attempt in range(5):
        try:
            published = _api("POST", "/me/threads_publish", data={"creation_id": creation_id})
            break
        except RuntimeError as exc:
            message = str(exc)
            if "4279009" not in message or attempt == 4:
                raise
            time.sleep(attempt + 1)
    assert published is not None
    thread_id = published.get("id")
    if not thread_id:
        raise RuntimeError("Threads did not return a post id")
    return {"threads_id": str(thread_id), "published_text": body}


def _publish_pending(room_id: str, post: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Try to push one already-stored post to Threads, recording the outcome.

    Never raises: the post is durable before this runs, and Threads being
    unavailable must not cost the platform a message.
    """
    try:
        remote = publish_platform_post(post["author"], post["text"], post.get("threads_parent_id"))
    except RuntimeError as exc:
        updated = update_post(room_id, post["id"], {"sync_state": "local", "sync_error": str(exc)[:200]})
        return updated or post, False
    updated = update_post(room_id, post["id"], {**remote, "sync_state": "published", "sync_error": ""})
    return updated or post, True


def create_platform_post(room_id: str, author: str, text: str, publish: bool = True,
                         parent_post_id: str | None = None,
                         username: str | None = None, author_role: str | None = None) -> dict[str, Any]:
    # One MAIA discussion room maps to one Threads root post.  Every later
    # platform message becomes a reply under that root, never a new root post.
    space = _require_active_space(room_id)
    existing = list_posts(room_id)
    root = next((p for p in existing if p.get("is_thread_root") and p.get("threads_id")), None)
    parent = next((p for p in existing if p.get("id") == parent_post_id), None)
    discussion_root_id = str(
        space.get("discussion_root_threads_id")
        or space.get("source_threads_id")  # compatibility with rooms imported before this field existed
        or (root or {}).get("threads_id")
        or ""
    )
    if not discussion_root_id:
        raise RuntimeError("discussion space has no official Threads root")
    if parent_post_id and not parent:
        raise RuntimeError("reply target was not found in this discussion space")
    if parent and publish and not parent.get("threads_id"):
        raise RuntimeError("reply target has not been published to Threads")
    effective_parent = parent or next((p for p in existing if p.get("threads_id") == discussion_root_id), None)
    post: dict[str, Any] = {
        "id": f"platform-{secrets.token_urlsafe(8)}", "room_id": room_id,
        "author": author[:60], "text": text, "source": "platform",
        "source_author": author[:60], "created_at": _now(), "threads_id": None,
        # The platform account behind the message.  author is only a nickname
        # snapshot and nicknames are not unique, so it cannot identify anyone.
        # author_role is likewise a snapshot: revoking someone's official
        # status must not retroactively rewrite posts they already made under
        # it, which are mirrored on Threads and cannot be rewritten there.
        "username": username, "author_role": author_role,
        "permalink": None, "sync_state": "local", "is_thread_root": False,
        "thread_root_id": discussion_root_id,
        # An untargeted MAIA message is a direct reply to the actual discussion
        # root.  For mention-imported rooms this is the user's original post,
        # not MAIA's automated "synced" acknowledgement.
        "parent_post_id": effective_parent.get("id") if effective_parent else parent_post_id,
        "threads_parent_id": effective_parent.get("threads_id") if effective_parent else discussion_root_id,
    }
    # Store first, publish second.  Threads is a mirror of the discussion, not
    # a gate on it: an outage, an expired token or an over-length body must
    # leave the message in the database rather than discard it.  sync_threads()
    # retries whatever is still marked local.
    stored = _upsert(room_id, post)[0]
    if not publish:
        return stored
    return _publish_pending(room_id, stored)[0]


def _mention_content(raw_text: str) -> str:
    """Keep only the human-written body of a valid #MAIA_SYNC source post."""
    match = re.search(r"(?is)(?:^|\n)\s*內容\s*[：:]\s*(.+?)\s*$", raw_text)
    if match:
        return match.group(1).strip()
    # Keep a useful fallback for older / incomplete posts without a 內容 line.
    lines = [line.strip() for line in raw_text.splitlines()]
    kept = [line for line in lines if line and "#MAIA_SYNC" not in line.upper()
            and not re.match(r"^@[^\s]+$", line) and not re.match(r"^主題\s*[：:]", line)]
    return "\n".join(kept).strip() or raw_text.strip()


def _external_post(item: dict[str, Any], room_id: str, kind: str) -> dict[str, Any]:
    remote_id = str(item.get("id") or "")
    raw_text = str(item.get("text") or "")
    display_text = _mention_content(raw_text) if kind == "mention" else raw_text
    return {
        "id": f"threads-{remote_id}", "room_id": room_id, "threads_id": remote_id,
        "author": "MAIA 官方帳號", "source_author": item.get("username") or "Threads user",
        "text": display_text, "raw_text": raw_text, "source": "threads", "kind": kind,
        "created_at": item.get("timestamp") or _now(), "permalink": item.get("permalink"),
        "sync_state": "imported", "threads_parent_id": (item.get("replied_to") or {}).get("id"), "parent_post_id": None,
    }


def sync_threads(room_id: str, limit: int = 50) -> dict[str, int]:
    """Import mentions plus replies under official posts, deduplicated by id."""
    space = _require_active_space(room_id)
    fields = "id,text,username,timestamp,permalink,root_post,replied_to"
    # New @MAIA posts belong to their own spaces and are handled only by
    # sync_mentions_to_spaces().  A room-level sync must never mix them here.
    imported_mentions = imported_replies = reply_errors = mention_errors = 0

    # Drain anything create_platform_post could not publish before importing,
    # so a message stranded by an outage reaches Threads on the next sync
    # instead of staying local forever.  Publish first: a post that lands now
    # is a parent the import below can attach incoming replies to.
    published = publish_errors = 0
    for post in list_posts(room_id):
        if post.get("source") == "platform" and post.get("sync_state") == "local":
            _, ok = _publish_pending(room_id, post)
            published += int(ok)
            publish_errors += int(not ok)

    # A locally created room is rooted at MAIA's post.  A room created from a
    # mention is rooted at the original Threads post, while MAIA's automated
    # acknowledgement is merely one child.  Query the real discussion root in
    # both cases, otherwise direct replies are attached to the acknowledgement.
    root_id = str(
        space.get("discussion_root_threads_id")
        or space.get("source_threads_id")  # compatibility with older imported rooms
        or space.get("threads_root_id")
        or ""
    )
    if not root_id:
        raise RuntimeError("discussion space has no Threads discussion root")
    for threads_root_id in [root_id]:
        try:
            replies = _get_all_pages(
                f"/{threads_root_id}/conversation",
                fields=fields,
                page_size=limit,
                extra_params={"reverse": "false"},
            )
        except RuntimeError:
            try:
                replies = _get_all_pages(f"/{threads_root_id}/replies", fields=fields, page_size=limit)
            except RuntimeError:
                reply_errors += 1
                continue
        for item in replies:
            imported = _external_post(item, room_id, "reply")
            parent = next((p for p in list_posts(room_id) if p.get("threads_id") == imported.get("threads_parent_id")), None)
            if parent:
                imported["parent_post_id"] = parent.get("id")
            _, added = _upsert(room_id, imported)
            imported_replies += int(added)
    _reconcile_parent_links(room_id)
    return {"mentions": imported_mentions, "replies": imported_replies,
            "mention_errors": mention_errors, "reply_errors": reply_errors,
            "published": published, "publish_errors": publish_errors}


def sync_mentions_to_spaces(limit: int = 50) -> dict[str, int]:
    """Serialize mention imports so manual and automatic sync cannot duplicate a bridge."""
    if not _MENTION_SYNC_LOCK.acquire(blocking=False):
        return {"created": 0, "skipped": 0, "stale": 0, "errors": 0, "busy": 1}
    try:
        return _sync_mentions_to_spaces(limit)
    finally:
        _MENTION_SYNC_LOCK.release()


def _sync_mentions_to_spaces(limit: int = 50) -> dict[str, int]:
    """Turn each newly-mentioned external Threads post into its own MAIA space."""
    fields = "id,text,username,timestamp,permalink,is_reply"
    try:
        mentions = _get_all_pages("/me/mentions", fields=fields, page_size=limit)
    except RuntimeError:
        return {"created": 0, "skipped": 0, "stale": 0, "errors": 1, "busy": 0}
    existing = {space.get("source_threads_id") for space in list_spaces(True)}
    cutoff = _mentions_not_before()
    created = skipped = stale = 0
    for item in mentions:
        source_id = str(item.get("id") or "")
        text = str(item.get("text") or "")
        title_match = re.search(r"(?im)^\s*主題\s*[：:]\s*(.+?)\s*$", text)
        if _is_before_cutoff(item.get("timestamp"), cutoff):
            stale += 1
            continue
        if (not source_id or source_id in existing or item.get("is_reply")
                or "#MAIA_SYNC" not in text.upper() or not title_match):
            skipped += 1
            continue
        room_id = f"mention-{secrets.token_urlsafe(6)}"
        bridge = publish_platform_post("MAIA 官方帳號", "此討論已同步至 MAIA 平台；可直接回覆本串。", source_id)
        root = {"id": f"platform-{secrets.token_urlsafe(8)}", "room_id": room_id, "author": "MAIA 官方帳號", "source_author": "MAIA 官方帳號", "text": "此討論已同步至 MAIA 平台；可直接回覆本串。", "source": "platform", "created_at": _now(), "threads_id": bridge["threads_id"], "is_thread_root": True, "thread_root_id": None, "sync_state": "published", "kind": "bridge"}
        # This automated acknowledgement is a child of the mentioned post;
        # it is not the root users should reply to.
        root["threads_parent_id"] = source_id
        _upsert(room_id, root)
        source = _external_post(item, room_id, "mention")
        source.update({"is_thread_root": True, "thread_root_id": source_id})
        _upsert(room_id, source)
        with _LOCK:
            spaces = _load_spaces()
            spaces.append({"id": room_id, "title": title_match.group(1)[:120], "creator": item.get("username") or "Threads user", "created_at": _now(), "archived": False, "threads_root_id": bridge["threads_id"], "discussion_root_threads_id": source_id, "source_threads_id": source_id, "source_permalink": item.get("permalink")})
            _save_spaces(spaces)
        created += 1
    return {"created": created, "skipped": skipped, "stale": stale, "errors": 0, "busy": 0}
