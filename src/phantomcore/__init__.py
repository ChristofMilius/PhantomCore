from __future__ import annotations

from phantomcore.bot import PhantomBot
from phantomcore.settings import get_settings


def main() -> None:
    settings = get_settings()
    bot = PhantomBot(settings)
    bot.run(settings.token)