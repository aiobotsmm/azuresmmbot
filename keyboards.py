from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

def main_menu(balance=0):
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💰 My Wallet"),
                KeyboardButton(text="💰 Add Balance")
            ],
            [
                KeyboardButton(text="📦 New Order"),
                KeyboardButton(text="📄 My Orders")
            ],
            [
                KeyboardButton(text="📞 Contact Admin")
            ]
        ],
        resize_keyboard=True
    )

def upi_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ I Paid", callback_data="paid_done")]
        ]
    )
