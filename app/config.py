"""Centralised configuration.

All runtime knobs live here. Values come from environment variables (or a
``.env`` file when present). The :class:`Settings` instance is constructed
exactly once via :func:`get_settings` and is treated as immutable everywhere
else in the codebase.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

AppEnv = Literal["development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class APISettings(BaseSettings):
    """HTTP layer configuration."""

    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="info", alias="API_LOG_LEVEL")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], alias="API_CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DatabaseSettings(BaseSettings):
    url: str = Field(
        default=f"sqlite+aiosqlite:///{_PROJECT_ROOT / 'data' / 'farmpilot.db'}",
        alias="DATABASE_URL",
    )
    echo: bool = Field(default=False, alias="DATABASE_ECHO")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class LoggingSettings(BaseSettings):
    level: LogLevel = Field(default="INFO", alias="LOG_LEVEL")
    json_output: bool = Field(default=False, alias="LOG_JSON")
    file: Path | None = Field(default=_PROJECT_ROOT / "logs" / "farmpilot.log", alias="LOG_FILE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class BrowserSettings(BaseSettings):
    headless: bool = Field(default=True, alias="BROWSER_HEADLESS")
    channel: str = Field(default="chromium", alias="BROWSER_CHANNEL")
    profiles_dir: Path = Field(default=_PROJECT_ROOT / "profiles", alias="BROWSER_PROFILES_DIR")
    extensions_dir: Path = Field(
        default=_PROJECT_ROOT / "extensions", alias="BROWSER_EXTENSIONS_DIR"
    )
    default_timeout_ms: int = Field(default=30_000, alias="BROWSER_DEFAULT_TIMEOUT_MS")
    user_agent: str | None = Field(default=None, alias="BROWSER_USER_AGENT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class WalletSettings(BaseSettings):
    extension: Literal["metamask", "rabby", "none"] = Field(
        default="none", alias="WALLET_EXTENSION"
    )
    extension_path: Path | None = Field(default=None, alias="WALLET_EXTENSION_PATH")
    default_mnemonic: str | None = Field(default=None, alias="WALLET_DEFAULT_MNEMONIC")
    default_password: str | None = Field(default=None, alias="WALLET_DEFAULT_PASSWORD")
    evm_rpcs_raw: str = Field(default="", alias="EVM_RPCS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def evm_rpcs(self) -> dict[str, str]:
        """Parse the ``key=url,key=url`` form used in env files into a dict."""
        out: dict[str, str] = {}
        if not self.evm_rpcs_raw:
            return out
        for chunk in self.evm_rpcs_raw.split(","):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            k, v = chunk.split("=", 1)
            out[k.strip().lower()] = v.strip()
        return out


class AISettings(BaseSettings):
    provider: Literal["openai", "anthropic", "none"] = Field(
        default="none", alias="AI_PROVIDER"
    )
    model: str = Field(default="gpt-4o-mini", alias="AI_MODEL")
    api_key: str | None = Field(default=None, alias="AI_API_KEY")
    temperature: float = Field(default=0.2, alias="AI_TEMPERATURE")
    max_tokens: int = Field(default=1024, alias="AI_MAX_TOKENS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ExecutionSettings(BaseSettings):
    """Knobs that govern how the executor agent behaves."""

    max_concurrency: int = Field(default=2, alias="EXEC_MAX_CONCURRENCY")
    human_delay_min_ms: int = Field(default=600, alias="EXEC_HUMAN_DELAY_MIN_MS")
    human_delay_max_ms: int = Field(default=2_400, alias="EXEC_HUMAN_DELAY_MAX_MS")
    retry_max_attempts: int = Field(default=4, alias="EXEC_RETRY_MAX_ATTEMPTS")
    retry_backoff_base_ms: int = Field(default=500, alias="EXEC_RETRY_BACKOFF_BASE_MS")
    retry_backoff_max_ms: int = Field(default=15_000, alias="EXEC_RETRY_BACKOFF_MAX_MS")
    risk_max_usd: float = Field(default=25.0, alias="EXEC_RISK_MAX_USD")
    dry_run: bool = Field(default=True, alias="EXEC_DRY_RUN")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("human_delay_max_ms")
    @classmethod
    def _max_gte_min(cls, v: int, info) -> int:
        min_v = info.data.get("human_delay_min_ms", 0)
        if v < min_v:
            raise ValueError("human_delay_max_ms must be >= human_delay_min_ms")
        return v


class Settings(BaseSettings):
    """Top-level settings aggregator."""

    app_name: str = Field(default="FarmPilotAI", alias="APP_NAME")
    app_env: AppEnv = Field(default="development", alias="APP_ENV")
    project_root: Path = Field(default=_PROJECT_ROOT)

    api: APISettings = Field(default_factory=APISettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    log: LoggingSettings = Field(default_factory=LoggingSettings)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    wallet: WalletSettings = Field(default_factory=WalletSettings)
    ai: AISettings = Field(default_factory=AISettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a singleton :class:`Settings`. Cached for the lifetime of the process."""
    return Settings()


SettingsDep = Annotated[Settings, "FastAPI dependency for Settings"]
