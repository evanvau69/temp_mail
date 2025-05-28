import os
import logging
import asyncio
import aiohttp
import re
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters
)

# Environment Variables (Render এ environment থেকে বসাতে হবে)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ডাটা স্টোরেজ (সাধারণ dict, প্রডাকশনে DB ব্যবহার করা উচিত)
free_trial_users = {}      # user_id: "active"
paid_subscriptions = {}    # user_id: {"plan": plan_name, "active": True}
user_sessions = {}         # user_id: {"sid": "", "auth": ""}
user_buy_messages = {}     # user_id: message_id (নাম্বার লিস্ট মেসেজ)

# কানাডার নম্বরের একটা উদাহরণ লিস্ট (প্লাস কোড ছাড়া, শুধু নম্বর)
canada_numbers = [
    "+12015550101", "+12015550102", "+12015550103", "+12015550104",
    "+12015550105", "+12015550106", "+12015550107", "+12015550108",
    "+12015550109", "+12015550110", "+12015550111", "+12015550112",
    "+12015550113", "+12015550114", "+12015550115", "+12015550116",
    "+12015550117", "+12015550118", "+12015550119", "+12015550120",
    "+12015550121", "+12015550122", "+12015550123", "+12015550124",
    "+12015550125", "+12015550126", "+12015550127", "+12015550128",
    "+12015550129", "+12015550130"
]

# ====================
# /start কমান্ড হ্যান্ডলার
# ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    username = update.effective_user.username or "N/A"

    if paid_subscriptions.get(user_id, {}).get("active"):
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name} Subscription চালু আছে এবার Log In করুন", reply_markup=reply_markup)
        return

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name} Free Trial চলছে, এবার Log In করুন", reply_markup=reply_markup)
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

# ======================
# /login কমান্ড হ্যান্ডলার
# ======================
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if paid_subscriptions.get(user_id, {}).get("active") or free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

# ======================
# Callback Query হ্যান্ডলার
# ======================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    # ==== Free Trial Plan ====
    if query.data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ আপনি এরই মধ্যে Free Trial ব্যবহার করেছেন।")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ আপনার Free Trial Subscription টি চালু হয়েছে")

            async def revoke():
                await asyncio.sleep(3600)  # ১ ঘন্টা পরে
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial টি শেষ হতে যাচ্ছে")
            asyncio.create_task(revoke())
        return

    # ==== Paid Plans ====
    if query.data.startswith("plan_") and query.data != "plan_free":
        plan_info = {
            "plan_1d": ("1 Day", "2"),
            "plan_7d": ("7 Day", "10"),
            "plan_15d": ("15 Day", "15"),
            "plan_30d": ("30 Day", "20")
        }
        duration, price = plan_info.get(query.data, ("", ""))

        text = (
            f"{user_name} {duration} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user_name}\n"
            f"🔆 User ID : {user_id}\n"
            f"🔆 Username : @{username}"
        )
        buttons = [
            [InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}_{duration}_{price}"),
             InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send ${price} to Binance Pay ID:\n"
            f"পেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{username}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: ${price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)
        return

    # ==== Approve Subscription ====
    if query.data.startswith("approve_"):
        parts = query.data.split("_")
        uid = int(parts[1])
        plan = parts[2]
        price = parts[3]
        paid_subscriptions[uid] = {"plan": plan, "active": True}
        await context.bot.send_message(chat_id=uid, text=f"✅ আপনার {plan} Subscription চালু করা হয়েছে")
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")
        return

    # ==== Cancel Subscription ====
    if query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")
        return

    # ==== Login Button ====
    if query.data == "login":
        await context.bot.send_message(chat_id=user_id, text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`", parse_mode='Markdown')
        return

    # ==== Buy Button ====
    if query.data.startswith("buy_"):
        # data format: buy_<number>
        number = query.data[4:]
        # Check balance and token status from session
        session = user_sessions.get(user_id)
        if not session:
            await query.answer("❌ আপনি লগইন করেননি। /login দিন।", show_alert=True)
            return

        sid = session.get("sid")
        auth = session.get("auth")

        # Simulate buying number: এখানে আসল লজিক দিতে হবে যেমন DB এ সেভ বা API কল
        # আগের Buy মেসেজ ডিলিট করা হবে
        if user_buy_messages.get(user_id):
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=user_buy_messages[user_id])
            except:
                pass

        buy_text = (
            f"🎉 আপনি সফলভাবে নাম্বার কিনেছেন:\n\n"
            f"📞 Number: {number}\n"
            f"⭕ User: {user_name}\n"
            f"⏰ সময় সীমা: ১ মাস\n\n"
            f"🙏 নাম্বার ব্যবহার করুন সাবধানে।"
        )
        sent_msg = await context.bot.send_message(chat_id=user_id, text=buy_text)
        user_buy_messages[user_id] = sent_msg.message_id
        return

# ===========================
# /buy কমান্ড: কানাডার নাম্বার লিস্ট দেখাবে
# ===========================
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # সাবস্ক্রিপশন চেক
    if not (paid_subscriptions.get(user_id, {}).get("active") or free_trial_users.get(user_id) == "active"):
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে /start এ গিয়ে Subscription নিন।")
        return

    # আগের Buy মেসেজ থাকলে ডিলিট কর
    if user_buy_messages.get(user_id):
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=user_buy_messages[user_id])
        except:
            pass

    # নাম্বার বাটন তৈরি করা
    keyboard = []
    for num in canada_numbers[:20]:  # প্রথম ২০ নাম্বার
        kb_num = num.replace("+1", "")  # প্লাস ওয়ান বাদ দিয়ে দেখানো
        keyboard.append([InlineKeyboardButton(kb_num, callback_data=f"buy_{num}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    sent = await update.message.reply_text("নিচের নাম্বার গুলোর মধ্যে একটি সিলেক্ট করুন:", reply_markup=reply_markup)
    user_buy_messages[user_id] = sent.message_id

# ========================
# Sid/Auth Token হ্যান্ডলার
# ========================
async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not (paid_subscriptions.get(user_id, {}).get("active") or free_trial_users.get(user_id) == "active"):
        return

    try:
        sid, auth = text.split(" ", 1)
    except Exception:
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

            user_sessions[user_id] = {"sid": sid, "auth": auth}
            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                f"বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 চেক করে নিবেন কম ব্যালেন্স থাকলে নাম্বার কিনা যাবে না ♻️\n\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )

# ====================
# Webhook হ্যান্ডলার
# ====================
async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

# ====================
# Application সেটআপ
# ====================
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))

# ====================
# Run Webhook
# ====================
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
