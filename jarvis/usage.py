"""Registro semplice: richieste ed errori del giorno, con limite giornaliero."""
from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("jarvis.usage")


def setup_logging(data_dir: Path) -> None:
    """Scrive il registro su data/jarvis.log (ruotato) e sul terminale."""
    data_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        data_dir / "jarvis.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(console)
    # Evita che le librerie scrivano il token del bot negli URL registrati.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)


class UsageTracker:
    """Conta richieste ed errori per giorno in data/usage.json."""

    def __init__(self, data_dir: Path, daily_limit: int, timezone: str = "Europe/Rome"):
        self.path = Path(data_dir) / "usage.json"
        self.daily_limit = daily_limit
        self.tz = ZoneInfo(timezone)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _today(self) -> str:
        return datetime.now(self.tz).date().isoformat()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        # Tieni solo gli ultimi 60 giorni.
        for old in sorted(data)[:-60]:
            del data[old]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def today(self) -> dict:
        return self._load().get(self._today(), {"requests": 0, "errors": 0})

    def try_consume(self) -> bool:
        """Registra una richiesta al modello. False se il limite di oggi e' raggiunto."""
        data = self._load()
        day = data.setdefault(self._today(), {"requests": 0, "errors": 0})
        if day["requests"] >= self.daily_limit:
            log.warning("Limite giornaliero raggiunto (%s)", self.daily_limit)
            return False
        day["requests"] += 1
        self._save(data)
        return True

    def record_error(self, what: str) -> None:
        data = self._load()
        day = data.setdefault(self._today(), {"requests": 0, "errors": 0})
        day["errors"] += 1
        self._save(data)
        log.error("Errore: %s", what)
