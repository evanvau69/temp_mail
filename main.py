import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # নিশ্চিত করো int type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}

# Canada area codes - উদাহরণ সরূপ কিছু কোড দিলাম, চাইলে আরো বাড়াতে পারো
CANADA_AREA_CODES = [
    "204", "236", "249", "250", "289", "306", "343", "365", "387", "403",
    "416", "418", "431", "437", "438", "450", "506", "514", "519", "548",
    "579", "581", "587", "604", "613", "639", "647", "672", "705", "709",
    "742", "778", "780", "782", "807", "819", "825", "867", "873", "902",
    "905"
]

# Permission চেক ডেকোরেটর
def permission_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if free_trial_users.get(user_id) != "active":
            if update.message:
                await update.message.reply_text("❌ আপনার অনুমতি নেই। প্রথমে Subscription নিন।")
            elif update.callback_query:
                await update.callback_query.answer("❌ আপনার অনুমতি নেই। প্রথমে Subscription নিন।", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


@permission_required
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

@permission_required
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

# /buy কমান্ড - random বা specific area code এর Canada নাম্বার ৩০ টা দিবে
@permission_required
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    import random

    def generate_random_number(area_code):
        # +1 হল Canada country code
        # নাম্বারের বাকিটা random 7 digit, 10 digit full: +1 + area_code + 7 random digits
        return f"+1{area_code}{random.randint(1000000, 9999999)}"

    area_code = None
    if args:
        candidate = args[0]
        # args থেকে area_code পেতে চেষ্টা করবো (3 digit numeric)
        if candidate.isdigit() and len(candidate) == 3 and candidate in CANADA_AREA_CODES:
            area_code = candidate

    if area_code is None:
        area_code = random.choice(CANADA_AREA_CODES)

    numbers = [generate_random_number(area_code) for _ in range(30)]

    text = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)
    await update.message.reply_text(text)


# ইউজার যেকোন মেসেজে number পাঠালে detect করবে এবং প্রত্যেক নাম্বারের নিচে Buy বাটন দিয়ে পাঠাবে
@permission_required
async def handle_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    import re

    # Canada phone number pattern: country code +1 and area code + 7 digit
    # ইউজার যেকোন ফরম্যাটে নাম্বার পাঠাতে পারে তাই নিচের প্যাটার্ন দিয়ে ক্যাপচার করব
    # উদাহরণ প্যাটার্ন: +1 416 123 4567, 14161234567, 4161234567 ইত্যাদি থেকে নাম্বার বের করবে
    # Simplify: country code +1 optional, area code must be valid canadian area code, then 7 digit number

    pattern = r"(?:\+?1)?\s*(" + "|".join(CANADA_AREA_CODES) + r")\s*\-?\s*(\d{3})\s*\-?\s*(\d{4})"
    matches = re.findall(pattern, text)

    if not matches:
        # যদি নাম্বার না পায়, কিছু রেসপন্স না দিতে চাইলে এখানে return করো
        return

    # প্রতিটা নাম্বার বানাবে +1 + area_code + 7 digit ফরম্যাটে
    buttons = []
    numbers_text_lines = []
    for match in matches:
        area_code = match[0]
        first3 = match[1]
        last4 = match[2]
        full_number = f"+1{area_code}{first3}{last4}"
        numbers_text_lines.append(full_number)
        buttons.append([InlineKeyboardButton("Buy 💰", callback_data=f"buy_{full_number}")])

    message_text = "নিচের নাম্বারগুলো থেকে Buy করতে পারবেন 👇\n" + "\n".join(numbers_text_lines)

    await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(buttons))


# Buy বাটনে ক্লিক করলে নাম্বার বাটন সহ মেসেজ edit হবে, balance check করবে এবং সাড়া দিবে
@permission_required
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    data = query.data

    if data == "plan_free":
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

    elif data.startswith("plan_"):
        plan_info = {
            "plan_1d": ("1 Day", "2$"),
            "plan_7d": ("7 Day", "10$"),
            "plan_15d": ("15 Day", "15$"),
            "plan_30d": ("30 Day", "20$")
        }
        duration, price = plan_info.get(data, ("", ""))

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
            f"Please send {price} to Binance Pay ID: \nপেমেন্ট করে প্রমাণ হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{username}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: {price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)

    elif data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`", parse_mode='Markdown')

    elif data.startswith("approve_"):
        uid = int(data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif data.startswith("buy_"):
        number = data[4:]
        # Twilio API দিয়ে Balance চেক করবো এবং Token Suspend চেক করবো
        # Sid, Auth টোকেন User থেকে আগে Sid/Auth হ্যান্ডলার থেকে পাবে বলে ধরে নিচ্ছি

        # এখানে User Sid/Auth টোকেন session dict এ থাকতে হবে
        sid_auth = user_sessions.get(user_id)
        if not sid_auth:
            await query.edit_message_text(f"❌ আপনার Sid/Auth Token সেট করা নেই। প্রথমে /login দিয়ে সেট করুন।")
            return

        sid, auth = sid_auth

        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            # চেক টোকেন Suspend নাকি
            async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                if resp.status == 401:
                    await query.edit_message_text("😥 টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                    return
                data = await resp.json()
                account_name = data['accounts'][0]['friendly_name']

            # ব্যালেন্স চেক
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

            # যদি ব্যালেন্স ১০$ এর নিচে ধরে নিচ্ছি (তুমি চাইলে প্ল্যান অনুযায়ী চেক করো)
            if balance < 10:
                await query.edit_message_text("❌ আপনার টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                return

            # Number buy successful - (simulate করার জন্য)
            # বাস্তবে তুমি Twilio API দিয়ে নাম্বার কিনবে এখানে সেই কল যুক্ত করবে
            await query.edit_message_text(
                f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n{number}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Message ✉️", callback_data=f"message_{number}")]])
            )

    elif data.startswith("message_"):
        number = data[8:]
        # এখানে প্রয়োজন মত ইউজারকে মেসেজ পাঠানোর জন্য UI দিতে পারো
        await query.answer("Message ফিচার আসছে শীঘ্রই...")



@permission_required
async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        sid, auth = text.split(" ", 1)
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

    user_sessions[user_id] = (sid, auth)

    await update.message.reply_text(
        f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
        f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
        f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
    )


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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_numbers))  # নাম্বার detect এর জন্য

# webhook সেটআপের জন্য যদি দরকার হয়
# app = web.Application()
# app.router.add_post('/webhook', handle_update)
# web.run_app(app, port=PORT)

if __name__ == "__main__":
    print("Bot Started")
    application.run_polling()
