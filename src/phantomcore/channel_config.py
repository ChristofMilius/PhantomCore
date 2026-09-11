from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import discord
from discord.ext import commands
from discord.utils import get

from phantomcore.settings import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "channel_config.json"

_DEFAULT_STRUCTURE = {
    "categories": [
        {
            "name": "bot-section",
            "channels": [
                {"name": "bot_chatter", "type": "text"},
                {"name": "bot_status", "type": "text"},
                {"name": "hermes_agent", "type": "text", "admin_only": True},
            ],
        },
        {"name": "dynamic_voice_lobby", "channels": []},
        {"name": "dynamic_chat_lobby", "channels": []},
        {
            "name": "Voice Lobby Template",
            "channels": [{"name": "Join to create a lobby", "type": "voice"}],
        },
    ]
}


@dataclass(frozen=True)
class ChannelEntry:
    name: str
    type: Literal["text", "voice"] = "text"
    admin_only: bool = False


@dataclass(frozen=True)
class CategoryConfig:
    name: str
    channels: tuple[ChannelEntry, ...] = ()


@dataclass(frozen=True)
class ChannelConfig:
    categories: tuple[CategoryConfig, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelConfig":
        categories = []
        for category in data.get("categories", []):
            channels = tuple(
                ChannelEntry(
                    name=channel["name"],
                    type=channel.get("type", "text"),
                    admin_only=bool(channel.get("admin_only", False)),
                )
                for channel in category.get("channels", [])
            )
            categories.append(CategoryConfig(name=category["name"], channels=channels))
        return cls(categories=tuple(categories))

    @classmethod
    def from_file(cls, path: Path = DEFAULT_CONFIG_PATH) -> "ChannelConfig":
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = _DEFAULT_STRUCTURE
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load {path}, using default structure: {e}")
            data = _DEFAULT_STRUCTURE
        return cls.from_dict(data)


_ensure_lock = asyncio.Lock()


async def ensure_channel_structure(bot: commands.Bot) -> None:
    """Idempotently create any configured category or channel that is missing."""
    async with _ensure_lock:
        config = ChannelConfig.from_file()
        guild = bot.get_guild(bot.settings.guild_id)
        if guild is None:
            return

        for category_config in config.categories:
            category = get(guild.categories, name=category_config.name)
            if category is None:
                category = await guild.create_category(category_config.name)
                print(f"Created category {category_config.name}")

            for entry in category_config.channels:
                if get(category.channels, name=entry.name) is not None:
                    continue

                overwrites = None
                if entry.admin_only:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(
                            read_messages=False, send_messages=False
                        ),
                        guild.me: discord.PermissionOverwrite(
                            read_messages=True, send_messages=True
                        ),
                    }

                kwargs = {"name": entry.name}
                if overwrites is not None:
                    kwargs["overwrites"] = overwrites
                if entry.type == "voice":
                    channel = await category.create_voice_channel(**kwargs)
                else:
                    channel = await category.create_text_channel(**kwargs)
                print(f"Created channel {entry.name} ({channel.id})")