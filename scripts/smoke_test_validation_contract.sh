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
