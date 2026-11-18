# Remote MCP server for Cloud Run (BUILD_GUIDE Step 13). The same image runs the
# briefing as a Cloud Run job (Step 21) with a different command.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Dependencies first, so code changes don't reinstall them. Only the server's
# own dependencies: no dev tools, no LLM SDKs (those are for the Mac briefing).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-default-groups --no-install-project

COPY sources ./sources
COPY briefing ./briefing
COPY deploy/routes.json ./deploy/routes.json
COPY server.py http_app.py ./
COPY scripts/check_keys.py ./scripts/check_keys.py

ENV PATH="/app/.venv/bin:$PATH"
# Run as an unprivileged user, not root. The copied files keep their Mac
# permissions (often owner-only), so make /app readable for that user first.
RUN useradd --system --no-create-home app && chmod -R a+rX /app
ENV HOME=/tmp
USER app
CMD ["python", "http_app.py"]
