import os
import re
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # আপনার Admin ID বসাবেন

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}
user_login_state = {}  # user_id -> bool: Login বাটনে ক্লিক করেছে কিনা

# কানাডার Area Codes (সর্বাধিক) - আরও যোগ করতে পারেন
CANADA_AREA_CODES = [
    "204", "226", "236", "249", "250", "289", "306", "343", "365", "387", "403",
    "416", "418", "431", "437", "438", "450", "506", "514", "519", "548", "579",
    "581", "587", "604", "613", "639", "647", "672", "705", "709", "742", "778",
    "780", "782", "807", "819", "825", "867", "873", "902", "905"
]

# একটা হেল্পার ফাংশন যা ইউজারের মেসেজ থেকে কানাডার নাম্বার গুলো ডিটেক্ট করবে
def extract_canadian_numbers(text):
    # ফোন নম্বরের প্যাটার্ন: +1 + 3 ডিজিট এরিয়া কোড + 7 ডিজিট নাম্বার
    # নম্বরের মাঝে - বা space থাকতে পারে, +1 থাকতে পারে বা নাও থাকতে পারে
    pattern = re.compile(r'(?:\+?1[-.\s]?)?(\d{3})[-.\s]?(\d{3})[-.\s]?(\d{4})')
    matches = pattern.findall(text)

    valid_numbers = []
    for m in matches:
        area_code = m[0]
        if area_code in CANADA_AREA_CODES:
            # +1-এর সাথে সম্পূর্ণ নম্বর তৈরি
            number = f"+1{area_code}{m[1]}{m[2]}"
            valid_numbers.append(number)
    return valid_numbers


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    username = update.effective_user.username or "N/A"

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{user_name} Subscription চালু আছে এবার Log In করুন", reply_markup=reply_markup
        )
        return

    keyboard = [
        [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
        [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
        [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
        [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
        [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?", reply_markup=reply_markup
    )


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
                await asyncio.sleep(3600)  # ১ ঘন্টা পরে ট্রায়াল শেষ
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial টি শেষ হয়েছে")

            asyncio.create_task(revoke())

    elif query.data.startswith("plan_") and query.data != "plan_free":
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
            [InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
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
        user_login_state[user_id] = True
        await query.message.delete()
        await context.bot.send_message(
            chat_id=user_id,
            text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`",
            parse_mode='Markdown'
        )

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif query.data.startswith("buy_"):
        # ফিচার: ইউজার নাম্বার বাটন ক্লিক করলে নাম্বার কিনবে
        number = query.data.split("_", 1)[1]
        user_sid_auth = user_sessions.get(user_id)
        if not user_sid_auth:
            await query.answer("❌ প্রথমে Login করুন এবং Token দিন।", show_alert=True)
            return

        sid, auth = user_sid_auth
        # Twilio API দিয়ে Check balance এবং Buy লজিক এখানে করবেন

        # ধরুন ক্রয় সফল:
        new_text = f"🎉 Congratulations! {number} নাম্বারটি কিনা হয়েছে 🎉"
        keyboard = [[InlineKeyboardButton("Message ✉️", callback_data=f"message_{number}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(new_text, reply_markup=reply_markup)


async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Login বাটনে ক্লিক করেছে কি না চেক
    if not user_login_state.get(user_id):
        await update.message.reply_text("⚠️ Login বাটনে ক্লিক করে তারপর Token পাঠান।")
        return

    # একবার Token নেওয়ার পর Login স্টেট False করে দিন
    user_login_state[user_id] = False

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    # Twilio API ভেরিফিকেশন শুরু
    try:
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                if resp.status == 401:
                    await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
                    return
                data = await resp.json()
                account_name = data['accounts'][0]['friendly_name']

            # ব্যালেন্স চেক
            balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
            async with session.get(balance_url) as b:
                balance_data = await b.json()
                balance = float(balance_data.get("balance", 0.0))
                currency = balance_data.get("currency", "USD")

                # USD না হলে রেট কনভার্ট (optional)
                if currency != "USD":
                    rate_url = f"https://open.er-api.com/v6/latest/{currency}"
                    async with session.get(rate_url) as rate_resp:
                        rates = await rate_resp.json()
                        usd_rate = rates["rates"].get("USD", 1)
                        balance = balance * usd_rate

            # ইউজার সেশনে Token সেভ করুন
            user_sessions[user_id] = (sid, auth)

            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥 🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                f"বিঃদ্রঃ নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন, কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )
    except Exception as e:
        logger.error(f"Twilio API Error: {e}")
        await update.message.reply_text("❌ টোকেন যাচাই করা যায়নি, আবার চেষ্টা করুন।")


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    args = context.args
    area_code = None
    if args:
        ac = args[0]
        if ac in CANADA_AREA_CODES:
            area_code = ac
        else:
            await update.message.reply_text("⚠️ অনুগ্রহ করে বৈধ Canada Area Code দিন।")
            return

    # র‍্যান্ডম ৩০ টি নম্বর জেনারেট
    import random
    def generate_number(ac):
        n = "".join([str(random.randint(0,9)) for _ in range(7)])
        return f"+1{ac}{n}"

    numbers = []
    if area_code:
        numbers = [generate_number(area_code) for _ in range(30)]
    else:
        # Random 30 টি area code থেকে
        numbers = [generate_number(random.choice(CANADA_AREA_CODES)) for _ in range(30)]

    msg = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)
    await update.message.reply_text(msg)


async def handle_number_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    text = update.message.text
    numbers = extract_canadian_numbers(text)
    if not numbers:
        await update.message.reply_text("⚠️ কোনো বৈধ Canada নাম্বার পাওয়া যায়নি।")
        return

    # প্রতিটি নাম্বারের নিচে Buy বাটন সহ মেসেজ পাঠানো
    for num in numbers:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_{num}")]])
        await update.message.reply_text(f"{num}", reply_markup=keyboard)


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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_messages))

if __name__ == "__main__":
    # For webhook
    # import ssl
    # ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    # ssl_context.load_cert_chain("cert.pem", "key.pem")
    # web.run_app(app, port=8443, ssl_context=ssl_context)

    application.run_polling()
