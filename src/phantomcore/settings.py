from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import discord
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_int(name: str) -> int:
    return int(_env(name))


def _env_list(name: str, default: list[str]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return tuple(default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    return int(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int
    owner_id: int
    bot_id: int
    bot_channel_id: int
    status_channel_id: int
    extensions: tuple[str, ...]
    data_dir: Path

    lmstudio_host: str
    lmstudio_model: str
    lmstudio_chat_config: dict[str, float | int]
    lmstudio_model_config: dict[str, int | dict]
    system_prompt: str

    lavalink_host: str
    lavalink_password: str
    lavalink_java: str
    stalker_channel_id: int | None
    claim_time: float

    @property
    def intents(self) -> discord.Intents:
        return discord.Intents.all()

    @property
    def lobbies_db(self) -> Path:
        return self.data_dir / "lobbies.db"

    @property
    def chat_history_dir(self) -> Path:
        return self.data_dir / "chat_histories"

    @property
    def lavalink_dir(self) -> Path:
        return PROJECT_ROOT / "lavalink"

    @property
    def lavalink_jar(self) -> Path:
        return self.lavalink_dir / "Lavalink.jar"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            token=_env("TOKEN"),
            guild_id=_env_int("GUILD_ID"),
            owner_id=_env_int("OWNER_ID"),
            bot_id=_env_int("BOT_ID"),
            bot_channel_id=_env_int("BOT_CHATTER"),
            status_channel_id=_env_int("BOT_STATUS"),
            extensions=_env_list(
                "EXTENSIONS",
                [
                    "dynamic_lobbies",
                    "rename_lobby",
                    "purge_commands",
                    "pull_commands",
                    "extension_helper",
                    "llm_module",
                    "stalker_player",
                    "commit_watcher",
                ],
            ),
            data_dir=Path(os.getenv("DATA_DIR", DATA_DIR)),
            lmstudio_host=os.getenv("LMSTUDIO_HOST", "localhost:1234"),
            lmstudio_model=os.getenv("LMSTUDIO_MODEL", "qwen/qwen3.8-27b"),
            lmstudio_chat_config={
                "temperature": float(os.getenv("LMSTUDIO_TEMPERATURE", "1.0")),
                "top_k": float(os.getenv("LMSTUDIO_TOP_K", "0.5")),
                "min_p": float(os.getenv("LMSTUDIO_MIN_P", "0.3")),
                "top_p": float(os.getenv("LMSTUDIO_TOP_P", "0.95")),
                "max_tokens": int(os.getenv("LMSTUDIO_MAX_TOKENS", "1024")),
            },
            lmstudio_model_config={
                "context_length": int(os.getenv("LMSTUDIO_CONTEXT_LENGTH", "8192")),
                "gpu": {"ratio": 1},
            },
            system_prompt=os.getenv(
                "SYSTEM_PROMPT",
                "You are the PhantomCore Discord bot. Be concise, witty, and helpful.",
            ),
            lavalink_host=os.getenv("LAVALINK_HOST", "127.0.0.1:7867"),
            lavalink_password=_env("LAVALINK_PASSWORD"),
            lavalink_java=os.getenv("JAVA_PATH", ""),
            stalker_channel_id=_env_optional_int("STALKER_CHANNEL"),
            claim_time=float(os.getenv("CLAIM_TIME", "300")),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()