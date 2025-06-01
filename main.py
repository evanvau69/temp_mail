import telebot
from telebot import types
import requests
from flask import Flask, request
import re

# === CONFIGURATION ===
API_TOKEN = 'YOUR_BOT_TOKEN'  # <-- এখানে তোমার Bot Token বসাও
CHANNEL_USERNAME = '@Evans_info'
WEBHOOK_URL = 'https://twilio-test-yqiu.onrender.com'  # <-- এখানে তোমার Render লিংক বসাও

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
user_sessions = {}  # Store user SID+AUTH

# === BUTTON GENERATORS ===
def join_verify_buttons():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Join 🟢", url="https://t.me/Evans_info"),
        types.InlineKeyboardButton("Verify ✅", callback_data="verify")
    )
    return markup

def login_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Login 🔑", callback_data="login"))
    return markup

def logout_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Log Out 🔙", callback_data="logout"))
    return markup

# === TWILIO LOGIN FUNCTION ===
def twilio_login(sid, token):
    try:
        acc = requests.get(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}.json',
            auth=(sid, token)
        )
        if acc.status_code != 200:
            return False, None, None

        name = acc.json().get('friendly_name', 'Unknown')

        balance_res = requests.get(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json',
            auth=(sid, token)
        )
        balance_data = balance_res.json()
        balance = float(balance_data['balance'])
        currency = balance_data['currency']

        # Currency convert if not USD
        if currency != 'USD':
            conv = requests.get(
                f"https://api.exchangerate.host/convert?from={currency}&to=USD&amount={balance}"
            ).json()
            balance = float(conv['result'])

        return True, name, f"{balance:.2f}"
    except:
        return False, None, None

# === /start HANDLER ===
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            bot.send_message(
                message.chat.id,
                "🎉 ধন্যবাদ বটটি এখন ব্যবহারের জন্য প্রস্তুত /login দিয়ে Log In করুন"
            )
        else:
            bot.send_message(
                message.chat.id,
                "🤖 বট ব্যবহার করতে চাইলে চ্যানেলে জয়েন থাকতে হবে",
                reply_markup=join_verify_buttons()
            )
    except:
        bot.send_message(message.chat.id, "❌ চ্যানেল যাচাই করা যাচ্ছে না। বটকে চ্যানেলের অ্যাডমিন বানান।")

# === VERIFY BUTTON HANDLER ===
@bot.callback_query_handler(func=lambda call: call.data == 'verify')
def verify_handler(call):
    user_id = call.from_user.id
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                "🎉 ধন্যবাদ বটটি এখন ব্যবহারের জন্য প্রস্তুত /login দিয়ে Log In করুন"
            )
        else:
            bot.answer_callback_query(
                call.id,
                "🍁 আগে Join বাটনে ক্লিক করে চ্যানেলে জয়েন হয়ে নে তার পর Verify কর ♻️",
                show_alert=True
            )
    except:
        bot.answer_callback_query(call.id, "❌ যাচাই করা যাচ্ছে না।")

# === /login HANDLER ===
@bot.message_handler(commands=['login'])
def login_command(message):
    bot.send_message(
        message.chat.id,
        "Login করার জন্য নিচের বাটনে ক্লিক করুন",
        reply_markup=login_button()
    )

# === LOGIN BUTTON CLICK ===
@bot.callback_query_handler(func=lambda call: call.data == 'login')
def login_click(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(
        call.message.chat.id,
        "অনুগ্রহ করে `<SID> <AUTH>` ফরম্যাটে পাঠান",
        parse_mode='Markdown'
    )

# === CREDENTIAL INPUT HANDLER ===
@bot.message_handler(func=lambda m: re.match(r'^AC[a-zA-Z0-9]{32} [a-zA-Z0-9]{32}$', m.text.strip()))
def sid_auth_handler(message):
    sid, auth = message.text.strip().split()
    success, name, balance = twilio_login(sid, auth)

    if success:
        user_sessions[message.from_user.id] = {'sid': sid, 'auth': auth}
        bot.send_message(
            message.chat.id,
            f"""🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥 🎉

⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : `{name}`
⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : `${balance}`

বিঃদ্রঃ নাম্বার কিনার আগে ব্যালেন্স চেক করে নিবেন ♻️
নাম্বার কিনার জন্য এই বট ব্যবহার করুন : @Twiliowork_bot

Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁
""",
            parse_mode='Markdown',
            reply_markup=logout_button()
        )
    else:
        bot.send_message(
            message.chat.id,
            "🎃 Congratulations 🎉 আপনার টোকেন নষ্ট হয়ে গেছে, অন্য টোকেন ব্যবহার করুন",
            reply_markup=login_button()
        )

# === LOGOUT BUTTON ===
@bot.callback_query_handler(func=lambda call: call.data == 'logout')
def logout_user(call):
    user_sessions.pop(call.from_user.id, None)
    bot.edit_message_text("Log Out Success ✅", call.message.chat.id, call.message.message_id)

# === WEBHOOK HANDLER ===
@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
        return 'ok', 200
    return 'invalid', 403

# === RUN FLASK APP ===
if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=8080)
