# main.py
import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from random import randint

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN environment variable is not set.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}

def generate_random_canadian_numbers(count=30):
    numbers = []
    for _ in range(count):
        area_code = randint(200, 999)
        number = f"+1{area_code}{randint(1000000, 9999999)}"
        numbers.append(number)
    return numbers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name
        username = update.effective_user.username or "N/A"

        if free_trial_users.get(user_id) == "active":
            keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"{user_name} Subscription চালু আছে এবার Log In করুন",
                reply_markup=reply_markup,
            )
            return

        keyboard = [
            [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
            [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
            [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
            [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
            [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?",
            reply_markup=reply_markup,
        )

    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "আপনার Subscription চালু আছে, নিচে Login করুন ⬇️",
            reply_markup=reply_markup,
        )
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
            await context.bot.send_message(
                chat_id=user_id, text="✅ আপনার Free Trial Subscription টি চালু হয়েছে"
            )
            asyncio.create_task(revoke_trial_later(user_id, context))

    elif query.data.startswith("plan_"):
        plan_info = {
            "plan_1d": ("1 Day", "2$"),
            "plan_7d": ("7 Day", "10$"),
            "plan_15d": ("15 Day", "15$"),
            "plan_30d": ("30 Day", "20$"),
        }
        duration, price = plan_info.get(query.data, ("", ""))
        text = (
            f"{user_name} {duration} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user_name}\n"
            f"🔆 User ID : {user_id}\n"
            f"🔆 Username : @{username}"
        )
        buttons = [
            [
                InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}"),
            ]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(buttons)
        )
        await query.message.delete()

    elif query.data == "login":
        await context.bot.send_message(
            chat_id=user_id,
            text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: <sid> <auth>",
            parse_mode="Markdown",
        )

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif query.data.startswith("buy_number_"):
        number = query.data.split("_", 2)[2]
        sid_auth = user_sessions.get(user_id, {}).get("sid_auth")
        if not sid_auth:
            await query.edit_message_text("⚠️ আগে Log In করুন তারপর Try করুন")
            return
        sid, auth = sid_auth
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
            async with session.get(balance_url) as resp:
                if resp.status == 401:
                    await query.edit_message_text("টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                    return
                data = await resp.json()
                balance = float(data.get("balance", 0.0))
                if balance < 1.0:
                    await query.edit_message_text(
                        "আপনার টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️"
                    )
                    return
            user_sessions[user_id]["last_number"] = number
            await query.edit_message_text(
                f"🎉 Congestion  নাম্বারটি কিনা হয়েছে 🎉\n\nনাম্বার: {number}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Message ✉️", callback_data="send_sms")]]
                ),
            )

async def revoke_trial_later(user_id, context):
    await asyncio.sleep(3600)
    free_trial_users.pop(user_id, None)
    await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial টি শেষ হতে যাচ্ছে")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return
    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text(
            "⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode="Markdown"
        )
        return
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
            if resp.status == 401:
                await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
                return
            data = await resp.json()
            account_name = data["accounts"][0]["friendly_name"]
        balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
        async with session.get(balance_url) as b:
            balance_data = await b.json()
            balance = float(balance_data.get("balance", 0.0))
            currency = balance_data.get("currency", "USD")
            if currency != "USD":
                rate_url = f"https://open.er-api.com/v6/latest/{currency}"
                async with session.get(rate_url) as rate_resp:
                    rates = await rate_resp.json()
                    usd_rate = rates["rates"].get("USD", 1)
                    balance = balance * usd_rate
            user_sessions[user_id] = user_sessions.get(user_id, {})
            user_sessions[user_id]["sid_auth"] = (sid, auth)
            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    if len(context.args) == 0:
        await update.message.reply_text("দয়া করে Area Code দিন, উদাহরণ: /buy 416")
        return

    areacode = context.args[0]
    if not areacode.isdigit() or len(areacode) != 3:
        await update.message.reply_text("সঠিক ৩ ডিজিটের Area Code দিন।")
        return

    # এখানে শুধু সেই Area Code এর নাম্বার তৈরি করবো
    def generate_numbers_with_areacode(count=30, code=areacode):
        numbers = []
        for _ in range(count):
            number = f"+1{code}{randint(1000000, 9999999)}"
            numbers.append(number)
        return numbers

    numbers = generate_numbers_with_areacode()
    user_sessions[user_id] = user_sessions.get(user_id, {})
    user_sessions[user_id]["numbers"] = numbers

    msg = f"আপনার Area Code {areacode} এর নাম্বার গুলো 👇👇\n" + "\n".join(numbers)
    await update.message.reply_text(msg)


async def handle_number_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return
    if user_id not in user_sessions or "numbers" not in user_sessions[user_id]:
        return
    text = update.message.text
    selected_numbers = []
    for num in user_sessions[user_id]["numbers"]:
        if num in text:
            selected_numbers.append(num)
    for num in selected_numbers:
        keyboard = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{num}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"নাম্বার: {num}", reply_markup=reply_markup)

async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

application = Application.builder().token(BOT_TOKEN).build()

# হ্যান্ডলার রেজিস্ট্রেশন
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_selection))

async def main():
    await application.initialize()
    await application.start()
    app = web.Application()
    app.router.add_post(f"/{BOT_TOKEN}", handle_update)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Bot is running on port {PORT} via webhook...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
