from unittest.mock import patch, AsyncMock


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_no_auth(client):
    resp = client.post("/api/v1/analyze", json={"text": "hello", "platform": "reddit"})
    assert resp.status_code == 401


def test_analyze_missing_input(client, auth_headers):
    resp = client.post("/api/v1/analyze", json={}, headers=auth_headers)
    assert resp.status_code == 400


def test_analyze_text_missing_platform(client, auth_headers):
    resp = client.post(
        "/api/v1/analyze",
        json={"text": "some post about AI prompts"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@patch("routes.analyze.generate_reply", new_callable=AsyncMock)
def test_analyze_with_text(mock_reply, client, auth_headers):
    mock_reply.return_value = {
        "skip": False,
        "draft_reply": "Here's some helpful advice about prompts.",
        "reasoning": "Relevant post about AI prompts.",
    }
    resp = client.post(
        "/api/v1/analyze",
        json={
            "text": "How do I write better system prompts for ChatGPT?",
            "platform": "reddit",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skip"] is False
    assert data["draft_reply"] is not None
    assert data["post"]["platform"] == "reddit"


@patch("routes.analyze.generate_reply", new_callable=AsyncMock)
def test_analyze_skip(mock_reply, client, auth_headers):
    mock_reply.return_value = {
        "skip": True,
        "draft_reply": None,
        "reasoning": "Post about cooking, not AI.",
    }
    resp = client.post(
        "/api/v1/analyze",
        json={"text": "Best pasta recipe?", "platform": "reddit"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skip"] is True
    assert data["draft_reply"] is None
