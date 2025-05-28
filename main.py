import asyncio
import json
from pathlib import Path
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ====== Config ======
BOT_TOKEN = "8167950944:AAENH9u3oP-H_Ht63Cqn9BI7xYvBeCWVUXs"
ADMIN_ID = 6165060012
PERMISSION_FILE = "permissions.json"

# ====== Load/Save Permissions ======
def load_permissions():
    path = Path(PERMISSION_FILE)
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_permissions(data):
    with open(PERMISSION_FILE, "w") as f:
        json.dump(data, f)

active_permissions = load_permissions()

# ====== Subscription Plans ======
plans = {
    "free": {"label": "⬜ 1 Hour - Free 🌸", "duration": 1, "price": 0},
    "1d": {"label": "🔴 1 Day - 2$", "duration": 24, "price": 2},
    "7d": {"label": "🟠 7 Day - 10$", "duration": 168, "price": 10},
    "15d": {"label": "🟡 15 Day - 15$", "duration": 360, "price": 15},
    "30d": {"label": "🟢 30 Day - 20$", "duration": 720, "price": 20},
}

free_trial_users = set()  # Keep track who took free trial

def get_main_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(plans["free"]["label"], callback_data="free")],
        [InlineKeyboardButton(plans["1d"]["label"], callback_data="1d")],
        [InlineKeyboardButton(plans["7d"]["label"], callback_data="7d")],
        [InlineKeyboardButton(plans["15d"]["label"], callback_data="15d")],
        [InlineKeyboardButton(plans["30d"]["label"], callback_data="30d")],
    ])

# ====== Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id_str = str(user.id)

    # Check active permission from JSON file
    if active_permissions.get(user_id_str):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{user.first_name} Subscription চালু আছে ✅\nএবার Log In করুন।",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Login 🔑", callback_data="login")]
            ])
        )
        return

    # No active permission: show subscription list
    msg = await update.message.reply_text(
        f"Welcome ×͜× ✿𝙴𝚅𝙰𝙽✿ ×͜× 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?",
        reply_markup=get_main_buttons()
    )
    context.user_data['menu_msg_id'] = msg.message_id

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    chat_id = query.message.chat_id
    plan_key = query.data
    user_id_str = str(user.id)

    # Delete button message with inline buttons
    await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)

    # Free trial logic
    if plan_key == "free":
        if user_id_str in free_trial_users:
            await context.bot.send_message(chat_id=chat_id, text="❌ আপনি আগে থেকেই Free Trial ব্যবহার করেছেন!")
            return

        active_permissions[user_id_str] = True
        save_permissions(active_permissions)

        free_trial_users.add(user_id_str)

        await context.bot.send_message(chat_id=chat_id, text="✅ আপনার Free Trial Subscription টি চালু হয়েছে!")

        # Wait for free trial duration (1 hour)
        await asyncio.sleep(plans["free"]["duration"] * 3600)

        # Remove permission after trial ends
        active_permissions.pop(user_id_str, None)
        save_permissions(active_permissions)
        await context.bot.send_message(chat_id=chat_id, text="🌻 আপনার Free Trial টি শেষ হতে যাচ্ছে।")

    # Paid plan logic
    elif plan_key in plans:
        plan = plans[plan_key]

        # Notify admin with approve/cancel buttons
        admin_msg = await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"""(User {user.full_name}) {plan['duration']} ঘণ্টার Subscription নিতে চাচ্ছে।

🔆 User Name: {user.full_name}
🔆 User Id: {user.id}
🔆 Username: @{user.username or 'N/A'}""",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("APPROVE ✅", callback_data=f"approve:{user.id}:{plan_key}"),
                    InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel:{user.id}")
                ]
            ])
        )
        context.user_data[f"admin_msg_{user.id}"] = admin_msg.message_id

        # Ask user to pay
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""Please send ${plan['price']} to Binance Pay ID: 
পেমেন্ট করে প্রমাণ হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490

Your payment details:
🆔 User ID: {user.id}
👤 Username: @{user.username or 'N/A'}
📋 Plan: {plan['label']}
💰 Amount: ${plan['price']}"""
        )

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("approve"):
        _, uid_str, plan_key = data.split(":")
        uid = int(uid_str)

        active_permissions[uid_str] = True
        save_permissions(active_permissions)

        await query.edit_message_text(f"✅ APPROVED for User ID: {uid}")
        await context.bot.send_message(chat_id=uid, text="🎉 আপনার Subscription Approved হয়েছে!")

    elif data.startswith("cancel"):
        _, uid_str = data.split(":")
        uid = int(uid_str)

        await query.edit_message_text(f"❌ Subscription Cancelled for User ID: {uid}")
        await context.bot.send_message(chat_id=uid, text="❌ আপনার Subscription Cancelled হয়েছে।")

async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    chat_id = query.message.chat_id

    await context.bot.send_message(chat_id=chat_id, text="🔑 লগইন সফল হয়েছে।")

# ====== Main ======
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button, pattern="^(free|1d|7d|15d|30d)$"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(approve|cancel):"))
    app.add_handler(CallbackQueryHandler(login_handler, pattern="^login$"))

    print("Bot is running...")
    app.run_polling()
