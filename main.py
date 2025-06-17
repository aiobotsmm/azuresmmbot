import asyncio
import logging
import sqlite3
import qrcode
import io
import math
import requests
import uvicorn
import os

from dotenv import load_dotenv
load_dotenv()  # ✅ Load from .env

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile, BufferedInputFile
)
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
#from admin_routes import admin_router

#from router import router
from aiogram import Router
from fastapi import FastAPI, Request
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from db import initialize_database, conn, cur #db.py
from states import Register, AddBalance, PlaceOrder #states.py
from keyboards import main_menu, upi_keyboard #keyboards.py


# --- CONFIG from .env ---
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
SMM_API_KEY = os.getenv("SMM_API_KEY")
SMM_API_URL = os.getenv("SMM_API_URL")
UPI_ID = os.getenv("UPI_ID")
SERVICES_PER_PAGE = 8

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- BOT & DISPATCHER ---
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=MemoryStorage())

# --- FASTAPI APP ---
app = FastAPI()

@app.post(WEBHOOK_PATH)
async def handle_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.exception("Webhook processing failed")
    return {"ok": True}

# --- Cancel Command (Global) ---
router = Router()
admin_router = Router()

from keyboards import main_menu  # Make sure this is available
@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("⚠️ No active operation to cancel.")
    else:
        await state.clear()
        await message.answer("❌ Operation cancelled.", reply_markup=main_menu())

# --- My Wallet Handler ---
from aiogram import types
from keyboards import main_menu  # if needed again

@router.message(lambda m: m.text == "💰 My Wallet")
async def show_wallet(m: Message):
    try:
        result = cur.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (m.from_user.id,)
        ).fetchone()

        if result:
            balance = result[0]
        else:
            balance = 0.0
            cur.execute(
                "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)",
                (m.from_user.id, balance)
            )
            conn.commit()

        await m.answer(f"💵 Current Balance: ₹{balance:.2f}")

    except Exception as e:
        print(f"[Wallet Error] {e}")
        await m.answer("⚠️ Failed to retrieve wallet balance.")

#addbalance

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
)
from aiogram.fsm.context import FSMContext
import io, qrcode, sqlite3, os
from states import AddBalance
from keyboards import upi_keyboard, main_menu
#from config import ADMIN_ID, UPI_ID  # ✅ pull sensitive constants from .env or config.py


# --- Step 1: User taps Add Balance ---
@router.message(F.text == "💰 Add Balance")
async def prompt_amount(m: Message, state: FSMContext):
    bonus_msg = (
        "🎁 *Recharge Bonus Offers:*\n"
        "• ₹500 — _Get 2% Bonus_\n"
        "• ₹1000 — _Get 3% Bonus_\n"
        "• ₹2000+ — _Get 6% Bonus_\n\n"
        "💡 Bonus is applied automatically when your payment is approved."
    )
    await m.answer(bonus_msg, parse_mode="Markdown")
    await m.answer("💳 Enter the amount to add:")
    await state.set_state(AddBalance.amount)

# --- Step 2: Process Amount ---
@router.message(AddBalance.amount)
async def process_amount(m: Message, state: FSMContext):
    try:
        amt = round(float(m.text.strip()), 2)
        if amt <= 0:
            raise ValueError
    except ValueError:
        return await m.answer("❌ Invalid amount. Enter a number greater than 0.")

    await state.update_data(amount=amt)

    qr_link = f"upi://pay?pa={UPI_ID}&pn=SMMBot&am={amt}&cu=INR"
    img = qrcode.make(qr_link)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    await m.answer_photo(
        BufferedInputFile(buf.getvalue(), filename="qr.png"),
        caption=f"📸 Scan and pay ₹{amt} using UPI.\nThen press '✅ I Paid'.",
        reply_markup=upi_keyboard()
    )
    await state.set_state(AddBalance.txn_id)

