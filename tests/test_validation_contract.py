import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def assert_422_contract(resp):
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == 422
    assert body["error"]["message"] == "Validation Error"
    assert isinstance(body["error"]["details"], list)
    assert len(body["error"]["details"]) >= 1
    d0 = body["error"]["details"][0]
    assert set(d0.keys()) == {"field", "message", "type"}

def test_invalid_json_parsing_field_body():
    """Invalid JSON -> RequestValidationError su loc=("body",) arba ("body", <int>)"""
    resp = client.post(
        "/test",
        content="invalid json",
        headers={"Content-Type": "application/json"}
    )
    assert_422_contract(resp)
    assert resp.json()["error"]["details"][0]["field"] == "body"

def test_wrong_type_body_field_strips_body_prefix():
    """Wrong type in body field -> strips body prefix"""
    resp = client.post("/test-model", json={"name": "Jonas", "age": "not_a_number"})
    assert_422_contract(resp)
    fields = [d["field"] for d in resp.json()["error"]["details"]]
    assert "age" in fields

def test_missing_required_field():
    """Missing required field -> field name without body prefix"""
    resp = client.post("/test-model", json={"age": 30})
    assert_422_contract(resp)
    fields = [d["field"] for d in resp.json()["error"]["details"]]
    assert "name" in fields

def test_nested_field_location():
    """Nested array error -> correct field path"""
    resp = client.post("/test-model", json={
        "name": "Jonas",
        "age": 30,
        "items": [{}]
    })
    assert_422_contract(resp)
    fields = [d["field"] for d in resp.json()["error"]["details"]]
    assert "items.0.name" in fields

def test_query_param_error_location():
    """Query param validation error -> field with query prefix"""
    resp = client.get("/users/123?limit=abc")
    assert_422_contract(resp)
    fields = [d["field"] for d in resp.json()["error"]["details"]]
    assert "query.limit" in fields

def test_path_param_error_location():
    """Path param validation error -> field with path prefix"""
    resp = client.get("/users/not_an_int?limit=10")
    assert_422_contract(resp)
    fields = [d["field"] for d in resp.json()["error"]["details"]]
    assert "path.user_id" in fields

def test_no_500_errors():
    """Ensure invalid inputs return 4xx, not 500"""
    invalid_requests = [
        ("POST", "/test", "invalid json"),
        ("POST", "/test-model", {"age": "not_a_number"}),
        ("GET", "/users/not_an_int?limit=abc", None),
    ]
    for method, url, data in invalid_requests:
        resp = client.request(
            method,
            url,
            json=data if isinstance(data, dict) else None,
            content=data if isinstance(data, str) else None,
            headers={"Content-Type": "application/json"} if isinstance(data, str) else None,
        )
        assert resp.status_code < 500, f"Got 5xx for {method} {url}"
