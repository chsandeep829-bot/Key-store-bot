import io
import random
import urllib.parse
import logging
import re
import threading
import json
import asyncio
import qrcode
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- CONFIGURATION ----------

TOKEN = "8790381588:AAFaYe8FSBBW5NL5mrirD2rcQiuiUVSisB0"
MERCHANT_UPI_ID = "paytm.s2zndyh@pty"
MERCHANT_NAME = "Key Store"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- DATA STORAGE & SECURITY LOCKS ----------

data_lock = threading.Lock()

# Global reference wrapper to allow our Webhook Thread to access the Telegram Bot App
bot_app_reference = None

# Track active checking orders. Format: { "ORD1234": {"user_id": 555666, "price": "120"} }
active_orders = {}

# Permanently logs claimed UTR numbers to block replay injection attacks
claimed_utrs = set()

# Product Stock List
license_keys = ["GPS-ABCD-1234-EFGH", "GPS-IJKL-5678-MNOP", "GPS-QRST-9012-UVWX"]

# ---------- MENUS ----------

main_menu = ReplyKeyboardMarkup([["🔑 Purchase Key", "📋 My Keys"], ["🎁 Redeem Code", "📖 How to Buy"], ["🆔 My ID", "🆘 Contact Support"]], resize_keyboard=True)
brands_menu = ReplyKeyboardMarkup([["GPS LOADER", "ZTRAX LOADER"], ["FIRE X LOADER", "SKIN LOADER"], ["⬅️ Back"]], resize_keyboard=True)
gps_menu = ReplyKeyboardMarkup([["1 DAY KEY - ₹120", "3 DAY KEY - ₹220"], ["7 DAY KEY - ₹320", "TEST KEY - ₹1"], ["⬅️ Back"]], resize_keyboard=True)
ztrax_menu = ReplyKeyboardMarkup([["ZTRAX 1 DAY - ₹120", "ZTRAX 3 DAY - ₹220"], ["ZTRAX 7 DAY - ₹320", "ZTRAX 5 HOURS - ₹60"], ["⬅️ Back"]], resize_keyboard=True)
firex_menu = ReplyKeyboardMarkup([["FIRE X 1 DAY - ₹120", "FIRE X 3 DAY - ₹220"], ["FIRE X 7 DAY - ₹320", "FIRE X 5 HOURS - ₹70"], ["⬅️ Back"]], resize_keyboard=True)
skin_menu = ReplyKeyboardMarkup([["SKIN 1 DAY - ₹120", "SKIN 3 DAY - ₹220"], ["SKIN 7 DAY - ₹320", "SKIN 5 HOURS - ₹70"], ["⬅️ Back"]], resize_keyboard=True)

# ---------- CORE SYSTEM UTILITIES ----------

