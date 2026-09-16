from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field

import discord
import wavelink
from discord.ext import commands
from discord.ui import Modal, View, TextInput

from phantomcore.settings import PROJECT_ROOT

LAVALINK_JAR = PROJECT_ROOT / "lavalink" / "Lavalink.jar"
DEFAULT_VOLUME = 50

RADIO_BASE = "https://stream.nightride.fm"
RADIO_STATIONS = {
    "nightride": "Synthwave / Retrowave / Outrun",
    "chillsynth": "Chillsynth / Chillwave / Instrumental",
    "datawave": "Glitchy Synthwave / IDM / Retro Computing",
    "spacesynth": "Spacesynth / Space Disco / Vocoder Italo",
    "darksynth": "Darksynth / Cyberpunk / Horror",
    "horrorsynth": "Horrorsynth / Witch House",
    "ebsm": "EBSM / Industrial / Clubbing",
}


def _node_up(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class MusicSession:
    """Per-guild state for the StalkerPlayer (replaces the old global Container)."""

    guild_id: int
    channel: discord.TextChannel
    player: wavelink.Player | None = None
    message: discord.Message | None = None
    controller: discord.Member | None = None
    target: discord.Member | None = None
    last_claim: float = 0.0
    panels: list[int] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def queue_len(self) -> int:
        if self.player is None:
            return 0
        return len(self.player.queue)


class PlayerModal(Modal, title="SearchBox"):
    search = TextInput(label="Search on Web")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.on_result(interaction, self.search.value.strip())

    async def on_result(self, interaction: discord.Interaction, query: str):
        raise NotImplementedError


class ClaimDialogue(View):
    """Ask the current controller to hand over control (old Dialogue)."""

    def __init__(self, user: discord.Member, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.target_user = user
        self.answer: bool | None = None

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.blurple, emoji="👌")
    async def button_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.button_reject.disabled = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        self.answer = True
        self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.blurple, emoji="🚫")
    async def button_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.button_accept.disabled = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        self.answer = False
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.target_user:
            await interaction.response.send_message(
                f"{interaction.user.display_name}, this is not for you to click!", ephemeral=True
            )
            return False
        return True


