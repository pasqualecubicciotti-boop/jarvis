"""Il "cervello": dialoga con Claude, esegue gli strumenti e chiede conferma quando serve."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .config import Settings
from .tools import ToolRegistry
from .usage import UsageTracker

log = logging.getLogger("jarvis.agent")

SYSTEM_PROMPT = (
    "Sei Jarvis, l'assistente personale del tuo unico utente, che parla con te su Telegram. "
    "Rispondi in italiano, in modo breve, chiaro e cordiale. "
    "Per sapere data e ora usa sempre lo strumento apposito, non indovinare. "
    "Se non sai o non puoi fare qualcosa, dillo onestamente. "
    "Le azioni che inviano, prenotano o pagano richiedono la conferma dell'utente: "
    "non aggirare mai questa regola."
)

MAX_HISTORY = 20  # messaggi ricordati
MAX_STEPS = 6  # giri massimi tra modello e strumenti per ogni messaggio


@dataclass
class Reply:
    text: str
    needs_confirmation: bool = False


@dataclass
class _Pending:
    block_ids: list[str]  # ordine originale dei tool_use
    results: dict[str, dict]  # tool_use_id -> tool_result gia' pronti
    queue: list[Any]  # tool_use che aspettano il sì/no


@dataclass
class _Chat:
    history: list[dict] = field(default_factory=list)
    pending: _Pending | None = None
    checkpoint: int = 0


class Agent:
    def __init__(
        self,
        settings: Settings,
        tools: ToolRegistry,
        usage: UsageTracker,
        client: Any | None = None,
    ):
        self.settings = settings
        self.tools = tools
        self.usage = usage
        self.client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._chats: dict[int, _Chat] = {}

    # ---- API pubblica -------------------------------------------------

    def has_pending(self, chat_id: int) -> bool:
        return self._chat(chat_id).pending is not None

    def reset(self, chat_id: int) -> None:
        self._chats.pop(chat_id, None)

    async def handle_message(self, chat_id: int, text: str) -> Reply:
        chat = self._chat(chat_id)
        if chat.pending:
            return self._ask_next(chat)
        self._trim(chat)
        chat.checkpoint = len(chat.history)
        chat.history.append({"role": "user", "content": text})
        return await self._loop(chat)

    async def resolve_confirmation(self, chat_id: int, approved: bool) -> Reply:
        chat = self._chat(chat_id)
        pending = chat.pending
        if not pending:
            return Reply("Non c'è nulla da confermare.")
        block = pending.queue.pop(0)
        tool = self.tools.get(block.name)
        if approved and tool:
            pending.results[block.id] = self._execute(tool, block)
        else:
            pending.results[block.id] = _result(block.id, "L'utente ha rifiutato questa azione.", True)
        if pending.queue:
            return self._ask_next(chat)
        chat.pending = None
        self._push_results(chat, pending.block_ids, pending.results)
        return await self._loop(chat)

    # ---- interno ------------------------------------------------------

    def _chat(self, chat_id: int) -> _Chat:
        return self._chats.setdefault(chat_id, _Chat())

    @staticmethod
    def _trim(chat: _Chat) -> None:
        """Tiene gli ultimi messaggi, ripartendo sempre da un messaggio testuale dell'utente."""
        if len(chat.history) <= MAX_HISTORY:
            return
        del chat.history[:-MAX_HISTORY]
        while chat.history and not (
            chat.history[0]["role"] == "user" and isinstance(chat.history[0]["content"], str)
        ):
            del chat.history[0]

    async def _loop(self, chat: _Chat) -> Reply:
        for _ in range(MAX_STEPS):
            if not self.usage.try_consume():
                self._rollback(chat)
                return Reply(
                    f"Ho raggiunto il limite di {self.usage.daily_limit} richieste per oggi. "
                    "Riprova domani (o alza JARVIS_DAILY_LIMIT)."
                )
            try:
                response = await self.client.messages.create(
                    model=self.settings.model,
                    max_tokens=self.settings.max_tokens,
                    system=SYSTEM_PROMPT,
                    tools=self.tools.to_api(),
                    messages=chat.history,
                    output_config={"effort": self.settings.effort},
                )
            except anthropic.APIError as exc:
                self.usage.record_error(f"{type(exc).__name__}: {exc}")
                self._rollback(chat)
                return Reply("Ho avuto un problema a contattare il modello. Riprova tra poco.")
            except Exception as exc:  # non far mai cadere il bot
                self.usage.record_error(f"{type(exc).__name__}: {exc}")
                self._rollback(chat)
                return Reply("Si è verificato un errore inatteso. L'ho registrato.")

            chat.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                reply = self._handle_tool_use(chat, response.content)
                if reply:
                    return reply
                continue

            text = "".join(b.text for b in response.content if b.type == "text").strip()
            if response.stop_reason == "refusal":
                text = text or "Non posso aiutarti con questa richiesta."
            elif response.stop_reason == "max_tokens":
                text = (text + "\n\n[risposta troncata: limite di lunghezza raggiunto]").strip()
            return Reply(text or "(nessuna risposta)")

        self.usage.record_error("Troppi giri di strumenti")
        self._rollback(chat)
        return Reply("Mi sono perso in troppi passaggi. Riprova con una richiesta più semplice.")

    def _handle_tool_use(self, chat: _Chat, content: list) -> Reply | None:
        blocks = [b for b in content if b.type == "tool_use"]
        results: dict[str, dict] = {}
        queue = []
        for block in blocks:
            tool = self.tools.get(block.name)
            if tool is None:
                results[block.id] = _result(block.id, f"Strumento sconosciuto: {block.name}", True)
            elif tool.requires_confirmation:
                queue.append(block)
            else:
                results[block.id] = self._execute(tool, block)
        ids = [b.id for b in blocks]
        if queue:
            chat.pending = _Pending(ids, results, queue)
            return self._ask_next(chat)
        self._push_results(chat, ids, results)
        return None

    def _execute(self, tool, block) -> dict:
        try:
            output = tool.func(block.input or {})
            return _result(block.id, output)
        except Exception as exc:
            self.usage.record_error(f"Strumento {tool.name}: {type(exc).__name__}: {exc}")
            return _result(block.id, f"Errore nello strumento: {exc}", True)

    def _ask_next(self, chat: _Chat) -> Reply:
        block = chat.pending.queue[0]
        tool = self.tools.get(block.name)
        what = tool.confirmation_text(block.input or {}) if tool else block.name
        return Reply(f"Vuoi che io proceda?\n\n{what}\n\nRispondi sì o no.", needs_confirmation=True)

    @staticmethod
    def _push_results(chat: _Chat, ids: list[str], results: dict[str, dict]) -> None:
        chat.history.append({"role": "user", "content": [results[i] for i in ids]})

    @staticmethod
    def _rollback(chat: _Chat) -> None:
        """Dopo un errore torna a prima del messaggio in corso, così la storia resta valida."""
        del chat.history[chat.checkpoint :]
        chat.pending = None


def _result(tool_use_id: str, content: str, is_error: bool = False) -> dict:
    result = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        result["is_error"] = True
    return result
