from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from conftest import make_message, text
from jarvis.bot import JarvisBot
from jarvis.reminders import ReminderStore
from jarvis.tools import build_default_tools


@pytest.fixture
def store(tmp_path):
    return ReminderStore(tmp_path, "Europe/Rome")


def iso(store, minutes):
    return (store.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def test_save_with_due_and_list(store):
    reg = build_default_tools(store.path.parent, "Europe/Rome", store)
    out = reg.get("save_reminder").func({"text": "Chiamare Anna", "due": iso(store, 60)})
    assert "Scriverò" in out
    assert "Chiamare Anna" in reg.get("list_reminders").func({})
    assert store.due() == []  # non ancora scaduto


def test_save_without_due_never_notifies(store):
    reg = build_default_tools(store.path.parent, "Europe/Rome", store)
    assert "non scriverò" in reg.get("save_reminder").func({"text": "idea", "when": "un giorno"})
    assert store.due(store.now() + timedelta(days=365)) == []


def test_past_or_invalid_due_rejected(store):
    reg = build_default_tools(store.path.parent, "Europe/Rome", store)
    with pytest.raises(ValueError):
        reg.get("save_reminder").func({"text": "x", "due": iso(store, -120)})
    with pytest.raises(ValueError):
        reg.get("save_reminder").func({"text": "x", "due": "domani"})


class FakeBot:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send_message(self, **kw):
        if self.fail:
            raise RuntimeError("rete assente")
        self.sent.append(kw)


async def test_due_reminder_sent_once_to_owner(settings, make_agent, store):
    agent, _ = make_agent([])
    bot = JarvisBot(settings, agent, store)
    store.add("Chiamare Anna", due=store.now() - timedelta(seconds=10))
    fake = FakeBot()
    ctx = SimpleNamespace(bot=fake)
    await bot.check_reminders(ctx)
    await bot.check_reminders(ctx)  # secondo giro: niente doppioni
    assert len(fake.sent) == 1
    assert fake.sent[0]["chat_id"] == settings.owner_id
    assert "Chiamare Anna" in fake.sent[0]["text"] and "ritardo" not in fake.sent[0]["text"]


async def test_late_reminder_is_flagged_and_failure_retries(settings, make_agent, store, usage):
    agent, _ = make_agent([])
    bot = JarvisBot(settings, agent, store)
    store.add("Vecchio", due=store.now() - timedelta(hours=2))
    await bot.check_reminders(SimpleNamespace(bot=FakeBot(fail=True)))
    assert usage.today()["errors"] == 1 and len(store.due()) == 1  # ancora da inviare
    ok = FakeBot()
    await bot.check_reminders(SimpleNamespace(bot=ok))
    assert "in ritardo" in ok.sent[0]["text"] and store.due() == []


def test_scheduler_registered_and_prompt_has_date(settings, make_agent, store):
    agent, _ = make_agent([])
    app = JarvisBot(settings, agent, store).build_application()
    assert app.job_queue is not None and len(app.job_queue.jobs()) == 1
    assert str(datetime.now().year) in agent._system()
