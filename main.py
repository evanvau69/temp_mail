import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)
import re
import random

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}
allowed_users = set()  # শুধু যাদের পারমিশন দিবে

CANADA_AREA_CODES = [
    "204", "236", "249", "250", "289", "306", "343", "365", "387", "403",
    "416", "418", "431", "437", "438", "450", "506", "514", "519", "548",
    "579", "581", "587", "604", "613", "639", "647", "672", "705", "709",
    "742", "778", "780", "782", "807", "819", "825", "867", "873", "902", "905"
]

def generate_random_numbers(area_code=None, count=30):
    numbers = []
    if area_code and area_code not in CANADA_AREA_CODES:
        return []
    for _ in range(count):
        ac = area_code if area_code else random.choice(CANADA_AREA_CODES)
        # Generate a random 7 digit number after area code
        number = f"+1{ac}{random.randint(1000000, 9999999)}"
        numbers.append(number)
    return numbers

def extract_canada_numbers(text):
    # Regex to find numbers with/without +, optional spaces etc
    pattern = r"(?:\+?1)?(204|236|249|250|289|306|343|365|387|403|416|418|431|437|438|450|506|514|519|548|579|581|587|604|613|639|647|672|705|709|742|778|780|782|807|819|825|867|873|902|905)\D*(\d{3})\D*(\d{4})"
    matches = re.findall(pattern, text)
    result = []
    for match in matches:
        number = "+1" + "".join(match)
        result.append(number)
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if free_trial_users.get(user_id) == "active" or user_id in allowed_users:
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{user_name} Subscription চালু আছে এবার Log In করুন", reply_markup=reply_markup)
    else:
        keyboard = [
            [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
            [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
            [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
            [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
            [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?", reply_markup=reply_markup)

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active" or user_id in allowed_users:
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active" and user_id not in allowed_users:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    args = context.args
    area_code = None
    if args:
        candidate = args[0]
        if candidate.isdigit() and candidate in CANADA_AREA_CODES:
            area_code = candidate

    numbers = generate_random_numbers(area_code)
    if not numbers:
        await update.message.reply_text("⚠️ সঠিক Canada Area Code দিন।")
        return

    msg_text = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)
    await update.message.reply_text(msg_text)

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
                await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial টি শেষ হয়েছে")
            asyncio.create_task(revoke())

    elif query.data.startswith("plan_") and query.data != "plan_free":
        plan_info = {
            "plan_1d": ("1 Day", "2"),
            "plan_7d": ("7 Day", "10"),
            "plan_15d": ("15 Day", "15"),
            "plan_30d": ("30 Day", "20")
        }
        duration, price = plan_info.get(query.data, ("", ""))

        text = (
            f"{user_name} {duration} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user_name}\n"
            f"🔆 User ID : {user_id}\n"
            f"🔆 Username : @{username}"
        )
        buttons = [
            [InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
             InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send ${price} to Binance Pay ID: \n"
            f"পেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{username}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: ${price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)

    elif query.data == "login":
        await context.bot.send_message(
            chat_id=user_id,
            text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`",
            parse_mode='Markdown'
        )

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        allowed_users.add(uid)
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif query.data.startswith("buy_"):
        number = query.data[4:]
        text = f"আপনি বেছে নিয়েছেন: {number}"
        buttons = [[InlineKeyboardButton("Buy 💰", callback_data=f"confirmbuy_{number}")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, reply_markup=reply_markup)

    elif query.data.startswith("confirmbuy_"):
        number = query.data[11:]
        uid = query.from_user.id

        # Check permission and balance before buy (simulate)
        if free_trial_users.get(uid) != "active" and uid not in allowed_users:
            await context.bot.send_message(chat_id=uid, text="❌ আপনার Subscription নেই।")
            return

        sid_auth = user_sessions.get(uid)
        if not sid_auth:
            await context.bot.send_message(chat_id=uid, text="❌ প্রথমে Login করুন।")
            return

        sid, auth = sid_auth
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            balance_resp = await session.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json")
            if balance_resp.status == 401:
                await context.bot.send_message(chat_id=uid, text="টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                return
            balance_data = await balance_resp.json()
            balance = float(balance_data.get("balance", 0.0))

            # Simulate price 1$
            price = 1.0
            if balance < price:
                await context.bot.send_message(chat_id=uid, text="আপনার টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                return

            # Simulate purchase success
            # Here you would call Twilio API to buy number - skipped for demo
            text = (
                f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n"
                f"এখানে নাম্বার টা থাকবে {number}"
            )
            buttons = [[InlineKeyboardButton("Message ✉️", callback_data=f"message_{number}")]]
            reply_markup = InlineKeyboardMarkup(buttons)

            await query.edit_message_text(text, reply_markup=reply_markup)

    elif query.data.startswith("message_"):
        number = query.data[8:]
        await query.answer("Message feature এখনো নেই", show_alert=True)

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if free_trial_users.get(user_id) != "active" and user_id not in allowed_users:
        await update.message.reply_text("❌ আপনার Subscription নেই।")
        return

    try:
        sid, auth = text.split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        account_resp = await session.get("https://api.twilio.com/2010-04-01/Accounts.json")
        if account_resp.status == 401:
            await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
            return
        data = await account_resp.json()
        account_name = data['accounts'][0]['friendly_name']

        balance_resp = await session.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json")
        balance_data = await balance_resp.json()
        balance = float(balance_data.get("balance", 0.0))

        await update.message.reply_text(
            f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
            f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
            f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
        )
        user_sessions[user_id] = (sid, auth)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active" and user_id not in allowed_users:
        await update.message.reply_text("❌ আপনার Subscription নেই।")
        return

    text = update.message.text
    numbers = extract_canada_numbers(text)
    if not numbers:
        await update.message.reply_text("⚠️ কোন Canada নম্বর পাওয়া যায়নি। দয়া করে সঠিক নম্বর পাঠান।")
        return

    for num in numbers:
        keyboard = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_{num}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(num, reply_markup=reply_markup)

async def approve_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # এই হ্যান্ডলার callback query গুলোর জন্য
    pass  # আগেই handle_callback এ আছে

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    try:
        await update.message.reply_text("⚠️ কিছু সমস্যা হয়েছে, আবার চেষ্টা করুন।")
    except:
        pass

async def webhook_handler(request):
    if request.method == "POST":
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return web.Response(text="ok")
    else:
        return web.Response(status=405)

if __name__ == "__main__":
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.Regex(r"^[a-zA-Z0-9]{34} [a-zA-Z0-9]{32}$"), handle_sid_auth))

    application.add_error_handler(error_handler)

    # Webhook setup
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL not set in environment variables.")
        exit(1)

    # Run aiohttp server for webhook
    app = web.Application()
    app.router.add_post("/" + BOT_TOKEN, webhook_handler)

    import ssl
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(os.getenv("SSL_CERT_PATH"), os.getenv("SSL_KEY_PATH"))

    runner = web.AppRunner(app)
    loop = asyncio.get_event_loop()

    async def start_webhook():
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8443)), ssl_context=ssl_context)
        await site.start()
        logger.info("Bot is running via webhook...")

    loop.create_task(start_webhook())
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    loop.run_forever()
