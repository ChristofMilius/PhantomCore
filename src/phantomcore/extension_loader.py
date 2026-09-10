from __future__ import annotations

import discord

from phantomcore.settings import Settings

load_results: list[str] = []


async def load_all_extensions(bot: discord.ext.commands.Bot, settings: Settings) -> None:
    load_results.clear()
    for ext in settings.extensions:
        try:
            await bot.load_extension(f"phantomcore.cogs.{ext}")
        except discord.DiscordException as err:
            load_results.append(f"Extension {ext} ERROR {err}!🚫")
        else:
            load_results.append(f"Extension {ext} has been loaded!✅")


async def unload_all_extensions(bot: discord.ext.commands.Bot, settings: Settings) -> None:
    load_results.clear()
    for ext in settings.extensions:
        try:
            await bot.unload_extension(f"phantomcore.cogs.{ext}")
        except discord.DiscordException as err:
            load_results.append(f"Extension {ext} ERROR {err}!🚫")
        else:
            load_results.append(f"Extension {ext} has been unloaded!✅")