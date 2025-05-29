import os
import re
import random
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# স্টোরেজ
free_trial_users = {}
user_sessions = {}  # user_id: {"sid": str, "auth": str}

# কানাডার এলাকা কোড লিস্ট (30টি র‍্যান্ডম)
CANADA_AREA_CODES = [
    "204", "226", "236", "249", "250", "289", "306", "343", "365",
    "367", "403", "416", "418", "431", "437", "438", "450", "506",
    "514", "519", "548", "579", "581", "587", "604", "613", "639",
    "647", "705", "709"
]

# নাম্বার জেনারেট করার ফাংশন
def generate_canada_numbers(area_code=None, count=30):
    area_codes = [area_code] if area_code else CANADA_AREA_CODES
    numbers = []
    for _ in range(count):
        ac = random.choice(area_codes)
        # কানাডিয়ান নাম্বার ফরম্যাট: +1 + AreaCode + 7 digit random number
        number = f"+1{ac}{random.randint(1000000, 9999999)}"
        numbers.append(number)
    return numbers

# ইউজার মেসেজ থেকে কানাডার নাম্বার বের করার রেগুলার এক্সপ্রেশন
CANADA_NUMBER_REGEX = re.compile(r"(?:\+?1)?(204|226|236|249|250|289|306|343|365|367|403|416|418|431|437|438|450|506|514|519|548|579|581|587|604|613|639|647|705|709)[-\s]?(\d{3})[-\s]?(\d{4})")

# নাম্বার থেকে ফরম্যাট ঠিক করার ফাংশন
def extract_canada_numbers_from_text(text):
    found_numbers = []
    for match in CANADA_NUMBER_REGEX.finditer(text):
        area = match.group(1)
        part2 = match.group(2)
        part3 = match.group(3)
        full_number = f"+1{area}{part2}{part3}"
        found_numbers.append(full_number)
    return list(set(found_numbers))  # ইউনিক করে রিটার্ন

# Twilio API দিয়ে ব্যালেন্স চেক করার ফাংশন
async def check_twilio_balance(sid, auth):
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        account_url = "https://api.twilio.com/2010-04-01/Accounts.json"
        async with session.get(account_url) as resp:
            if resp.status == 401:
                return "suspended", None
            if resp.status != 200:
                return "error", None
            data = await resp.json()
            account_name = data['accounts'][0]['friendly_name']

        balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
        async with session.get(balance_url) as bresp:
            if bresp.status != 200:
                return "error", None
            balance_data = await bresp.json()
            balance = float(balance_data.get("balance", 0.0))
            return "ok", (account_name, balance)

# স্টার্ট কমান্ড
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

# লগইন কমান্ড
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

# Callback হ্যান্ডলার
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
            [InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
             InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send {price} to Binance Pay ID: \nপেমেন্ট করে প্রমাণ হিসেবে Admin এর কাছে স্ক্রিনশট অথবা transaction ID দিন @Mr_Evan3490\n\n"
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

    elif query.data.startswith("buy_"):
        # buy_ নাম্বার থেকে নাম্বার নেবো
        buy_number = query.data[4:]
        sid_auth = user_sessions.get(user_id)
        if not sid_auth:
            await query.answer("❌ প্রথমে লগইন করুন।")
            return
        sid, auth = sid_auth["sid"], sid_auth["auth"]

        # ব্যালেন্স চেক
        status, bal_data = await check_twilio_balance(sid, auth)
        if status == "suspended":
            await query.answer("টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️", show_alert=True)
            return
        elif status != "ok":
            await query.answer("ব্যালেন্স চেক করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।", show_alert=True)
            return

        account_name, balance = bal_data
        cost_per_number = 1.0  # ধরলাম প্রতিটি নাম্বারের দাম 1$

        if balance < cost_per_number:
            await query.answer("আপনার টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️", show_alert=True)
            return

        # ব্যালেন্স আছে, নাম্বার কিনে ফেলা হলো
        # এখানে আপনি Twilio API দিয়ে প্রকৃত নাম্বার ক্রয় লজিক যোগ করবেন

        # মেসেজ এডিট
        new_text = (
            f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n"
            f"নাম্বার: {buy_number}"
        )
        # নতুন বাটন
        keyboard = [[InlineKeyboardButton("Message ✉️", callback_data=f"msg_{buy_number}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(new_text, reply_markup=reply_markup)

    elif query.data.startswith("msg_"):
        buy_number = query.data[4:]
        await query.answer(f"আপনি এখন এই নাম্বারে মেসেজ পাঠাতে পারবেন: {buy_number}", show_alert=True)

# ইউজারের টোকেন লোগইন হ্যান্ডলার
async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    status, bal_data = await check_twilio_balance(sid, auth)
    if status == "suspended":
        await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
        return
    if status != "ok":
        await update.message.reply_text("❌ টোকেন যাচাই করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")
        return

    account_name, balance = bal_data
    user_sessions[user_id] = {"sid": sid, "auth": auth}

    await update.message.reply_text(
        f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
        f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
        f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
    )

# /buy কমান্ড হ্যান্ডলার
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে লগইন করুন অথবা Subscription নিন।")
        return

    args = context.args
    area_code = None
    if args:
        code = args[0]
        # এলাকা কোড চেক করুন যদি লিস্টে থাকে
        if code in CANADA_AREA_CODES:
            area_code = code
        else:
            await update.message.reply_text("⚠️ অনুগ্রহ করে বৈধ কানাডার এরিয়া কোড দিন।")
            return

    numbers = generate_canada_numbers(area_code)

    # নাম্বারগুলো টেক্সট হিসেবে তৈরি করুন
    msg_text = "আপনার নাম্বার গুলো হলো 👇👇\n"
    for n in numbers:
        msg_text += n + "\n"

    await update.message.reply_text(msg_text)

# ইউজার মেসেজ থেকে নাম্বার ডিটেকশন ও বাটন অ্যাড করা
async def handle_numbers_with_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    text = update.message.text
    found_numbers = extract_canada_numbers_from_text(text)
    if not found_numbers:
        return  # কোন নাম্বার পাওয়া যায় নি

    # প্রতিটি নাম্বারের জন্য বাটন বানানো
    buttons = []
    for num in found_numbers:
        buttons.append([InlineKeyboardButton("Buy 💰", callback_data=f"buy_{num}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("\n".join(found_numbers), reply_markup=reply_markup)

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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_numbers_with_buttons))

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
