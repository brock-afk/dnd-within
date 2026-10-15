# Digests, so a rebuild can't silently pick up a different image.
FROM python:3.15-slim@sha256:f48fda6d59b2b3437781d1c3ccf4aa0e26ae871de3cdd758b49ab45ee7291619

COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# The venv lives outside /app so the dev bind mount of the project doesn't hide it.

# Non-root, with the code root-owned, so a compromised app can't rewrite itself.
RUN useradd --system --uid 10001 --no-create-home app
# uv installs everything; the base image's pip (and its vendored libraries) is unused attack surface.
RUN python -m pip uninstall --yes --quiet pip

WORKDIR /app

# Install dependencies first so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
# Official content packs. Third-party packs (content-private/) are mounted at deploy, never built in.
COPY content ./content
COPY app ./app

USER app
EXPOSE 8000
# Bring the database schema up to date, then start the app.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 3"]
