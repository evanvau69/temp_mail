# Canada Number Buyer Telegram Bot

import os
import logging
import asyncio
import aiohttp
import random
import re
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Storage ---
free_trial_users = {}
user_sessions = {}
user_tokens = {}
user_numbers = {}

# --- Area Codes for Canada ---
canada_areas = ['204', '236', '249', '250', '289', '306', '343', '365', '387', '403', '416', '418', '431', '437', '438', '450', '506', '514', '519', '548', '579', '581', '587', '604', '613', '639', '647', '672', '705', '709', '742', '778', '780', '782', '807', '819', '825', '867', '873', '902', '905']

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    username = update.effective_user.username or "N/A"

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name} Subscription চালু আছে এবার Log In করুন", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
        [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
        [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
        [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
        [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")]
    ]
    await update.message.reply_text(f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?", reply_markup=InlineKeyboardMarkup(keyboard))

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    if query.data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ আপনি এরই মধ্যে Free Trial ব্যবহার করেছেন।")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ আপনার Free Trial Subscription টি চালু হয়েছে")

            async def revoke():
                await asyncio.sleep(3600)
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial টি শেষ হতে যাচ্ছে")

            asyncio.create_task(revoke())

    elif query.data.startswith("plan_"):
        plan_info = {
            "plan_1d": ("1 Day", "2$"),
            "plan_7d": ("7 Day", "10$"),
            "plan_15d": ("15 Day", "15$"),
            "plan_30d": ("30 Day", "20$")
        }
        duration, price = plan_info.get(query.data, ("", ""))

        buttons = [[
            InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")
        ]]

        text = f"{user_name} {duration} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n🔆 User Name : {user_name}\n🔆 User ID : {user_id}\n🔆 Username : @{username}"

        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(buttons))

        payment_msg = (
            f"Please send ${price} to Binance Pay ID: \nপেমেন্ট করে প্রমান দিন @Mr_Evan3490\n\n"
            f"🆔 User ID: {user_id}\n👤 Username: @{username}\n📋 Plan: {duration}\n💰 Amount: ${price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)

    elif query.data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`", parse_mode='Markdown')

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

# Token Login Handler
async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    try:
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                if resp.status == 401:
                    await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন ♻️")
                    return
                data = await resp.json()
                account_name = data['accounts'][0].get('friendly_name', 'Unknown')

            balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
            async with session.get(balance_url) as b:
                if b.status != 200:
                    await update.message.reply_text("❌ ব্যালেন্স তথ্য আনতে সমস্যা হয়েছে")
                    return

                balance_data = await b.json()
                balance = float(balance_data.get("balance", 0.0))
                currency = balance_data.get("currency", "USD")

                user_tokens[user_id] = {'sid': sid, 'auth': auth, 'balance': balance}

                await update.message.reply_text(
                    f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥 🎉\n\n"
                    f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                    f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                    f"বিঃদ্রঃ নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন ♻️"
                )
    except Exception as e:
        await update.message.reply_text(f"❌ Login করতে সমস্যা হয়েছে: {str(e)}")

# Webhook setup
async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))

async def main():
    await application.initialize()
    await application.start()
    app = web.Application()
    app.router.add_post(f"/{BOT_TOKEN}", handle_update)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Bot is running via webhook...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