# --- Step 3: Handle "I Paid" button ---
@router.callback_query(F.data == "paid_done")
async def ask_txnid(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📥 Enter your UPI Transaction ID:")
    await c.answer()

# --- Step 4: Save txn_id and notify admin ---
@router.message(AddBalance.txn_id)
async def save_txnid(m: Message, state: FSMContext):
    d = await state.get_data()
    amount = d.get("amount")
    txn_id = m.text.strip()

    try:
        cur.execute(
            "INSERT INTO payments (user_id, amount, txn_id) VALUES (?, ?, ?)",
            (m.from_user.id, amount, txn_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return await m.answer("❗ This transaction ID is already used.")

    approve_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"ap_{m.from_user.id}_{amount}_{txn_id}")],
        [InlineKeyboardButton(text="❌ Decline", callback_data=f"de_{m.from_user.id}_{amount}_{txn_id}")]
    ])

    await m.answer("✅ Submitted for approval. You’ll be notified once processed.")
    await bot.send_message(
        ADMIN_ID,
        f"🧾 *New Payment Request*\n👤 User ID: `{m.from_user.id}`\n💸 Amount: ₹{amount}\n🧾 Txn ID: `{txn_id}`",
        reply_markup=approve_btn,
        parse_mode="Markdown"
    )
    await state.clear()
#appprove or decline by admin
from aiogram.types import CallbackQuery
from aiogram import F
from aiogram.utils.markdown import hbold
import sqlite3

@router.callback_query(F.data.startswith("ap_"))
async def approve_payment(callback: CallbackQuery):
    try:
        _, uid, amt, txn = callback.data.split("_", 3)
        user_id = int(uid)
        amount = float(amt)

        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        cur.execute("UPDATE payments SET status = 'approved' WHERE txn_id = ?", (txn,))
        conn.commit()

        await callback.message.edit_text("✅ Payment Approved!")
        await bot.send_message(
            user_id,
            f"✅ ₹{amount:.2f} has been added to your wallet.\nThank you for recharging!"
        )
        # ✅ Notify group
        try:
            await bot.send_message(
                GROUP_ID,
                f"💳 *Payment Approved*\n👤 User ID: `{user_id}`\n💰 Amount: ₹{amount:.2f}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print("❗ Failed to notify group about payment:", e)
        await callback.answer()

    except Exception as e:
        await callback.answer("⚠️ Failed to approve.", show_alert=True)
        print(f"[Approve Error]: {e}")

@router.callback_query(F.data.startswith("de_"))
async def decline_payment(callback: CallbackQuery):
    try:
        _, uid, amt, txn = callback.data.split("_", 3)
        user_id = int(uid)
        amount = float(amt)

        cur.execute("UPDATE payments SET status = 'declined' WHERE txn_id = ?", (txn,))
        conn.commit()

        await callback.message.edit_text("❌ Payment Declined.")
        await bot.send_message(
            user_id,
            f"❌ Your payment of ₹{amount:.2f} was declined.\nPlease check the UPI or contact support."
        )
        await callback.answer()

    except Exception as e:
        await callback.answer("⚠️ Failed to decline.", show_alert=True)
        print(f"[Decline Error]: {e}")

# --- Order States ---
class PlaceOrder(StatesGroup):
    svc_id = State()
    svc_name = State()
    svc_rate = State()
    svc_min = State()
    svc_max = State()
    svc_link = State()
    svc_qty = State()
    svc_cost = State()

# --- Start Order Process ---
@router.message(F.text == "📦 New Order")
async def start_order(message: Message, state: FSMContext):
    response = requests.post(SMM_API_URL, data={"key": SMM_API_KEY, "action": "services"})
    if response.status_code != 200:
        return await message.answer("⚠️ Failed to fetch services.")
    
    services = response.json()
    await state.update_data(services=services)
    await show_services_page(message.chat.id, services, page=0)

async def show_services_page(chat_id, services, page: int):
    start = page * SERVICES_PER_PAGE
    end = start + SERVICES_PER_PAGE
    buttons = [
        [InlineKeyboardButton(text=f"{svc['name']} ₹{svc['rate']}", callback_data=f"svc_{svc['service']}")]
        for svc in services[start:end]
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"page_{page-1}"))
    if end < len(services):
        nav.append(InlineKeyboardButton(text="➡️ Next", callback_data=f"page_{page+1}"))
    if nav:
        buttons.append(nav)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(chat_id, f"📋 Choose a service (Page {page+1})", reply_markup=keyboard)

# --- Pagination ---
@router.callback_query(F.data.startswith("page_"))
async def paginate_services(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[1])
    data = await state.get_data()
    services = data.get("services", [])
    await callback.message.delete()
    await show_services_page(callback.message.chat.id, services, page)
    await callback.answer()

