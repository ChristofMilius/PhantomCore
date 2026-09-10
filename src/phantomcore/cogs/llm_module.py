from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import discord
from discord.ext import commands

from phantomcore.settings import Settings

# LM Studio splices reasoning and the final answer into the raw stream content
# with an internal separator: <reasoning>__LM_STUDIO_INTERNAL_LSEP_SYNTHETIC_REASONING_END_<tag>__<answer>
_REASONING_SEP = re.compile(r"__LM_STUDIO_INTERNAL_LSEP_SYNTHETIC_REASONING_END_[\w-]+__")


def strip_reasoning(raw: str) -> str:
    match = _REASONING_SEP.search(raw)
    if match:
        return raw[match.end() :].strip()
    return raw.strip()


class LLMModule(commands.Cog, name="llm_module"):
    """Chat with a local LM Studio inference server in the bot channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings: Settings = bot.settings
        self.settings.chat_history_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._model = None
        self.chat_history: dict[int, list[dict]] = {}
        self.max_length = 2000

    @property
    def bot_channel(self) -> discord.TextChannel | None:
        # Resolved lazily: channels are only cached after the bot is ready.
        return self.bot.get_channel(self.settings.bot_channel_id)

    def _load_model(self):
        import lmstudio as lms

        if self._model is None:
            self._client = lms.Client(self.settings.lmstudio_host)
            self._model = self._client.llm.model(
                self.settings.lmstudio_model, config=self.settings.lmstudio_model_config
            )
        return self._model

    # --- mention + memory helpers -------------------------------------------

    async def is_bot_mentioned(self, message: discord.Message) -> bool:
        bot_member = message.guild.get_member(self.bot.user.id)
        if bot_member is None:
            return False
        bot_roles = [role for role in bot_member.roles if role != message.guild.default_role]

        if self.bot.user.mentioned_in(message):
            return True
        for role in bot_roles:
            if message.content.startswith(f"<@&{role.id}>"):
                return True
        return False

    def _history_path(self, user_id: int) -> Path:
        return self.settings.chat_history_dir / f"user_{user_id}.json"

    async def load_chat_history(self, user_id: int) -> None:
        file_path = self._history_path(user_id)
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                self.chat_history[user_id] = [
                    msg
                    for msg in history
                    if not _REASONING_SEP.search(msg.get("content", ""))
                ]
            else:
                self.chat_history[user_id] = [
                    {"role": "system", "content": self.settings.system_prompt}
                ]
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load chat history for user {user_id}: {e}")
            self.chat_history[user_id] = [
                {"role": "system", "content": self.settings.system_prompt}
            ]

    async def save_chat_history(self, user_id: int) -> None:
        try:
            with open(self._history_path(user_id), "w", encoding="utf-8") as f:
                json.dump(self.chat_history[user_id], f, indent=2)
        except Exception as e:
            print(f"Error saving chat history for user {user_id}: {e}")

    # --- response generation -------------------------------------------------

    async def generate_response(self, user_id: int, message: discord.Message) -> str:
        if user_id not in self.chat_history:
            await self.load_chat_history(user_id)

        self.chat_history[user_id].append(
            {"role": "user", "content": f"{message.author.display_name}: {message.content}"}
        )

        conversation_lines = []
        for msg in self.chat_history[user_id]:
            role = msg.get("role", "user")
            label = {"user": "User", "assistant": "Assistant", "system": "System"}.get(role, "User")
            conversation_lines.append(f"{label}: {msg['content']}")
        conversation = "\n".join(conversation_lines)

        try:
            response_content = await asyncio.to_thread(self._respond, conversation)
        except Exception as e:
            print(f"Error generating response: {e}")
            response_content = f"Sorry, I encountered an error processing your request: {e}"

        self.chat_history[user_id].append({"role": "assistant", "content": response_content})
        await self.save_chat_history(user_id)

        return response_content

    def _respond(self, conversation: str) -> str:
        model = self._load_model()
        result = model.respond(conversation, config=self.settings.lmstudio_chat_config)
        raw = result.content if hasattr(result, "content") else str(result)
        return strip_reasoning(raw)

    # --- message sending -----------------------------------------------------

    async def chunk_text(self, text: str) -> list[str]:
        if len(text) <= self.max_length:
            return [text]

        chunks = []
        while text:
            if len(text) <= self.max_length:
                chunks.append(text)
                break

            chunk = text[: self.max_length]
            last_space = chunk.rfind(" ")
            if last_space == -1:
                chunks.append(text[: self.max_length])
                text = text[self.max_length :]
            else:
                chunks.append(text[:last_space])
                text = text[last_space:].lstrip()
        return chunks

    async def send_chunked_response(self, message: discord.Message, response: str) -> None:
        for chunk in await self.chunk_text(response):
            await message.channel.send(chunk)

    # --- listener ------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel != self.bot_channel:
            return
        if message.author == self.bot.user:
            return
        if await self.is_bot_mentioned(message):
            async with message.channel.typing():
                response = await self.generate_response(message.author.id, message)
                await self.send_chunked_response(message, response)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LLMModule(bot))