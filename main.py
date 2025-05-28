import os
import logging
import asyncio
import aiohttp
import re
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

free_trial_users = {}
user_sessions = {}
user_twilio = {}

# Utility function to detect Canada numbers from any message
def extract_canada_numbers(text):
    return list(set(re.findall(r"\+?1\d{10}", text)))

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
        [InlineKeyboardButton("🔸 7 Day - 10$", callback_data="plan_7d")],
        [InlineKeyboardButton("🔹 15 Day - 15$", callback_data="plan_15d")],
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
        text = f"{user_name} {duration} Subscription নিতে চাচ্ছে।\n\n🔆 Username : @{username}\n🔆 User ID : {user_id}"
        buttons = [[InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}"), InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]]
        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(buttons))
        await context.bot.send_message(chat_id=user_id, text=f"Please send ${price} to Binance Pay ID: ...\nপেমেন্ট প্রমাণ Admin @Mr_Evan3490 কে দিন\n\nPlan: {duration}, Amount: ${price}")

    elif query.data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`", parse_mode='Markdown')

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ আপনার Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription বাতিল করা হয়েছে।")

    elif query.data.startswith("buy_"):
        phone = query.data.split("_", 1)[1]
        session = user_twilio.get(user_id)
        if not session:
            await query.edit_message_text("❌ Token সেট করা হয়নি। Login করুন।")
            return
        sid, auth = session
        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as s:
                # Try buying number
                payload = {"PhoneNumber": phone}
                url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
                async with s.post(url, data=payload) as resp:
                    if resp.status == 401:
                        await query.edit_message_text("টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                        return
                    elif resp.status != 201:
                        await query.edit_message_text("আপনার  টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                        return
                    await query.edit_message_text(f"🎉 Congestion  নাম্বারটি কিনা হয়েছে 🎉\n\n{phone}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Message ✉️", callback_data="msg")]]))
        except:
            await query.edit_message_text("⚠️ নাম্বার কেনা যায়নি, আবার চেষ্টা করুন")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    text = update.message.text
    if re.fullmatch(r".*1\d{10}.*", text):
        numbers = extract_canada_numbers(text)
        for number in numbers:
            keyboard = [[InlineKeyboardButton("Buy 💰", callback_data=f"buy_{number}")]]
            await update.message.reply_text(f"{number}", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    try:
        sid, auth = text.strip().split(" ", 1)
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
                user_twilio[user_id] = (sid, auth)
                await update.message.reply_text(f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\nবিঃদ্রঃ নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন ♻️\nFounded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁")
    except:
        await update.message.reply_text("⚠️ সঠিকভাবে Sid এবং Auth দিন, উদাহরণ: `<sid> <auth>`", parse_mode='Markdown')

async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
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
