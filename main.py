import os
import re
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)
from random import randint

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}

# কানাডার বৈধ Area Codes সাধারণত 200-999 এর মধ্যে
def generate_canadian_numbers(area_code=None, count=30):
    numbers = []
    for _ in range(count):
        ac = area_code if area_code and 200 <= area_code <= 999 else randint(200, 999)
        number = f"+1{ac}{randint(1000000, 9999999)}"
        numbers.append(number)
    return numbers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name} Subscription চালু আছে, Login করুন", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
        [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
        [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
        [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
        [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন?", reply_markup=reply_markup)

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ আপনি ইতোমধ্যে Free Trial ব্যবহার করেছেন।")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ আপনার Free Trial Subscription চালু হয়েছে")
            asyncio.create_task(revoke_trial_later(user_id, context))

    elif query.data.startswith("plan_"):
        # এখানে Admin কে Subscription রিকোয়েস্ট পাঠানো যাবে (Optional)
        await query.edit_message_text("Subscription রিকোয়েস্ট পাঠানো হয়েছে।")

    elif query.data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন (Format: `<sid> <auth>`)")

    elif query.data.startswith("buy_number_"):
        number = query.data[len("buy_number_"):]
        sid_auth = user_sessions.get(user_id, {}).get("sid_auth")
        if not sid_auth:
            await query.edit_message_text("⚠️ আগে Log In করুন তারপর Try করুন")
            return
        sid, auth = sid_auth

        # Twilio balance চেক ও suspend চেক
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
            async with session.get(balance_url) as resp:
                if resp.status == 401:
                    await query.edit_message_text("টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                    return
                data = await resp.json()
                balance = float(data.get("balance", 0.0))
                if balance < 1.0:
                    await query.edit_message_text("আপনার টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                    return

        # সফল ক্রয়
        user_sessions.setdefault(user_id, {})
        user_sessions[user_id]["last_number"] = number
        await query.edit_message_text(
            f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\nনাম্বার: {number}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Message ✉️", callback_data="send_sms")]]
            )
        )

    elif query.data == "send_sms":
        await context.bot.send_message(chat_id=user_id, text="এই ফিচারটি এখনো তৈরী হয়নি।")

async def revoke_trial_later(user_id, context):
    await asyncio.sleep(3600)
    free_trial_users.pop(user_id, None)
    await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial শেষ হয়েছে")

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
                await update.message.reply_text("🎃 টোকেন Suspend হয়েছে, অন্য টোকেন ব্যবহার করুন")
                return
            data = await resp.json()
            account_name = data['accounts'][0]['friendly_name']
        balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
        async with session.get(balance_url) as b:
            balance_data = await b.json()
            balance = float(balance_data.get("balance", 0.0))
            user_sessions.setdefault(user_id, {})
            user_sessions[user_id]["sid_auth"] = (sid, auth)
            await update.message.reply_text(
                f"🎉 Log In Successful 🎉\n\n"
                f"⭕ Account Name : {account_name}\n"
                f"⭕ Account Balance : ${balance:.2f}\n\n"
                f"নাম্বার কিনার আগে ব্যালেন্স চেক করুন।"
            )

def extract_canadian_numbers(text):
    # কানাডিয়ান নাম্বার +1 AreaCode (3 digits) 7 digits নম্বরের সাথে খোঁজা
    pattern = r"(?:\+?1)?(2[0-9]{2}|[3-9][0-9]{2})([0-9]{7})"
    matches = re.findall(pattern, text)
    numbers = []
    for area, rest in matches:
        num = f"+1{area}{rest}"
        numbers.append(num)
    return list(set(numbers))  # ডুপ্লিকেট বাদ

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    args = context.args
    area_code = None
    if args and args[0].isdigit():
        area_code = int(args[0])

    numbers = generate_canadian_numbers(area_code=area_code)
    user_sessions.setdefault(user_id, {})
    user_sessions[user_id]["numbers"] = numbers

    msg = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)
    await update.message.reply_text(msg)

async def handle_number_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    if user_id not in user_sessions or "numbers" not in user_sessions[user_id]:
        return

    text = update.message.text
    numbers_found = extract_canadian_numbers(text)
    if not numbers_found:
        return

    for num in numbers_found:
        keyboard = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{num}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"নাম্বার: {num}", reply_markup=reply_markup)

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
    logger.info(f"Bot is running on port {port}...")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
