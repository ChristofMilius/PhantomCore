from __future__ import annotations

import discord
from discord.ext import commands
from discord.utils import get

from phantomcore.db import LobbiesDB

VOICE_CATEGORY = "dynamic-voice-lobby"
JAIL_CATEGORY = "Jail"


class RenameLobby(commands.Cog, name="rename_lobby"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = LobbiesDB(bot.settings.lobbies_db)

    @commands.hybrid_command(
        description="rename the lobby you are currently in",
        qualified_name="rename_lobby",
        name="rename_lobby",
    )
    @commands.bot_has_guild_permissions(manage_channels=True)
    @commands.cooldown(rate=1, per=60)
    async def rename_lobby(self, ctx: commands.Context, *, name: str):
        await ctx.defer(ephemeral=True)
        voice = ctx.author.voice
        if not voice or not voice.channel:
            await ctx.reply(
                f"{ctx.author.mention} is not connected to a voice lobby!",
                ephemeral=True,
                delete_after=10,
            )
            return

        vc = voice.channel
        category = vc.category.name if vc.category else None

        if category == VOICE_CATEGORY:
            data = self.db.get(vc.id)
            if data:
                tc = get(ctx.guild.channels, id=data[1])
                await vc.edit(name=name)
                await tc.edit(name=f"{name}-chat")
                await ctx.reply(
                    f"{ctx.author.mention} renamed the lobby to '{name}'",
                    ephemeral=True,
                    delete_after=10,
                )
            else:
                await ctx.reply(
                    f"{ctx.author.mention} lobby was not found in the database!",
                    ephemeral=True,
                    delete_after=10,
                )
        elif category != VOICE_CATEGORY and category != JAIL_CATEGORY:
            await vc.edit(name=name)
            await ctx.reply(
                f"{ctx.author.mention} renamed the lobby to '{name}'",
                ephemeral=True,
                delete_after=10,
            )
        else:
            await ctx.reply(
                f"{ctx.author.mention} is not connected to a voice lobby!",
                ephemeral=True,
                delete_after=10,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RenameLobby(bot))