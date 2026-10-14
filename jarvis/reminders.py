"""Archivio dei promemoria (file JSON) con orari precisi, usato dagli strumenti e dall'avviso automatico."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class ReminderStore:
    def __init__(self, data_dir: Path, timezone: str):
        self.path = Path(data_dir) / "reminders.json"
        self.tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def all(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, text: str, when: str = "", due: datetime | None = None) -> dict:
        items = self.all()
        item = {
            "id": uuid.uuid4().hex[:6],
            "text": text,
            "when": when,
            "due": due.isoformat(timespec="minutes") if due else None,
            "done": False,
            "created": self.now().isoformat(timespec="minutes"),
        }
        items.append(item)
        self._save(items)
        return item

    def due(self, now: datetime | None = None) -> list[dict]:
        """Promemoria con orario scaduto e non ancora comunicati."""
        now = now or self.now()
        result = []
        for it in self.all():
            if it.get("done") or not it.get("due"):
                continue
            when = datetime.fromisoformat(it["due"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=self.tz)
            if when <= now:
                result.append(it)
        return result

    def mark_done(self, reminder_id: str) -> None:
        items = self.all()
        for it in items:
            if it["id"] == reminder_id:
                it["done"] = True
        self._save(items)
