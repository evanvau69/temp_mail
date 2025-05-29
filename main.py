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
user_sessions = {}

CANADA_AREA_CODES = ['204', '236', '249', '250', '289', '306', '343', '365', '403', '416', '418', '431', '437', '438', '450', '506', '514', '519', '579', '581', '587', '604', '613', '639', '647', '672', '705', '709', '778', '780', '782', '807', '819', '825', '867', '873', '902', '905']

# Cost per number (Assuming fixed cost, can adjust if needed)
NUMBER_COST = 1.0  # $1 per number (আপনি চাইলে পরিবর্তন করতে পারেন)

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

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
        return

    args = context.args
    selected_area_codes = []

    if args:
        area_code = args[0]
        if area_code in CANADA_AREA_CODES:
            selected_area_codes = [area_code] * 30
        else:
            await update.message.reply_text("⚠️ আপনার দেওয়া area code পাওয়া যায়নি। অনুগ্রহ করে সঠিক কানাডার area code দিন।")
            return
    else:
        count = min(30, len(CANADA_AREA_CODES))
        selected_area_codes = random.sample(CANADA_AREA_CODES, count)

    phone_numbers = [f"+1{code}{random.randint(1000000, 9999999)}" for code in selected_area_codes]

    message_text = "আপনার নাম্বার গুলো হলো 👇👇\n\n" + "\n".join(phone_numbers)
    buttons = [[InlineKeyboardButton(num, callback_data=f"number_{num}")] for num in phone_numbers]
    buttons.append([InlineKeyboardButton("Cancel ❌", callback_data="cancel_buy")])
    reply_markup = InlineKeyboardMarkup(buttons)

    sent_msg = await update.message.reply_text(message_text, reply_markup=reply_markup)

    async def delete_message():
        await asyncio.sleep(300)
        try:
            await sent_msg.delete()
        except:
            pass

    asyncio.create_task(delete_message())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    # ফ্রি প্ল্যান নেওয়া
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

    # Subscription প্ল্যান রিকোয়েস্ট (অ্যাডমিনের কাছে যাবে)
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
        buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{selected_number}")]])
        await context.bot.send_message(chat_id=user_id, text=f"{selected_number}", reply_markup=buy_button)

    elif query.data.startswith("buy_number_"):
        number_to_buy = query.data[len("buy_number_"):]

        # Check user session login & token
        session = user_sessions.get(user_id)
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(chat_id=user_id, text="❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
            return

        sid = session.get("sid")
        auth = session.get("auth")

        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
            # Check Twilio account status and balance
            try:
                async with session_http.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                    if resp.status == 401:
                        await context.bot.send_message(chat_id=user_id, text="টোকেন Suspend হয়েছে 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                        return
                    data = await resp.json()
                    account_sid = data['accounts'][0]['sid']

                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Balance.json"
                async with session_http.get(balance_url) as balance_resp:
                    balance_data = await balance_resp.json()
                    balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                # Convert currency to USD if needed
                if currency != "USD":
                    rate_url = f"https://open.er-api.com/v6/latest/{currency}"
                    async with session_http.get(rate_url) as rate_resp:
                        rates = await rate_resp.json()
                        usd_rate = rates["rates"].get("USD", 1)
                        balance *= usd_rate

                if balance < NUMBER_COST:
                    await context.bot.send_message(chat_id=user_id, text="আপনার  টোকেনে পর্যাপ্ত ব্যালেন্স নাই 😥 অন্য টোকেন ব্যবহার করুন ♻️")
                    return

                # Simulate buying number (actual buying API calls should be added here if available)
                # For now, assume buy is successful and deduct cost from balance variable (just for display)
                balance_after = balance - NUMBER_COST

                # Edit original message that had the number + buy button
                # Find message to edit (callback query message)
                message = query.message
                new_text = (
                    f"🎉 Congestion নাম্বারটি কিনা হয়েছে 🎉\n\n"
                    f"☯️ Your Number : {number_to_buy}\n"
                    f"☯️ Your Balance : ${balance_after:.2f}\n"
                    f"☯️ Cost : ${NUMBER_COST:.2f}"
                )
                message_buttons = [[InlineKeyboardButton("📧 Message ✉️", callback_data=f"message_{number_to_buy}")]]
                new_markup = InlineKeyboardMarkup(message_buttons)

                await message.edit_text(new_text, reply_markup=new_markup)

            except Exception as e:
                logger.error(f"Error during buy_number: {e}")
                await context.bot.send_message(chat_id=user_id, text="কিছু ভুল হয়েছে, আবার চেষ্টা করুন।")

    elif query.data.startswith("message_"):
        selected_number = query.data[len("message_"):]
        session = user_sessions.get(user_id)
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(chat_id=user_id, text="❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
            return

        sid = session.get("sid")
        auth = session.get("auth")

        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
                # Get messages received on this number
                sms_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?To={selected_number}"
                async with session_http.get(sms_url) as resp:
                    data = await resp.json()
                    messages = data.get("messages", [])

                    if messages:
                        latest = messages[0]
                        body = latest.get("body", "❓ কোন কন্টেন্ট নেই")
                        from_number = latest.get("from", "Unknown")

                        new_text = (
                            f"📨 নতুন মেসেজ পাওয়া গেছে ✅\n\n"
                            f"🔸 From: {from_number}\n"
                            f"🔸 Body: {body}"
                        )
                        await query.edit_message_text(new_text)
                    else:
                        original_text = query.message.text
                        await query.edit_message_text("No message received ❌")

                        async def revert_text():
                            await asyncio.sleep(5)
                            try:
                                await query.message.edit_text(original_text, reply_markup=query.message.reply_markup)
                            except:
                                pass

                        asyncio.create_task(revert_text())
        except Exception as e:
            logger.error(f"Message fetch error: {e}")
            await context.bot.send_message(chat_id=user_id, text="🚫 মেসেজ পড়তে সমস্যা হয়েছে, পরে চেষ্টা করুন।")


# ✅ Updated function to detect Canada numbers from messy text
def extract_canada_numbers(text: str):
    results = set()
    digits_only = re.findall(r'\d{10,11}', text)

    for number in digits_only:
        digits = number[-10:]
        area_code = digits[:3]

        if area_code in CANADA_AREA_CODES:
            formatted = "+1" + digits
            results.add(formatted)

    return list(results)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    text = update.message.text.strip()

    # First try login
    if " " in text:
        try:
            sid, auth = text.split(" ", 1)
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
                            balance *= usd_rate

                    user_sessions[user_id] = {"sid": sid, "auth": auth, "logged_in": True}

                    await update.message.reply_text(
                        f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                        f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
                        f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
                    )
                    return
        except:
            pass

    # Then try number extraction
    numbers_found = extract_canada_numbers(text)
    if not numbers_found:
        return

    for number in numbers_found:
        buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{number}")]])
        await update.message.reply_text(f"আপনার দেওয়া নাম্বারটি শনাক্ত হলো:\n{number}", reply_markup=buy_button)

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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

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
