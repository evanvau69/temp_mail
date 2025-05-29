import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import random

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}
user_sid_auth = {}
user_purchased_numbers = {}

canada_area_codes = ["204", "226", "236", "249", "250", "289", "306", "343", "365", "387", "403", "416", "418", "431", "437", "438", "450", "506", "514", "519", "548", "579", "581", "587", "604", "613", "639", "647", "672", "705", "709", "742", "778", "782", "807", "819", "825", "867", "873", "902", "905"]

def generate_random_number(area_code):
    return f"+1{area_code}{random.randint(2000000, 9999999)}"

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
        buttons = [[InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}"),
                    InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send ${price} to Binance Pay ID: \nপেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{username}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: ${price}"
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

    elif query.data.startswith("num_"):
        number = query.data.split("_", 1)[1]
        buttons = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_{number}")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await context.bot.send_message(chat_id=user_id, text=f"আপনি নির্বাচন করেছেন: {number}", reply_markup=reply_markup)

    elif query.data.startswith("buy_"):
        number = query.data.split("_", 1)[1]
        sid_auth = user_sid_auth.get(user_id)
        if not sid_auth:
            await context.bot.send_message(chat_id=user_id, text="⚠️ আপনি এখনো Log In করেননি।")
            return
        sid, auth = sid_auth
        
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            buy_url = "https://api.twilio.com/2010-04-01/Accounts/{}/IncomingPhoneNumbers.json".format(sid)
            data = {"PhoneNumber": number}

            # delete previous
            if user_purchased_numbers.get(user_id):
                prev_sid = user_purchased_numbers[user_id]
                delete_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{prev_sid}.json"
                await session.delete(delete_url)

            async with session.post(buy_url, data=data) as resp:
                if resp.status == 401:
                    await context.bot.send_message(chat_id=user_id, text="Token Suspended অন্য টোকেন দিয়ে Log In করুন ♻️")
                    return
                elif resp.status == 400:
                    await context.bot.send_message(chat_id=user_id, text="Token এ নাম্বার কিনার মতো Balance নাই অন্য টোকেন দিয়ে Log In করুন ♻️")
                    return
                result = await resp.json()
                user_purchased_numbers[user_id] = result['sid']

                buttons = [[InlineKeyboardButton("📧 Message ✉️", callback_data="msg")]]
                reply_markup = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    text=f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n{number}",
                    reply_markup=reply_markup
                )

    elif query.data == "cancel_numbers":
        await query.message.delete()
        await context.bot.send_message(chat_id=user_id, text="নাম্বার কিনা বাতিল হয়েছে ☢️")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return
    try:
        sid, auth = update.message.text.strip().split(" ", 1)
        user_sid_auth[user_id] = (sid, auth)
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
            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    numbers = []
    area_codes = random.sample(canada_area_codes, 30) if not args else [args[0]] * 30

    for area_code in area_codes:
        num = generate_random_number(area_code)
        numbers.append(num)

    text = "আপনার নাম্বার গুলো হলো 👇👇\n" + "\n".join(numbers)
    buttons = [[InlineKeyboardButton(num, callback_data=f"num_{num}")] for num in numbers]
    buttons.append([InlineKeyboardButton("Cancel ❌", callback_data="cancel_numbers")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(text, reply_markup=reply_markup)

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
