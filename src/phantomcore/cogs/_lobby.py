from __future__ import annotations

import asyncio

import discord
from discord.ext import commands
from discord.utils import get

from phantomcore.channel_config import ensure_channel_structure
from phantomcore.db import LobbiesDB


class LobbyManager(commands.Cog):
    """Base class for dynamic lobby management.

    Subclasses only configure the category/channel naming scheme via the
    class attributes; the whole lobby lifecycle lives here.
    """

    VOICE_CATEGORY = ""
    CHAT_CATEGORY = ""
    TEMPLATE_CATEGORY = "Voice Lobby Template"
    TEMPLATE_CHANNEL = "Join to create a lobby"
    VOICE_CHANNEL_PREFIX = ""
    CHAT_CHANNEL_PREFIX = ""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = LobbiesDB(bot.settings.lobbies_db)
        self.video_state: list[int] = []
        self.stream_state: list[int] = []
        self.voice_state: list[int] = []
        self._ensure_on_ready = True

    # --- structure setup ------------------------------------------------------

    async def cog_load(self) -> None:
        if self.bot.is_ready():
            await self._ensure_structure()
            self._ensure_on_ready = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._ensure_on_ready:
            return
        self._ensure_on_ready = False
        await self._ensure_structure()

    async def _ensure_structure(self) -> None:
        """Idempotently create the configured categories and template channel."""
        await ensure_channel_structure(self.bot)

    # --- state helpers ------------------------------------------------------

    async def _voice_state(self, member: discord.Member, channel: discord.VoiceChannel) -> None:
        if member.voice.self_deaf:
            if member.id not in self.voice_state:
                self.voice_state.append(member.id)
            print(f"{member.name} is deaf")
            await channel.send(f"{member.name} is deaf")
        elif member.voice.self_mute:
            if member.id not in self.voice_state:
                self.voice_state.append(member.id)
            print(f"{member.name} is mute")
            await channel.send(f"{member.name} is mute")
        elif not member.voice.self_deaf or not member.voice.self_mute:
            if member.id in self.voice_state:
                self.voice_state.remove(member.id)
                print(f"{member.name} is back")
                await channel.send(f"{member.name} is back")

    async def _stream_state(self, member: discord.Member, channel: discord.VoiceChannel) -> None:
        if member.voice.self_stream:
            if member.id not in self.stream_state:
                self.stream_state.append(member.id)
                print(f"{member.name} started streaming")
                await channel.send(f"{member.name} started streaming")
        elif not member.voice.self_stream:
            if member.id in self.stream_state:
                self.stream_state.remove(member.id)
                print(f"{member.name} stopped streaming")
                await channel.send(f"{member.name} stopped streaming")

    async def _video_state(self, member: discord.Member, channel: discord.VoiceChannel) -> None:
        if member.voice.self_video:
            if member.id not in self.video_state:
                self.video_state.append(member.id)
                print(f"{member.name} opened the camera")
                await channel.send(f"{member.name} opened the camera")
        elif not member.voice.self_video:
            if member.id in self.video_state:
                self.video_state.remove(member.id)
                print(f"{member.name} closed the camera")
                await channel.send(f"{member.name} closed the camera")

    # --- lobby lifecycle ----------------------------------------------------

    async def _new_lobby(self, member: discord.Member, after: discord.VoiceState) -> None:
        """Create a voice lobby, its chat lobby and a role, then pull the user in."""
        category_voice = get(member.guild.categories, name=self.VOICE_CATEGORY)
        category_chat = get(member.guild.categories, name=self.CHAT_CATEGORY)

        nums = set()
        num = 0
        for chan in self.bot.get_all_channels():
            if chan.category == category_voice and chan.name.startswith(self.VOICE_CHANNEL_PREFIX):
                suffix = chan.name.removeprefix(self.VOICE_CHANNEL_PREFIX)
                if suffix.isdigit():
                    nums.update([int(suffix)])

        for nu in range(1, 100):
            if nu not in nums:
                num = nu
                break

        guild = after.channel.guild
        vc, tc = await asyncio.gather(
            guild.create_voice_channel(
                f"{self.VOICE_CHANNEL_PREFIX}{num}",
                category=category_voice,
                user_limit=after.channel.user_limit,
            ),
            guild.create_text_channel(f"{self.CHAT_CHANNEL_PREFIX}{num}", category=category_chat),
        )
        role = await guild.create_role(name=f"{vc.id}")

        await asyncio.gather(
            tc.set_permissions(role, read_messages=True, send_messages=True, read_message_history=True),
            member.add_roles(role),
        )

        self.db.add(vc.id, tc.id, role.id)

        await member.move_to(vc)

    async def _empty_lobby(self, before: discord.VoiceState) -> None:
        """Delete the empty voice lobby and its chat lobby + role."""
        if len(before.channel.members) != 0:
            return

        print(f"{before.channel.name} is now empty")
        data = self.db.get(before.channel.id)
        if data:
            lobby_id, chat_id, role_id = data
            await get(before.channel.guild.roles, id=role_id).delete()
            await get(before.channel.guild.channels, id=chat_id).delete()
            await get(before.channel.guild.channels, id=lobby_id).delete()
            self.db.remove(lobby_id)

    # --- event dispatch -----------------------------------------------------

    async def _just_joined(self, member: discord.Member, after: discord.VoiceState) -> None:
        category = after.channel.category
        if category is not None and category.name == self.TEMPLATE_CATEGORY:
            print(f"{member.name} joined {after.channel.name}")
            await self._new_lobby(member, after)
        elif category is not None and category.name == self.VOICE_CATEGORY:
            role = get(member.guild.roles, name=f"{after.channel.id}")
            await member.add_roles(role)
            print(f"{member.name} joined {after.channel.name}")
            await self._voice_state(member, after.channel)

    async def _switched_channels(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        before_cat = before.channel.category.name if before.channel.category else None
        after_cat = after.channel.category.name if after.channel.category else None

        if before_cat == self.TEMPLATE_CATEGORY and after_cat == self.VOICE_CATEGORY:
            print(f"{member.name} joined {after.channel.name}")
            await self._voice_state(member, after.channel)

        elif before_cat == self.VOICE_CATEGORY and after_cat == self.VOICE_CATEGORY:
            if before.channel.id != after.channel.id:
                await self._empty_lobby(before)
                role = get(member.guild.roles, name=f"{before.channel.id}")
                if role:
                    await member.remove_roles(role)
                role = get(member.guild.roles, name=f"{after.channel.id}")
                await member.add_roles(role)
                print(f"{member.name} switched to {after.channel.name}")
            await self._voice_state(member, after.channel)
            await self._stream_state(member, after.channel)
            await self._video_state(member, after.channel)

        elif before_cat == self.VOICE_CATEGORY and after_cat == self.TEMPLATE_CATEGORY:
            role = get(member.guild.roles, name=f"{before.channel.id}")
            if role:
                await member.remove_roles(role)
            await self._empty_lobby(before)
            await self._new_lobby(member, after)

        elif (
            before_cat != self.TEMPLATE_CATEGORY
            and before_cat != self.VOICE_CATEGORY
            and after_cat == self.TEMPLATE_CATEGORY
        ):
            await self._empty_lobby(before)
            await self._new_lobby(member, after)
            await self._voice_state(member, after.channel)
            await self._stream_state(member, after.channel)
            await self._video_state(member, after.channel)

        elif before_cat == self.VOICE_CATEGORY and (
            after_cat != self.VOICE_CATEGORY and after_cat != self.TEMPLATE_CATEGORY
        ):
            role = get(member.guild.roles, name=f"{before.channel.id}")
            if role:
                await member.remove_roles(role)
            await self._empty_lobby(before)
            await self._voice_state(member, after.channel)
            await self._stream_state(member, after.channel)
            await self._video_state(member, after.channel)

    async def _just_left(self, member: discord.Member, before: discord.VoiceState) -> None:
        role = get(member.guild.roles, name=f"{before.channel.id}")
        if role:
            await member.remove_roles(role)
        await self._empty_lobby(before)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if not before.channel:
            await self._just_joined(member, after)
        elif before.channel and after.channel:
            await self._switched_channels(member, before, after)
        elif not after.channel:
            await self._just_left(member, before)