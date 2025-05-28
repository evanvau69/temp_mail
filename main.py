import os
import logging
import asyncio
import aiohttp
import random
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

# কানাডার নম্বরের একটা উদাহরণ লিস্ট (প্লাস কোডসহ)
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
        number = query.data[4:]
        session = user_sessions.get(user_id)
        if not session:
            await query.answer("❌ আপনি লগইন করেননি। /login দিন।", show_alert=True)
            return

        sid = session.get("sid")
        auth = session.get("auth")

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
# /buy কমান্ড: কানাডার নাম্বার লিস্ট দেখাবে (Area code অপশন সহ)
# ===========================
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not (paid_subscriptions.get(user_id, {}).get("active") or free_trial_users.get(user_id) == "active"):
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে /start এ গিয়ে Subscription নিন।")
        return

    if user_buy_messages.get(user_id):
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=user_buy_messages[user_id])
        except:
            pass

    args = context.args
    if args:
        area_code = args[0]
        # কানাডার নম্বর থেকে ফিল্টার করব, প্লাস ওয়ান বাদ দিয়ে পরে area_code চেক করব
        filtered_numbers = [num for num in canada_numbers if num[2:2+len(area_code)] == area_code]
        if not filtered_numbers:
            await update.message.reply_text(f"Area code '{area_code}' এর জন্য কোন নাম্বার পাওয়া যায়নি।")
            return
        numbers_to_show = filtered_numbers[:20]
    else:
        numbers_to_show = random.sample(canada_numbers, k=20)

    numbers_text = "\n".join(numbers_to_show)
    await update.message.reply_text(f"নিচে নাম্বার লিস্ট (২০ টি):\n\n{numbers_text}")

    keyboard = []
    for num in numbers_to_show:
        keyboard.append([InlineKeyboardButton(num, callback_data=f"buy_{num}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    sent = await update.message.reply_text("নিচের নাম্বার গুলোর মধ্যে একটি সিলেক্ট করুন:", reply_markup=reply_markup)
    user_buy_messages[user_id] = sent.message_id

# ===========================
# /sid <sid> <auth> কমান্ড দিয়ে লগইন
# ===========================
async def sid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 2:
        await update.message.reply_text("❌ ভুল ফরম্যাট! ব্যবহার করুন:\n/sid <sid> <auth>")
        return

    sid, auth = context.args
    user_sessions[user_id] = {"sid": sid, "auth": auth}
    await update.message.reply_text("✅ লগইন সফল হয়েছে!")

# ======================
# /help কমান্ড হ্যান্ডলার
# ======================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start - Subscription নিন\n"
        "/login - লগইন করুন\n"
        "/buy [area_code] - নাম্বার কিনুন (কানাডার)\n"
        "/sid <sid> <auth> - লগইন তথ্য দিন\n"
        "/help - সাহায্য"
    )
    await update.message.reply_text(help_text)

# ======================
# মেইন ফাংশন, বট শুরু
# ======================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("sid", sid_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot Started...")
    app.run_polling()

if __name__ == "__main__":
    main()
