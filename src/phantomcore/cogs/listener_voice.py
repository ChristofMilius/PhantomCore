from __future__ import annotations

from discord.ext import commands

from phantomcore.cogs._lobby import LobbyManager


class ListenerVoice(LobbyManager, name="listener_voice"):
    VOICE_CATEGORY = "dynamic-voice-lobby"
    CHAT_CATEGORY = "dynamic-chat-lobby"
    VOICE_CHANNEL_PREFIX = "dynamic-voice-"
    CHAT_CHANNEL_PREFIX = "dynamic-chat-"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ListenerVoice(bot))