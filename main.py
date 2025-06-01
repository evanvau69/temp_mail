import telebot
from telebot import types
from flask import Flask, request

API_TOKEN = '7947607009:AAEJ4PoR-YrfvIWOBDHJ3yW4kB4BDK4xpfQ'
CHANNEL_USERNAME = '@Evans_info'
WEBHOOK_PATH = "bot-evan-x123456"
WEBHOOK_URL = f"https://twilio-test-yqiu.onrender.com/bot-evan-x123456"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
user_messages = {}

def is_user_in_channel(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if is_user_in_channel(user_id):
        bot.send_message(user_id, "🎉 ধন্যবাদ বটটি এখন ব্যবহারের জন্য প্রস্তুত /login দিয়ে Log In করুন")
    else:
        markup = types.InlineKeyboardMarkup()
        join_btn = types.InlineKeyboardButton("Join 🟢", url="https://t.me/Evans_info")
        verify_btn = types.InlineKeyboardButton("Verify ✅", callback_data="verify_join")
        markup.add(join_btn, verify_btn)
        sent = bot.send_message(user_id, "বট ব্যবহার করতে চাইলে চ্যানেলে জয়েন থাকতে হবে", reply_markup=markup)
        user_messages[user_id] = sent.message_id

@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def handle_verify(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if is_user_in_channel(user_id):
        if user_id in user_messages:
            try:
                bot.delete_message(chat_id, user_messages[user_id])
            except:
                pass
        bot.send_message(chat_id, "🎉 ধন্যবাদ বটটি এখন ব্যবহারের জন্য প্রস্তুত /login দিয়ে Log In করুন")
    else:
        bot.send_message(chat_id, "🍁 আগে Join বাটনে ক্লিক করে চ্যানেলে জয়েন হয়ে নে তার পর Verify কর ♻️")

# ✅ /login handler
@bot.message_handler(commands=['login'])
def handle_login(message):
    markup = types.InlineKeyboardMarkup()
    login_btn = types.InlineKeyboardButton("Login 🔑", callback_data="start_login")
    markup.add(login_btn)
    bot.send_message(message.chat.id, "Login করার জন্য নিচের বাটনে ক্লিক করুন", reply_markup=markup)

# === Webhook Route ===
@app.route(f"/{WEBHOOK_PATH}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

# === Set Webhook ===
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=8080)
