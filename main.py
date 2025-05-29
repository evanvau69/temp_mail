import os
import re
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}

# Canada area codes sample (you can expand or modify)
CANADA_AREA_CODES = [
    "204", "236", "249", "250", "289", "306", "343", "365", "387",
    "403", "416", "418", "431", "437", "438", "450", "506", "514",
    "519", "548", "579", "581", "587", "604", "613", "639", "647",
    "672", "705", "709", "778", "780", "782", "807", "819", "825",
    "867", "873", "902", "905"
]

def generate_random_numbers(area_code: str, count: int = 30):
    """Generate random 7-digit numbers prefixed with +1 and area code."""
    import random

    numbers = set()
    while len(numbers) < count:
        number = f"+1{area_code}{random.randint(1000000, 9999999)}"
        numbers.add(number)
    return list(numbers)

def extract_canada_numbers(text: str):
    """
    Extract valid Canada phone numbers from arbitrary text.
    Canada numbers: +1 followed by a valid area code and 7-digit number.
    Format flexible with or without +, spaces, dashes, text around numbers.
    """
    # Regex to catch variants like +1 416 1234567, 14161234567, 1-416-123-4567, etc.
    pattern = re.compile(
        r"(?:\+?1\s*[-.\s]?)?"        # country code +1 optional with separators
        r"(\d{3})"                   # area code (3 digits)
        r"[-.\s]*"                   # optional separator
        r"(\d{3})"                   # first 3 digits
        r"[-.\s]*"                   # optional separator
        r"(\d{4})"                   # last 4 digits
    )
    matches = pattern.findall(text)
    valid_numbers = []
    for area, first3, last4 in matches:
        if area in CANADA_AREA_CODES:
            valid_numbers.append(f"+1{area}{first3}{last4}")
    return list(set(valid_numbers))  # unique

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

    elif query.data.startswith("plan_") and not query.data.startswith(("plan_free")):
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

    # New callbacks for buy process
    elif query.data.startswith("buy_"):
        # Format: buy_<number>
        number = query.data[4:]
        # Edit the message: show confirmation + new button "Message ✉️"
        msg_text = f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n{number}"
        buttons = [[InlineKeyboardButton("Message ✉️", callback_data=f"message_{number}")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text=msg_text, reply_markup=reply_markup)

        # Now simulate buy process: check balance, suspend, etc.
        user_sid_auth = user_sessions.get(user_id)
        if not user_sid_auth:
            # No sid/auth saved
            await context.bot.send_message(chat_id=user_id, text="❌ আপনার Sid/Auth সেভ করা হয়নি, দয়া করে /login দিয়ে Login করুন।")
            return

        sid, auth = user_sid_auth

        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            # Check balance
            balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
            try:
                async with session.get(balance_url) as resp:
                    if resp.status == 401:
                        # Token suspended
                        await context.bot.send_message(chat_id=user_id, text="😥 টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন")
                        return
                    if resp.status != 200:
                        await context.bot.send_message(chat_id=user_id, text="❌ ব্যালেন্স চেক করতে সমস্যা হচ্ছে, পরে চেষ্টা করুন।")
                        return
                    balance_data = await resp.json()
                    balance = float(balance_data.get("balance", 0.0))
            except Exception:
                await context.bot.send_message(chat_id=user_id, text="❌ ব্যালেন্স চেক করতে সমস্যা হচ্ছে, পরে চেষ্টা করুন।")
                return

            # For demo purpose, let's assume each number costs 1 USD
            cost = 1.0
            if balance < cost:
                await context.bot.send_message(chat_id=user_id, text="❌ আপনার টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                return

            # Simulate number buy (Here you'd call Twilio API to buy number, simplified)
            # After successful purchase, deduct balance (simulate)
            # We do not actually deduct balance since it's external; just notify success.

            # Notify user purchase success
            await context.bot.send_message(chat_id=user_id, text=f"✅ নাম্বার {number} সফলভাবে কেনা হয়েছে। ধন্যবাদ!")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    # Test auth by getting account info
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        try:
            async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                if resp.status == 401:
                    await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
                    return
                data = await resp.json()
                account_name = data['accounts'][0]['friendly_name']
        except Exception:
            await update.message.reply_text("❌ টোকেন যাচাই করতে সমস্যা হয়েছে, আবার চেষ্টা করুন।")
            return

        # Save sid/auth for user session
        user_sessions[user_id] = (sid, auth)

        # Get balance
        balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
        try:
            async with session.get(balance_url) as b:
                balance_data = await b.json()
                balance = float(balance_data.get("balance", 0.0))
                currency = balance_data.get("currency", "USD")
        except Exception:
            balance = 0.0
            currency = "USD"

        if currency != "USD":
            rate_url = f"https://open.er-api.com/v6/latest/{currency}"
            try:
                async with session.get(rate_url) as rate_resp:
                    rates = await rate_resp.json()
                    usd_rate = rates["rates"].get("USD", 1)
                    balance = balance * usd_rate
            except Exception:
                pass

        await update.message.reply_text(
            f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
            f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
            f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
        )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    # Determine area code list to pick from
    if args:
        area_code = args[0]
        if area_code not in CANADA_AREA_CODES:
            await update.message.reply_text("⚠️ অনুগ্রহ করে একটি সঠিক কানাডিয়ান এরিয়া কোড দিন। উদাহরণ: /buy 416")
            return
        numbers = generate_random_numbers(area_code)
    else:
        # Pick 30 random numbers from 30 random area codes
        import random
        random_areas = random.sample(CANADA_AREA_CODES, 30)
        numbers = []
        for ac in random_areas:
            numbers.extend(generate_random_numbers(ac, 1))
        # ensure exactly 30 numbers
        numbers = numbers[:30]

    msg_text = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)

    await update.message.reply_text(msg_text)

async def handle_number_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    When user sends message containing numbers to buy,
    parse all Canada numbers and send each with a "Buy 💰" button,
    all in one message (multiple lines).
    """

    user_id = update.effective_user.id
    text = update.message.text

    numbers = extract_canada_numbers(text)
    if not numbers:
        return  # no canada numbers found

    # Build a single message with all numbers, each followed by a Buy button inline
    # Because Telegram inline buttons can only be one markup per message,
    # we will send multiple messages, each with a number and a button, or
    # better: send one message with numbered lines and buttons for all numbers

    # We'll send a message listing all numbers with Buy buttons per number (1 button each)
    # Since Telegram limits max buttons per row and message, better to send multiple messages if > 10 numbers
    # But here user can send max 100 numbers so keep max 50 buttons in one message to be safe

    MAX_BUTTONS_PER_MSG = 50
    buttons = []
    text_lines = []
    count = 0

    # Telegram buttons rows: each row one button
    for num in numbers:
        buttons.append([InlineKeyboardButton(f"Buy 💰 {num}", callback_data=f"buy_{num}")])
        text_lines.append(num)
        count += 1
        if count == MAX_BUTTONS_PER_MSG:
            # send partial message
            reply_markup = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(chat_id=user_id, text="নিম্নলিখিত নাম্বার থেকে বাছাই করুন:\n" + "\n".join(text_lines), reply_markup=reply_markup)
            buttons = []
            text_lines = []
            count = 0

    # Send remaining if any
    if buttons:
        reply_markup = InlineKeyboardMarkup(buttons)
        await context.bot.send_message(chat_id=user_id, text="নিম্নলিখিত নাম্বার থেকে বাছাই করুন:\n" + "\n".join(text_lines), reply_markup=reply_markup)

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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_selection))

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
    logger.info("Bot started.")
    await application.updater.start_polling()
    await application.idle()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
