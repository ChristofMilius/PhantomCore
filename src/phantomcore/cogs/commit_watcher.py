from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from discord.utils import get

from phantomcore.settings import PROJECT_ROOT

logger = logging.getLogger("discord")

DEVELOPMENT_CATEGORY = "development"
UPDATES_CHANNEL = "updates"
_STATE_PATH = PROJECT_ROOT / "data" / "commits_seen.json"
_POLL_SECONDS = 60
_MAX_COMMITS_PER_POLL = 10


class CommitWatcher(commands.Cog, name="commit_watcher"):
    """Posts new pushed commits to the #updates channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_sha: str | None = None
        self._web_url = ""
        self._repo_name = ""

    async def cog_load(self) -> None:
        self._read_state()
        self._web_url = await self._repo_web_url()
        self._repo_name = self._repo_name_from_url(self._web_url)
        self.check_commits.start()

    async def cog_unload(self) -> None:
        self.check_commits.cancel()

    # -- helpers ----------------------------------------------------------

    def _read_state(self) -> None:
        try:
            with open(_STATE_PATH, encoding="utf-8") as f:
                self._last_sha = json.load(f).get("last_sha")
        except (OSError, ValueError):
            self._last_sha = None

    def _write_state(self) -> None:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"last_sha": self._last_sha}, f)
        except OSError as err:
            logger.warning("commit_watcher could not persist state: %s", err)

    async def _git(self, *args: str) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(PROJECT_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
        except OSError as err:
            logger.warning("commit_watcher could not run git: %s", err)
            return 1, ""
        text = (out or b"").decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            detail = (err or b"").decode("utf-8", errors="replace").strip()
            logger.warning("commit_watcher git %s failed: %s", args[0], detail)
        return proc.returncode, text

    async def _repo_web_url(self) -> str:
        code, remote = await self._git("remote", "get-url", "origin")
        if code != 0 or not remote:
            return ""
        path = remote.split("@")[-1]
        if path.endswith(".git"):
            path = path[:-4]
        return "https://" + path.replace(":", "/")

    @staticmethod
    def _repo_name_from_url(web_url: str) -> str:
        return web_url.rstrip("/").rsplit("/", 1)[-1] if web_url else ""

    def _commit_embed(
        self, sha: str, author: str, summary: str, tstamp: datetime | None
    ) -> discord.Embed:
        embed = discord.Embed(
            title=summary,
            colour=discord.Color.blurple(),
            url=f"{self._web_url}/commit/{sha}",
        )
        if self._repo_name:
            embed.set_author(name=self._repo_name)
        embed.set_footer(text=f"{self._web_url} · {sha[:7]}")
        if tstamp is not None:
            embed.timestamp = tstamp
        return embed

    # -- polling ----------------------------------------------------------

    @tasks.loop(seconds=_POLL_SECONDS)
    async def check_commits(self) -> None:
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(self.bot.settings.guild_id)
        if guild is None:
            return
        category = get(guild.categories, name=DEVELOPMENT_CATEGORY)
        if category is None:
            return
        updates = get(category.channels, name=UPDATES_CHANNEL)
        if updates is None:
            return

        await self._git("fetch", "origin")
        code, current = await self._git("rev-parse", "origin/main")
        if code != 0 or not current:
            return

        if self._last_sha is None:
            self._last_sha = current
            self._write_state()
            logger.info("commit_watcher seeded at %s", current)
            return

        if self._last_sha == current:
            return

        code, log = await self._git(
            "log",
            "--format=%H%x1f%an%x1f%aI%x1f%s",
            "--reverse",
            f"{self._last_sha}..{current}",
        )
        if code != 0:
            self._last_sha = current
            self._write_state()
            return

        commits = []
        for line in log.splitlines():
            if "\x1f" not in line:
                continue
            sha, author, iso, summary = line.split("\x1f", 3)
            if sha == self._last_sha:
                continue
            commits.append((sha, author, iso, summary))
            if len(commits) >= _MAX_COMMITS_PER_POLL:
                break

        self._last_sha = current
        self._write_state()

        for sha, author, iso, summary in commits:
            try:
                tstamp = datetime.fromisoformat(iso).astimezone(timezone.utc)
            except ValueError:
                tstamp = None
            await updates.send(embed=self._commit_embed(sha, author, summary, tstamp))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommitWatcher(bot))