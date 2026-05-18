# Python reference container

A single Docker image that serves **both** the playground UI and the FastAPI
backend for the Python implementation of `JsonMerge`.

## Layout

The shared assets live at the **repo root** so every `example_<lang>/`
container can pull them in unchanged:

```diagram
╭───────────────────────── repo root (build context) ─────────────────────────╮
│  index.html        ← shared playground (one HTML for every language)        │
│  JsonMerge.js      ← shared in-browser JS port                              │
│  example_data/     ← shared sample JSON (already external, like the HTML)   │
│  docs/             ← shared design + OpenAPI spec                           │
│  img/              ← shared diagrams                                        │
│                                                                             │
│  example_python/   ← this language's server + Dockerfile                    │
│  example_go/       ← (future) — would reuse all the shared assets above     │
│  example_node/     ← (future)                                               │
╰─────────────────────────────────────────────────────────────────────────────╯
```

The `example_python/Dockerfile` `COPY`s the shared assets into the image
and `server.py` mounts them as static routes (`/`, `/JsonMerge.js`,
`/example_data/*`, `/docs/*`, `/img/*`) so one container = UI + API.

## Run with Docker

```bash
# from repo root
docker build -f example_python/Dockerfile -t json-merger-python .
docker run --rm -p 9090:9090 json-merger-python
```

Then open <http://localhost:9090/> — the **API (live)** tab will already
be pointing at this container (`http://localhost:9090`).

## Run with Docker Compose

```bash
docker compose -f example_python/docker-compose.yml up --build
```

## Endpoints served by the container

| Path              | Description                                              |
|-------------------|----------------------------------------------------------|
| `/`               | Playground (`index.html`)                                |
| `/JsonMerge.js`   | Shared in-browser JS port                                |
| `/example_data/*` | Sample JSON used by the **Load:** buttons                |
| `/docs/*`         | DESIGN.md, API.md, openapi.yaml                          |
| `/img/*`          | Diagrams referenced from README/DESIGN                   |
| `/api/*`          | FastAPI JSON endpoints (see `/api-docs`)                 |
| `/api-docs`       | Swagger UI rendering the hand-maintained `openapi.yaml`  |
| `/docs` (FastAPI) | Auto-generated Swagger UI — note `/docs/*` static takes precedence; use `/redoc` for the auto spec |

## Adding another language

1. Create `example_<lang>/` with the server code.
2. Add `example_<lang>/Dockerfile` whose build context is the repo root
   (so it can `COPY index.html JsonMerge.js example_data docs img ...`
   the same way the Python one does).
3. Make the server also serve those static paths.

Result: every container ships the same UI, only the backend changes.
