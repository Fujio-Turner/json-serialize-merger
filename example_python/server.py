"""FastAPI server exposing ``JsonMerge`` operations as HTTP endpoints.

Spec
----
This server follows the Apollo OpenAPI conventions documented in
``docs/guides/APOLLO_API_OPENAPI.md``:

* All API routes are mounted under ``/api/``.
* Every error response has the standard shape
  ``{"status_code": int, "error": str, "detail": str | object | array}``.
* ``HTTPException``, ``RequestValidationError``, and uncaught ``Exception``
  are normalized by three global handlers registered in ``create_app``.

Multi-field validation
----------------------
The merge operations can fail for *many* reasons at once (missing
``_his``, malformed records, non-numeric ``t``, invalid path strings,
unknown ``_hisF`` markers, …). Instead of returning the first error and
stopping, every endpoint runs the request through ``collect_issues`` and
returns **all** problems at once as a 400 with a structured ``detail``
list:

    {
      "status_code": 400,
      "error": "Bad Request",
      "detail": [
        {"loc": ["body", "doc", "_his", "name", "t"],
         "code": "invalid_type",
         "msg":  "expected integer epoch seconds, got 'yesterday'"},
        ...
      ]
    }

Run
---
    pip install fastapi uvicorn cbor2
    python3 server.py
    # → http://localhost:9090/docs   (Swagger UI)
    # → http://localhost:9090/openapi.yaml   (raw spec)
"""

from __future__ import annotations

import copy
import os
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# Make JsonMerge importable when running from the repo root or this dir.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import JsonMerge  # noqa: E402

VERSION = "3.0.0"

# ---------------------------------------------------------------------------
# Multi-issue validation
# ---------------------------------------------------------------------------

RESERVED_KEYS = JsonMerge.RESERVED_KEYS


def _push(issues: List[Dict[str, Any]], loc: List[Any], code: str, msg: str) -> None:
    issues.append({"loc": loc, "code": code, "msg": msg})


def _validate_path_string(p: Any, loc_prefix: List[Any], issues: List[Dict[str, Any]]) -> None:
    """Path must be a non-empty string and parse without raising."""
    if not isinstance(p, str) or p == "":
        _push(issues, loc_prefix, "invalid_path", f"path must be a non-empty string (got {type(p).__name__})")
        return
    try:
        JsonMerge.parse_path(p)
    except Exception as e:  # pragma: no cover (regex is permissive)
        _push(issues, loc_prefix, "invalid_path", f"unparseable path {p!r}: {e}")


def _validate_his_record(rec: Any, loc_prefix: List[Any], issues: List[Dict[str, Any]]) -> None:
    """A single record in the dict-of-dicts ``_his`` form: {t, h?}."""
    if not isinstance(rec, dict):
        _push(issues, loc_prefix, "invalid_type", f"_his entry must be an object, got {type(rec).__name__}")
        return
    if "t" not in rec:
        _push(issues, loc_prefix + ["t"], "missing_field", "_his record is missing required field 't'")
    elif not isinstance(rec["t"], int) or isinstance(rec["t"], bool):
        _push(issues, loc_prefix + ["t"], "invalid_type",
              f"'t' must be an integer epoch (seconds), got {type(rec['t']).__name__}: {rec['t']!r}")
    elif rec["t"] < 0:
        _push(issues, loc_prefix + ["t"], "out_of_range", f"'t' must be >= 0 (got {rec['t']})")
    if "h" in rec and not isinstance(rec["h"], str):
        _push(issues, loc_prefix + ["h"], "invalid_type",
              f"'h' must be a string (got {type(rec['h']).__name__})")
    if "v" in rec:
        # schemaV-3: 'v' should NOT be stored in _his anymore.
        _push(issues, loc_prefix + ["v"], "schema_drift",
              "_his entry contains 'v' — schemaV-3 stores values in the doc body only")


