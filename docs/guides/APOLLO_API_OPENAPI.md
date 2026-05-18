# API & OpenAPI Guide — Apollo (reference copy)

> **Source:** <https://github.com/Fujio-Turner/Apollo/blob/main/guides/API_OPENAPI.md>
>
> Stored here verbatim as the reference spec that the `json-serialize-merger`
> Python server (`example_python/server.py`) follows for its public API
> surface (route layout, error response shape, OpenAPI organization,
> reusable error responses, tagging conventions).

---

# API & OpenAPI Guide — Apollo

> Spec format: [OpenAPI 3.1.0](https://spec.openapis.org/oas/latest.html)
>
> Live docs:
> - [`/api-docs`](http://localhost:9090/api-docs) — Swagger UI **rendering the hand-maintained `docs/openapi.yaml`** (curated descriptions, examples, schemas)
> - [`/openapi.yaml`](http://localhost:9090/openapi.yaml) — raw YAML spec, served verbatim for external clients & codegen
> - [`/docs`](http://localhost:9090/docs) (Swagger UI) and [`/redoc`](http://localhost:9090/redoc) — **FastAPI auto-generated** views derived from `server.py`

---

## 1. What Is OpenAPI?

OpenAPI is a **YAML/JSON specification** that describes a REST API in a machine-readable format. It is **not** an HTML page — it's a structured data file that tools render into interactive documentation, client SDKs, and test suites.

Our spec lives at `docs/openapi.yaml`. The human-friendly markdown summary lives at `docs/API.md`.

### What We Ship

| Artifact | Path | Purpose |
|---|---|---|
| OpenAPI spec | `docs/openapi.yaml` | Machine-readable, source of truth |
| Markdown reference | `docs/API.md` | Quick-reference for developers |
| Swagger UI | `/docs` (live) | Interactive explorer (auto-served by FastAPI) |
| Redoc | `/redoc` (live) | Clean read-only docs (auto-served by FastAPI) |

FastAPI auto-generates Swagger UI and Redoc from the route definitions in `server.py`. The `openapi.yaml` file is our **hand-maintained** spec that includes richer descriptions, examples, and reusable schemas.

---

## 2. Project Structure

```
docs/
├── openapi.yaml          # OpenAPI 3.1 spec — ALL endpoints
├── API.md                 # Markdown quick reference
└── DESIGN.md              # Links to both

apollo/web/
└── server.py              # FastAPI app — route definitions + error handlers
```

---

## 3. How Errors Work

All API errors return a consistent JSON shape. This is enforced by three global exception handlers registered in `create_app()` inside `server.py`.

### Error Response Shape

```json
{
  "status_code": 400,
  "error": "Bad Request",
  "detail": "Not a directory: /foo"
}
```

| Field | Type | Description |
|---|---|---|
| `status_code` | `int` | HTTP status code (matches the response status) |
| `error` | `string` | Human-readable error category (from `HTTPStatus.phrase`) |
| `detail` | `string \| object \| array` | Specific error message or validation payload |

### Exception Handlers

The three handlers in `server.py` catch everything:

```
HTTPException          →  { status_code, HTTPStatus.phrase, exc.detail }
RequestValidationError →  { 422, "Validation Error", exc.errors() }
Exception (catch-all)  →  { 500, "Internal Server Error", "An unexpected error occurred" }
```

### How to Raise Errors in Endpoint Code

Use FastAPI's built-in `HTTPException`. The global handler normalizes it automatically:

```python
from fastapi import HTTPException

# In an endpoint:
raise HTTPException(status_code=404, detail="Node not found: func::main.py::foo")
raise HTTPException(status_code=400, detail="Not a directory: /tmp/bad")
raise HTTPException(status_code=503, detail="Chat not available. Set XAI_API_KEY.")
```

**Do not** return error dicts manually with 200 status codes. Always `raise HTTPException(...)` so the response flows through the global handler and gets the standard shape.

### Reusable Error Responses in openapi.yaml

Six reusable error responses are defined under `components/responses/`:

| Ref Name | Code | When to use |
|---|---|---|
| `BadRequest` | 400 | Invalid input, bad path, missing required field |
| `NotFound` | 404 | Node, thread, or resource not found |
| `ValidationError` | 422 | Pydantic / query-param validation failures |
| `ServiceUnavailable` | 503 | AI chat or image generation not configured |
| `UnsupportedOperation` | 501 | Feature unavailable in current environment (e.g. Docker) |
| `InternalServerError` | 500 | Unexpected server error |

Reference them in path definitions with `$ref`:

```yaml
"400":
  $ref: "#/components/responses/BadRequest"
```

---

## 4. Tags

Every endpoint belongs to exactly one tag. Tags group endpoints in the docs UI and in `openapi.yaml`.

| Tag | Prefix | Description |
|---|---|---|
| System | `/api/env`, `/api/version` | Runtime environment flags and backend version |
| ... | ... | (see Apollo project for full list — adapt the table to your domain) |

When adding a new endpoint, assign it to an existing tag. If none fit, add a new tag entry to both the `tags:` list in `openapi.yaml` and the table above.

---

## 5. Adding a New Endpoint

### Step 1 — Write the Route in `server.py`

Add your endpoint inside `create_app()`, grouped with related routes. Follow the existing pattern:

```python
@app.post("/api/bookmarks")
async def create_bookmark(request: Request):
    body = await request.json()
    title = body.get("title", "")
    node_id = body.get("node_id")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    return {"id": bookmark_id, "title": title, "node_id": node_id}
```

**Conventions:**
- All API routes start with `/api/`.
- Use `async def` for endpoints that do I/O or call `await`.
- Parse JSON bodies with `request.json()` (no Pydantic models yet — we may adopt them later).
- Return plain dicts — FastAPI serializes them to JSON.
- Raise `HTTPException` for errors — never return error dicts with 200.
- Place the route near related endpoints.

### Step 2 — Add to `docs/openapi.yaml`

Add a new path entry under `paths:`. Every endpoint needs an `operationId` (camelCase, unique) and at least one success response plus relevant `$ref`-ed error responses.

### Step 3 — Add to `docs/API.md`

Document the endpoint in human-readable form.

### Step 4 — Verify

Start the server, open `/docs`, click "Try it out", verify the standard
`{status_code, error, detail}` shape on errors.

---

## 6. Updating an Existing Endpoint

Keep `server.py`, `docs/openapi.yaml`, and `docs/API.md` in sync.

---

## 7. Deleting an Endpoint

Remove it from `server.py`, `openapi.yaml`, `API.md`, and any frontend calls.

---

## 8. Adding a New Reusable Schema

Define under `components.schemas` with PascalCase names; `$ref` it from
path definitions.

---

## 9. SSE Streaming Endpoints

- Pre-stream errors → raise `HTTPException` as normal.
- Mid-stream errors → emit an SSE error frame `data: [ERROR] ...`.
- End-of-stream → `data: [DONE]\n\n`.

---

## 10. Checklist

- [ ] Route added/modified in `server.py`
- [ ] Errors use `raise HTTPException(...)` (not manual error dicts)
- [ ] Path entry added/updated in `docs/openapi.yaml`
- [ ] `operationId` is set and unique
- [ ] Correct tag assigned
- [ ] All error responses use `$ref` to reusable responses
- [ ] Section added/updated in `docs/API.md`
- [ ] Tested via `/docs` Swagger UI "Try it out"
- [ ] Error responses return `{status_code, error, detail}` shape
