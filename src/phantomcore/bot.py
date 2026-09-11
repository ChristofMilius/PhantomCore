from __future__ import annotations

import logging
import traceback
from datetime import datetime

import discord
from discord.ext import commands

from phantomcore.channel_config import ensure_channel_structure
from phantomcore.extension_loader import (
    load_all_extensions,
    unload_all_extensions,
    load_results,
)
from phantomcore.settings import Settings

logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
    logger.addHandler(handler)


class PhantomBot(commands.Bot):
    def __init__(self, settings: Settings):
        self.settings = settings
        super().__init__(
            command_prefix="\\",
            description="-=PhantomCore=-",
            owner_id=settings.owner_id,
            intents=settings.intents,
        )

    # --- lifecycle --------------------------------------------------------

    async def setup_hook(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.chat_history_dir.mkdir(parents=True, exist_ok=True)
        await load_all_extensions(self, self.settings)

    async def on_ready(self) -> None:
        await self.tree.sync()
        await ensure_channel_structure(self)

        status_channel = self.get_channel(self.settings.status_channel_id)
        bot_channel = self.get_channel(self.settings.bot_channel_id)
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        owner = await self.fetch_user(self.settings.owner_id)

        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=owner.name)
        )
        if bot_channel is not None:
            await bot_channel.send(f"Online! {current_time}")

        if status_channel is not None:
            await status_channel.purge(limit=None)
            for result in load_results:
                await status_channel.send(result)

    # --- error handling ----------------------------------------------------

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        embed = discord.Embed(
            title="Error!",
            description="SORRY!",
            colour=discord.Color.random(),
        )
        embed.set_thumbnail(url=self.user.avatar)

        error_str = str(error)
        embed.add_field(name="Error_Content!", value=f"{current_time} | {error_str}", inline=True)
        print(error_str)
        traceback.print_exc()
        await ctx.channel.send(mention_author=True, embed=embed)

    # --- extension management ----------------------------------------------

    @commands.command()
    @commands.is_owner()
    async def load_ext(self, ctx: commands.Context, ext: str | None = None):
        if ext == "all":
            await load_all_extensions(self, self.settings)
            for result in load_results:
                await ctx.send(result)
            await ctx.reply("Done loading!")
        else:
            try:
                await self.load_extension(f"phantomcore.cogs.{ext}")
            except commands.ExtensionAlreadyLoaded:
                await ctx.reply(f"Extension {ext} was already loaded!❌")
            else:
                await ctx.reply(f"Extension {ext} has been loaded!✅")

    @commands.command()
    @commands.is_owner()
    async def unload_ext(self, ctx: commands.Context, ext: str | None = None):
        if ext == "all":
            await unload_all_extensions(self, self.settings)
            for result in load_results:
                await ctx.send(result)
            await ctx.reply("Done unloading!")
        else:
            try:
                await self.unload_extension(f"phantomcore.cogs.{ext}")
            except commands.ExtensionNotLoaded:
                await ctx.reply(f"Extension {ext} was not loaded!❌")
            else:
                await ctx.reply(f"Extension {ext} has been unloaded!✅")

    @commands.command()
    @commands.is_owner()
    async def reload_ext(self, ctx: commands.Context, ext: str | None = None):
        if ext == "all":
            async with ctx.typing():
                await unload_all_extensions(self, self.settings)
                for result in load_results:
                    await ctx.send(result)
                await load_all_extensions(self, self.settings)
                for result in load_results:
                    await ctx.send(result)
                await ctx.reply("Done reloading!")
        else:
            async with ctx.typing():
                await self.unload_extension(f"phantomcore.cogs.{ext}")
                await ctx.send(f"Extension {ext} has been unloaded!✅")
                await self.load_extension(f"phantomcore.cogs.{ext}")
                await ctx.send(f"Extension {ext} has been loaded!✅")
                await ctx.reply("Done reloading!")

    @commands.command()
    @commands.is_owner()
    async def show_ext(self, ctx: commands.Context):
        await ctx.reply(list(self.settings.extensions))