def _validate_his_block(his: Any, loc_prefix: List[Any], issues: List[Dict[str, Any]]) -> None:
    """Validate a `_his` block in any of the three wire forms."""
    if not isinstance(his, dict):
        _push(issues, loc_prefix, "invalid_type", f"_his must be an object, got {type(his).__name__}")
        return
    # Detect columnar / cbor by signature; otherwise treat as dict-of-dicts.
    keys = set(his.keys())
    if keys >= {"p", "t"} and all(isinstance(his.get(k), list) for k in ("p", "t")):
        # columnar
        if len(his["p"]) != len(his["t"]):
            _push(issues, loc_prefix, "shape_mismatch",
                  f"columnar _his: len(p)={len(his['p'])} != len(t)={len(his['t'])}")
        if "h" in his and isinstance(his["h"], list) and len(his["h"]) != len(his["p"]):
            _push(issues, loc_prefix + ["h"], "shape_mismatch",
                  f"columnar _his: len(h)={len(his['h'])} != len(p)={len(his['p'])}")
        for i, p in enumerate(his["p"]):
            _validate_path_string(p, loc_prefix + ["p", i], issues)
        for i, t in enumerate(his["t"]):
            if not isinstance(t, int) or isinstance(t, bool) or t < 0:
                _push(issues, loc_prefix + ["t", i], "invalid_type",
                      f"columnar t[{i}] must be int >= 0 (got {t!r})")
        return
    if keys >= {"d", "s"} and isinstance(his.get("d"), str) and isinstance(his.get("s"), str):
        # cbor blob — defer integrity check to unpack_his
        return
    # dict-of-dicts
    for path, rec in his.items():
        _validate_path_string(path, loc_prefix + [path], issues)
        _validate_his_record(rec, loc_prefix + [path], issues)


def validate_managed_doc(
    doc: Any,
    loc_prefix: Optional[List[Any]] = None,
    *,
    require_managed: bool = True,
) -> List[Dict[str, Any]]:
    """Collect *every* structural problem with ``doc`` into one list.

    ``require_managed=True``: the doc must have ``_his`` + ``upDtEp``.
    ``require_managed=False``: used by ``make_new_doc`` where ``_his`` is
    being created.
    """
    issues: List[Dict[str, Any]] = []
    loc_prefix = list(loc_prefix or ["body"])
    if not isinstance(doc, dict):
        _push(issues, loc_prefix, "invalid_type", f"document must be a JSON object, got {type(doc).__name__}")
        return issues
    if require_managed:
        if "_his" not in doc:
            _push(issues, loc_prefix + ["_his"], "missing_field",
                  "document is not managed: missing '_his' sidecar")
        if "upDtEp" not in doc:
            _push(issues, loc_prefix + ["upDtEp"], "missing_field",
                  "document is not managed: missing 'upDtEp'")
    # Whenever upDtEp/crDtEp are present they must be integer epochs,
    # regardless of whether the doc is required to be fully managed.
    for ep_key in ("upDtEp", "crDtEp"):
        if ep_key in doc and (not isinstance(doc[ep_key], int) or isinstance(doc[ep_key], bool)):
            _push(issues, loc_prefix + [ep_key], "invalid_type",
                  f"'{ep_key}' must be an integer epoch, got {type(doc[ep_key]).__name__}: {doc[ep_key]!r}")
    if "_his" in doc:
        _validate_his_block(doc["_his"], loc_prefix + ["_his"], issues)
    fmt = doc.get("_hisF")
    if fmt is not None and fmt not in ("c", "b"):
        _push(issues, loc_prefix + ["_hisF"], "invalid_value",
              f"_hisF must be one of 'c' (columnar) | 'b' (cbor) | absent (dict), got {fmt!r}")
    if "schemaV" in doc and doc["schemaV"] not in (2, 3):
        _push(issues, loc_prefix + ["schemaV"], "unsupported_schema",
              f"schemaV {doc['schemaV']} not supported (expected 2 or 3)")
    return issues


