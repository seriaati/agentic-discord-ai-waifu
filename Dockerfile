# Build stage: install dependencies into a virtual environment
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first (cached separately from source code)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy source and install the project itself
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


# Final stage: lean image without uv
FROM python:3.14-slim-bookworm

# Node.js runtime for the Playwright MCP server (browser tools)
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Playwright MCP server + Chromium. Browsers must be installed via the MCP's
# own nested playwright (it pins an alpha build whose browser revision differs
# from stable), into a shared path readable by the non-root user.
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright
RUN npm install -g @playwright/mcp \
    && node /usr/local/lib/node_modules/@playwright/mcp/node_modules/playwright/cli.js \
        install --with-deps chromium \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

# --browser chromium: use the playwright-managed Chromium above (the default
# "chrome" channel expects a system Google Chrome install).
# --no-sandbox: Chromium can't sandbox as an unprivileged user under Docker's
# default seccomp profile.
ENV BROWSER_MCP_COMMAND="playwright-mcp --browser chromium --no-sandbox"

# Non-root user for security. Needs a real home: Chromium's crashpad handler
# aborts the whole browser without a writable $HOME.
RUN groupadd --system --gid 999 botuser \
    && useradd --system --gid 999 --uid 999 --create-home botuser \
    && mkdir -p /app/logs \
    && chown botuser:botuser /app/logs

WORKDIR /app

# Copy the built virtualenv and application from the builder
COPY --from=builder --chown=botuser:botuser /app/.venv /app/.venv
COPY --from=builder --chown=botuser:botuser /app /app

COPY --chown=botuser:botuser entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER botuser

CMD ["/app/entrypoint.sh"]