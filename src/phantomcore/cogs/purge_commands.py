from __future__ import annotations

import asyncio
import random
import time

import discord
from discord.ext import commands
from discord.utils import get

from phantomcore.db import LobbiesDB

VOICE_CATEGORY = "dynamic-voice-lobby"


class PurgeCommands(commands.Cog, name="purge_commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = LobbiesDB(bot.settings.lobbies_db)

    @commands.hybrid_command(
        description="spawns random strings in chat for testing",
        qualified_name="flooder",
        name="flooder",
    )
    @commands.is_owner()
    @commands.cooldown(rate=1, per=60)
    async def flooder(self, ctx: commands.Context, amount: int):
        await ctx.defer(ephemeral=True)
        limit = 255
        max_allowed = round(limit / 10)

        if not amount <= max_allowed:
            await ctx.send(f"Maximum allowed is {max_allowed}", ephemeral=True)
            ctx.command.cooldown.reset()
            return

        for _ in range(amount):
            random_string = ""
            for _ in range(amount):
                random_integer = random.randint(0, limit)
                random_string += chr(random_integer)
            await ctx.send(random_string)
        await ctx.send("Done flooding!", ephemeral=True)

    # this command is meant to "tabula rasa"
    @commands.hybrid_command(
        description="purges channel history with args as length for review",
        qualified_name="purge_chat",
        name="purge_chat",
    )
    @commands.has_guild_permissions(manage_messages=True)
    @commands.cooldown(rate=1, per=60)
    async def purge_chat(self, ctx: commands.Context, amount: int):
        await ctx.defer(ephemeral=True)

        if amount <= 0:
            await ctx.send(
                "Invalid amount. Must be a positive number.", ephemeral=True, delete_after=5
            )
            return

        start = time.perf_counter()
        messages = [
            m
            async for m in ctx.channel.history(limit=amount)
            if m.type == discord.MessageType.default
        ]
        n = len(messages)

        if n == 0:
            await ctx.send(
                f"{self.purge_chat.qualified_name} found nothing to purge",
                ephemeral=True,
                delete_after=5,
            )
            return

        # individual deletes with a delay to avoid Discord rate limits
        for message in messages:
            await message.delete()
            await asyncio.sleep(0.8)

        end = time.perf_counter()
        await ctx.send(
            f"Done purging -> {n} messages! -> {self.purge_chat.qualified_name} "
            f"took {round(end - start)} seconds to process.",
            ephemeral=True,
            delete_after=3,
        )

    @commands.hybrid_command(
        description="purges empty voice channels and associated text channels",
        name="purge_lobby",
        qualified_name="purge_lobby",
    )
    @commands.has_guild_permissions(manage_channels=True)
    @commands.cooldown(rate=1, per=60)
    async def purge_lobby(self, ctx: commands.Context):
        await ctx.defer()

        if not ctx.guild:
            ctx.command.cooldown.reset()
            return

        to_delete = []
        for vc in ctx.guild.voice_channels:
            if vc.category and vc.category.name == VOICE_CATEGORY and not vc.members:
                data = self.db.get(vc.id)
                if data:
                    to_delete.append(data)

        n = len(to_delete)

        if n:
            for lobby_id, chat_id, role_id in to_delete:
                await get(ctx.guild.roles, id=role_id).delete()
                await get(ctx.guild.channels, id=chat_id).delete()
                await get(ctx.guild.channels, id=lobby_id).delete()
                self.db.remove(lobby_id)
            await ctx.send(f"Done purging -> {n} lobbies!", ephemeral=True)
            to_delete.clear()
        else:
            ctx.command.cooldown.reset()
            await ctx.send("Nothing found to purge.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PurgeCommands(bot))