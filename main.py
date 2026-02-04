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
