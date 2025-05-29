import os
import re
import logging
import asyncio
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Admin Telegram ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}  # সেশন স্টোরেজ (যেখানে sid-auth token রাখা যেতে পারে)

# Canada এর প্রায় সকল Area Code লিস্ট (৫০+)
CANADA_AREA_CODES = [
    '204', '236', '250', '289', '343', '365', '387', '403', '416', '418', '431', '437',
    '438', '450', '506', '514', '519', '579', '581', '587', '604', '613', '639', '647',
    '672', '705', '709', '742', '778', '780', '782', '807', '819', '867', '873', '902',
    '905', '226', '249', '289', '365', '437', '519', '548', '613', '647', '705', '807',
    '905', '343', '289', '226'
]

# --- নাম্বার detect করার ফাংশন ---
def extract_canada_numbers(text):
    # Regex যা বিভিন্ন ফরম্যাটে নাম্বার ধরবে
    pattern = re.compile(r'(\+?1)?\s*[-.(]*\s*(\d{3})\s*[-.)]*\s*(\d{3})\s*[-.]*\s*(\d{4})')
    found_numbers = []
    for match in pattern.finditer(text):
        area_code = match.group(2)
        if area_code in CANADA_AREA_CODES:
            # +1XXXXXXXXXX ফরম্যাটে নাম্বার বানানো
            number = '+1' + area_code + match.group(3) + match.group(4)
            if number not in found_numbers:
                found_numbers.append(number)
    return found_numbers

