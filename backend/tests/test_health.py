def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "roskyro-healthcare-os-api"


def test_unknown_route_is_json_404(client):
    """Regression guard: main.py's exception handler must reshape FastAPI's
    default 404 into the app's flat `{"error": "..."}` convention (not
    Starlette's default `{"detail": "Not Found"}`), since the frontend's
    error handling reads `error`."""
    resp = client.get("/api/this-route-does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.json()
