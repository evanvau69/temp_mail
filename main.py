import os
import re
import random
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    constants
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}  # user_id -> {"sid": "", "auth": "", "balance": 0, "account_name": ""}
user_active_numbers = {}  # user_id -> currently bought number


# --- Helper: Extract only Canadian numbers from text ---
def extract_canadian_numbers(text):
    canadian_area_codes = (
        "204|236|249|250|289|306|343|365|387|403|416|418|431|437|438|450|506|514|519|548|579|581|"
        "587|604|613|639|647|672|705|709|742|778|780|782|807|819|825|867|873|902|905"
    )
    pattern = re.compile(
        r'(?:\+?1[-.\s]?)?'
        r'(?:\(?(' + canadian_area_codes + r')\)?)[-.\s]?(\d{3})[-.\s]?(\d{4})'
    )
    matches = pattern.findall(text)
    numbers = []
    for area, part1, part2 in matches:
        number = f"+1{area}{part1}{part2}"
        numbers.append(number)
    return numbers


# --- Fixed list of 30 Canadian numbers for /buy ---
canada_numbers = [
    "+12025550101", "+14165550102", "+16045550103", "+12045550104", "+14165550105",
    "+16045550106", "+12025550107", "+14165550108", "+16045550109", "+12045550110",
    "+14165550111", "+16045550112", "+12025550113", "+14165550114", "+16045550115",
    "+12045550116", "+14165550117", "+16045550118", "+12025550119", "+14165550120",
    "+16045550121", "+12045550122", "+14165550123", "+16045550124", "+12025550125",
    "+14165550126", "+16045550127", "+12045550128", "+14165550129", "+16045550130"
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    username = update.effective_user.username or "N/A"

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{user_name} Subscription চালু আছে এবার Log In করুন",
            reply_markup=reply_markup
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
        f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?",
        reply_markup=reply_markup
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
        await context.bot.send_message(
            chat_id=user_id,
            text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif query.data.startswith("buy_"):
        number = query.data[4:]  # buy_ + number
        prev_number = user_active_numbers.get(user_id)
        # ডিলিট পুরানো নাম্বার
        if prev_number:
            await context.bot.delete_message(chat_id=user_id, message_id=user_sessions.get(user_id, {}).get("last_buy_msg_id", 0))
        # সিমুলেট নাম্বার কিনা হয়েছে
        user_active_numbers[user_id] = number
        text = f"🎉 Congestion {number} নাম্বারটি কিনা হয়েছে 🎉"
        buttons = [[InlineKeyboardButton("Message ✉️", callback_data=f"message_{number}")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        msg = await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)
        user_sessions.setdefault(user_id, {})["last_buy_msg_id"] = msg.message_id


async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    try:
        sid, auth = update.message.text.strip().split()
    except ValueError:
        await update.message.reply_text("❌ ভুল ফরম্যাট! শুধু `<sid> <auth>` এই ফরম্যাটে দিন।")
        return

    user_sessions[user_id] = {"sid": sid, "auth": auth, "balance": 0, "account_name": ""}
    await update.message.reply_text("✅ Sid এবং Auth Token সফলভাবে সংরক্ষণ করা হয়েছে।")


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    numbers_text = "\n".join(canada_numbers)
    # ৩০টা নাম্বার টেক্সট আকারে পাঠানো
    await update.message.reply_text(f"Canada এর নাম্বার লিস্ট (৩০ টি):\n\n{numbers_text}")

    # বাটন লিস্ট তৈরি
    buttons = []
    for number in canada_numbers:
        buttons.append([InlineKeyboardButton(number, callback_data=f"buy_{number}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("নিচের বাটন থেকে নাম্বার বেছে নিন:", reply_markup=reply_markup)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # কানাডার নাম্বারগুলো ইউজারের মেসেজ থেকে বের করে নাও
    numbers = extract_canadian_numbers(text)
    if not numbers:
        await update.message.reply_text("কোনো বৈধ কানাডার নাম্বার পাওয়া যায়নি।")
        return

    buttons = []
    for number in numbers:
        buttons.append([InlineKeyboardButton(number, callback_data=f"buy_{number}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("আপনার নাম্বার গুলোর বাটন নিচে:", reply_markup=reply_markup)


async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("buy", buy_command))

    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.Regex(r"^\S+\s+\S+$"), handle_sid_auth))

    logger.info("Bot started")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
