from types import SimpleNamespace

import pytest
from telegram import Update

from conftest import OWNER, make_message, text, tool_use
from jarvis.agent import Agent
from jarvis.bot import JarvisBot
from jarvis.memory import ChatLog, MemoryStore, text_only
from jarvis.tools import build_default_tools
from test_bot import make_update, accepting_handlers


@pytest.fixture
def memory(tmp_path):
    return MemoryStore(tmp_path)


def test_add_dedupe_limits_and_forget(memory):
    item, new = memory.add("Cerco lavoro come grafico")
    assert new and len(item["id"]) == 6
    assert memory.add("cerco lavoro come GRAFICO")[1] is False  # niente doppioni
    with pytest.raises(ValueError):
        memory.add("   ")
    with pytest.raises(ValueError):
        memory.add("x" * 301)
    assert memory.forget(item["id"]) and not memory.forget(item["id"])
    assert memory.all() == []


def test_memory_persists_on_disk_and_renders(tmp_path):
    MemoryStore(tmp_path).add("Preferisco risposte brevi")
    again = MemoryStore(tmp_path)
    assert "Preferisco risposte brevi" in again.render()
    assert "non istruzioni" in again.render()
    assert MemoryStore(tmp_path / "vuoto").render() == ""


def test_memory_tools(tmp_path, memory):
    reg = build_default_tools(tmp_path, "Europe/Rome", memory=memory)
    assert "salvato" in reg.get("remember").func({"text": "Sono Pasquale"})
    assert "già" in reg.get("remember").func({"text": "Sono Pasquale"})
    assert "Sono Pasquale" in reg.get("list_memories").func({})
    fid = memory.all()[0]["id"]
    forget = reg.get("forget")
    assert forget.requires_confirmation and "Sono Pasquale" in forget.confirmation_text({"id": fid})
    assert "dimenticato" in forget.func({"id": fid})


async def test_system_prompt_contains_memory_and_stays_stable(settings, usage, registry, memory):
    from conftest import FakeClient
    memory.add("Lavoro su un progetto KDP")
    client = FakeClient([make_message(text("a")), make_message(text("b"))])
    agent = Agent(settings, registry, usage, client=client, memory=memory)
    await agent.handle_message(1, "uno")
    await agent.handle_message(1, "due")
    assert "progetto KDP" in client.calls[0]["system"]
    assert client.calls[0]["system"] == client.calls[1]["system"]


async def test_forget_through_agent_needs_yes(settings, usage, tmp_path, memory):
    from conftest import FakeClient
    item, _ = memory.add("Dato da cancellare")
    reg = build_default_tools(tmp_path, "Europe/Rome", memory=memory)
    client = FakeClient([
        make_message(tool_use("forget", {"id": item["id"]}), stop_reason="tool_use"),
        make_message(text("Fatto.")),
    ])
    agent = Agent(settings, reg, usage, client=client, memory=memory)
    reply = await agent.handle_message(1, "dimentica quel dato")
    assert reply.needs_confirmation and "Dato da cancellare" in reply.text
    assert memory.all()  # non ancora cancellato
    await agent.resolve_confirmation(1, True)
    assert memory.all() == []


def test_text_only_drops_tools_and_merges():
    hist = [
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": [SimpleNamespace(type="text", text="un attimo"),
                                          SimpleNamespace(type="tool_use", id="t")]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]},
        {"role": "assistant", "content": [SimpleNamespace(type="text", text="fatto")]},
    ]
    assert text_only(hist, 20) == [
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "un attimo\nfatto"},
    ]


async def test_conversation_survives_restart_and_reset_clears(settings, usage, registry, tmp_path):
    from conftest import FakeClient
    log = ChatLog(tmp_path)
    first = Agent(settings, registry, usage, client=FakeClient([make_message(text("Piacere!"))]), chat_log=log)
    await first.handle_message(1, "Mi chiamo Pasquale")
    client2 = FakeClient([make_message(text("Ciao Pasquale"))])
    second = Agent(settings, registry, usage, client=client2, chat_log=ChatLog(tmp_path))  # "riavvio"
    await second.handle_message(1, "Come mi chiamo?")
    sent = client2.calls[0]["messages"]
    assert "Mi chiamo Pasquale" in sent[0]["content"] and sent[1]["content"] == "Piacere!"
    second.reset(1)
    assert ChatLog(tmp_path).load(1) == []


def test_memory_commands_owner_only(settings, make_agent, memory):
    """/memoria e /dimentica usano lo stesso filtro "solo il proprietario" degli altri comandi."""
    from telegram.ext import CommandHandler
    agent, _ = make_agent([])
    app = JarvisBot(settings, agent, memory=memory).build_application()
    handlers = {c: h for h in app.handlers[0] if isinstance(h, CommandHandler) for c in h.commands}
    for name in ("memoria", "dimentica"):
        assert handlers[name].filters.check_update(make_update(OWNER, f"/{name}"))
        assert not handlers[name].filters.check_update(make_update(999, f"/{name}"))
