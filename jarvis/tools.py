"""Strumenti che Jarvis puo' usare.

Ogni strumento che invia, prenota o paga deve essere creato con
requires_confirmation=True: Jarvis non lo esegue finche' non rispondi "si'".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .memory import MemoryStore
from .reminders import ReminderStore

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


def build_default_tools(
    data_dir: Path,
    timezone: str,
    store: ReminderStore | None = None,
    memory: MemoryStore | None = None,
) -> ToolRegistry:
    tz = ZoneInfo(timezone)
    store = store or ReminderStore(data_dir, timezone)
    memory = memory or MemoryStore(data_dir, timezone)

    def remember(args: dict) -> str:
        item, is_new = memory.add(str(args.get("text", "")))
        return f"Appunto salvato (id {item['id']})." if is_new else f"Lo sapevo già (id {item['id']})."

    def list_memories(_: dict) -> str:
        items = memory.all()
        if not items:
            return "Nessun appunto salvato."
        return "\n".join(f"- ({it['id']}) {it['text']}" for it in items)

    def forget(args: dict) -> str:
        fid = str(args.get("id", "")).strip()
        return "Appunto dimenticato." if memory.forget(fid) else f"Nessun appunto con id {fid}."

    def describe_forget(args: dict) -> str:
        it = memory.get(str(args.get("id", "")).strip())
        return f"Dimenticare l'appunto: «{it['text']}»" if it else "Dimenticare un appunto (id non trovato)"

    def get_datetime(_: dict) -> str:
        now = datetime.now(tz)
        return f"{GIORNI[now.weekday()]} {now:%d/%m/%Y %H:%M} (fuso {timezone})"

    def save_reminder(args: dict) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            raise ValueError("Il testo del promemoria è vuoto")
        due = None
        raw_due = str(args.get("due", "")).strip()
        if raw_due:
            try:
                due = datetime.fromisoformat(raw_due)
            except ValueError:
                raise ValueError("Formato di 'due' non valido: usa AAAA-MM-GGTHH:MM") from None
            if due.tzinfo is None:
                due = due.replace(tzinfo=tz)
            if due < store.now() - timedelta(minutes=1):
                raise ValueError("L'orario indicato è già passato")
        item = store.add(text, str(args.get("when", "")).strip(), due)
        if due:
            return f"Promemoria salvato (id {item['id']}). Scriverò all'utente il {due:%d/%m/%Y alle %H:%M}."
        return f"Promemoria salvato senza orario preciso (id {item['id']}): non scriverò all'utente."

    def list_reminders(_: dict) -> str:
        items = store.all()
        if not items:
            return "Nessun promemoria salvato."
        lines = []
        for it in items:
            if it.get("due"):
                when = f" [{datetime.fromisoformat(it['due']):%d/%m/%Y %H:%M}]"
            elif it.get("when"):
                when = f" [{it['when']}]"
            else:
                when = ""
            state = " (già comunicato)" if it.get("done") else ""
            lines.append(f"- ({it['id']}){when} {it['text']}{state}")
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
                description=(
                    "Salva un promemoria. Se passi 'due' (data e ora precise), Jarvis scrive all'utente su Telegram a quell'ora. "
                    "Se l'utente chiede un orario ('domani alle 9'), calcola la data esatta e passala in 'due'."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Cosa ricordare"},
                        "due": {
                            "type": "string",
                            "description": "Data e ora esatte, fuso orario dell'utente, formato AAAA-MM-GGTHH:MM (es. 2026-10-15T09:00). Facoltativo.",
                        },
                        "when": {"type": "string", "description": "Orario in parole libere, solo se 'due' non è possibile. Facoltativo."},
                    },
                    "required": ["text"],
                },
                func=save_reminder,
            ),
            Tool(
                name="remember",
                description=(
                    "Salva un appunto duraturo sull'utente (preferenze, obiettivi, progetti, fatti stabili). "
                    "Usalo quando l'utente chiede di ricordare qualcosa o condivide un'informazione importante che servirà in futuro. "
                    "Scrivi l'appunto in una frase breve e autonoma. Non salvare dati sensibili (password, chiavi, numeri di carta)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "L'appunto, una frase breve"}},
                    "required": ["text"],
                },
                func=remember,
            ),
            Tool(
                name="list_memories",
                description="Elenca gli appunti salvati sull'utente, con il loro id.",
                input_schema={"type": "object", "properties": {}},
                func=list_memories,
            ),
            Tool(
                name="forget",
                description="Cancella un appunto salvato, dato il suo id (vedi list_memories). L'utente deve confermare.",
                input_schema={
                    "type": "object",
                    "properties": {"id": {"type": "string", "description": "id dell'appunto"}},
                    "required": ["id"],
                },
                func=forget,
                requires_confirmation=True,
                describe=describe_forget,
            ),
            Tool(
                name="list_reminders",
                description="Elenca tutti i promemoria salvati.",
                input_schema={"type": "object", "properties": {}},
                func=list_reminders,
            ),
        ]
    )
