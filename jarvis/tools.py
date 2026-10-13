"""Strumenti che Jarvis puo' usare.

Ogni strumento che invia, prenota o paga deve essere creato con
requires_confirmation=True: Jarvis non lo esegue finche' non rispondi "si'".
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    func: Callable[[dict], str]
    requires_confirmation: bool = False
    # Testo mostrato nella domanda sì/no. Riceve gli argomenti dello strumento.
    describe: Callable[[dict], str] | None = None

    def to_api(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def confirmation_text(self, args: dict) -> str:
        if self.describe:
            return self.describe(args)
        return f"{self.name}: {json.dumps(args, ensure_ascii=False)}"


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def to_api(self) -> list[dict]:
        return [t.to_api() for t in self._tools.values()]


def build_default_tools(data_dir: Path, timezone: str) -> ToolRegistry:
    tz = ZoneInfo(timezone)
    reminders_file = Path(data_dir) / "reminders.json"

    def load() -> list[dict]:
        try:
            return json.loads(reminders_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_datetime(_: dict) -> str:
        now = datetime.now(tz)
        return f"{GIORNI[now.weekday()]} {now:%d/%m/%Y %H:%M} (fuso {timezone})"

    def save_reminder(args: dict) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            raise ValueError("Il testo del promemoria è vuoto")
        items = load()
        item = {
            "id": uuid.uuid4().hex[:6],
            "text": text,
            "when": str(args.get("when", "")).strip(),
            "created": datetime.now(tz).isoformat(timespec="minutes"),
        }
        items.append(item)
        reminders_file.parent.mkdir(parents=True, exist_ok=True)
        reminders_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"Promemoria salvato (id {item['id']})."

    def list_reminders(_: dict) -> str:
        items = load()
        if not items:
            return "Nessun promemoria salvato."
        lines = []
        for it in items:
            when = f" [{it['when']}]" if it.get("when") else ""
            lines.append(f"- ({it['id']}){when} {it['text']}")
        return "\n".join(lines)

    return ToolRegistry(
        [
            Tool(
                name="get_datetime",
                description="Restituisce la data e l'ora attuali. Usalo ogni volta che serve sapere che giorno o che ora è.",
                input_schema={"type": "object", "properties": {}},
                func=get_datetime,
            ),
            Tool(
                name="save_reminder",
                description="Salva un promemoria in un file. Non invia notifiche: serve solo a ricordare.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Cosa ricordare"},
                        "when": {
                            "type": "string",
                            "description": "Quando, in forma libera (es. 'domani alle 9'). Facoltativo.",
                        },
                    },
                    "required": ["text"],
                },
                func=save_reminder,
            ),
            Tool(
                name="list_reminders",
                description="Elenca tutti i promemoria salvati.",
                input_schema={"type": "object", "properties": {}},
                func=list_reminders,
            ),
        ]
    )
