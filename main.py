import telebot
from telebot import types
from flask import Flask, request
import requests

API_TOKEN = '7947607009:AAEJ4PoR-YrfvIWOBDHJ3yW4kB4BDK4xpfQ'
CHANNEL_USERNAME = '@Evans_info'
WEBHOOK_PATH = "bot-evan-x123456"
WEBHOOK_URL = f"https://twilio-test-yqiu.onrender.com/bot-evan-x123456"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
user_messages = {}
user_login_state = {}

# ✅ চ্যানেল সাবস্ক্রিপশন চেক
def is_user_in_channel(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# ✅ START command
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

# ✅ Verify বাটনের কাজ
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

# ✅ /login কমান্ড
@bot.message_handler(commands=['login'])
def handle_login(message):
    markup = types.InlineKeyboardMarkup()
    login_btn = types.InlineKeyboardButton("Login 🔑", callback_data="start_login")
    markup.add(login_btn)
    bot.send_message(message.chat.id, "Login করার জন্য নিচের বাটনে ক্লিক করুন", reply_markup=markup)

# ✅ Login 🔑 বাটন হ্যান্ডলার
@bot.callback_query_handler(func=lambda call: call.data == "start_login")
def ask_for_login(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    user_login_state[user_id] = 'awaiting_login'
    bot.send_message(chat_id, "🔐 এখন নিচের মতো করে SID এবং AUTH TOKEN দিন:\n\n`ACxxxxxxxxxxxxxxxxx Yyyyyyyyyyyyyyyyyyyyyyy`", parse_mode="Markdown")

# ✅ SID + TOKEN ইনপুট হ্যান্ডলার
@bot.message_handler(func=lambda message: user_login_state.get(message.from_user.id) == 'awaiting_login')
def handle_sid_token(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        sid, token = message.text.strip().split()
    except:
        bot.send_message(chat_id, "❌ ভুল ফরম্যাট! দয়া করে এমনভাবে দিন:\n`SID AUTH_TOKEN`", parse_mode="Markdown")
        return

    ok, name, balance, currency = twilio_login(sid, token)

    if ok:
        user_login_state.pop(user_id)
        bot.send_message(chat_id, f"""🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥 🎉

⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : `{name}`
⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : `${balance}`

বিঃদ্রঃ  নাম্বার কিনার আগে অবশ্যই ব্যালেন্স চেক করে নিবেন ♻️
নাম্বার কিনার জন্য এই বট ব্যবহার করুন: @Twiliowork_bot

Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁
""", parse_mode="Markdown", reply_markup=logout_button())
    else:
        bot.send_message(chat_id, f"🎃 Congratulations 🎉 আপনার টোকেন নষ্ট হয়ে গেছে, অন্য টোকেন ব্যবহার করুন", reply_markup=login_button())

# ✅ Twilio login helper
def twilio_login(account_sid, auth_token):
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
        resp = requests.get(url, auth=(account_sid, auth_token))
        if resp.status_code != 200:
            return False, "Invalid credentials", None, None
        name = resp.json().get("friendly_name", "Unknown")
        bal_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Balance.json"
        bal_resp = requests.get(bal_url, auth=(account_sid, auth_token))
        if bal_resp.status_code != 200:
            return True, name, "0.00", "USD"
        bal_data = bal_resp.json()
        balance = bal_data.get("balance", "0.00")
        currency = bal_data.get("currency", "USD")
        return True, name, balance, currency
    except:
        return False, "Error", None, None

# ✅ Log Out button
def logout_button():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Log Out 🔙", callback_data="logout_user")
    markup.add(btn)
    return markup

# ✅ Login button (retry)
def login_button():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Login 🔑", callback_data="start_login")
    markup.add(btn)
    return markup

# ✅ Log Out callback
@bot.callback_query_handler(func=lambda call: call.data == "logout_user")
def logout_user(call):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "✅ Log Out Success")

# ✅ Webhook Route (for Render)
@app.route(f"/{WEBHOOK_PATH}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

# ✅ Webhook Setter
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=8080)
