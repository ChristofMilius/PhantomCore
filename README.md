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
- **Hermes agent channel** — an admin-only `hermes_agent` text channel under
  `bot-section`, reserved for exchanging hermes-agent context. Separate from
  the LLM module; auto-created with the rest of the structure.
- **Extension management** — load/unload/reload cogs at runtime and a
  `/helper` command that posts one embed per cog with load/unload/reload
  buttons into the status channel.
- **StalkerPlayer** (`stalker_player`) — a music player panel driven by
  buttons. Auto-boots a local [Lavalink] 4 server with the youtube plugin and
  plays/pauses/skips/loops tracks, stalking a chosen user across voice
  channels with optional claimable control.
- **Commit watcher** (`commit_watcher`) — polls the `origin/main` remote and
  posts each newly pushed commit to the `development` → `updates` channel as
  an embed whose author line names the source repo (so a shared `#updates`
  stays attributed across multiple remotes).

## Setup

1. **Create the bot** at https://discord.com/developers/applications and copy
   its token.
2. **Configure** channels: the desired server structure lives in
   `channel_config.json` (repo root) — a `bot-section` category with
   `bot_chatter`, `bot_status`, `stalker_player` and the admin-only
   `hermes_agent`, plus the lobby categories (`dynamic_voice_lobby`,
   `dynamic_chat_lobby`, "Voice Lobby Template" with its join channel).
   Everything in this file is auto-created when missing; the
   only manual step is copying the ids Discord assigns to `bot_chatter` and
   `bot_status` into the corresponding `.env` entries (`BOT_CHATTER`,
   `BOT_STATUS`), and `stalker_player` into `STALKER_CHANNEL`.

   Auto-creation is re-checked on every boot (and each reconnect), so a
   category or channel deleted while the bot was offline is restored
   automatically, IDs included. Type is enforced too: if a channel exists
   under a configured name but with the wrong kind (e.g. a text channel
   where the config declares `voice`), it is not left in place to block the
   intended channel — it is renamed to `<name>-archived-<HHMMSS>` (history
   preserved) and the correct type is created fresh.
3. **Copy** `.env.example` to `.env` and fill in the values.

## StalkerPlayer / Lavalink

The music player needs a Lavalink server. The bot can boot its own:

- Place `Lavalink.jar` (v4) into `lavalink/` — the bundled config
  `lavalink/application.yml` enables the youtube plugin.
  **Use Lavalink 4.1.7 or newer.** 4.0.0 (bundled with the repo in the past)
  predates Discord's current voice-server handling: tracks load and "play", but
  no audio reaches the channel. The jar is gitignored (local-only); keep
  4.1.7+ in `lavalink/Lavalink.jar`.
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

### Launcher shim (`pcore.cmd`)

`pcore.cmd` is a single portable launcher that runs the bot as a detached
background process with no console window and manages its lifecycle. It
self-detects its install location: a copy living in `%USERPROFILE%\bin` (a
PATH-accessible bin folder) resolves the project from a `PHANTOMCORE_ROOT`
placeholder near the top of the file — replace that one line with the real
project root once, on install. A copy anywhere else uses `%~dp0`, so the repo
can live or move anywhere and the same file can be copied into a bin folder
unmodified apart from that single edit.

| Command              | Effect                                                            |
| -------------------- | ----------------------------------------------------------------- |
| `pcore` / `pcore start` | Start the bot hidden in the background; stdout/stderr land in `data\bot.stdout_HHMMSS.log` and `data\bot.stderr_HHMMSS.log` |
| `pcore stop`         | Stop the bot and any Lavalink server it spawned                   |
| `pcore status`       | Report whether the bot is running                                 |
| `pcore logs`         | Print the most recent bot output log                             |

## Dependencies & security

Dependencies keep loose `>=` minimum constraints in `pyproject.toml` so pip
resolution stays forward-compatible. All pinned versions are currently the
latest release on PyPI and show no known CVEs at the pinned versions (checked
against the OSV database). The only routine maintenance is to refresh the lock
with

```powershell
uv lock && uv sync
```

## Env vars

| Variable            | Required | Description                                    |
| ------------------- | -------- | ---------------------------------------------- |
| `TOKEN`             | yes      | Discord bot token                              |
| `GUILD_ID`          | yes      | Server that the bot operates in                |
| `OWNER_ID`          | yes      | Bot owner (for owner-only commands)            |
| `BOT_ID`            | yes      | The bot's own user id                          |
| `BOT_CHATTER`       | yes      | Id of the bot chat channel (LM Studio + "Online" msg); auto-created via `channel_config.json`, fill in the assigned id |
| `BOT_STATUS`        | yes      | Id of the extension status channel; auto-created via `channel_config.json`, fill in the assigned id |
| `EXTENSIONS`        | no       | Comma-separated cogs to load (default: all core cogs) |
| `LMSTUDIO_HOST`     | no       | LM Studio endpoint, default `localhost:1234`   |
| `LMSTUDIO_MODEL`    | no       | Model id on the LM Studio server               |
| `SYSTEM_PROMPT`     | no       | System prompt used for LLM chat                |
| `LAVALINK_HOST`     | no       | Lavalink endpoint, default `127.0.0.1:7867`    |
| `LAVALINK_PASSWORD` | yes      | Lavalink server password (no default; injected into the booted server) |
| `JAVA_PATH`         | no       | Path to a Java 17+ `java.exe` for Lavalink     |
| `STALKER_CHANNEL`   | no       | Channel id for the music panel (default: the command channel); auto-created via `channel_config.json`, fill in the assigned id |
| `CLAIM_TIME`        | no       | Seconds to wait before control can change hands, default `300` |

## License

MIT

[LM Studio]: https://lmstudio.ai
[Lavalink]: https://github.com/lavalink-devs/Lavalink