"""Avvio: python -m jarvis"""
import os
import sys

from dotenv import load_dotenv

from .agent import Agent
from .bot import JarvisBot
from .config import ConfigError, Settings
from .tools import build_default_tools
from .usage import UsageTracker, setup_logging


def main() -> None:
    load_dotenv()
    try:
        settings = Settings.from_env(os.environ)
    except ConfigError as exc:
        sys.exit(f"Configurazione non valida: {exc}")

    setup_logging(settings.data_dir)
    usage = UsageTracker(settings.data_dir, settings.daily_limit, settings.timezone)
    tools = build_default_tools(settings.data_dir, settings.timezone)
    agent = Agent(settings, tools, usage)
    app = JarvisBot(settings, agent).build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
