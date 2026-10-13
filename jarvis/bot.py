"""Collegamento con Telegram. Risponde solo al proprietario; tutti gli altri sono ignorati."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import Agent, Reply
from .config import Settings

log = logging.getLogger("jarvis.bot")

YES = {"si", "sì", "s", "yes", "y", "ok", "certo", "confermo"}
NO = {"no", "n", "annulla", "stop"}
TELEGRAM_LIMIT = 4000


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Sì", callback_data="confirm:yes"),
          InlineKeyboardButton("❌ No", callback_data="confirm:no")]]
    )


def _chunks(text: str) -> list[str]:
    return [text[i : i + TELEGRAM_LIMIT] for i in range(0, len(text), TELEGRAM_LIMIT)] or [""]


async def _send(bot, chat_id: int, reply: Reply) -> None:
    parts = _chunks(reply.text)
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        markup = _keyboard() if (reply.needs_confirmation and last) else None
        await bot.send_message(chat_id=chat_id, text=part, reply_markup=markup)


class JarvisBot:
    def __init__(self, settings: Settings, agent: Agent):
        self.settings = settings
        self.agent = agent

    def build_application(self) -> Application:
        app = Application.builder().token(self.settings.telegram_token).build()
        # Il filtro sull'ID utente fa si' che chiunque altro non riceva alcuna risposta.
        owner = filters.User(user_id=self.settings.owner_id) & filters.ChatType.PRIVATE
        app.add_handler(CommandHandler("start", self.on_start, filters=owner))
        app.add_handler(CommandHandler("nuova", self.on_reset, filters=owner))
        app.add_handler(CommandHandler("stato", self.on_status, filters=owner))
        app.add_handler(MessageHandler(owner & filters.TEXT & ~filters.COMMAND, self.on_text))
        app.add_handler(
            CallbackQueryHandler(self.on_button, pattern="^confirm:(yes|no)$")
        )
        app.add_error_handler(self.on_error)
        return app

    async def on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            "Ciao, sono Jarvis. Scrivimi quello che ti serve.\n"
            "/nuova – dimentica la conversazione\n/stato – richieste di oggi"
        )

    async def on_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.agent.reset(update.effective_chat.id)
        await update.effective_message.reply_text("Fatto, ho dimenticato la conversazione.")

    async def on_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = self.agent.usage.today()
        await update.effective_message.reply_text(
            f"Oggi: {today['requests']}/{self.agent.usage.daily_limit} richieste, "
            f"{today['errors']} errori. Modello: {self.settings.model}."
        )

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        text = update.effective_message.text.strip()
        if self.agent.has_pending(chat_id):
            word = text.lower().strip(" .!")
            if word in YES or word in NO:
                reply = await self.agent.resolve_confirmation(chat_id, word in YES)
            else:
                reply = await self.agent.handle_message(chat_id, text)  # richiede di nuovo il sì/no
        else:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            reply = await self.agent.handle_message(chat_id, text)
        await _send(context.bot, chat_id, reply)

    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query.from_user.id != self.settings.owner_id:
            return  # ignorato in silenzio
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)
        reply = await self.agent.resolve_confirmation(
            query.message.chat_id, query.data == "confirm:yes"
        )
        await _send(context.bot, query.message.chat_id, reply)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.agent.usage.record_error(f"Telegram: {type(context.error).__name__}: {context.error}")
