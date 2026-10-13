from datetime import datetime
from types import SimpleNamespace

from telegram import Chat, Message, Update, User
from telegram.ext import MessageHandler

from conftest import OWNER, make_message, text
from jarvis.bot import JarvisBot


def make_update(user_id, body="ciao"):
    user = User(id=user_id, first_name="T", is_bot=False)
    chat = Chat(id=user_id, type="private")
    msg = Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text=body)
    return Update(update_id=1, message=msg)


def accepting_handlers(app, update):
    return [h for h in app.handlers[0] if h.check_update(update)]


def test_only_owner_is_served(settings, make_agent):
    agent, _ = make_agent([])
    app = JarvisBot(settings, agent).build_application()
    assert accepting_handlers(app, make_update(OWNER))
    assert accepting_handlers(app, make_update(999)) == []
    assert accepting_handlers(app, make_update(999, "/start")) == []


async def test_owner_text_flow_and_button_from_stranger_ignored(settings, make_agent):
    agent, client = make_agent([make_message(text("Ciao!"))])
    bot = JarvisBot(settings, agent)
    sent = []

    class FakeBot:
        async def send_message(self, **kw): sent.append(kw)
        async def send_chat_action(self, **kw): pass

    ctx = SimpleNamespace(bot=FakeBot())
    await bot.on_text(make_update(OWNER), ctx)
    assert sent[0]["text"] == "Ciao!"

    stranger_query = SimpleNamespace(from_user=SimpleNamespace(id=999), data="confirm:yes")
    await bot.on_button(SimpleNamespace(callback_query=stranger_query), ctx)
    assert len(sent) == 1