def validate_changes(changes: Any, loc_prefix: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """Validate update_doc-style ``changes`` argument (list-of-dicts OR dict)."""
    issues: List[Dict[str, Any]] = []
    loc_prefix = list(loc_prefix or ["body", "changes"])
    if changes is None:
        _push(issues, loc_prefix, "missing_field", "'changes' is required")
        return issues
    if isinstance(changes, dict):
        return issues
    if not isinstance(changes, list):
        _push(issues, loc_prefix, "invalid_type",
              f"'changes' must be a list of {{path: value}} dicts or a nested dict, got {type(changes).__name__}")
        return issues
    for i, item in enumerate(changes):
        if not isinstance(item, dict):
            _push(issues, loc_prefix + [i], "invalid_type",
                  f"changes[{i}] must be an object, got {type(item).__name__}")
            continue
        for path in item.keys():
            _validate_path_string(path, loc_prefix + [i, path], issues)
            if JsonMerge._top_segment(path) in RESERVED_KEYS:
                _push(issues, loc_prefix + [i, path], "reserved_key",
                      f"path {path!r} starts with a reserved key and cannot be updated")
    return issues


def raise_if(issues: List[Dict[str, Any]]) -> None:
    """If any issues collected, raise a 400 with the full list as detail."""
    if issues:
        raise HTTPException(status_code=400, detail=issues)


# ---------------------------------------------------------------------------
# App factory + global error handlers
# ---------------------------------------------------------------------------

def _error_payload(status_code: int, detail: Any) -> Dict[str, Any]:
    phrase = HTTPStatus(status_code).phrase if status_code in {s.value for s in HTTPStatus} else "Error"
    return {"status_code": status_code, "error": phrase, "detail": detail}


def create_app() -> FastAPI:
    app = FastAPI(
        title="json-serialize-merger",
        version=VERSION,
        description=(
            "HTTP wrapper around JsonMerge.py. Demonstrates per-field, "
            "timestamp-based JSON merging plus pack/unpack of the `_his` "
            "metadata between JSON and binary CBOR forms."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # local-only demo; tighten for production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- global error handlers (Apollo spec) ------------------------------

    @app.exception_handler(HTTPException)
    async def _http_exc(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_error_payload(exc.status_code, exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _req_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content={"status_code": 422,
                                     "error": "Validation Error",
                                     "detail": exc.errors()})

    @app.exception_handler(Exception)
    async def _catch_all(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500,
                            content={"status_code": 500,
                                     "error": "Internal Server Error",
                                     "detail": f"{type(exc).__name__}: {exc}"})

    # ---- Helpers ----------------------------------------------------------

    async def _read_json(request: Request) -> Dict[str, Any]:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=[{
                "loc": ["body"], "code": "invalid_json",
                "msg": f"request body is not valid JSON: {e}"
            }])
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail=[{
                "loc": ["body"], "code": "invalid_type",
                "msg": "request body must be a JSON object"
            }])
        return body

    def _make_merger(cfg: Optional[Dict[str, Any]] = None) -> JsonMerge.JSONMERGE:
        cfg = cfg or {}
        if not isinstance(cfg, dict):
            raise HTTPException(status_code=400, detail=[{
                "loc": ["body", "config"], "code": "invalid_type",
                "msg": "'config' must be a JSON object"
            }])
        return JsonMerge.JSONMERGE(cfg)

    # ---- System -----------------------------------------------------------

    @app.get("/api/version", tags=["System"], operation_id="getVersion")
    async def version() -> Dict[str, Any]:
        return {"version": VERSION, "schemaV": JsonMerge.SCHEMA_VERSION}

    @app.get("/api/env", tags=["System"], operation_id="getEnv")
    async def env() -> Dict[str, Any]:
        try:
            import cbor2  # noqa: F401
            cbor_available = True
        except Exception:
            cbor_available = False
        return {
            "cbor_available": cbor_available,
            "reserved_keys": sorted(list(RESERVED_KEYS)),
        }

    # ---- Lifecycle --------------------------------------------------------

    @app.post("/api/make-new-doc", tags=["Lifecycle"], operation_id="makeNewDoc")
    async def make_new_doc(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        doc = body.get("doc")
        cfg = body.get("config")
        issues: List[Dict[str, Any]] = []
        if doc is None:
            _push(issues, ["body", "doc"], "missing_field", "'doc' is required")
        elif not isinstance(doc, dict):
            _push(issues, ["body", "doc"], "invalid_type",
                  f"'doc' must be a JSON object, got {type(doc).__name__}")
        raise_if(issues)
        m = _make_merger(cfg)
        out = m.make_new_doc(copy.deepcopy(doc))
        return {"doc": out}

    @app.post("/api/update-doc", tags=["Lifecycle"], operation_id="updateDoc")
    async def update_doc(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        doc = body.get("doc")
        changes = body.get("changes")
        cfg = body.get("config")
        issues = validate_managed_doc(doc, ["body", "doc"], require_managed=False)
        issues.extend(validate_changes(changes, ["body", "changes"]))
        raise_if(issues)
        m = _make_merger(cfg)
        out = m.update_doc(copy.deepcopy(doc), changes)
        return {"doc": out}

    # ---- Diff / Patch -----------------------------------------------------

    @app.post("/api/diff", tags=["Diff"], operation_id="diffDocs")
    async def diff_docs(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        a, b = body.get("a"), body.get("b")
        issues: List[Dict[str, Any]] = []
        if not isinstance(a, dict):
            _push(issues, ["body", "a"], "invalid_type", "'a' must be a JSON object")
        if not isinstance(b, dict):
            _push(issues, ["body", "b"], "invalid_type", "'b' must be a JSON object")
        raise_if(issues)
        m = _make_merger(body.get("config"))
        return {"ops": m.diff_docs(a, b)}

    @app.post("/api/patch", tags=["Diff"], operation_id="patchDoc")
    async def patch_doc(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        doc = body.get("doc")
        ops = body.get("ops")
        issues = validate_managed_doc(doc, ["body", "doc"], require_managed=False)
        if not isinstance(ops, list):
            _push(issues, ["body", "ops"], "invalid_type", "'ops' must be a JSON Patch array")
        else:
            for i, op in enumerate(ops):
                if not isinstance(op, dict):
                    _push(issues, ["body", "ops", i], "invalid_type", "each op must be an object")
                    continue
                kind = op.get("op")
                if kind not in ("add", "replace", "remove"):
                    _push(issues, ["body", "ops", i, "op"], "invalid_value",
                          f"unsupported op {kind!r} (supported: add, replace, remove)")
                if "path" not in op:
                    _push(issues, ["body", "ops", i, "path"], "missing_field",
                          "every op needs a 'path'")
        raise_if(issues)
        m = _make_merger(body.get("config"))
        return {"doc": m.patch_doc(copy.deepcopy(doc), ops)}

    # ---- Merge ------------------------------------------------------------

    @app.post("/api/merge-doc-request", tags=["Merge"], operation_id="mergeDocRequest")
    async def merge_doc_request(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        d1, d2 = body.get("doc1"), body.get("doc2")
        issues = validate_managed_doc(d1, ["body", "doc1"], require_managed=False)
        issues.extend(validate_managed_doc(d2, ["body", "doc2"], require_managed=False))
        raise_if(issues)
        m = _make_merger(body.get("config"))
        return {"doc": m.merge_doc_request(copy.deepcopy(d1), copy.deepcopy(d2))}

    @app.post("/api/blind-merge", tags=["Merge"], operation_id="blindMerge")
    async def blind_merge(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        d1, d2 = body.get("doc1"), body.get("doc2")
        issues = validate_managed_doc(d1, ["body", "doc1"], require_managed=False)
        issues.extend(validate_managed_doc(d2, ["body", "doc2"], require_managed=False))
        raise_if(issues)
        m = _make_merger(body.get("config"))
        return {"doc": m.blind_merge(copy.deepcopy(d1), copy.deepcopy(d2))}

    @app.post("/api/three-way-merge", tags=["Merge"], operation_id="threeWayMerge")
    async def three_way_merge(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        base, ours, theirs = body.get("base"), body.get("ours"), body.get("theirs")
        issues: List[Dict[str, Any]] = []
        for name, val in [("base", base), ("ours", ours), ("theirs", theirs)]:
            issues.extend(validate_managed_doc(val, ["body", name], require_managed=False))
        raise_if(issues)
        m = _make_merger(body.get("config"))
        merged, conflicts = m.three_way_merge(
            copy.deepcopy(base), copy.deepcopy(ours), copy.deepcopy(theirs))
        return {"doc": merged, "conflicts": conflicts}

    # ---- Pack / Unpack ----------------------------------------------------

    @app.post("/api/pack-his", tags=["Pack"], operation_id="packHis")
    async def pack_his(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        doc = body.get("doc")
        fmt = body.get("fmt", "cols")
        issues = validate_managed_doc(doc, ["body", "doc"], require_managed=True)
        if fmt not in ("cols", "cbor"):
            _push(issues, ["body", "fmt"], "invalid_value",
                  f"fmt must be 'cols' or 'cbor', got {fmt!r}")
        if fmt == "cbor":
            try:
                import cbor2  # noqa: F401
            except ImportError:
                _push(issues, ["body", "fmt"], "unavailable",
                      "'cbor' format requires the 'cbor2' package")
        raise_if(issues)
        return {"doc": JsonMerge.pack_his(doc, fmt=fmt)}

    @app.post("/api/unpack-his", tags=["Pack"], operation_id="unpackHis")
    async def unpack_his(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        doc = body.get("doc")
        issues = validate_managed_doc(doc, ["body", "doc"], require_managed=False)
        raise_if(issues)
        try:
            out = JsonMerge.unpack_his(doc)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=[{
                "loc": ["body", "doc", "_his"], "code": "integrity_failure", "msg": str(e)}])
        return {"doc": out}

    # ---- Inspect ----------------------------------------------------------

    @app.post("/api/validate", tags=["Inspect"], operation_id="validateDoc")
    async def validate(request: Request) -> Dict[str, Any]:
        body = await _read_json(request)
        doc = body.get("doc")
        # Structural pre-check: collect everything wrong *before* asking the
        # library — this is the multi-error response in action.
        issues = validate_managed_doc(doc, ["body", "doc"], require_managed=True)
        m = _make_merger(body.get("config"))
        warnings: List[str] = []
        if not issues:  # only run lib's validate if the shape is sane
            warnings = m.validate(doc)
        return {"structural_issues": issues, "warnings": warnings}

    # ---- Spec / static ----------------------------------------------------

    REPO_ROOT = HERE.parent
    OPENAPI_YAML = REPO_ROOT / "docs" / "openapi.yaml"

    @app.get("/openapi.yaml", include_in_schema=False)
    async def raw_spec() -> Any:
        if not OPENAPI_YAML.exists():
            raise HTTPException(status_code=404, detail=f"missing {OPENAPI_YAML}")
        return FileResponse(str(OPENAPI_YAML), media_type="application/yaml")

    # /api-docs — Apollo-style Swagger UI that renders the hand-maintained
    # docs/openapi.yaml (not the FastAPI-auto-generated /openapi.json).
    # This is the one with the curated descriptions, examples and reusable
    # error schemas the spec was written for.
    from fastapi.responses import HTMLResponse

    @app.get("/api-docs", include_in_schema=False)
    async def api_docs() -> HTMLResponse:
        if not OPENAPI_YAML.exists():
            raise HTTPException(status_code=404, detail=f"missing {OPENAPI_YAML}")
        html = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <title>json-serialize-merger — /api-docs (hand-maintained spec)</title>
  <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css\" />
  <style>body { margin:0 } #info-bar {
    font: 12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    padding:6px 12px; background:#1f2937; color:#d1d5db;
  } #info-bar a { color:#93c5fd; margin-right:14px }</style>
</head>
<body>
  <div id=\"info-bar\">
    <b>/api-docs</b> &middot; renders <code>docs/openapi.yaml</code> (hand-maintained)
    &nbsp;|&nbsp;
    <a href=\"/openapi.yaml\">/openapi.yaml</a>
    <a href=\"/docs\">/docs (auto)</a>
    <a href=\"/redoc\">/redoc (auto)</a>
    <a href=\"/api/version\">/api/version</a>
  </div>
  <div id=\"swagger-ui\"></div>
  <script src=\"https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
  <script src=\"https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js\"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: '/openapi.yaml',
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [ SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset ],
      plugins: [ SwaggerUIBundle.plugins.DownloadUrl ],
      layout: 'StandaloneLayout',
    });
  </script>
</body>
</html>"""
        return HTMLResponse(html)

    # ---- Shared playground UI --------------------------------------------
    # The same `index.html` / `JsonMerge.js` / `example_data/` assets that
    # the repo serves at the root are re-served here so that a single
    # container hosts both the UI and the API. The build context for the
    # Docker image is the repo root (see example_python/Dockerfile), so
    # these directories are copied alongside the Python code.
    INDEX_HTML  = REPO_ROOT / "index.html"
    JSON_MERGE  = REPO_ROOT / "JsonMerge.js"
    README_MD   = REPO_ROOT / "README.md"
    LICENSE     = REPO_ROOT / "LICENSE"

    for sub, mount in [
        ("example_data", "/example_data"),
        ("docs",         "/docs"),
        ("img",          "/img"),
    ]:
        d = REPO_ROOT / sub
        if d.is_dir():
            app.mount(mount, StaticFiles(directory=str(d)), name=sub)

    if JSON_MERGE.is_file():
        @app.get("/JsonMerge.js", include_in_schema=False)
        async def _serve_js() -> FileResponse:
            return FileResponse(str(JSON_MERGE), media_type="application/javascript")

    if README_MD.is_file():
        @app.get("/README.md", include_in_schema=False)
        async def _serve_readme() -> FileResponse:
            return FileResponse(str(README_MD), media_type="text/markdown")

    if LICENSE.is_file():
        @app.get("/LICENSE", include_in_schema=False)
        async def _serve_license() -> FileResponse:
            return FileResponse(str(LICENSE), media_type="text/plain")

    @app.get("/", include_in_schema=False)
    async def root():
        # If the shared playground HTML is bundled in (the Docker case, or
        # when the server is run from the repo root), serve it. Otherwise
        # fall back to the API-only text index.
        if INDEX_HTML.is_file():
            return FileResponse(str(INDEX_HTML), media_type="text/html")
        return PlainTextResponse(
            "json-serialize-merger API\n"
            "  - /api-docs       Swagger UI rendering the hand-maintained docs/openapi.yaml\n"
            "  - /docs           Swagger UI (auto-generated by FastAPI)\n"
            "  - /redoc          Redoc (auto-generated by FastAPI)\n"
            "  - /openapi.yaml   hand-maintained spec (raw)\n"
            "  - /api/version    server version\n"
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "9090"))
    uvicorn.run("server:app", host=host, port=port, reload=False)
