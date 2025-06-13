import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import random
import re

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database simulation
free_trial_users = {}
user_sessions = {}

# Canada area codes
CANADA_AREA_CODES = ['204', '236', '249', '250', '289', '306', '343', '365', '403', '416', '418', '431', '437', '438', '450', '506', '514', '519', '579', '581', '587', '604', '613', '639', '647', '672', '705', '709', '778', '780', '782', '807', '819', '825', '867', '873', '902', '905']

# Bot commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name} Subscription active! Please login:", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton("1 Hour - Free 🌸", callback_data="plan_free")],
        [InlineKeyboardButton("1 Day - $2", callback_data="plan_1d")],
        [InlineKeyboardButton("7 Days - $10", callback_data="plan_7d")],
        [InlineKeyboardButton("15 Days - $15", callback_data="plan_15d")],
        [InlineKeyboardButton("30 Days - $20", callback_data="plan_30d")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Welcome {user_name}!\nPlease choose a subscription plan:",
        reply_markup=reply_markup
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Your subscription is active. Please login:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ No active subscription. Please subscribe first.")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ No active subscription. Please subscribe first.")
        return

    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ Please login first using /login")
        return

    args = context.args
    selected_area_codes = []

    if args:
        area_code = args[0]
        if area_code in CANADA_AREA_CODES:
            selected_area_codes = [area_code] * 30
        else:
            await update.message.reply_text("⚠️ Invalid area code. Please provide a valid Canada area code.")
            return
    else:
        count = min(30, len(CANADA_AREA_CODES))
        selected_area_codes = random.sample(CANADA_AREA_CODES, count)

    phone_numbers = [f"+1{code}{random.randint(1000000, 9999999)}" for code in selected_area_codes]

    message_text = "Available numbers:\n\n" + "\n".join(phone_numbers)
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

    if query.data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ You already used free trial")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ Free trial activated (1 hour)")

            async def revoke():
                await asyncio.sleep(3600)
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(chat_id=user_id, text="⏰ Your free trial has expired")
            asyncio.create_task(revoke())

    elif query.data.startswith("plan_"):
        plan_info = {
            "plan_1d": ("1 Day", "$2"),
            "plan_7d": ("7 Days", "$10"),
            "plan_15d": ("15 Days", "$15"),
            "plan_30d": ("30 Days", "$20")
        }
        duration, price = plan_info.get(query.data, ("", ""))

        text = (
            f"{user_name} wants {duration} subscription\n\n"
            f"User ID: {user_id}\n"
            f"Username: @{username}"
        )
        buttons = [[InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
                   InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send {price} to complete payment\n\n"
            f"User ID: {user_id}\n"
            f"Plan: {duration}\n"
            f"Amount: {price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)

    elif query.data == "login":
        await context.bot.send_message(
            chat_id=user_id,
            text="Please enter your Twilio credentials in format:\n\n<SID> <AUTH_TOKEN>",
            parse_mode='Markdown'
        )

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(chat_id=uid, text="✅ Subscription activated")
        await query.edit_message_text("✅ Approved")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Request canceled")

    elif query.data == "cancel_buy":
        await query.edit_message_text("❌ Number selection canceled")

    elif query.data.startswith("number_"):
        selected_number = query.data[len("number_"):]
        buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{selected_number}")]])
        await context.bot.send_message(chat_id=user_id, text=f"Selected: {selected_number}", reply_markup=buy_button)

    elif query.data.startswith("buy_number_"):
        number_to_buy = query.data[len("buy_number_"):]
        session = user_sessions.get(user_id)
        
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(chat_id=user_id, text="❌ Please login first")
            return

        sid = session.get("sid")
        auth = session.get("auth")

        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
            try:
                # Get current balance
                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                async with session_http.get(balance_url) as balance_resp:
                    balance_data = await balance_resp.json()
                    current_balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                # Purchase number (Twilio API call)
                purchase_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
                payload = {
                    "PhoneNumber": number_to_buy,
                    "SmsUrl": "https://your-webhook-url.com/sms"  # Replace with your webhook
                }
                
                async with session_http.post(purchase_url, data=payload) as purchase_resp:
                    if purchase_resp.status != 201:
                        error = await purchase_resp.json()
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Purchase failed: {error.get('message', 'Unknown error')}"
                        )
                        return
                    
                    purchase_data = await purchase_resp.json()
                    actual_cost = float(purchase_data.get("cost", 0.0))

                # Get updated balance
                async with session_http.get(balance_url) as new_balance_resp:
                    new_balance_data = await new_balance_resp.json()
                    new_balance = float(new_balance_data.get("balance", 0.0))

                # Send confirmation
                success_msg = (
                    f"✅ Number purchased successfully!\n\n"
                    f"📞 Number: {number_to_buy}\n"
                    f"💸 Actual cost: {actual_cost:.2f} {currency}\n"
                    f"💰 New balance: {new_balance:.2f} {currency}"
                )
                
                await query.edit_message_text(
                    text=success_msg,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📨 View Messages", callback_data=f"msg_{number_to_buy}")]
                    ])
                )

            except Exception as e:
                logger.error(f"Purchase error: {str(e)}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Error during purchase. Please try again later."
                )

    elif query.data.startswith("msg_"):
        number = query.data[len("msg_"):]
        session = user_sessions.get(user_id)
        
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(chat_id=user_id, text="❌ Please login first")
            return

        sid = session.get("sid")
        auth = session.get("auth")

        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
                sms_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?To={number}"
                async with session_http.get(sms_url) as resp:
                    data = await resp.json()
                    messages = data.get("messages", [])

                    if messages:
                        latest = messages[0]
                        msg_text = (
                            f"📨 Latest message:\n\n"
                            f"From: {latest.get('from', 'Unknown')}\n"
                            f"Body: {latest.get('body', 'No content')}"
                        )
                        await query.edit_message_text(msg_text)
                    else:
                        await query.edit_message_text("No messages received yet")
        except Exception as e:
            logger.error(f"Message error: {str(e)}")
            await context.bot.send_message(chat_id=user_id, text="❌ Error fetching messages")

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

    # Handle login
    if " " in text:
        try:
            sid, auth = text.split(" ", 1)
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
                async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                    if resp.status == 401:
                        await update.message.reply_text("❌ Invalid credentials")
                        return
                    
                    data = await resp.json()
                    account_name = data['accounts'][0]['friendly_name']
                    
                    # Get balance
                    balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                    async with session.get(balance_url) as b:
                        balance_data = await b.json()
                        balance = float(balance_data.get("balance", 0.0))
                        currency = balance_data.get("currency", "USD")

                    user_sessions[user_id] = {
                        "sid": sid,
                        "auth": auth,
                        "logged_in": True
                    }

                    await update.message.reply_text(
                        f"✅ Login successful!\n\n"
                        f"Account: {account_name}\n"
                        f"Balance: {balance:.2f} {currency}"
                    )
                    return
        except Exception as e:
            logger.error(f"Login error: {str(e)}")

    # Handle number extraction
    numbers_found = extract_canada_numbers(text)
    if numbers_found:
        for number in numbers_found:
            buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{number}")]])
            await update.message.reply_text(f"Found number: {number}", reply_markup=buy_button)

async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

# Bot setup
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
    logger.info("Bot is running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
