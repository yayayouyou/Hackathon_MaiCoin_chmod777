from __future__ import annotations

import json
from types import SimpleNamespace

from agent_ui import community_insights as insights


class FakeProvider:
    model = "fake-bedrock"

    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=json.dumps({
            "headline": "社群關注風險控管",
            "summary": "昨日討論集中在分批布局與回測風險。",
            "directions": [{"topic": "分批布局", "why_it_matters": "參與者關心下跌風險。"}],
            "disagreements": ["進場時點仍有分歧"],
            "sentiment": -12,
        }, ensure_ascii=False))


def _use_store(monkeypatch, tmp_path):
    monkeypatch.setattr(insights, "_STORE", tmp_path / "community-insights.json")


def test_posts_for_day_uses_taipei_calendar_boundary(monkeypatch):
    monkeypatch.setattr(insights, "list_posts", lambda _room_id: [
        {"id": "before", "created_at": "2026-07-31T15:59:59Z", "text": "before"},
        {"id": "start", "created_at": "2026-07-31T16:00:00Z", "text": "start"},
        {"id": "end", "created_at": "2026-08-01T15:59:59Z", "text": "end"},
        {"id": "after", "created_at": "2026-08-01T16:00:00Z", "text": "after"},
        {"id": "hidden", "created_at": "2026-08-01T01:00:00Z", "text": "bridge", "kind": "bridge"},
    ])

    assert [post["id"] for post in insights.posts_for_day("room", "2026-08-01")] == ["start", "end"]


def test_empty_room_uses_deterministic_insight_without_bedrock(monkeypatch, tmp_path):
    _use_store(monkeypatch, tmp_path)
    monkeypatch.setattr(insights, "posts_for_day", lambda *_: [])
    provider = FakeProvider()

    result = insights.generate_room_insight({"id": "room-1", "title": "BTC"}, "2026-08-01", provider)

    assert result["post_count"] == 0
    assert result["model"] == "deterministic"
    assert provider.calls == []


def test_daily_generation_builds_rooms_before_lobby(monkeypatch, tmp_path):
    _use_store(monkeypatch, tmp_path)
    monkeypatch.setattr(insights, "list_spaces", lambda: [
        {"id": "room-1", "title": "BTC"},
        {"id": "room-2", "title": "ETH"},
    ])
    monkeypatch.setattr(insights, "posts_for_day", lambda room_id, _day: [
        {"id": f"{room_id}-post", "text": "昨日留言", "created_at": "2026-08-01T01:00:00Z"},
    ])
    provider = FakeProvider()

    result = insights.generate_daily_insights("2026-08-01", provider)

    assert result["rooms"] == 2
    assert result["lobby"]["room_count"] == 2
    assert result["lobby"]["post_count"] == 2
    assert len(provider.calls) == 3
    assert insights.get_insight("room", "2026-08-01", "room-1") is not None
    assert insights.get_insight("lobby", "2026-08-01") is not None

    # Scheduled checks are cheap and do not call Bedrock again while the
    # source counts and prompt version remain unchanged.
    insights.generate_daily_insights("2026-08-01", provider)
    assert len(provider.calls) == 3
