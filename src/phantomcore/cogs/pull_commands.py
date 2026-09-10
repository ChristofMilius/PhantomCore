from __future__ import annotations

import typing

import discord
from discord.ext import commands
from discord.ui import View

from phantomcore.settings import Settings


class PullButton(View):
    def __init__(self, user: discord.Member, target: discord.VoiceChannel):
        super().__init__(timeout=None)
        self.member = user
        self.channel = target

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.blurple, emoji="⁉️")
    async def button_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.button_reject.disabled = True
        button.label = "Accepted"
        button.emoji = "👌"
        button.disabled = True
        await self.member.move_to(self.channel)
        await interaction.response.edit_message(view=self)
        await interaction.delete_original_response()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.blurple, emoji="⁉️")
    async def button_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.button_accept.disabled = True
        button.label = "Rejected"
        button.emoji = "👌"
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.delete_original_response()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(
                f"🚫You are not {self.member.mention}!🚫", ephemeral=True
            )
            return False

        if not self.member.voice:
            await interaction.response.send_message(
                f"🚫{self.member.mention} is NOT connected to a lobby!🚫", ephemeral=True
            )
            self.stop()
            return False

        return True


class PullCommands(commands.Cog, name="pull_commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings: Settings = bot.settings

    @commands.hybrid_command(
        name="mlt_pull", description="pulls multiple members into voice_channel of user"
    )
    @commands.cooldown(rate=1, per=60)
    async def mlt_pull(
        self, ctx: commands.Context, members: commands.Greedy[discord.Member] = None
    ):
        await ctx.defer()

        if not ctx.author.voice:
            await ctx.send(
                f"🚫User {ctx.author.mention} is not connected to a lobby!🚫", ephemeral=True
            )
            return

        if members is None or not members:
            await ctx.send("🚫No members selected🚫", ephemeral=True)
            return

        channel = ctx.author.voice.channel

        for member in members:
            if member == ctx.author:
                await ctx.send(
                    f"🚫{ctx.author.mention} You cannot pull yourself!🚫", ephemeral=True
                )
                continue
            elif member.id == self.settings.bot_id:
                try:
                    await channel.connect()
                except discord.ClientException:
                    await member.move_to(channel)
                await ctx.send(f"{member.mention} pulled in {channel}", ephemeral=True)
            else:
                if not member.voice:
                    await ctx.send(
                        f"🚫{member.mention} is NOT connected to a lobby!🚫", ephemeral=True
                    )
                    continue
                view = PullButton(member, channel)
                await ctx.send(f"{ctx.author.mention} send a pull request to {member.mention}",
                               view=view)

    @commands.hybrid_command(
        description="pulls a single member into voice_channel of user",
        qualified_name="sgl_pull",
        name="sgl_pull",
    )
    @commands.cooldown(rate=1, per=60)
    async def sgl_pull(
        self, ctx: commands.Context, member: typing.Optional[discord.Member] = None
    ):
        await ctx.defer()

        if not ctx.author.voice:
            await ctx.send(
                f"🚫User {ctx.author.mention} is not connected to a lobby!🚫", ephemeral=True
            )
            return

        if member is None:
            await ctx.send("🚫No member selected🚫", ephemeral=True)
            return

        if member == ctx.author:
            await ctx.send(
                f"🚫{ctx.author.mention} You cannot pull yourself!🚫", ephemeral=True
            )
            return

        channel = ctx.author.voice.channel

        if member.id == self.settings.bot_id:
            try:
                await channel.connect()
            except discord.ClientException:
                await member.move_to(channel)
            await ctx.send(f"{member.mention} pulled in {channel}", ephemeral=True)
        else:
            if not member.voice:
                await ctx.send(
                    f"🚫{member.mention} is NOT connected to a lobby!🚫", ephemeral=True
                )
                return

            view = PullButton(member, channel)
            await ctx.send(f"{ctx.author.mention} send a pull request to {member.mention}",
                           view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PullCommands(bot))