# --- Show Service Detail ---
@router.callback_query(F.data.startswith("svc_"))
async def service_detail(callback: CallbackQuery, state: FSMContext):
    svc_id = callback.data.split("_")[1]
    data = await state.get_data()
    services = data.get("services", [])

    svc = next((s for s in services if str(s["service"]) == svc_id), None)
    if not svc:
        return await callback.answer("❌ Service not found", show_alert=True)

    rate_with_profit = round(float(svc['rate']) * 1.10, 2)
    await state.update_data(
        svc_id=svc_id,
        svc_name=svc["name"],
        svc_rate=rate_with_profit,
        svc_min=svc.get("min", 0),
        svc_max=svc.get("max", 0)
    )

    desc = svc.get("description", "No description.")
    min_val = svc.get("min", "?")
    max_val = svc.get("max", "?")

    text = (
        f"📌 *{svc['name']}*\n"
        f"{desc}\n"
        f"💰 Rate: ₹{rate_with_profit} per 1k units\n"
        f"🔢 Min: {min_val} | Max: {max_val}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Select", callback_data=f"select_{svc_id}")]
        ]
    )
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# --- Ask for Link ---
@router.callback_query(F.data.startswith("select_"))
async def input_link(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔗 Please send the link/username:")
    await state.set_state(PlaceOrder.svc_link)
    await callback.answer()

# --- Ask for Quantity ---
@router.message(PlaceOrder.svc_link)
async def input_quantity(message: Message, state: FSMContext):
    await state.update_data(svc_link=message.text.strip())
    await message.answer("📦 Enter quantity:")
    await state.set_state(PlaceOrder.svc_qty)

# --- Confirm Order ---
@router.message(PlaceOrder.svc_qty)
async def confirm_order(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except:
        return await message.answer("❌ Invalid quantity. Please enter a positive number.")

    data = await state.get_data()
    rate = float(data["svc_rate"])
    cost = round(qty * rate / 1000, 2)

    # Balance check
    row = cur.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,)).fetchone()
    balance = row[0] if row else 0
    if balance < cost:
        return await message.answer("❌ Insufficient balance.")

    await state.update_data(svc_qty=qty, svc_cost=cost)

    text = (
        f"⚠️ Please confirm your order:\n\n"
        f"📦 *Service:* {data['svc_name']}\n"
        f"🔗 *Link:* {data['svc_link']}\n"
        f"🔢 *Qty:* {qty}\n"
        f"💰 *Cost:* ₹{cost:.2f}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Confirm Order", callback_data="confirm_order")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_order")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "confirm_order")
