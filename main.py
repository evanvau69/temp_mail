import os
import logging
import asyncio
import aiohttp
import re
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}
mock_canada_numbers = {
    "default": [f"+1{str(i).zfill(10)}" for i in range(2041234567, 2041234597)],
    "647": [f"+1647{str(i).zfill(6)}" for i in range(100000, 100030)]
}

def extract_canadian_numbers(text):
    pattern = r"(?:\+?1)?\d{10}"
    return re.findall(pattern, text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        await update.message.reply_text(f"{user_name} Subscription চালু আছে এবার Log In করুন", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
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
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Login 🔑", callback_data="login")]]))
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
        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"{user_name} {duration} Subscription নিতে চাচ্ছে\n\n🔆 Username: @{username}", reply_markup=InlineKeyboardMarkup(buttons))
        await context.bot.send_message(chat_id=user_id, text=f"Please send ${price} to Binance Pay ID...\nপেমেন্টের প্রমাণ দিন @Admin")

    elif query.data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন 🎉\nব্যবহার: `<sid> <auth>`", parse_mode='Markdown')

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription বাতিল করা হয়েছে।")

    elif query.data.startswith("buy_"):
        number = query.data.split("_")[1]
        user_id = query.from_user.id
        sid, auth = user_sessions.get(user_id, (None, None))

        if not sid or not auth:
            await context.bot.send_message(chat_id=user_id, text="⛔️ প্রথমে লগইন করুন `/login` কমান্ড দিয়ে।")
            return

        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
                buy_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
                async with session.post(buy_url, data={"PhoneNumber": f"+1{number}"}) as resp:
                    if resp.status == 401:
                        await context.bot.send_message(chat_id=user_id, text="😥 টোকেন Suspend হয়েছে ♻️")
                        return
                    elif resp.status == 400:
                        await context.bot.send_message(chat_id=user_id, text="❌ ব্যালেন্স নেই বা নাম্বার খালি নেই ♻️")
                        return
                    await query.edit_message_text(
                        f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n📞 {number}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Message ✉️", callback_data="message")]])
                    )
        except Exception as e:
            await context.bot.send_message(chat_id=user_id, text="❌ কিছু সমস্যা হয়েছে, আবার চেষ্টা করুন।")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return
    try:
        sid, auth = update.message.text.strip().split(" ", 1)
        user_sessions[user_id] = (sid, auth)
    except:
        await update.message.reply_text("⚠️ উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        async with session.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json") as b:
            if b.status == 401:
                await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে")
                return
            balance_data = await b.json()
            balance = float(balance_data.get("balance", 0.0))
            await update.message.reply_text(f"🎉 Logged In\nBalance: ${balance:.2f}")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    area = context.args[0] if context.args else "default"
    numbers = mock_canada_numbers.get(area, mock_canada_numbers["default"])
    msg = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)
    await update.message.reply_text(msg)

async def detect_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    numbers = extract_canadian_numbers(text)
    for number in numbers:
        clean = number[-10:]
        button = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_{clean}")]]
        await update.message.reply_text(f"+1{clean}", reply_markup=InlineKeyboardMarkup(button))

async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detect_numbers))
application.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, handle_sid_auth))

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
