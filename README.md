# PhantomCore

A Discord bot for Phantom's server. Refactored from an earlier dynamic-lobby
Discord bot as a cleaner `src`-layout uv project with a fully extensible cog
architecture and a local LLM chat module.

## Features

- **Dynamic lobbies** (`dynamic_lobbies` / `listener_voice`) — when a user
  joins the "Voice Lobby Template" voice channel, a voice lobby + chat lobby +
  access role are created, tracked in SQLite, and cleaned up when empty.
- **Rename / purge / pull** utilities — rename your current voice channel,
  purge chat history or stale empty lobbies, and pull members into your
  channel with accept/reject buttons.
- **LLM chat** (`llm_module`) — @-mention the bot in #bot_channel to talk to a
  local [LM Studio] server. Per-user chat history is persisted to JSON.
- **Extension management** — load/unload/reload cogs at runtime and a
  `/helper` command that posts one embed per cog with load/unload/reload
  buttons into the status channel.
- **StalkerPlayer** (`stalker_player`) — a music player panel driven by
  buttons. Auto-boots a local [Lavalink] 4 server with the youtube plugin and
  plays/pauses/skips/loops tracks, stalking a chosen user across voice
  channels with optional claimable control.

## Setup

1. **Create the bot** at https://discord.com/developers/applications and copy
   its token.
2. **Configure** channels: create a `bot-section` category with a status
   channel and a bot channel. The lobby structure (`dynamic_voice_lobby` +
   `dynamic_chat_lobby` categories and the "Voice Lobby Template" category
   with a join channel) is created automatically by the lobby cogs on first
   start.
3. **Copy** `.env.example` to `.env` and fill in the values.

## StalkerPlayer / Lavalink

The music player needs a Lavalink server. The bot can boot its own:

- Place `Lavalink.jar` (v4) into `lavalink/` — the bundled config
  `lavalink/application.yml` enables the youtube plugin.
- Provide a portable Java 17+ JRE at `lavalink/jre/bin/java.exe`, or point
  `JAVA_PATH` at any Java 17+ `java.exe`.
- Run `\stalker` in Discord; the panel posts into the configured channel.
  Commands: `\stalker`, `\play <query>`, `\pause`, `\resume`, `\skip`,
  `\stop`, `\join`, `\leave`, `\stalk @user`, `\unstalk`.

## Usage

```powershell
uv run phantomcore
```

The console script is registered in `pyproject.toml`; you can also use
`uv run python -m phantomcore`.

## Env vars

| Variable            | Required | Description                                    |
| ------------------- | -------- | ---------------------------------------------- |
| `TOKEN`             | yes      | Discord bot token                              |
| `GUILD_ID`          | yes      | Server that the bot operates in                |
| `OWNER_ID`          | yes      | Bot owner (for owner-only commands)            |
| `BOT_ID`            | yes      | The bot's own user id                          |
| `BOT_CHANNEL`       | yes      | Id of the bot chat channel (LM Studio + "Online" msg) |
| `BOT_STATUS_CHANNEL`| yes      | Id of the extension status channel             |
| `EXTENSIONS`        | no       | Comma-separated cogs to load (default: all core cogs) |
| `LMSTUDIO_HOST`     | no       | LM Studio endpoint, default `localhost:1234`   |
| `LMSTUDIO_MODEL`    | no       | Model id on the LM Studio server               |
| `SYSTEM_PROMPT`     | no       | System prompt used for LLM chat                |
| `LAVALINK_HOST`     | no       | Lavalink endpoint, default `127.0.0.1:7867`    |
| `LAVALINK_PASSWORD` | yes      | Lavalink server password (no default; injected into the booted server) |
| `JAVA_PATH`         | no       | Path to a Java 17+ `java.exe` for Lavalink     |
| `STALKER_CHANNEL`   | no       | Channel id for the music panel (default: the command channel) |
| `CLAIM_TIME`        | no       | Seconds to wait before control can change hands, default `300` |

## License

MIT

[LM Studio]: https://lmstudio.ai
[Lavalink]: https://github.com/lavalink-devs/Lavalink