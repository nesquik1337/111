from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

from storage import Storage


load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment")


storage = Storage(os.getenv("BOT_DB_PATH", "bot.db"))
router = Router()
GAME_PRESETS = ["Dota 2", "CS2", "Valorant", "Apex Legends"]


class CreateRequestFlow(StatesGroup):
    choosing_game = State()
    entering_time = State()


def menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая заявка"), KeyboardButton(text="📋 Мои заявки")],
            [KeyboardButton(text="👥 Моя группа")],
        ],
        resize_keyboard=True,
    )


def game_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"game:{title}")] for title in GAME_PRESETS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def response_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Могу играть", callback_data=f"req:{request_id}:yes"),
                InlineKeyboardButton(text="Не могу", callback_data=f"req:{request_id}:no"),
            ]
        ]
    )


def requests_kb(request_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Заявка #{req_id}", callback_data=f"status:{req_id}")]
        for req_id in request_ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mention_or_name(username: str | None, full_name: str) -> str:
    return f"@{username}" if username else full_name


@router.message(CommandStart())
async def start(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    storage.upsert_user(user.id, user.username, user.full_name)
    await message.answer(
        "Привет! Я помогу собрать тиммейта для игры внутри твоей группы.\n\n"
        "Команды:\n"
        "/create_group <название> — создать группу\n"
        "/join_group <код> — вступить в группу\n"
        "/my_group — показать группу\n"
        "/new_request — создать заявку\n"
        "/my_requests — мои заявки и статусы\n",
        reply_markup=menu_kb(),
    )


@router.message(Command("create_group"))
async def create_group(message: Message, command: CommandObject) -> None:
    user = message.from_user
    if user is None:
        return

    storage.upsert_user(user.id, user.username, user.full_name)
    group_name = (command.args or "").strip()
    if not group_name:
        await message.answer("Использование: /create_group <название группы>")
        return

    group = storage.create_group(user.id, group_name)
    await message.answer(
        f"Группа создана: {group.name}\n"
        f"Код приглашения: `{group.invite_code}`\n"
        "Отправь код друзьям: /join_group <код>",
        parse_mode="Markdown",
    )


@router.message(Command("join_group"))
async def join_group(message: Message, command: CommandObject) -> None:
    user = message.from_user
    if user is None:
        return

    storage.upsert_user(user.id, user.username, user.full_name)
    invite_code = (command.args or "").strip()
    if not invite_code:
        await message.answer("Использование: /join_group <код приглашения>")
        return

    group = storage.join_group(user.id, invite_code)
    if group is None:
        await message.answer("Группа с таким кодом не найдена.")
        return

    await message.answer(f"Ты вступил в группу: {group.name}")


@router.message(Command("my_group"))
@router.message(F.text == "👥 Моя группа")
async def my_group(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    storage.upsert_user(user.id, user.username, user.full_name)
    db_user = storage.get_user(user.id)
    if db_user is None or db_user.group_id is None:
        await message.answer("Ты пока не в группе. Создай /create_group или вступи /join_group")
        return

    group = storage.get_group(db_user.group_id)
    if group is None:
        await message.answer("Группа не найдена, создай новую /create_group")
        return

    await message.answer(f"Твоя группа: {group.name}\nКод приглашения: `{group.invite_code}`", parse_mode="Markdown")


@router.message(Command("new_request"))
@router.message(F.text == "➕ Новая заявка")
        "Привет! Я помогу собрать тиммейта для игры.\n\n"
        "Команды:\n"
        "/new_request — создать заявку\n"
        "/my_requests — мои последние заявки и статусы\n"
    )


@router.message(Command("new_request"))
async def new_request(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None:
        return

    storage.upsert_user(user.id, user.username, user.full_name)
    db_user = storage.get_user(user.id)
    if db_user is None or db_user.group_id is None:
        await message.answer("Сначала нужно быть в группе: /create_group или /join_group")
        return

    await state.set_state(CreateRequestFlow.choosing_game)
    await message.answer(
        "Выбери игру кнопкой ниже или напиши свою:",
        reply_markup=game_kb(),
    )


@router.callback_query(F.data.startswith("game:"))
async def choose_game_from_button(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None:
        return
    game = callback.data.split(":", maxsplit=1)[1]
    await state.update_data(game=game)
    await state.set_state(CreateRequestFlow.entering_time)
    await callback.answer("Игра выбрана")
    await callback.message.reply(f"Игра: {game}\nТеперь укажи время (например: Сегодня 21:30).")
    await state.set_state(CreateRequestFlow.choosing_game)
    await message.answer("Какую игру ищешь? Напиши название (например: Dota 2, CS2, Valorant).")


@router.message(CreateRequestFlow.choosing_game)
async def chosen_game(message: Message, state: FSMContext) -> None:
    game = (message.text or "").strip()
    if not game:
        await message.answer("Название игры пустое. Попробуй ещё раз.")
        return
    await state.update_data(game=game)
    await state.set_state(CreateRequestFlow.entering_time)
    await message.answer("На какое время планируешь игру? Пример: Сегодня 21:30.")


@router.message(CreateRequestFlow.entering_time)
async def entered_time(message: Message, state: FSMContext, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return

    play_time = (message.text or "").strip()
    if not play_time:
        await message.answer("Время пустое. Попробуй ещё раз.")
        return

    data = await state.get_data()
    game = data.get("game")
    if not isinstance(game, str):
        await message.answer("Сценарий сбился. Нажми /new_request и начни заново.")
        await state.clear()
        return

    db_user = storage.get_user(user.id)
    if db_user is None or db_user.group_id is None:
        await message.answer("Ты не в группе. Нажми /my_group и проверь статус.")
        await state.clear()
        return

    request_id = storage.create_request(user.id, game, play_time)
    await state.clear()

    creator_label = mention_or_name(user.username, user.full_name)
    request_id = storage.create_request(user.id, game, play_time)
    await state.clear()

    creator = storage.get_user(user.id)
    creator_label = mention_or_name(creator.username if creator else user.username, user.full_name)
    text = (
        f"🎮 Новая заявка #{request_id}\n"
        f"Кто: {creator_label}\n"
        f"Игра: {game}\n"
        f"Когда: {play_time}\n\n"
        "Сможешь присоединиться?"
    )

    recipients = storage.get_other_users_in_same_group(user.id)
    recipients = storage.get_other_users(user.id)
    sent_count = 0
    for recipient in recipients:
        try:
            await bot.send_message(recipient.user_id, text, reply_markup=response_kb(request_id))
            sent_count += 1
        except TelegramBadRequest:
            continue

    await message.answer(
        f"Заявка #{request_id} создана в группе. Уведомления отправлены: {sent_count}.\n"
        f"Заявка #{request_id} создана. Уведомления отправлены: {sent_count} пользователям.\n"
        "Проверить ответы: /my_requests"
    )


@router.callback_query(F.data.startswith("req:"))
async def handle_response(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user is None or callback.data is None:
        return

    _, request_id_str, response = callback.data.split(":", maxsplit=2)
    request_id = int(request_id_str)

    req = storage.get_request(request_id)
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    user = storage.get_user(callback.from_user.id)
    if user is None or user.group_id is None or user.group_id != req.creator_group_id:
        await callback.answer("Эта заявка не из твоей группы", show_alert=True)
        return

    storage.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
    storage.save_response(request_id, callback.from_user.id, response)

    response_human = "✅ Могу играть" if response == "yes" else "❌ Не могу"
    await callback.answer("Ответ сохранён")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=response_kb(request_id))
        await callback.message.reply(f"Твой ответ по заявке #{request_id}: {response_human}")

    responses = storage.get_request_responses(request_id)
    yes = [r.full_name for r in responses if r.response == "yes"]
    no = [r.full_name for r in responses if r.response == "no"]

    status_text = (
        f"📊 Обновление по заявке #{request_id}\n"
        f"Игра: {req.game}\nКогда: {req.play_time}\n\n"
        f"✅ Могут: {', '.join(yes) if yes else 'пока нет'}\n"
        f"❌ Не могут: {', '.join(no) if no else 'пока нет'}"
    )

    try:
        await bot.send_message(req.creator_id, status_text)
    except TelegramBadRequest:
        pass


@router.message(Command("my_requests"))
@router.message(F.text == "📋 Мои заявки")
async def my_requests(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    storage.upsert_user(user.id, user.username, user.full_name)
    requests = storage.get_creator_requests(user.id, limit=10)
    if not requests:
        await message.answer("У тебя пока нет заявок. Создать: /new_request")
        return

    await message.answer(
        "Выбери заявку, чтобы посмотреть текущие ответы:",
        reply_markup=requests_kb([req.id for req in requests]),
    )


@router.callback_query(F.data.startswith("status:"))
async def request_status(callback: CallbackQuery) -> None:
    if callback.data is None:
        return

    request_id = int(callback.data.split(":", maxsplit=1)[1])
    req = storage.get_request(request_id)
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if callback.from_user is None or callback.from_user.id != req.creator_id:
        await callback.answer("Эта заявка тебе недоступна", show_alert=True)
        return

    responses = storage.get_request_responses(request_id)
    yes = [mention_or_name(r.username, r.full_name) for r in responses if r.response == "yes"]
    no = [mention_or_name(r.username, r.full_name) for r in responses if r.response == "no"]

    text = (
        f"📋 Заявка #{request_id}\n"
        f"Игра: {req.game}\n"
        f"Время: {req.play_time}\n\n"
        f"✅ Могу играть: {', '.join(yes) if yes else 'пока нет'}\n"
        f"❌ Не могу: {', '.join(no) if no else 'пока нет'}"
    )
    await callback.answer()
    await callback.message.reply(text)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    dp = Dispatcher()
    dp.include_router(router)

    bot = Bot(TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
