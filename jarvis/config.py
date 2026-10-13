"""Lettura della configurazione dalle variabili d'ambiente (mai scritta nel codice)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_MODEL = "claude-haiku-5-5"
VALID_EFFORTS = ("low", "medium", "high")


class ConfigError(Exception):
    """Configurazione mancante o non valida."""


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    owner_id: int
    anthropic_api_key: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 1024
    effort: str = "low"
    daily_limit: int = 100
    timezone: str = "Europe/Rome"
    data_dir: Path = Path("data")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        def need(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise ConfigError(f"Manca la variabile {name} nel file .env")
            return value

        def number(name: str, default: int) -> int:
            raw = env.get(name, "").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                raise ConfigError(f"{name} deve essere un numero intero") from None
            if value <= 0:
                raise ConfigError(f"{name} deve essere maggiore di zero")
            return value

        try:
            owner_id = int(need("TELEGRAM_OWNER_ID"))
        except ValueError:
            raise ConfigError("TELEGRAM_OWNER_ID deve essere un numero") from None

        effort = env.get("JARVIS_EFFORT", "").strip() or "low"
        if effort not in VALID_EFFORTS:
            raise ConfigError(f"JARVIS_EFFORT deve essere uno tra: {', '.join(VALID_EFFORTS)}")

        return cls(
            telegram_token=need("TELEGRAM_BOT_TOKEN"),
            owner_id=owner_id,
            anthropic_api_key=need("ANTHROPIC_API_KEY"),
            model=env.get("JARVIS_MODEL", "").strip() or DEFAULT_MODEL,
            max_tokens=number("JARVIS_MAX_TOKENS", 1024),
            effort=effort,
            daily_limit=number("JARVIS_DAILY_LIMIT", 100),
            timezone=env.get("JARVIS_TIMEZONE", "").strip() or "Europe/Rome",
            data_dir=Path(env.get("JARVIS_DATA_DIR", "").strip() or "data"),
        )
