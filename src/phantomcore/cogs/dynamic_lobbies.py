from __future__ import annotations

from discord.ext import commands

from phantomcore.cogs._lobby import LobbyManager


class DynamicLobbies(LobbyManager, name="dynamic_lobbies"):
    VOICE_CATEGORY = "dynamic_voice_lobby"
    CHAT_CATEGORY = "dynamic_chat_lobby"
    VOICE_CHANNEL_PREFIX = "dynamic_voice_"
    CHAT_CHANNEL_PREFIX = "dynamic_chat_"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DynamicLobbies(bot))