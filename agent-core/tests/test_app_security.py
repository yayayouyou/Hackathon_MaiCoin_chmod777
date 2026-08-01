"""M4：核准/拒絕端點的來源驗證（擋瀏覽器 CSRF）。"""
import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient
from agent_ui.app import app, _APPROVAL_SECRET

client = TestClient(app)


def test_approve_without_secret_is_forbidden():
    r = client.post("/api/approve_order", json={"token": "appr-x"})
    assert r.status_code == 403


def test_approve_with_wrong_secret_is_forbidden():
    r = client.post("/api/approve_order", json={"token": "appr-x"},
                    headers={"X-Approval-Secret": "wrong"})
    assert r.status_code == 403


def test_reject_without_secret_is_forbidden():
    r = client.post("/api/reject_order", json={"token": "appr-x"})
    assert r.status_code == 403


def test_approve_with_correct_secret_passes_auth():
    # 通過來源驗證後才進入業務邏輯：未知 token → 200 + ERROR（而非 403）
    r = client.post("/api/approve_order", json={"token": "appr-nonexistent"},
                    headers={"X-Approval-Secret": _APPROVAL_SECRET})
    assert r.status_code == 200
    assert r.json()["status"] == "ERROR"


def test_config_exposes_secret_for_same_origin_frontend():
    assert client.get("/api/config").json().get("approval_secret")


def test_no_permissive_cors_is_configured():
    """核准端點的 CSRF 防線建立在「跨源讀不到 /api/config」之上。

    一旦有人為了讓 frontend-pixel 跨網域打後端而加上
    `CORSMiddleware(allow_origins=["*"])`，這條防線會**無聲**崩潰：
    惡意頁面就能先讀走 approval_secret，再帶著它 POST /api/approve_order。

    正確做法是讓前端同源（開發走 vite 的 /api proxy，部署走 CloudFront 的
    /api/* behavior）。這條測試就是那個決定的看門狗。
    """
    from starlette.middleware.cors import CORSMiddleware
    for m in app.user_middleware:
        assert m.cls is not CORSMiddleware, (
            "偵測到 CORSMiddleware。核准端點的 CSRF 防線依賴同源政策——"
            "請改用 proxy 讓前端同源，不要開 CORS。"
        )
