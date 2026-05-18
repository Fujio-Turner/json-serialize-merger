# API Reference

> Server: [`example_python/server.py`](../example_python/server.py) · Spec: [`docs/openapi.yaml`](./openapi.yaml) · Conventions: [`docs/guides/APOLLO_API_OPENAPI.md`](./guides/APOLLO_API_OPENAPI.md)

Run locally:

```bash
pip install fastapi uvicorn cbor2
python3 example_python/server.py
# → http://localhost:9090/docs        Swagger UI
# → http://localhost:9090/openapi.yaml hand-maintained spec
```

## Error shape (all 4xx/5xx)

Every error response has the same envelope. The `detail` field is a
**list of issues** for any endpoint that performs structural validation,
so callers get every problem in one round-trip:

```json
{
  "status_code": 400,
  "error": "Bad Request",
  "detail": [
    { "loc": ["body", "doc", "_his", "name", "t"],
      "code": "invalid_type",
      "msg":  "'t' must be an integer epoch (seconds), got str: 'yesterday'" },
    { "loc": ["body", "changes", 0, "_his.foo"],
      "code": "reserved_key",
      "msg":  "path '_his.foo' starts with a reserved key and cannot be updated" }
  ]
}
```

| `code` | Meaning |
|---|---|
| `invalid_json` | Body wasn't valid JSON |
| `invalid_type` | A field has the wrong JSON type |
| `invalid_value` | Wrong enum / domain value |
| `missing_field` | A required field wasn't provided |
| `invalid_path` | A dotted/bracket path string couldn't be parsed |
| `reserved_key` | Attempted to write a reserved bookkeeping key |
| `shape_mismatch` | Columnar `_his` arrays have inconsistent lengths |
| `out_of_range` | Numeric value outside the allowed range |
| `schema_drift` | Legacy v2 artifact (e.g. `v` inside `_his`) under v3 |
| `unsupported_schema` | `schemaV` not understood |
| `unavailable` | Optional dependency missing (e.g. `cbor2`) |
| `integrity_failure` | CBOR blob hash didn't verify |

## Endpoints

| Tag       | Method | Path                       | Purpose |
|-----------|--------|----------------------------|---------|
| System    | GET    | `/api/version`             | Server + schema version |
| System    | GET    | `/api/env`                 | Feature flags (cbor available, reserved keys) |
| Lifecycle | POST   | `/api/make-new-doc`        | Stamp a plain doc with `_his` |
| Lifecycle | POST   | `/api/update-doc`          | Apply changes (multiple shapes accepted) |
| Diff      | POST   | `/api/diff`                | Produce RFC 6902 patch (a → b) |
| Diff      | POST   | `/api/patch`               | Apply RFC 6902 patch + refresh `_his` |
| Merge     | POST   | `/api/merge-doc-request`   | Asymmetric merge (newer fields of doc2 into doc1) |
| Merge     | POST   | `/api/blind-merge`         | Symmetric per-field newer-wins reconcile |
| Merge     | POST   | `/api/three-way-merge`     | Git-style 3-way merge with conflict list |
| Pack      | POST   | `/api/pack-his`            | Re-encode `_his` to `cols` or `cbor` |
| Pack      | POST   | `/api/unpack-his`          | Restore `_his` to dict-of-dicts |
| Inspect   | POST   | `/api/validate`            | Structural + drift validation (multi-issue) |

### `POST /api/update-doc`

```json
// Request
{
  "doc":     { "...managed doc..." },
  "changes": [{ "address.city": "Lake Falls West" }, { "tags[1]": "net60" }],
  "config":  { "qtyMath": true, "addHashes": true }
}

// 200 OK
{ "doc": { "...updated managed doc..." } }
```

### `POST /api/validate`

Returns **both** lists so the UI can render structural problems
separately from per-field drift warnings:

```json
{
  "structural_issues": [
    { "loc": ["body","doc","_his","name","t"], "code": "missing_field",
      "msg":  "_his record is missing required field 't'" }
  ],
  "warnings": [ "hash mismatch at apples (tampered?)" ]
}
```

### `POST /api/pack-his`

```json
// Request
{ "doc": { "...managed..." }, "fmt": "cols" }   // or "cbor"

// 200 OK — packed doc with _hisF marker
{ "doc": { "_his": { "p":[…], "t":[…], "h":[…] }, "_hisF": "c", "...":"..." } }
```

`cbor` requires the `cbor2` package; otherwise returns a 400 with
`{"code":"unavailable"}`.
