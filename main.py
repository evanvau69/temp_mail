import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import random
import re

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}  # ইউজারের লগইন স্টেট রাখবে: {"logged_in": True/False, "sid": "...", "auth": "..."}

CANADA_AREA_CODES = ['204', '236', '249', '250', '289', '306', '343', '365', '403', '416', '418', '431', '437', '438',
                     '450', '506', '514', '519', '579', '581', '587', '604', '613', '639', '647', '672', '705', '709',
                     '778', '780', '782', '807', '819', '825', '867', '873', '902', '905']

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
    # চেক লগইন
    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
        return

    args = context.args
    selected_area_codes = []

    if args:
        area_code = args[0]
        if area_code in CANADA_AREA_CODES:
            selected_area_codes = [area_code] * 30  # একই কোড ৩০ বার
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
    buttons = [[InlineKeyboardButton(num, callback_data=f"number_{num}")] for num in phone_numbers]
    buttons.append([InlineKeyboardButton("Cancel ❌", callback_data="cancel_buy")])
    reply_markup = InlineKeyboardMarkup(buttons)

    msg = await update.message.reply_text(message_text, reply_markup=reply_markup)

    # ৫ মিনিট পর মেসেজ ডিলিটের জন্য asyncio টাস্ক
    async def delete_message_later(chat_id, message_id):
        await asyncio.sleep(300)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    asyncio.create_task(delete_message_later(update.effective_chat.id, msg.message_id))

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
        # ইউজারের জন্য Buy বাটন সহ মেসেজ পাঠানো
        buttons = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_{selected_number}")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await context.bot.send_message(chat_id=user_id, text=f"আপনি নির্বাচন করেছেন: {selected_number}", reply_markup=reply_markup)

    elif query.data.startswith("buy_"):
        number_to_buy = query.data[len("buy_"):]
        await context.bot.send_message(chat_id=user_id, text=f"🎉 আপনি নাম্বার কিনতে যাচ্ছেন: {number_to_buy}\n\nঅনুগ্রহ করে পেমেন্ট সম্পন্ন করুন এবং Admin কে জানান।")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # টোকেন সাসপেন্ড হলে লগইন স্টেট False করে দিবো
    try:
        sid, auth = update.message.text.strip().split(" ", 1)
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')
        return

    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
            if resp.status == 401:
                user_sessions[user_id] = {"logged_in": False, "sid": None, "auth": None}
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

            # লগইন স্টেট সেট করা
            user_sessions[user_id] = {"logged_in": True, "sid": sid, "auth": auth}

            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f} USD\n\n"
                f"✅ এখন আপনি /buy কমান্ড ব্যবহার করতে পারবেন।"
            )

def extract_canadian_numbers(text):
    numbers_found = []
    cleaned_text = re.sub(r"[^\d+]", " ", text)
    possible_numbers = cleaned_text.split()

    for num in possible_numbers:
        cleaned_num = re.sub(r"[^\d]", "", num)
        if cleaned_num.startswith("1") and len(cleaned_num) == 11:
            area = cleaned_num[1:4]
            if area in CANADA_AREA_CODES:
                formatted = f"+1{cleaned_num[1:]}"
                numbers_found.append(formatted)
        elif len(cleaned_num) == 10:
            area = cleaned_num[0:3]
            if area in CANADA_AREA_CODES:
                formatted = f"+1{cleaned_num}"
                numbers_found.append(formatted)

    return list(set(numbers_found))

async def detect_and_send_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
        return

    text = update.message.text or ""
    numbers = extract_canadian_numbers(text)

    if not numbers:
        await update.message.reply_text("কোনো বৈধ কানাডার নাম্বার পাওয়া যায়নি আপনার মেসেজে। দয়া করে সঠিক নম্বর পাঠান।")
        return

    buttons = [[InlineKeyboardButton(num, callback_data=f"number_{num}")] for num in numbers]
    reply_markup = InlineKeyboardMarkup(buttons)
    msg = await update.message.reply_text("নিচের নাম্বার গুলো থেকে যেটা কিনতে চান সেটাতে ক্লিক করুন:", reply_markup=reply_markup)

    async def delete_message_later(chat_id, message_id):
        await asyncio.sleep(300)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Failed to delete message: {e}")

    asyncio.create_task(delete_message_later(update.effective_chat.id, msg.message_id))

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, detect_and_send_numbers))
    application.add_handler(MessageHandler(filters.Regex(r'^\S+\s+\S+$'), handle_sid_auth))  # sid auth login

    application.run_polling()

if __name__ == "__main__":
    main()
