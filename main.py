import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # আপনার Admin Telegram User ID

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# একটা সিম্পল স্টোরেজ (ডাটাবেস নয়, সেশন হিসেবে)
user_permissions = {}
free_trial_users = set()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if user_id in user_permissions and user_permissions[user_id] == "subscribed":
        # Already subscribed user
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name}, আপনার Subscription চালু আছে। এখন Login করুন।", reply_markup=reply_markup)
    elif user_id in free_trial_users:
        await update.message.reply_text("আপনার Free Trial ইতিমধ্যে চালু আছে।")
    else:
        keyboard = [
            [InlineKeyboardButton(" 1 Hour - Free 🌸", callback_data="free_trial")],
            [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="1_day")],
            [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="7_day")],
            [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="15_day")],
            [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="30_day")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Welcome {user_name} 🌸\nআপনি কোনটি নিতে চাচ্ছেন..?", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "NoUsername"

    if query.data == "free_trial":
        if user_id in free_trial_users:
            await query.edit_message_text("আপনি ইতিমধ্যে Free Trial ব্যবহার করেছেন।")
            return
        free_trial_users.add(user_id)
        user_permissions[user_id] = "free_trial"
        await query.edit_message_text("আপনার Free Trial Subscription টি চালু হয়েছে ✅")
        # TODO: এখানে ফ্রি ট্রায়াল সময় শেষ হলে মেসেজ পাঠানো এবং permission বাতিল করার লজিক যোগ করতে হবে
        return

    # If user clicked on paid subscription
    plans = {
        "1_day": ("1 Day", 2),
        "7_day": ("7 Day", 10),
        "15_day": ("15 Day", 15),
        "30_day": ("30 Day", 20),
    }

    if query.data in plans:
        plan_name, amount = plans[query.data]
        # Admin কে মেসেজ পাঠানোর লজিক (Bot এ নিজেই)
        msg = (
            f"🔆 User Name : {user_name}\n"
            f"🔆 User Id : {user_id}\n"
            f"🔆 Username : @{username}\n\n"
            f"Subscription নিতে চাচ্ছে: {plan_name} - ${amount}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
             InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]))
        await query.edit_message_text("Admin কে Subscription অনুরোধ পাঠানো হয়েছে। অনুগ্রহ করে অপেক্ষা করুন।")

    # Approve or Cancel by admin
    if query.data.startswith("approve_") or query.data.startswith("cancel_"):
        if query.from_user.id != ADMIN_ID:
            await query.answer("আপনি এ কাজ করার অনুমতি পাচ্ছেন না!", show_alert=True)
            return
        target_user_id = int(query.data.split("_")[1])
        if query.data.startswith("approve_"):
            user_permissions[target_user_id] = "subscribed"
            await context.bot.send_message(chat_id=target_user_id, text="আপনার Subscription অনুমোদিত হয়েছে। Login করুন।")
            await query.edit_message_text("Subscription Approved ✅")
        else:
            await context.bot.send_message(chat_id=target_user_id, text="Subscription অনুরোধ বাতিল করা হয়েছে।")
            await query.edit_message_text("Subscription Cancelled ❌")

    if query.data == "login":
        await query.edit_message_text("Login করার ব্যবস্থা এখানে দিবেন।")

async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

if __name__ == "__main__":
    from aiohttp import web
    import asyncio

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    web_app = web.Application()
    web_app.router.add_post(f"/{BOT_TOKEN}", handle_update)

    port = int(os.environ.get("PORT", "10000"))

    logging.info(f"Starting server on port {port}")

    web.run_app(web_app, host="0.0.0.0", port=port)