async def place_final_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id

    # SMM API Order Placement
    try:
        response = requests.post(SMM_API_URL, data={
            "key": SMM_API_KEY,
            "action": "add",
            "service": data['svc_id'],
            "link": data['svc_link'],
            "quantity": data['svc_qty']
        })

        resp_json = response.json()
        if 'order' not in resp_json:
            await callback.message.answer(f"❌ Order failed: {resp_json.get('error', 'Unknown error')}")
            return await state.clear()

        order_id = str(resp_json['order'])
        cost = data['svc_cost']
        qty = data['svc_qty']

        # Deduct balance and save order
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (cost, user_id))
        cur.execute("""
            INSERT INTO orders(user_id, order_id, service_name, link, quantity, price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, order_id, data['svc_name'], data['svc_link'], qty, cost, 'pending'))
        conn.commit()

        # User notification
        await callback.message.answer(
            f"✅ Order placed!\n🆔 Order ID: `{order_id}`\n💰 Cost: ₹{cost:.2f}",
            parse_mode="Markdown"
        )

        # Admin + Group notification
        user_row = cur.execute("SELECT name FROM users WHERE user_id = ?", (user_id,)).fetchone()
        user_name = user_row[0] if user_row else "Unknown"
        notif_msg = (
            f"📥 *New Order Received!*\n"
            f"👤 `{user_id}` ({user_name})\n"
            f"🆔 Order: `{order_id}`\n"
            f"📦 {data['svc_name']}\n"
            f"🔗 {data['svc_link']}\n"
            f"🔢 Qty: {qty}\n"
            f"💰 ₹{cost:.2f}\n"
            f"⏳ Status: pending"
        )

        await bot.send_message(ADMIN_ID, notif_msg, parse_mode="Markdown")
        await bot.send_message(GROUP_ID, notif_msg, parse_mode="Markdown")

    except Exception as e:
        print("❌ Order placement error:", e)
        await callback.message.answer("❌ An unexpected error occurred while placing the order.")
    
    await state.clear()

# --- Cancel Order ---
@router.callback_query(F.data == "cancel_order")
async def cancel_order_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("❌ Order cancelled.")
    await state.clear()

# 📄 My Orders
@router.message(F.text == "📄 My Orders")
async def view_orders(message: Message):
    try:
        rows = cur.execute(
            "SELECT order_id, service_name, quantity, price, status FROM orders WHERE user_id=?",
            (message.from_user.id,)
        ).fetchall()

        if not rows:
            return await message.answer("❌ You haven't placed any orders yet.")

        msg = "📦 *Your Orders:*\n\n"
        for order_id, name, qty, price, status in rows:
            msg += (
                f"🆔 Order ID: `{order_id}`\n"
                f"📦 Service: {name}\n"
                f"🔢 Qty: {qty}\n"
                f"💰 Amount: ₹{price:.2f}\n"
                f"📊 Status: {status.capitalize()}\n\n"
            )

        await message.answer(msg, parse_mode="Markdown")

    except Exception as e:
        print("⚠️ Error loading orders:", e)
        await message.answer("⚠️ Could not retrieve your orders at this time. Please try again.")
# --- Contact Admin Handler ---
@router.message(F.text == "📞 Contact Admin")
async def contact_admin(m: Message):
    await m.answer(
        "📩 For support, contact us on Telegram: [@sastasmmhelper_bot](https://t.me/sastasmmhelper_bot)",
        parse_mode="Markdown"
    )
    
#/addbalance
@router.message(Command("addbalance"))
async def add_balance_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized access.")

    parts = m.text.strip().split()
    if len(parts) != 3:
        return await m.answer("📌 Usage: `/addbalance <user_id> <amount>`", parse_mode="Markdown")

    try:
        uid = int(parts[1])
        amt = float(parts[2])
        if amt <= 0:
            raise ValueError
    except ValueError:
        return await m.answer("❌ Invalid format or amount. Please use a positive number.", parse_mode="Markdown")

    user = cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
    if not user:
        return await m.answer("❌ User not found in database.", parse_mode="Markdown")

    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
    conn.commit()

    await m.answer(f"✅ ₹{amt:.2f} added to user `{uid}`", parse_mode="Markdown")
    try:
        await bot.send_message(uid, f"✅ ₹{amt:.2f} has been added to your wallet by the admin.", parse_mode="Markdown")
    except Exception as e:
        await m.answer(f"⚠️ User notified failed.\nReason: {e}")

# --- /deduct command ---
@router.message(Command("deduct"))
async def deduct_balance_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized access.")

    parts = m.text.strip().split()
    if len(parts) != 3:
        return await m.answer("📌 Usage: `/deduct <user_id> <amount>`", parse_mode="Markdown")

    try:
        uid = int(parts[1])
        amt = float(parts[2])
        if amt <= 0:
            raise ValueError
    except ValueError:
        return await m.answer("❌ Invalid user ID or amount. Please enter a positive number.", parse_mode="Markdown")

    bal = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    if not bal:
        return await m.answer("❌ User not found.", parse_mode="Markdown")
    if bal[0] < amt:
        return await m.answer("❌ Insufficient balance to deduct.", parse_mode="Markdown")

    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, uid))
    conn.commit()

    await m.answer(f"✅ ₹{amt:.2f} deducted from user `{uid}`", parse_mode="Markdown")
    try:
        await bot.send_message(uid, f"⚠️ ₹{amt:.2f} has been deducted from your wallet by the admin.", parse_mode="Markdown")
    except Exception as e:
        await m.answer(f"⚠️ Unable to notify user.\nReason: {e}")

# --- /bonusadd command ---
@router.message(Command("bonusadd"))
async def add_bonus_command(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized access.")

    parts = m.text.strip().split()
    if len(parts) != 3:
        return await m.answer("📌 Usage: `/bonusadd <user_id> <amount>`", parse_mode="Markdown")

    try:
        user_id = int(parts[1])
        bonus = float(parts[2])
        if bonus <= 0:
            raise ValueError

        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, user_id))
        conn.commit()

        await m.answer(f"✅ ₹{bonus:.2f} bonus added to user `{user_id}`", parse_mode="Markdown")

        try:
            await bot.send_message(
                user_id,
                f"🎁 Bonus Alert!\nYou've received ₹{bonus:.2f} bonus from support. Thank you for using our panel.",
                parse_mode="Markdown"
            )
        except Exception as notify_error:
            await m.answer(f"⚠️ Bonus added, but failed to notify user.\nReason: {notify_error}")

    except ValueError:
        await m.answer("❌ Invalid input. Amount must be a positive number.", parse_mode="Markdown")
    except Exception as e:
        await m.answer(f"⚠️ Error: `{e}`", parse_mode="Markdown")

# ----- /checkbalance Command -----
@router.message(Command("checkbalance"))
async def check_balance_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized.")
    parts = m.text.split()
    if len(parts) != 2:
        return await m.answer("Usage: /checkbalance <user_id>")
    try:
        uid = int(parts[1])
    except ValueError:
        return await m.answer("❌ Invalid user ID.")
    row = cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
    if not row:
        return await m.answer("❌ User not found.")
    bal = row[0]
    await m.answer(f"👤 User ID: {uid}\n💰 Balance: ₹{bal:.2f}")

# ----- /userorders Command -----
@router.message(Command("userorders"))
async def user_orders_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized.")
    parts = m.text.split()
    if len(parts) != 2:
        return await m.answer("Usage: /userorders <user_id>")
    try:
        uid = int(parts[1])
    except ValueError:
        return await m.answer("❌ Invalid user ID.")
    rows = cur.execute(
        "SELECT order_id, service_name, quantity, price, status FROM orders WHERE user_id=?",
        (uid,)
    ).fetchall()
    if not rows:
        return await m.answer("No orders found.")
    msg = f"📦 Order history for user {uid}:\n\n" + "\n\n".join(
        [f"#{r[0]} • {r[1]} x{r[2]} • ₹{r[3]:.2f} • {r[4]}" for r in rows])
    await m.answer(msg)

# ----- /listusers Command -----
@router.message(Command("listusers"))
async def list_users_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized.")
    rows = cur.execute("SELECT user_id, name, phone, balance FROM users").fetchall()
    if not rows:
        return await m.answer("No users found.")
    msg = "👥 Registered Users:\n\n" + "\n".join(
        [f"{r[0]} • {r[1]} • {r[2]} • ₹{r[3]:.2f}" for r in rows])
    await m.answer(msg)

# ----- /stats Command -----
@router.message(Command("stats"))
async def stats_cmd(m: Message):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Unauthorized.")
    total_users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_orders = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    revenue = cur.execute("SELECT SUM(price) FROM orders").fetchone()[0] or 0.0
    revenue = round(float(revenue), 2)

    msg = (
        "📊 Bot Statistics:\n"
        f"• Total Users: {total_users}\n"
        f"• Total Orders: {total_orders}\n"
        f"• Total Revenue: ₹{revenue:.2f}"
    )
    await m.answer(msg)

#groupmsg
@router.message()
async def get_group_id(m: Message):
    if m.chat.type in ("group", "supergroup"):
        print(f"Group ID: {m.chat.id}")
        await m.answer(f"This group's chat ID is: `{m.chat.id}`", parse_mode="Markdown")
GROUP_ID = -4651688106  # 🔁 Your actual group ID here
@router.message(Command("testgroup"))
async def test_group_send(m: Message):
    try:
        await bot.send_message(GROUP_ID, "✅ Bot is able to send messages to this group!")
        await m.answer("✅ Test message sent to the group.")
    except Exception as e:
        await m.answer(f"❌ Failed to send to group.\nError: {e}")

#-----/update-orders-----
async def update_pending_orders():
    pending_orders = cur.execute("SELECT order_id, user_id FROM orders WHERE status = 'pending'").fetchall()
    updated_count = 0

    for order_id, user_id in pending_orders:
        try:
            resp = requests.post(SMM_API_URL, data={
                "key": SMM_API_KEY,
                "action": "status",
                "order": order_id
            }).json()

            new_status = resp.get("status")
            if new_status and new_status != "pending":
                cur.execute("UPDATE orders SET status=? WHERE order_id=?", (new_status, order_id))
                conn.commit()
                updated_count += 1
                try:
                    await bot.send_message(
                        user_id,
                        f"📦 Your order `{order_id}` status is now *{new_status}*.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        except Exception as e:
            print(f"❗ Error updating order {order_id}: {e}")
    return updated_count

#starts 
import asyncio
import logging
from aiogram import Bot, Dispatcher
#from your_module import bot, dp, router, admin_router, initialize_database  # 👈 Replace with actual imports

async def main():
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    
    dp.include_router(router)
    dp.include_router(admin_router)
    dp.services_cache = []

    await bot.delete_webhook(drop_pending_updates=True)  # ⛔ Remove webhook if any
    logging.info("🤖 Bot is starting via long polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

