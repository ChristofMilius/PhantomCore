from __future__ import annotations

import discord
from discord.ext import commands
from discord.ui import Button, View


class LoaderButtons(View):
    def __init__(self, bot: commands.Bot, ext: str, channel):
        super().__init__(timeout=None)
        self.extension = ext
        self.channel = channel
        self.bot = bot

    async def _toggle(self, interaction: discord.Interaction, action: str) -> None:
        try:
            if action == "load":
                await self.bot.load_extension(f"phantomcore.cogs.{self.extension}")
            elif action == "unload":
                await self.bot.unload_extension(f"phantomcore.cogs.{self.extension}")
            elif action == "reload":
                await self.bot.unload_extension(f"phantomcore.cogs.{self.extension}")
                await self.bot.load_extension(f"phantomcore.cogs.{self.extension}")
        except discord.DiscordException as err:
            await self.channel.send(str(err))
        except AttributeError as aerr:
            await self.channel.send(str(aerr))

    def _reset_buttons(self) -> None:
        self.button_load.label, self.button_load.emoji = "Load", "❔"
        self.button_unload.label, self.button_unload.emoji = "Unload", "❔"
        self.button_reload.label, self.button_reload.emoji = "Reload", "❔"

    @discord.ui.button(label="Load", style=discord.ButtonStyle.blurple, emoji="❔")
    async def button_load(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._reset_buttons()
        await self._toggle(interaction, "load")
        button.label, button.emoji = self.extension, "✅"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Unload", style=discord.ButtonStyle.blurple, emoji="❔")
    async def button_unload(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._reset_buttons()
        await self._toggle(interaction, "unload")
        button.label, button.emoji = self.extension, "✅"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Reload", style=discord.ButtonStyle.blurple, emoji="❔")
    async def button_reload(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._reset_buttons()
        await self._toggle(interaction, "reload")
        button.label, button.emoji = self.extension, "✅"
        await interaction.response.edit_message(view=self)


class ExtensionHelper(commands.Cog, name="extension_helper"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        description="Brings up the Helper Embed", qualified_name="helper", name="helper"
    )
    @commands.is_owner()
    async def helper(self, ctx: commands.Context):
        channel = self.bot.get_channel(self.bot.settings.status_channel_id)
        if channel is None:
            await ctx.send("Status channel could not be found!", ephemeral=True)
            return

        embed = discord.Embed(
            title="Jump",
            description=f"[#{channel.name}]({channel.jump_url})",
            colour=discord.Color.random(),
        )
        await ctx.send(embed=embed, ephemeral=True)

        messages = [m async for m in channel.history(limit=None)]
        n = len(messages)
        await channel.purge(limit=n)
        await ctx.send(
            f"Purged <{channel.name}> -> {n} messages!", ephemeral=True, delete_after=3
        )

        for ext in self.bot.settings.extensions:
            cog = self.bot.get_cog(ext)
            view = LoaderButtons(self.bot, ext, channel)
            embed = discord.Embed(
                title=cog.__class__.__name__ if cog else ext,
                type="article",
                description=ext,
                colour=discord.Color.random(),
            )
            embed.set_thumbnail(url=self.bot.user.avatar)
            if cog:
                for command in cog.walk_commands():
                    embed.add_field(
                        name=command.name, value=command.description or "—", inline=False
                    )
            await channel.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExtensionHelper(bot))