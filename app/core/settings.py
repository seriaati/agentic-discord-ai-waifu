from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    discord_token: str
    env: Literal["dev", "prod"]

    anthropic_api_key: str
    chat_model: str = "claude-sonnet-4-6"
    # Playwright MCP browser tools; requires Node.js (npx) on the host.
    browser_enabled: bool = False
    # Command that launches the Playwright MCP server. The Docker image
    # overrides this to run its preinstalled copy with --no-sandbox.
    browser_mcp_command: str = "npx @playwright/mcp@latest"

    postgres_password: str
    postgres_db: str = "agentic-discord-ai-waifu"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"

    @property
    def database_url(self) -> str:
        return f"asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


load_dotenv()
SETTINGS = Settings()  # pyright: ignore[reportCallIssue]
