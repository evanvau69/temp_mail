from flask import Flask, request
import telebot
import requests
import random
import string
import re
import os

API_TOKEN = os.environ.get("BOT_TOKEN")  # Render Dashboard থেকে সেট করবে
bot = telebot.TeleBot(API_TOKEN)

app = Flask(__name__)

user_data = {}

# Generate temp mail
def generate_email():
    login = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    domain = random.choice(["1secmail.com", "1secmail.org", "1secmail.net"])
    return login, domain

# Extract OTP
def extract_otp(text):
    matches = re.findall(r'\b\d{4,8}\b', text)
    return matches[0] if matches else None

# Receive new Telegram updates via webhook
@app.route(f"/{API_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

# Telegram command: /get_mail
@bot.message_handler(commands=['get_mail'])
def get_mail(message):
    user_id = message.chat.id
    login, domain = generate_email()
    user_data[user_id] = {'login': login, 'domain': domain, 'emails': []}
    email_address = f"{login}@{domain}"
    bot.send_message(user_id, f"📬 তোমার নতুন Temp Mail:\n`{email_address}`", parse_mode="Markdown")

# Check mail manually (bonus)
@bot.message_handler(commands=['check'])
def check_mail(message):
    user_id = message.chat.id
    if user_id not in user_data:
        bot.send_message(user_id, "❌ আগে /get_mail দিয়ে মেইল জেনারেট করো।")
        return

    login = user_data[user_id]['login']
    domain = user_data[user_id]['domain']
    prev_ids = user_data[user_id]['emails']
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    
    resp = requests.get(url).json()
    new_msgs = []

    for msg in resp:
        if msg['id'] not in prev_ids:
            user_data[user_id]['emails'].append(msg['id'])
            read_url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg['id']}"
            full_msg = requests.get(read_url).json()
            text = full_msg.get("textBody") or full_msg.get("htmlBody") or "(No text)"
            otp = extract_otp(text)
            if otp:
                bot.send_message(user_id, f"🔐 OTP পাওয়া গেছে:\n`{otp}`", parse_mode="Markdown")
            else:
                bot.send_message(user_id, f"✉️ মেইল এসেছে:\n\n{msg['subject']}\n\n{text}", parse_mode="Markdown")

    if not new_msgs:
        bot.send_message(user_id, "📭 নতুন কোনো মেইল পাওয়া যায়নি।")

# Root check
@app.route("/", methods=["GET"])
def root():
    return "Bot is running!"