class SearchSelectView(View):
    """Choose one of the search results to enqueue."""

    def __init__(self, tracks: list[wavelink.Playable], callback, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        choices = [
            discord.SelectOption(
                label=(t.title or "?")[:90],
                value=str(i),
                description=(t.author or "?")[:90],
            )
            for i, t in enumerate(tracks)
        ]
        select = discord.ui.Select(placeholder="Pick a track to enqueue...", options=choices[:25])
        select.callback = lambda inter: self._pick(inter, select)
        self.add_item(select)
        self._tracks = tracks
        self._callback = callback

    async def _pick(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        index = int(select.values[0])
        await self._callback(interaction, self._tracks[index], self)


class RadioSelectView(View):
    """Choose one of the Nightride FM stations to enqueue as a stream."""

    def __init__(self, callback, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        choices = [
            discord.SelectOption(label=name.upper(), value=name, description=desc)
            for name, desc in RADIO_STATIONS.items()
        ]
        select = discord.ui.Select(placeholder="Pick a station to tune in...", options=choices)
        select.callback = lambda inter: self._pick(inter, select)
        self.add_item(select)
        self._callback = callback

    async def _pick(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        await self._callback(interaction, select.values[0], self)


class PlayerPanel(View):
    """All the buttons on the UI. Rebuilt from session state on every change."""

    def __init__(self, cog: "StalkerPlayer", session: MusicSession, *, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session = session
        self._recompute()  # disables/options per current state

    # -- state ------------------------------------------------------------

    def _player(self) -> wavelink.Player | None:
        return self.session.player

    def _is_connected(self) -> bool:
        player = self._player()
        return player is not None and player.connected and player.channel is not None

    def _is_playing(self) -> bool:
        player = self._player()
        return player is not None and player.playing

    def _is_paused(self) -> bool:
        player = self._player()
        return player is not None and player.paused

    def _is_looping_song(self) -> bool:
        player = self._player()
        return player is not None and player.queue.mode is wavelink.QueueMode.loop

    def _is_looping_queue(self) -> bool:
        player = self._player()
        return player is not None and player.queue.mode is wavelink.QueueMode.loop_all

    def _recompute(self) -> None:
        connected = self._is_connected()
        playing = self._is_playing()
        paused = self._is_paused()
        queue_len = self.session.queue_len
        has_history = bool(self.session.player is not None and self.session.player.queue.history)
        has_track = self.session.player is not None and (self.session.player.current is not None or queue_len)
        following = self.session.target is not None

        self.button_search.disabled = not connected
        self.button_purge.disabled = not connected or queue_len == 0
        self.button_radio.disabled = not connected
        self.button_back.disabled = not connected or not has_history
        self.button_toggle.disabled = not connected or not (playing or paused)
        self.button_toggle.label = "resume" if paused else "pause"
        self.button_toggle.emoji = "⏯️" if paused else "⏸️"
        self.button_play.disabled = not connected or playing or (not queue_len and not has_history)
        self.button_stop.disabled = not connected or not (playing or paused)
        self.button_forward.disabled = not connected or not (playing or paused or queue_len)
        self.button_loop_song.disabled = not connected or not has_track
        self.button_loop_song.style = (
            discord.ButtonStyle.success if self._is_looping_song() else discord.ButtonStyle.secondary
        )
        self.button_loop_queue.disabled = not connected or not has_track
        self.button_loop_queue.style = (
            discord.ButtonStyle.success if self._is_looping_queue() else discord.ButtonStyle.secondary
        )
        self.button_follow.disabled = not connected or following
        self.button_unfollow.disabled = not connected or not following
        self.button_join.disabled = connected
        self.button_leave.disabled = not connected

    # -- permissions ------------------------------------------------------

    def _owned(self, interaction: discord.Interaction) -> bool:
        return self.session.controller is not None and interaction.user == self.session.controller

    async def _kick_out(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"hands off! **`{interaction.user.display_name}`** claim control or else!", ephemeral=True
        )

    # -- row 0: search + purge --------------------------------------------

    @discord.ui.button(label="search", emoji="🔎", row=0)
    async def button_search(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return

        modal = SearchModal(self.cog, self.session)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="purge queue", emoji="🔥", row=0)
    async def button_purge(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        player = self.session.player
        if player is not None:
            player.queue.clear()
        await self._sync()
        await self._notice(interaction, "queue has been purged")

    @discord.ui.button(label="radio", emoji="📻", row=0)
    async def button_radio(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        picker = RadioSelectView(self.cog._radio_pick)
        await interaction.followup.send("Pick a Nightride FM station:", view=picker, ephemeral=True)

    # -- row 1: navigation + transport ------------------------------------

    @discord.ui.button(label="bwd", emoji="⏪", row=1)
    async def button_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._previous(self.session)

    @discord.ui.button(label="pause", emoji="⏸️", row=1)
    async def button_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        player = self.session.player
        if player is not None:
            await player.pause(not player.paused)
        await self._sync()

    @discord.ui.button(label="play", emoji="▶️", row=1)
    async def button_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._start_playing(self.session)

    @discord.ui.button(label="stop", emoji="⏹️", row=1)
    async def button_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._stop(self.session)

    @discord.ui.button(label="fwd", emoji="⏩", row=1)
    async def button_forward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._skip(self.session)

    # -- row 2: loops ------------------------------------------------------

    @discord.ui.button(label="loop song", emoji="🔂", row=2)
    async def button_loop_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._loop_song_toggle(self.session)

    @discord.ui.button(label="loop queue", emoji="🔁", row=2)
    async def button_loop_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._loop_queue_toggle(self.session)

    # -- row 3: stalk + claim ---------------------------------------------

    @discord.ui.button(label="follow", emoji="🧲", row=3)
    async def button_follow(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        self.session.target = interaction.user
        await self._sync()
        await self._notice(interaction, f"now following {interaction.user.display_name}")

    @discord.ui.button(label="unfollow", emoji="🚷", row=3)
    async def button_unfollow(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        self.session.target = None
        await self._sync()
        await self._notice(interaction, "no longer following anyone")

    @discord.ui.button(label="claim control", emoji="🙏", row=3)
    async def button_claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._owned(interaction):
            await interaction.response.send_message(
                f"{interaction.user.mention}, you are already in control of the StalkerPlayer!", ephemeral=True
            )
            return

        claim_time = self.cog.bot.settings.claim_time
        since = time.time() - self.session.last_claim
        if self.session.last_claim and since < claim_time:
            remaining = claim_time - since
            await interaction.response.send_message(
                f"{interaction.user.mention}, this can only be done once every {int(claim_time)} seconds! "
                f"Try again in {int(remaining)} seconds.",
                ephemeral=True,
            )
            return

        self.session.last_claim = time.time()
        controller = self.session.controller or interaction.user
        dialogue = ClaimDialogue(controller, timeout=30.0)
        await interaction.response.send_message(
            f"{controller.mention} | {interaction.user.mention} claims control of the player, do you allow it?",
            view=dialogue,
        )
        await dialogue.wait()
        if dialogue.answer is True:
            self.session.controller = interaction.user
            await interaction.followup.send(f"{interaction.user.mention} is now in control!", ephemeral=True)
        elif dialogue.answer is False:
            await interaction.followup.send(f"{controller.mention} rejected the claim.", ephemeral=True)
        await self._sync()

    # -- row 4: join + leave ----------------------------------------------

    @discord.ui.button(label="join", emoji="🛖", row=4)
    async def button_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        try:
            await self.cog._join_voice(self.session, interaction.user)
        except RuntimeError as err:
            await self._notice(interaction, str(err))
            return
        await self._sync()

    @discord.ui.button(label="leave", emoji="🚪", row=4)
    async def button_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owned(interaction):
            await self._kick_out(interaction)
            return
        await interaction.response.defer()
        await self.cog._leave_voice(self.session)
        await self._sync()

    # -- helpers ----------------------------------------------------------

    async def _sync(self) -> None:
        await self.cog._sync(self.session)

    async def _notice(self, interaction: discord.Interaction, text: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)


class SearchModal(PlayerModal):
    """Modal that opens a picker with the top search results (old SearchBox)."""

    def __init__(self, cog: "StalkerPlayer", session: MusicSession):
        super().__init__()
        self.cog = cog
        self.session = session

    async def on_result(self, interaction: discord.Interaction, query: str) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        try:
            tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTube)
        except Exception as err:
            await interaction.followup.send(f"No query results! ({err})", ephemeral=True)
            return

        if not tracks:
            await interaction.followup.send("No query results!", ephemeral=True)
            return

        if isinstance(tracks, wavelink.Playlist):
            await self.cog._enqueue_many(self.session, list(tracks))
            await interaction.followup.send(f"added playlist {tracks.name!r} ({len(tracks)} tracks)", ephemeral=True)
            return

        if len(tracks) == 1:
            await self.cog._enqueue(self.session, tracks[0])
            await interaction.followup.send(f"added: {tracks[0].title}", ephemeral=True)
            return

        picker = SearchSelectView(tracks, self.cog._search_pick)
        await interaction.followup.send("Pick a track:", view=picker)


class StalkerPlayer(commands.Cog, name="stalker_player"):
    """Port of the old warshipai StalkerPlayer on wavelink 3 + Lavalink 4."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: dict[int, MusicSession] = {}
        self._lavalink_lock = asyncio.Lock()
        self._lavalink_proc: subprocess.Popen | None = None
        self._pool_ready = False

    # ------------------------------------------------------------------
    # lavalink lifecycle
    # ------------------------------------------------------------------

    def _node_target(self) -> tuple[str, int]:
        host, _, port = self.bot.settings.lavalink_host.partition(":")
        return host, int(port or 7867)

    async def _ensure_lavalink(self) -> None:
        async with self._lavalink_lock:
            host, port = self._node_target()

            if not _node_up(host, port):
                settings = self.bot.settings
                java = settings.lavalink_java.strip() or (
                    str(PROJECT_ROOT / "lavalink" / "jre" / "bin" / "java.exe")
                    if (PROJECT_ROOT / "lavalink" / "jre" / "bin" / "java.exe").exists()
                    else "java"
                )
                if not shutil.which(java) and not os.path.exists(java):
                    raise RuntimeError(
                        f"Java executable not found: {java!r}. Set JAVA_PATH in .env to a "
                        f"valid java.exe, or unset it to use the bundled JRE."
                    )
                if not LAVALINK_JAR.exists():
                    raise RuntimeError(f"Lavalink jar not found at {LAVALINK_JAR}")
                settings.lavalink_dir.mkdir(parents=True, exist_ok=True)
                (settings.lavalink_dir / "logs").mkdir(exist_ok=True)
                log = open(settings.lavalink_dir / "logs" / "lavalink.log", "a")
                try:
                    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                except AttributeError:
                    flags = 0
                self._lavalink_proc = subprocess.Popen(
                    [java, "-jar", str(LAVALINK_JAR)],
                    cwd=str(settings.lavalink_dir),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                    env={
                        **os.environ,
                        "LAVALINK_SERVER_PASSWORD": settings.lavalink_password,
                    },
                )

            deadline = time.monotonic() + 45
            while not _node_up(host, port):
                if time.monotonic() > deadline:
                    raise RuntimeError("Lavalink did not become reachable in time")
                await asyncio.sleep(0.5)

            node: wavelink.Node | None = None
            if not self._pool_ready or not wavelink.Pool.nodes:
                node = wavelink.Node(
                    uri=f"http://{host}:{port}",
                    password=self.bot.settings.lavalink_password,
                    inactive_player_timeout=120,
                )
                await wavelink.Pool.connect(client=self.bot, nodes=[node], cache_capacity=None)
            else:
                node = wavelink.Pool.get_node()

            ready = time.monotonic() + 15
            while node is not None and node.status is not wavelink.NodeStatus.CONNECTED:
                if time.monotonic() > ready:
                    raise RuntimeError("Lavalink node did not become ready in time")
                await asyncio.sleep(0.2)
            self._pool_ready = True

    # ------------------------------------------------------------------
    # session plumbing
    # ------------------------------------------------------------------

    def _panel_channel(self, ctx: commands.Context) -> discord.TextChannel:
        channel = self.bot.get_channel(self.bot.settings.stalker_channel_id) if self.bot.settings.stalker_channel_id else None
        return channel if channel is not None else ctx.channel

    def _get_or_create(self, ctx: commands.Context, channel: discord.TextChannel) -> MusicSession:
        session = self.sessions.get(ctx.guild.id)
        if session is None:
            session = MusicSession(guild_id=ctx.guild.id, channel=channel, controller=ctx.author)
            self.sessions[ctx.guild.id] = session
        return session

    async def _join_voice(self, session: MusicSession, member: discord.Member) -> None:
        if member.voice is None or member.voice.channel is None:
            raise RuntimeError(f"{member.mention} you are not connected to a voice channel!")
        channel = member.voice.channel
        guild = self.bot.get_guild(session.guild_id)
        vc = guild.voice_client if guild is not None else None

        if vc is None:
            await channel.connect(cls=wavelink.Player)
            session.player = guild.voice_client
        elif isinstance(vc, wavelink.Player):
            if vc.channel and vc.channel.id == channel.id:
                session.player = vc
            else:
                await vc.move_to(channel)
                session.player = vc
        else:
            await vc.disconnect()
            await channel.connect(cls=wavelink.Player)
            session.player = guild.voice_client

    async def _leave_voice(self, session: MusicSession) -> None:
        player = session.player
        if player is not None:
            try:
                await player.disconnect(force=True)
            except Exception:
                pass
        session.player = None
        session.target = None

    async def _purge_panels(self, session: MusicSession) -> None:
        for message_id in session.panels:
            try:
                message = await session.channel.fetch_message(message_id)
                if message:
                    await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass
        session.panels.clear()

    async def _sync(self, session: MusicSession) -> None:
        async with session.lock:
            embed = self._embed(session)
            view = PlayerPanel(self, session)
            if session.message is None:
                session.message = await session.channel.send(embed=embed, view=view)
                session.panels.append(session.message.id)
            else:
                try:
                    await session.message.edit(embed=embed, view=view)
                except discord.NotFound:
                    session.message = await session.channel.send(embed=embed, view=view)
                    session.panels.append(session.message.id)

    def _embed(self, session: MusicSession) -> discord.Embed:
        player = session.player
        current = player.current if player is not None else None
        controller = session.controller
        embed = discord.Embed(title="StalkerPlayer", colour=discord.Color.blurple())

        description = []
        if controller is not None:
            description.append(f"{controller.mention} is in control")
        if session.target is not None:
            description.append(f"stalking {session.target.mention}")
        embed.description = "\n".join(description) or None

        if player is None:
            status = "offline"
        elif player.paused:
            status = "paused"
        elif player.playing:
            status = f"playing · ping {player.ping}ms"
        else:
            status = "idle"
        embed.add_field(name="Status", value=status, inline=False)

        if current is not None:
            length = f"{current.length // 60000}:{current.length % 60000:02d}" if not current.is_stream else "LIVE"
            embed.add_field(name="Now Playing", value=f"{current.title}\n*{current.author}* · {length}", inline=False)
            embed.add_field(name="Link", value=f"[Open]({current.uri})" if current.uri else "—", inline=False)
            if current.artwork:
                embed.set_image(url=current.artwork)
        else:
            embed.add_field(name="Now Playing", value="Nothing playing", inline=False)
            embed.add_field(name="Link", value="—", inline=False)

        queue_len = session.queue_len
        mode = "off"
        if player is not None:
            if player.queue.mode is wavelink.QueueMode.loop:
                mode = "song"
            elif player.queue.mode is wavelink.QueueMode.loop_all:
                mode = "queue"
        embed.set_footer(text=f"{queue_len} tracks in queue · loop: {mode}")
        return embed

    # ------------------------------------------------------------------
    # playback helpers
    # ------------------------------------------------------------------

    async def _start_playing(self, session: MusicSession) -> bool:
        player = session.player
        if player is None or not player.connected:
            return False
        if player.playing:
            return True
        history = player.queue.history
        if player.queue.is_empty:
            if history is None or len(history) == 0:
                return False
            await player.play(history[-1], volume=DEFAULT_VOLUME, paused=False, add_history=False)
            return True
        try:
            track = player.queue.get()
        except wavelink.QueueEmpty:
            return False
        await player.play(track, volume=DEFAULT_VOLUME, paused=False)
        return True

    async def _enqueue(self, session: MusicSession, track: wavelink.Playable) -> None:
        player = session.player
        if player is not None:
            player.queue.put(track)
            if player.current is None:
                await self._start_playing(session)
        await self._sync(session)

    async def _enqueue_many(self, session: MusicSession, tracks: list[wavelink.Playable]) -> None:
        player = session.player
        if player is not None:
            player.queue.put(tracks)
            if player.current is None:
                await self._start_playing(session)
        await self._sync(session)

    async def _search_pick(self, interaction: discord.Interaction, track: wavelink.Playable, view: View) -> None:
        session = self.sessions.get(int(interaction.guild_id))
        if session is not None:
            await self._enqueue(session, track)
        if interaction.response.is_done():
            await interaction.followup.send(f"added: {track.title}", ephemeral=True)
        else:
            await interaction.response.send_message(f"added: {track.title}", ephemeral=True)
        view.stop()

    async def _radio_pick(self, interaction: discord.Interaction, station: str, view: View) -> None:
        async def reply(text: str) -> None:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)

        session = self.sessions.get(int(interaction.guild_id))
        if session is not None:
            try:
                tracks = await wavelink.Playable.search(f"{RADIO_BASE}/{station}.mp3")
            except Exception as err:
                await reply(f"Could not tune in to {station}: {err}")
                view.stop()
                return
            if not tracks:
                await reply(f"Could not tune in to {station}: no stream loaded")
                view.stop()
                return
            first = tracks[0] if isinstance(tracks, list) else list(tracks)[0]
            if session.player is not None and session.player.connected:
                await session.player.play(first, volume=DEFAULT_VOLUME, paused=False)
            else:
                await self._enqueue(session, first)
            await self._sync(session)
        await reply(f"tuned in to {station} FM")
        view.stop()

    async def _toggle_pause(self, session: MusicSession) -> None:
        player = session.player
        if player is None:
            return
        await player.pause(not player.paused)

    async def _stop(self, session: MusicSession) -> None:
        player = session.player
        if player is None:
            return
        await player.stop(force=False)

    async def _skip(self, session: MusicSession) -> None:
        player = session.player
        if player is None:
            return
        history = player.queue.history
        if player.current is None and player.queue.is_empty and (history is None or len(history) == 0):
            return
        try:
            track = player.queue.get()
        except wavelink.QueueEmpty:
            if history is not None and len(history) > 0:
                await player.play(history[-1], volume=DEFAULT_VOLUME, paused=False, add_history=False)
            return
        await player.play(track, volume=DEFAULT_VOLUME, paused=False)

    async def _previous(self, session: MusicSession) -> None:
        player = session.player
        if player is None:
            return
        history = player.queue.history
        if history is None or len(history) == 0:
            return
        track = history[-1]
        if player.current is not None and player.current == track:
            track = history[-2] if len(history) > 1 else history[-1]
        await player.play(track, replace=True, volume=DEFAULT_VOLUME, paused=False)

    async def _loop_song_toggle(self, session: MusicSession) -> None:
        player = session.player
        if player is None:
            return
        if player.queue.mode is wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.normal
        else:
            player.queue.mode = wavelink.QueueMode.loop

    async def _loop_queue_toggle(self, session: MusicSession) -> None:
        player = session.player
        if player is None:
            return
        if player.queue.mode is wavelink.QueueMode.loop_all:
            player.queue.mode = wavelink.QueueMode.normal
        else:
            player.queue.mode = wavelink.QueueMode.loop_all

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------

    @commands.hybrid_command(name="stalker_player", aliases=["stalker"], description="Boot the StalkerPlayer panel")
    async def stalker(self, ctx: commands.Context) -> None:
        await ctx.defer()
        channel = self._panel_channel(ctx)
        session = self._get_or_create(ctx, channel)

        try:
            await self._ensure_lavalink()
        except RuntimeError as err:
            await ctx.send(f"Lavalink trouble: {err}", ephemeral=True)
            return

        if ctx.author.voice:
            await self._join_voice(session, ctx.author)
        await self._purge_panels(session)
        await self._sync(session)
        if ctx.channel.id != channel.id:
            await ctx.send(f"StalkerPlayer panel posted in {channel.mention}", ephemeral=True)

    @commands.hybrid_command(name="join", description="Join the StalkerPlayer to your voice channel")
    async def join(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(f"{ctx.author.mention}, you are not connected to a voice channel!", ephemeral=True)
            return
        await self._ensure_lavalink()
        try:
            await self._join_voice(session, ctx.author)
        except RuntimeError as err:
            await ctx.send(str(err), ephemeral=True)
            return
        await self._sync(session)

    @commands.hybrid_command(name="leave", description="Make the StalkerPlayer leave the voice channel")
    async def leave(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        await self._leave_voice(session)
        await self._sync(session)

    @commands.hybrid_command(name="play", description="Search and enqueue a track")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(f"{ctx.author.mention}, join a voice channel first!", ephemeral=True)
            return
        await ctx.defer()
        session = self._get_or_create(ctx, ctx.channel)
        await self._ensure_lavalink()
        if session.player is None:
            await self._join_voice(session, ctx.author)
        try:
            tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTube)
        except Exception as err:
            await ctx.send(f"No results: {err}", ephemeral=True)
            return
        if not tracks:
            await ctx.send("No results!", ephemeral=True)
            return
        if isinstance(tracks, wavelink.Playlist):
            await self._enqueue_many(session, list(tracks))
            await ctx.send(f"added playlist {tracks.name!r} ({len(tracks)} tracks)")
        else:
            await self._enqueue(session, tracks[0])
            await ctx.send(f"added: {tracks[0].title}")

    @commands.hybrid_command(name="radio", description="Tune into a Nightride FM station")
    async def radio(self, ctx: commands.Context) -> None:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(f"{ctx.author.mention}, join a voice channel first!", ephemeral=True)
            return
        await ctx.defer()
        session = self._get_or_create(ctx, ctx.channel)
        await self._ensure_lavalink()
        if session.player is None:
            await self._join_voice(session, ctx.author)
        picker = RadioSelectView(self._radio_pick)
        await ctx.send("Pick a Nightride FM station:", view=picker)

    @commands.hybrid_command(name="pause", description="Pause the currently playing track")
    async def pause(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        await self._toggle_pause(session)
        await self._sync(session)

    @commands.hybrid_command(name="resume", description="Resume the paused track")
    async def resume(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        if session.player is not None:
            await session.player.pause(False)
        await self._sync(session)

    @commands.hybrid_command(name="skip", description="Skip to the next track")
    async def skip(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        await self._skip(session)
        await self._sync(session)

    @commands.hybrid_command(name="stop", description="Stop the current track")
    async def stop(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        await self._stop(session)
        await self._sync(session)

    @commands.hybrid_command(name="stalk", description="Stalk a user and play music wherever they go")
    async def stalk(self, ctx: commands.Context, *, member: discord.Member) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        session.target = member
        await self._sync(session)
        await ctx.send(f"stalking {member.mention}", ephemeral=True)
        if member.voice and member.voice.channel is not None:
            await self._join_voice(session, member)
            await self._sync(session)

    @commands.hybrid_command(name="unstalk", description="Stop stalking the target user")
    async def unstalk(self, ctx: commands.Context) -> None:
        session = self._get_or_create(ctx, ctx.channel)
        session.target = None
        await self._sync(session)
        await ctx.send("no longer stalking anyone", ephemeral=True)

    # ------------------------------------------------------------------
    # listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        session = self.sessions.get(member.guild.id)
        if session is None or session.target != member:
            return

        if after.channel is None:
            await self._leave_voice(session)
            await self._sync(session)
        elif before.channel is None or before.channel.id != after.channel.id:
            guild = self.bot.get_guild(session.guild_id)
            vc = guild.voice_client if guild is not None else None
            if isinstance(vc, wavelink.Player):
                try:
                    await vc.move_to(after.channel)
                except discord.ClientException as err:
                    t = self.bot.get_channel(session.channel.id)
                    if t is not None:
                        await t.send(f"could not follow {member.display_name}: {err}")
            else:
                await self._join_voice(session, member)
                await self._sync(session)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        print(f"Lavalink node {payload.node!r} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        if payload.player is None:
            return
        session = self.sessions.get(payload.player.guild.id)
        if session is not None and session.player is payload.player:
            await self._sync(session)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        if payload.player is None:
            return
        session = self.sessions.get(payload.player.guild.id)
        if session is not None and session.player is payload.player:
            await self._sync(session)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload) -> None:
        if payload.player is None:
            return
        print(f"Track stuck on {payload.player.guild.id}: {payload.track!r}")
        try:
            await payload.player.skip(force=True)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        if payload.player is None:
            return
        print(f"Track exception on {payload.player.guild.id}: {payload.exception}")
        try:
            await payload.player.skip(force=True)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: wavelink.NodeDisconnectedEventPayload) -> None:
        print(f"Lavalink node {payload.node!r} disconnected!")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StalkerPlayer(bot))