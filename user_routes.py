from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from states import Register
from keyboards import main_menu
import logging

# Use global DB cursor/connection
from main import cur, conn

router = Router()

@router.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    try:
        row = cur.execute("SELECT balance FROM users WHERE user_id=?", (m.from_user.id,)).fetchone()

        if row:
            balance = row[0] or 0
            await m.answer(
                f"👋 Welcome back!\n💰 Balance: ₹{balance:.2f}",
                reply_markup=main_menu(balance)
            )
            await state.clear()
        else:
            await m.answer("👋 Welcome! Please enter your full name:")
            await state.set_state(Register.name)

    except Exception as e:
        logging.exception("Error in /start")
        await m.answer("⚠️ An error occurred. Please try again later.")

@router.message(Register.name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await m.answer("📞 Please enter your phone number:")
    await state.set_state(Register.phone)

@router.message(Register.phone)
async def reg_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    phone = m.text.strip()

    try:
        cur.execute(
            "INSERT OR IGNORE INTO users(user_id, name, phone) VALUES (?, ?, ?)",
            (m.from_user.id, name, phone)
        )
        conn.commit()

        row = cur.execute("SELECT balance FROM users WHERE user_id=?", (m.from_user.id,)).fetchone()
        balance = row[0] if row else 0

        await m.answer("✅ Registration complete!", reply_markup=main_menu(balance))
        await state.clear()

    except Exception as e:
        logging.exception("Registration error")
        await m.answer("⚠️ Registration failed. Please try again.")
        await state.clear()
