import os
import logging
import asyncio
import aiohttp
import random
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}
user_active_numbers = {}  # user_id: active_number

# Canada area codes for random selection
CANADA_AREA_CODES = [
    "204", "226", "236", "249", "250", "289", "306", "343", "365", "367",
    "403", "416", "418", "431", "437", "438", "450", "506", "514", "519",
    "579", "581", "587", "604", "613", "647", "672", "705", "709", "742",
    "778", "780", "782", "807", "819", "825", "867", "873", "902", "905"
]

def generate_canadian_number(area_code):
    # 7 digit random number part
    return f"+1{area_code}{random.randint(1000000, 9999999)}"

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

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    # Subscription related callbacks
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

    # Buy command related callbacks

    elif query.data.startswith("cancel_numbers"):
        # Cancel button pressed on numbers message
        await query.edit_message_text("নাম্বার কিনা বাতিল হয়েছে ☢️")

    elif query.data.startswith("select_number_"):
        # User selected a number from the list
        number = query.data[len("select_number_"):]
        buttons = [
            [InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{number}")],
            [InlineKeyboardButton("Cancel ❌", callback_data="cancel_numbers")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(f"আপনি নির্বাচন করেছেন:\n{number}", reply_markup=reply_markup)

    elif query.data.startswith("buy_number_"):
        number = query.data[len("buy_number_"):]
        user_id = query.from_user.id

        # Check if user has active number, delete old number message if exists
        old_number = user_active_numbers.get(user_id)
        if old_number:
            try:
                # This deletes old message where old number was shown with buttons
                # Assuming you stored message ids if needed
                pass
            except Exception as e:
                logger.warning(f"Failed to delete old number message: {e}")

        sid_auth = user_sessions.get(user_id)
        if not sid_auth:
            await context.bot.send_message(chat_id=user_id, text="❌ Token দেওয়া হয়নি। আগে /login দিয়ে লগইন করুন।")
            return

        sid, auth = sid_auth

        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            # Check Twilio balance
            try:
                async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                    if resp.status == 401:
                        await context.bot.send_message(chat_id=user_id, text="Token Suspended, অন্য টোকেন দিয়ে Log In করুন ♻️")
                        return
                    data = await resp.json()
                    account_name = data['accounts'][0]['friendly_name']

                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                async with session.get(balance_url) as balance_resp:
                    balance_data = await balance_resp.json()
                    balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                if currency != "USD":
                    rate_url = f"https://open.er-api.com/v6/latest/{currency}"
                    async with session.get(rate_url) as rate_resp:
                        rates = await rate_resp.json()
                        usd_rate = rates["rates"].get("USD", 1)
                        balance = balance * usd_rate

                if balance < 1.0:  # Adjust threshold as per requirement
                    await context.bot.send_message(chat_id=user_id, text="Token এ নাম্বার কিনার মতো Balance নাই অন্য টোকেন দিয়ে Log In করুন ♻️")
                    return

                # Here you should place the actual number buying API call
                # Simulate success buying after some delay
                await asyncio.sleep(1)

                user_active_numbers[user_id] = number

                buttons = [
                    [InlineKeyboardButton("📧 Message ✉️", callback_data="message_placeholder")]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n{number}",
                    reply_markup=reply_markup
                )

            except Exception as e:
                logger.error(f"Error during number buy: {e}")
                await context.bot.send_message(chat_id=user_id, text="নাম্বার কিনতে সমস্যা হয়েছে, পরে চেষ্টা করুন।")

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

            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )
            # Save sid/auth for the user session
            user_sessions[user_id] = (sid, auth)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    args = context.args
    numbers = []

    if args:
        # User provided area code
        area_code = args[0]
        if area_code not in CANADA_AREA_CODES:
            await update.message.reply_text("❌ Invalid Canada Area Code. দয়া করে সঠিক কোড দিন।")
            return
        for _ in range(30):
            numbers.append(generate_canadian_number(area_code))
    else:
        # Random 30 numbers with different area codes
        chosen_area_codes = random.sample(CANADA_AREA_CODES, 30)
        for area_code in chosen_area_codes:
            numbers.append(generate_canadian_number(area_code))

    numbers_text = "আপনার নাম্বার গুলো হলো 👇👇\n\n"
    for num in numbers:
        numbers_text += f"{num}\n"

    buttons = []
    for num in numbers:
        buttons.append([InlineKeyboardButton(num, callback_data=f"select_number_{num}")])
    buttons.append([InlineKeyboardButton("Cancel ❌", callback_data="cancel_numbers")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(numbers_text, reply_markup=reply_markup)

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
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_sid_auth))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web_app = web.Application()
    web_app.router.add_post("/", handle_update)
    web.run_app(web_app, port=port)
