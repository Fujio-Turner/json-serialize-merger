# ---------------------------------------------------------------------------
# json-serialize-merger — Python reference container
#
# Build context MUST be the repo root, not example_python/, so the build
# can pull in the *shared* assets that every example_<lang>/ container
# wants to host (index.html, JsonMerge.js, example_data/, docs/, img/).
#
#   docker build -f example_python/Dockerfile -t json-merger-python ..
#   docker run --rm -p 9090:9090 json-merger-python
#
# Or simply use the bundled compose file:
#
#   docker compose -f example_python/docker-compose.yml up --build
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=9090

WORKDIR /app

# Python deps first — gives Docker a stable cache layer.
COPY example_python/requirements.txt /app/example_python/requirements.txt
RUN pip install -r /app/example_python/requirements.txt

# Shared playground assets (HTML + JS + sample JSON + spec + images).
# These live at the repo root precisely so every language container can
# COPY them in unmodified.
COPY index.html        /app/index.html
COPY JsonMerge.js      /app/JsonMerge.js
COPY README.md         /app/README.md
COPY LICENSE           /app/LICENSE
COPY example_data      /app/example_data
COPY docs              /app/docs
COPY img               /app/img

# Python implementation + FastAPI server.
COPY example_python    /app/example_python

EXPOSE 9090

# server.py reads HOST / PORT from the env, falling back to 127.0.0.1:9090.
CMD ["python3", "example_python/server.py"]