def generate_upi_qr(price, order_reference_id):
    """Draws payment QR code target directly into ephemeral system RAM."""
    upi_payload = f"upi://pay?pa={MERCHANT_UPI_ID}&pn={urllib.parse.quote(MERCHANT_NAME)}&am={price}&cu=INR&tn={order_reference_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=3)
    qr.add_data(upi_payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    bio.name = 'upi_qr.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio, upi_payload

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Processes live bank notifications and delivers keys automatically."""
        global bot_app_reference
        try:
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))
            text = data.get("message", "")

            # 1. Parse standard 10-12 digit Indian banking UTR reference string
            utr_match = re.search(r'\b\d{10,12}\b', text)
            # 2. Parse the distinct Order Reference Token matching this payment (e.g., ORD1234)
            order_match = re.search(r'\b(ORD\d{4})\b', text)
            
            if utr_match and order_match:
                detected_utr = utr_match.group(0)
                detected_order = order_match.group(0)
                with data_lock:
                    # Guard against double claims or replay exploits
                    if detected_utr not in claimed_utrs and detected_order in active_orders:
                        order_info = active_orders[detected_order]
                        target_user_id = order_info["user_id"]
                        item_price = order_info["price"]
                        
                        if license_keys:
                            # Pop an available license product code out of stock pool array
                            delivered_product_key = license_keys.pop(0)
                            claimed_utrs.add(detected_utr)
                            active_orders.pop(detected_order, None)
                            logger.info(f"🚀 AUTO-DELIVERING KEY: UTR {detected_utr} maps to User ID {target_user_id}")
                            
                            # Push asynchronous key notification message context to user inside main thread loop
                            if bot_app_reference:
                                asyncio.run_coroutine_threadsafe(
                                    bot_app_reference.bot.send_message(
                                        chat_id=target_user_id,
                                        text=f"✅ *Payment Received & Verified!*\n\n"
                                             f"💵 Amount: *₹{item_price}*\n"
                                             f"🧾 UTR Reference: `{detected_utr}`\n\n"
                                             f"🔑 *Your License Key:* \n`{delivered_product_key}`",
                                        parse_mode="Markdown",
                                        reply_markup=main_menu
                                    ),
                                    bot_app_reference.loop
                                )
                        else:
                            logger.error("⚠️ Webhook matched user order, but license keys array stock is empty!")
                            if bot_app_reference:
                                asyncio.run_coroutine_threadsafe(
                                    bot_app_reference.bot.send_message(
                                        chat_id=target_user_id,
                                        text="⚠️ *Payment Received successfully!*\n\n"
                                             "However, our system is currently out of stock. Please show this message to support to get your key generated manually.",
                                        parse_mode="Markdown"
                                    ),
                                    bot_app_reference.loop
                                )
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            logger.error(f"Error parsing transaction tracking endpoint context: {e}")
            self.send_error(500)

def start_server():
    server = HTTPServer(("0.0.0.0", 8080), WebhookHandler)
    server.serve_forever()

# ---------- BOT SYSTEM ROUTINES ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to Key Store!", reply_markup=main_menu)

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Absolute priority check for Back navigation
    if "Back" in text or "⬅️" in text:
        await update.message.reply_text("Main Menu", reply_markup=main_menu)
        return

    if text == "🔑 Purchase Key":
        await update.message.reply_text("Select brand:", reply_markup=brands_menu)
    elif text == "GPS LOADER":
        await update.message.reply_text("⏳ Select:", reply_markup=gps_menu)
    elif text == "ZTRAX LOADER":
        await update.message.reply_text("⏳ Select:", reply_markup=ztrax_menu)
    elif text == "FIRE X LOADER":
        await update.message.reply_text("⏳ Select:", reply_markup=firex_menu)
    elif text == "SKIN LOADER":
        await update.message.reply_text("⏳ Select:", reply_markup=skin_menu)
    elif text == "🆔 My ID":
        await update.message.reply_text(f"ID: `{user_id}`", parse_mode="Markdown")
    elif any(icon in text for icon in ["🔑", "📋", "🎁", "📖", "🆘"]):
        return
    elif "₹" in text:
        price_match = re.findall(r'₹(\d+)', text)
        if price_match:
            price = price_match[0]
            random_order_suffix = random.randint(1000, 9999)
            order_reference_id = f"ORD{random_order_suffix}"
            with data_lock:
                active_orders[order_reference_id] = {"user_id": user_id, "price": price}
            qr_stream, link = generate_upi_qr(price, order_reference_id)
            caption = (
                f"💳 *Payment Request Generated*\n\n"
                f"💵 Amount to Pay: *₹{price}*\n"
                f"🧾 Transaction Reference ID: `{order_reference_id}`\n\n"
                f"👉 Scan the QR code using any UPI app (GPay/PhonePe/Paytm). "
                f"Your license key will be delivered right here in this chat **automatically** the instant the payment clears!"
            )
            await update.message.reply_photo(photo=qr_stream, caption=caption, parse_mode="Markdown")

if __name__ == '__main__':
    # Start separate backend network listening ports safely
    threading.Thread(target=start_server, daemon=True).start()

    # Run Telegram Application Factory setup pipelines
    app = ApplicationBuilder().token(TOKEN).build()
    bot_app_reference = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))
    print("Starting secure automatic-delivery bot system pipeline...")
    app.run_polling()

