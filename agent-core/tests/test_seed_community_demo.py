from datetime import datetime

from scripts.seed_community_demo import ROOMS, SEED_VERSION, build_records


def test_demo_seed_has_multiple_threads_users_and_balanced_volume():
    spaces, posts = build_records("2026-08-02")

    assert len(ROOMS) == len(spaces) == 6
    assert len(posts) == 30
    assert len({post["author_username"] for post in posts}) >= 8
    assert all(space["synthetic"] and space["demo_seed"] == SEED_VERSION for space in spaces)
    assert all(post["synthetic"] and post["sync_state"] == "demo" for post in posts)
    assert all(post["threads_id"] is None for post in posts)


def test_demo_posts_land_inside_requested_taipei_day():
    _spaces, posts = build_records("2026-08-02")
    utc_times = [datetime.fromisoformat(post["created_at"].replace("Z", "+00:00")) for post in posts]

    assert min(utc_times).isoformat() >= "2026-08-02T01:00:00+00:00"
    assert max(utc_times).isoformat() < "2026-08-02T16:00:00+00:00"
    assert len({(post["space_id"], post["post_key"]) for post in posts}) == len(posts)


def test_each_demo_room_has_one_root_and_a_reference():
    spaces, posts = build_records("2026-08-02")

    for space in spaces:
        room_posts = [post for post in posts if post["space_id"] == space["space_id"]]
        assert len(room_posts) == 5
        assert sum(post["is_thread_root"] for post in room_posts) == 1
        assert space["reference_url"].startswith("https://")
