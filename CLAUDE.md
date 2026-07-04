# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An agentic "AI waifu" Discord bot: per-user personas delivered via channel webhooks, backed by the Claude Agent SDK with memory, observation, and proactive messaging. `PROJECT.md` records the full vision, feasibility notes, and decided constraints (API-key auth only, cost gating) — read it before making design-level changes.

## Commands

```bash
uv run main.py                     # run the bot (needs .env; see Settings below)
ruff check                         # lint (extensive rule set in ruff.toml)
ruff format                        # format (line length 100, skip-magic-trailing-comma)
pyright                            # type check (config in pyproject.toml; ruff/pyright are global tools, not venv deps)
uv run tortoise makemigrations     # generate migration from model changes
uv run tortoise upgrade            # apply migrations
```

There is no test suite. Docker: `docker build .`; the entrypoint runs `tortoise upgrade` then `python main.py`. The tortoise CLI finds its config through `[tool.tortoise]` in pyproject.toml → `app.db.conn.TORTOISE_ORM`; migration files in `migrations/` are auto-generated (ruff ignores them).

## Architecture

Flow: Discord events → cogs (`app/cogs/`) → agent layer (`app/agent/`) → services (`app/services/`) → Tortoise models (`app/db/models.py`) → PostgreSQL.

- **Entry**: `main.py` opens `Database` and `MyBot` as async context managers. `MyBot.setup_hook` auto-loads every module in `app/cogs/` as a cog (plus jishaku) — dropping a new file there is all that's needed to register it. Slash-command errors funnel through the custom `CommandTree` → `app/core/error_handler.py`.
- **Agent layer** (`app/agent/`): wraps the Claude Agent SDK. `chat.py:generate_reply` builds a per-turn system prompt (base prompt + persona + memory context from `build_memory_context` + time), and runs a `ClaudeSDKClient` turn with WebSearch/WebFetch, an in-process MCP "memory" server (`tools.py`: remember_fact, remember_date, set_reminder, write_diary, read_diary — tools close over the `User`/`Persona`), and optionally the Playwright browser MCP. `proactive.py:decide_proactive_message` is a one-shot `query()` where the model answers `SKIP` to stay silent.
- **Personas** are scoped per (discord_id, channel_id). `cogs/chat.py` responds to *every* non-bot guild message in a channel where the author has a persona (no mention needed), and delivers through a reused channel webhook (`services/webhook.py`, name/avatar overridden per message) with fallback to a normal reply. Personas keep a per-day diary (`DiaryEntry`, unique per persona+date, appended not replaced).
- **Observation → proactive pipeline**: `cogs/observer.py` (opt-in per user) writes presence/voice `Observation` rows; `cogs/proactive.py` runs a `tasks.loop` that gates cheaply (opt-in, cooldown, quiet hours, unhandled observations) *before* invoking the model, then delivers via the user's `last_persona` webhook to that persona's bound channel. `cogs/reminder.py` is a similar loop delivering due `Reminder` rows.
- **Settings** (`app/core/settings.py`): pydantic-settings from `.env` — requires `discord_token`, `env` (dev/prod), `anthropic_api_key`, `postgres_password`; `browser_enabled` toggles Playwright MCP.

## Claude Agent SDK gotchas (hard-won, do not regress)

- External stdio MCP servers connect **asynchronously**; a one-shot `query()` races the connection and the model never sees the tools. Use `ClaudeSDKClient` and poll `get_mcp_status()` until the server leaves `"pending"` (see `_wait_for_browser_server` in `app/agent/chat.py`). In-process SDK servers don't race.
- Allow a whole MCP server with `mcp__playwright` — the `mcp__playwright__*` wildcard form does **not** work.
- Always pass `strict_mcp_config=True`, otherwise the SDK subprocess inherits the host user's `~/.claude` MCP servers into every bot query.
- The SDK bundles a native CLI binary — no Node needed for the SDK itself. Node exists in the Docker image only for `@playwright/mcp`, whose browsers must be installed via its own nested playwright CLI (it pins an alpha build); the container needs `--browser chromium --no-sandbox` and a real `$HOME` for the bot user (see Dockerfile comments).

## Conventions

- Timezone: user-facing wall-clock time is **per-user** (`User.timezone`, IANA name, default `Asia/Taipei`; set via `/me timezone`). Use `get_user_now`/`get_user_tz` (`app/utils/misc.py`) for anything user-scoped — diary days, reminder input, greeting windows, quiet hours, prompt time context; `get_utc8_now` remains for non-user-scoped absolute timestamps. DB stores tz-aware datetimes (`use_tz=True`, timezone `Asia/Taipei` in `app/db/conn.py`); `wake_time`/`sleep_time` are user-local wall clock.
- User-facing bot text (error fallbacks, proactive messages) is Traditional Chinese.
- Discord limits are enforced at call sites via module constants (`DISCORD_MESSAGE_LIMIT = 2000`, webhook username ≤ 80, etc.) — keep doing this when adding send paths.
