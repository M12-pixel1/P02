#!/usr/bin/env python3
"""
Prometheus Validation Contract - Single-file Patch Pack

This script writes the full patch pack (main.py, tests, smoke script, GitHub Actions workflow)
to the current working directory with the correct paths.

Usage:
  python prometheus_patch_pack.py

After running:
  pip install fastapi pydantic pytest uvicorn httpx
  pytest -v
  python -m uvicorn main:app --port 8000
  bash scripts/smoke_test_validation_contract.sh
"""

from __future__ import annotations

import os
from pathlib import Path

FILES: dict[str, str] = {}

FILES["main.py"] = r'''
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()

def loc_to_field(loc: list) -> str:
    """
    Field nustatymas tik iš loc (be msg scan / heuristikų).

    Taisyklės:
    - loc == ["body"] -> "body"
    - loc startswith ["body", <int>, <int>, ...] -> "body" (JSON decode offset / byte position)
    - loc startswith ["body", "field", ...] -> "field...." (nuimam "body")
    - kitais atvejais -> "query.x", "path.id", "header.x_token", ir t.t.

    Defensyvu:
    - ignoruojam None elementus (jei kada nors pasirodytų).
    """
    if not loc:
        return ""

    # Defensive: filter None (should be rare, but keeps handler 500-proof)
    loc_clean = [x for x in loc if x is not None]
    if not loc_clean:
        return ""

    if loc_clean[0] == "body":
        if len(loc_clean) == 1:
            return "body"

        rest = loc_clean[1:]

        # JSON decode error dažnai turi loc=("body", 11) arba ("body", 0, 1) — tik int indeksai/pozicijos
        if rest and all(isinstance(x, int) for x in rest):
            return "body"

        # Realūs field'ai (arba mixed path) — nuimam "body"
        return ".".join(str(x) for x in rest)

    return ".".join(str(x) for x in loc_clean)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for e in exc.errors():
        loc = list(e.get("loc", []))
        details.append({
            "field": loc_to_field(loc),
            "message": e.get("msg", ""),
            "type": e.get("type", ""),
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": 422,
                "message": "Validation Error",
                "details": details
            }
        }
    )


# Minimal test endpoints for validation contract
@app.get("/")
async def root():
    return {"message": "API is running"}


@app.post("/test")
async def test_endpoint(payload: dict):
    # Accept any dict to exercise JSON parsing and RequestValidationError paths
    return {"ok": True}


class ItemModel(BaseModel):
    name: str


class TestModel(BaseModel):
    name: str
    age: int
    email: Optional[str] = None
    items: Optional[List[ItemModel]] = None


@app.post("/test-model")
async def test_model_endpoint(item: TestModel):
    return {"ok": True, "data": item.model_dump()}


# Endpoints to validate query/path loc formatting (for contract tests)
@app.get("/users/{user_id}")
async def users(user_id: int, limit: int = 10):
    return {"user_id": user_id, "limit": limit}
'''.lstrip()

FILES["scripts/smoke_test_validation_contract.sh"] = r'''
#!/bin/bash
set -euo pipefail

API="http://localhost:8000"

echo "1) Health check"
curl -fsS "$API/" | head -c 120; echo

echo "2) Invalid JSON -> field=body"
RESP=$(curl -s -X POST "$API/test"   -H "Content-Type: application/json"   -d 'invalid json'   -w "
%{http_code}")
CODE=$(echo "$RESP" | tail -n1)
BODY=$(echo "$RESP" | head -n -1)
echo "$BODY" | jq .
test "$CODE" = "422"
test "$(echo "$BODY" | jq -r '.error.details[0].field')" = "body"

echo "3) Pydantic wrong type -> field includes age"
RESP=$(curl -s -X POST "$API/test-model"   -H "Content-Type: application/json"   -d '{"name":"Jonas","age":"x"}'   -w "
%{http_code}")
CODE=$(echo "$RESP" | tail -n1)
BODY=$(echo "$RESP" | head -n -1)
echo "$BODY" | jq .
test "$CODE" = "422"
echo "$BODY" | jq -e '.error.details[].field | select(.=="age")' >/dev/null

echo "4) Missing required field"
RESP=$(curl -s -X POST "$API/test-model"   -H "Content-Type: application/json"   -d '{"age":30}'   -w "
%{http_code}")
CODE=$(echo "$RESP" | tail -n1)
BODY=$(echo "$RESP" | head -n -1)
test "$CODE" = "422"
echo "$BODY" | jq .
echo "$BODY" | jq -e '.error.details[].field | select(.=="name")' >/dev/null

echo "5) Query param error -> field=query.limit"
RESP=$(curl -s "$API/users/123?limit=abc" -w "
%{http_code}")
CODE=$(echo "$RESP" | tail -n1)
BODY=$(echo "$RESP" | head -n -1)
echo "$BODY" | jq .
test "$CODE" = "422"
echo "$BODY" | jq -e '.error.details[].field | select(.=="query.limit")' >/dev/null

echo "6) Path param error -> field=path.user_id"
RESP=$(curl -s "$API/users/not_an_int?limit=10" -w "
%{http_code}")
CODE=$(echo "$RESP" | tail -n1)
BODY=$(echo "$RESP" | head -n -1)
echo "$BODY" | jq .
test "$CODE" = "422"
echo "$BODY" | jq -e '.error.details[].field | select(.=="path.user_id")' >/dev/null

echo "OK: smoke test passed"
'''.lstrip()

FILES["tests/test_validation_contract.py"] = r'''
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
'''.lstrip()

FILES[".github/workflows/p0-validation.yml"] = r'''
name: P0 Validation Contract

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  p0:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install system deps
        run: |
          sudo apt-get update
          sudo apt-get install -y jq

      - name: Install python deps
        run: |
          python -m pip install --upgrade pip
          pip install fastapi pydantic pytest uvicorn httpx

      - name: Pytest acceptance
        run: |
          pytest tests/test_validation_contract.py -v --tb=short

      - name: Start server
        run: |
          python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
          sleep 3

      - name: Smoke
        run: |
          chmod +x scripts/smoke_test_validation_contract.sh
          bash scripts/smoke_test_validation_contract.sh

      - name: No 500 check
        run: |
          status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:8000/test"             -H "Content-Type: application/json" -d "invalid json")
          echo "Invalid JSON status: $status"
          if [ "$status" -ge 500 ]; then
            echo "❌ Found 5xx"
            exit 1
          fi
          pkill -f "uvicorn main:app" || true
          echo "✅ No 5xx detected"
'''.lstrip()


def write_file(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def main() -> None:
    root = Path.cwd()
    for rel_path, data in FILES.items():
        write_file(root / rel_path, data)

    # Make scripts executable on *nix
    try:
        os.chmod(root / "scripts/smoke_test_validation_contract.sh", 0o755)
    except Exception:
        pass

    print("✅ Patch pack written:")
    for rel_path in FILES.keys():
        print(f" - {rel_path}")

    print("\nNext commands:")
    print("  pip install fastapi pydantic pytest uvicorn httpx")
    print("  pytest -v")
    print("  python -m uvicorn main:app --port 8000")
    print("  bash scripts/smoke_test_validation_contract.sh")


if __name__ == "__main__":
    main()