# --- /start কমান্ড ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name}, Subscription চালু আছে, লগইন করুন", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
        [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
        [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
        [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
        [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চান?", reply_markup=reply_markup)

# --- /login কমান্ড ---
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

# --- Callback Handler ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name

    data = query.data

    if data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ আপনি আগেই Free Trial ব্যবহার করেছেন।")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ আপনার Free Trial Subscription চালু হয়েছে")

            async def revoke():
                await asyncio.sleep(3600)  # 1 ঘন্টা পরে
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial শেষ হয়েছে")

            asyncio.create_task(revoke())

    elif data.startswith("plan_") and data != "plan_free":
        plan_info = {
            "plan_1d": ("1 Day", "2$"),
            "plan_7d": ("7 Day", "10$"),
            "plan_15d": ("15 Day", "15$"),
            "plan_30d": ("30 Day", "20$")
        }
        duration, price = plan_info.get(data, ("Unknown", "0$"))

        text = (
            f"{user_name} {duration} Subscription নিতে চাচ্ছেন।\n\n"
            f"🔆 User Name : {user_name}\n"
            f"🔆 User ID : {user_id}\n"
            f"🔆 Username : @{query.from_user.username or 'N/A'}"
        )
        buttons = [
            [InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
             InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send {price} to Binance Pay ID.\n"
            f"পেমেন্টের প্রমাণ Admin-কে দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{query.from_user.username or 'N/A'}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: {price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)

    elif data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার: `<sid> <auth>`", parse_mode="Markdown")

    elif data.startswith("approve_"):
        uid = int(data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif data.startswith("buy_"):
        # buy_<number> ফরম্যাট থেকে নাম্বার বের করা
        buy_number = data[4:]
        # মেসেজ এডিট করে কনফার্মেশন দেখানো
        confirm_text = f"🎉 Congratulations! নাম্বারটি কিনা হয়েছে 🎉\n\nনাম্বার: {buy_number}"
        keyboard = [[InlineKeyboardButton("Message ✉️", callback_data=f"msg_{buy_number}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=confirm_text, reply_markup=reply_markup)

    elif data.startswith("msg_"):
        # message button এ ক্লিক করলে যা হবে (এখানে আপনি কাস্টমাইজ করতে পারবেন)
        msg_number = data[4:]
        await context.bot.send_message(chat_id=user_id, text=f"আপনি এই নাম্বার দিয়ে মেসেজ পাঠাতে চান: {msg_number}")

# --- /buy কমান্ড --- 
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই, প্রথমে Subscription নিন।")
        return

    args = context.args
    # যদি args থাকে এবং valid canada area code হয়, সেটা থেকে নাম্বার দিবে, না হলে র‍্যান্ডম ৩০ টি দিবে
    area_code = None
    if args:
        arg_code = args[0]
        if arg_code.isdigit() and arg_code in CANADA_AREA_CODES:
            area_code = arg_code

    # ৩০ টি নম্বর তৈরী করার জন্য (র‍্যান্ডম বা নির্দিষ্ট Area code)
    import random

    def generate_random_number(code):
        # 7 digit random অংশ
        rest = ''.join(str(random.randint(0,9)) for _ in range(7))
        return f"+1{code}{rest}"

    numbers_list = []
    if area_code:
        for _ in range(30):
            numbers_list.append(generate_random_number(area_code))
    else:
        for _ in range(30):
            code = random.choice(CANADA_AREA_CODES)
            numbers_list.append(generate_random_number(code))

    # ইউজারকে নাম্বার দেখানো
    msg_text = "আপনার নাম্বার গুলো হলো 👇👇\n\n" + "\n".join(numbers_list)
    await update.message.reply_text(msg_text)

# --- ইউজার যখন নাম্বার দিবে ---
async def handle_numbers_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই, প্রথমে Subscription নিন।")
        return

    text = update.message.text
    numbers = extract_canada_numbers(text)
    if not numbers:
        await update.message.reply_text("কোনো বৈধ Canada নাম্বার পাওয়া যায়নি। আবার চেষ্টা করুন।")
        return

    # reply তে সব নাম্বার ও নিচে আলাদা আলাদা Buy button দিতে হবে
    buttons = []
    for num in numbers:
        buttons.append([InlineKeyboardButton(f"Buy 💰", callback_data=f"buy_{num}")])

    # মেসেজ পাঠাবো
    reply_markup = InlineKeyboardMarkup(buttons)
    msg_text = "আপনার নাম্বার গুলো থেকে বাছাই করুন:\n\n" + "\n".join(numbers)
    await update.message.reply_text(msg_text, reply_markup=reply_markup)

# --- Sid এবং Auth Token handle করা ---
async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    text = update.message.text.strip()

    # যদি text Sid Auth ফরম্যাট না হয় তাহলে পাস
    if len(text.split()) != 2:
        # এটা মনে হবে নাম্বার, তাই অন্য ফাংশনে হ্যান্ডেল হবে
        return

    sid, auth = text.split()

    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
        try:
            # Twilio account verify
            async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                if resp.status == 401:
                    await update.message.reply_text("টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                    return
                data = await resp.json()
                account_name = data['accounts'][0]['friendly_name']

            # Twilio balance check
            balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
            async with session.get(balance_url) as bresp:
                if bresp.status != 200:
                    await update.message.reply_text("Balance check করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")
                    return
                balance_data = await bresp.json()
                balance = float(balance_data.get("balance", 0.0))
                currency = balance_data.get("currency", "USD")

                # যদি USD না হয় তাহলে রেট কনভার্ট করতে পারবেন (optional)

            await update.message.reply_text(
                f"🎉 Log In Successful 🎉\n\n"
                f"⭕ Account Name: {account_name}\n"
                f"⭕ Account Balance: ${balance:.2f}\n\n"
                f"বিঃদ্রঃ নাম্বার কিনার আগে অবশ্যই ব্যালেন্স চেক করবেন।"
            )
            # সেশন এ sid-auth সেট করা যাবে যদি প্রয়োজন হয়
            user_sessions[user_id] = (sid, auth)

        except Exception as e:
            logger.error(f"Error verifying Twilio token: {e}")
            await update.message.reply_text("টোকেন যাচাই করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")

# --- মূল Handler যুক্ত করা ---
async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    # Sid/Auth কে আলাদা হ্যান্ডেল করা
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))
    # নাম্বার detect করার জন্য আলাদা হ্যান্ডলার (যা আগে sid_auth এ পাস না হওয়া টেক্সট পাবেন)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_numbers_message))

    await application.initialize()
    await application.start()

    # Webhook সেটআপ (যদি প্রয়োজন হয়)
    from aiohttp import web
    async def handle_update(request):
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_post("/webhook", handle_update)
    await web._run_app(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
