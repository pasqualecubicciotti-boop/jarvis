"""Tutti i test usano chiavi FINTE e un client Claude simulato: nessuna rete, nessun costo."""
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from jarvis.agent import Agent
from jarvis.config import Settings
from jarvis.tools import Tool, ToolRegistry, build_default_tools
from jarvis.usage import UsageTracker

OWNER = 111


@pytest.fixture
def settings(tmp_path):
    return Settings(
        telegram_token="123456:FAKE-TOKEN",
        owner_id=OWNER,
        anthropic_api_key="sk-ant-FAKE",
        data_dir=tmp_path,
        daily_limit=5,
    )


def make_message(*blocks, stop_reason="end_turn") -> Message:
    return Message(
        id="msg_fake", type="message", role="assistant", model="claude-haiku-5-5",
        content=list(blocks), stop_reason=stop_reason, stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def text(t):
    return TextBlock(type="text", text=t)


def tool_use(name, input_, id="toolu_1"):
    return ToolUseBlock(type="tool_use", id=id, name=name, input=input_)


class FakeClient:
    """Imita AsyncAnthropic: restituisce risposte preparate e ricorda le richieste."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    async def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def usage(settings):
    return UsageTracker(settings.data_dir, settings.daily_limit)


@pytest.fixture
def sent():
    return []


@pytest.fixture
def registry(settings, sent):
    reg = build_default_tools(settings.data_dir, settings.timezone)
    risky = Tool(
        name="send_email",
        description="Invia una email (strumento di prova)",
        input_schema={"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]},
        func=lambda a: sent.append(a["to"]) or "Email inviata.",
        requires_confirmation=True,
        describe=lambda a: f"Inviare una email a {a['to']}",
    )
    return ToolRegistry([*reg._tools.values(), risky])


@pytest.fixture
def make_agent(settings, usage, registry):
    def _make(responses):
        client = FakeClient(responses)
        return Agent(settings, registry, usage, client=client), client
    return _make
