import telebot
from telebot import types
import requests
from flask import Flask, request
import re

# === CONFIG ===
API_TOKEN = '7947607009:AAEJ4PoR-YrfvIWOBDHJ3yW4kB4BDK4xpfQ'
CHANNEL_USERNAME = '@Evans_info'
WEBHOOK_URL = 'https://twilio-test-yqiu.onrender.com/bot-evan-x123456'

# === BOT & FLASK INIT ===
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
user_sessions = {}  # store logged-in user sessions

# === MARKUPS ===
def join_verify_buttons():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton('Join 🟢', url='https://t.me/Evans_info'),
        types.InlineKeyboardButton('Verify ✅', callback_data='verify')
    )
    return markup

def login_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Login 🔑', callback_data='login'))
    return markup

def logout_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Log Out 🔙', callback_data='logout'))
    return markup

# === TWILIO LOGIN FUNCTION ===
def twilio_login(sid, token):
    try:
        acc = requests.get(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}.json',
            auth=(sid, token)
        )
        if acc.status_code == 200:
            acc_data = acc.json()
            name = acc_data.get('friendly_name', 'N/A')

            # Get balance
            balance_req = requests.get(
                f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json',
                auth=(sid, token)
            )
            balance_data = balance_req.json()
            balance = float(balance_data['balance'])
            currency = balance_data['currency']

            # Convert to USD if needed
            if currency != 'USD':
                rate_req = requests.get(f'https://api.exchangerate.host/convert?from={currency}&to=USD&amount={balance}')
                balance = float(rate_req.json()['result'])

            return True, name, f"{balance:.2f}"
    except:
        pass
    return False, None, None

# === START COMMAND ===
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
        bot.send_message(message.chat.id, "❌ চ্যানেল যাচাই করা যাচ্ছে না, বটকে অ্যাডমিন দিন।")

# === VERIFY BUTTON ===
@bot.callback_query_handler(func=lambda call: call.data == 'verify')
def verify_channel(call):
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

# === LOGIN COMMAND ===
@bot.message_handler(commands=['login'])
def login_command(message):
    bot.send_message(message.chat.id, "Login করার জন্য নিচের বাটনে ক্লিক করুন", reply_markup=login_button())

# === LOGIN BUTTON CLICK ===
@bot.callback_query_handler(func=lambda call: call.data == 'login')
def login_button_click(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(
        call.message.chat.id,
        "অনুগ্রহ করে `<SID> <AUTH>` ফরম্যাটে পাঠান।",
        parse_mode='Markdown'
    )

# === HANDLE SID AUTH TEXT ===
@bot.message_handler(func=lambda m: re.match(r'^AC[a-zA-Z0-9]{32} [a-zA-Z0-9]{32}$', m.text.strip()))
def handle_twilio_login(message):
    sid, token = message.text.strip().split()
    success, name, balance = twilio_login(sid, token)

    if success:
        user_sessions[message.from_user.id] = {'sid': sid, 'token': token}
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

# === LOG OUT ===
@bot.callback_query_handler(func=lambda call: call.data == 'logout')
def logout_handler(call):
    user_sessions.pop(call.from_user.id, None)
    bot.edit_message_text("Log Out Success ✅", call.message.chat.id, call.message.message_id)

# === FLASK ROUTE FOR WEBHOOK ===
@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'ok', 200
    return 'Invalid', 403

# === STARTUP HOOK ===
if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=8080)
