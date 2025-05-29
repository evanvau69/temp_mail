import os
import logging
import asyncio
import aiohttp
from aiohttp import web
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import random

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}

CANADA_AREA_CODES = ['204', '236', '249', '250', '289', '306', '343', '365', '403', '416',
                    '418', '431', '437', '438', '450', '506', '514', '519', '579', '581',
                    '587', '604', '613', '639', '647', '672', '705', '709', '778', '780',
                    '782', '807', '819', '825', '867', '873', '902', '905']

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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?", reply_markup=reply_markup)

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check if user has active subscription
    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    # Check if user has logged in with valid token
    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
        return

    args = context.args
    selected_area_codes = []

    if args:
        area_code = args[0]
        if area_code in CANADA_AREA_CODES:
            selected_area_codes = [area_code] * 30  # ৩০ নাম্বার একই area code দিয়ে
        else:
            await update.message.reply_text("⚠️ আপনার দেওয়া area code পাওয়া যায়নি। অনুগ্রহ করে সঠিক কানাডার area code দিন।")
            return
    else:
        count = min(30, len(CANADA_AREA_CODES))
        selected_area_codes = random.sample(CANADA_AREA_CODES, count)

    phone_numbers = []
    for code in selected_area_codes:
        number = f"+1{code}{random.randint(1000000, 9999999)}"
        phone_numbers.append(number)

    message_text = "আপনার নাম্বার গুলো হলো 👇👇\n\n" + "\n".join(phone_numbers)

    buttons = []
    for num in phone_numbers:
        buttons.append([InlineKeyboardButton(num, callback_data=f"number_{num}")])

    buttons.append([InlineKeyboardButton("Cancel ❌", callback_data="cancel_buy")])
    reply_markup = InlineKeyboardMarkup(buttons)

    sent_msg = await update.message.reply_text(message_text, reply_markup=reply_markup)

    # Auto delete after 5 minutes (300 seconds)
    async def delete_message():
        await asyncio.sleep(300)
        try:
            await sent_msg.delete()
        except:
            pass

    asyncio.create_task(delete_message())

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

        text = (
            f"{user_name} {duration} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user_name}\n"
            f"🔆 User ID : {user_id}\n"
            f"🔆 Username : @{username}"
        )
        buttons = [
            [InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}"),
             InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send {price} to Binance Pay ID: \nপেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{username}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: {price}"
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

    elif query.data == "cancel_buy":
        await query.edit_message_text("নাম্বার কিনা বাতিল হয়েছে ☢️")

    elif query.data.startswith("number_"):
        selected_number = query.data[len("number_"):]
        buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{selected_number}")]])
        await context.bot.send_message(chat_id=user_id, text=f"{selected_number}", reply_markup=buy_button)

    elif query.data.startswith("buy_number_"):
        number_to_buy = query.data[len("buy_number_"):]
        await context.bot.send_message(chat_id=user_id, text=f"আপনি এই নাম্বারটি কিনতে চান: {number_to_buy}\n\nকিনার প্রক্রিয়া এখানে যোগ করুন।")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
            if resp.status == 401:
                await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
                return
            data = await resp.json()
            account_name = data['accounts'][0]['friendly_name']
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

            user_sessions[user_id] = {"sid": sid, "auth": auth, "logged_in": True}

            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )

def extract_canada_numbers(text: str):
    area_codes_pattern = "(" + "|".join(CANADA_AREA_CODES) + ")"
    pattern = re.compile(
        rf"(?:\+?1[\s\-\.]?)?"        # country code optional +1 or 1
        rf"{area_codes_pattern}"      # valid area code
        rf"[\s\-\.]?"                 # optional separator
        rf"(\d{{3}})"                 # first 3 digits
        rf"[\s\-\.]?"                 # optional separator
        rf"(\d{{4}})"                 # last 4 digits
    )
    matches = pattern.finditer(text)
    results = []
    for match in matches:
        area_code = match.group(1)
        part1 = match.group(2)
        part2 = match.group(3)
        full_number = f"+1{area_code}{part1}{part2}"
        results.append(full_number)
    return results

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    numbers = extract_canada_numbers(text)
    if numbers:
        for num in numbers:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{num}")]])
            await update.message.reply_text(f"আপনার দেওয়া নাম্বার শনাক্ত হলো:\n{num}", reply_markup=keyboard)
    else:
        # যদি নাম্বার না পাওয়া যায় তাহলে চুপ থাকুন বা মেসেজ দিন (এখানে কোনো মেসেজ নাই)
        pass

# Simple web server for health check or ping to keep bot awake (for Heroku etc.)
async def handle_root(request):
    return web.Response(text="Bot is running")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle_root)
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on port {port}")

async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    # Separate handlers for sid_auth and number detection so both work on any text
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start web server concurrently
    await run_web_server()

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Bot started...")
    await application.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
