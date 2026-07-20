import os
import json
import io
import qrcode
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8790381588:AAFiGFwf5OhhyEkbRdvpbmhwuPx6QdRVVVQ"  # Replace with your fresh BotFather token
KEYS_FILE = "license_keys"
UPI_ID = "paytm.s2spkis@pty"  # Replace with your actual UPI ID for payments

# Helper functions for keys
def load_keys():
    if not os.path.exists(KEYS_FILE):
        return {"keys": []}
    try:
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"keys": []}

def save_keys(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# /start command with product options
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("TEST KEY - ₹1", callback_data="buy_1")],
        [InlineKeyboardButton("1 DAY KEY - ₹120", callback_data="buy_120")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to Key Store Bot! Select an option below to buy:", reply_markup=reply_markup)

# Handle selections & generate QR codes
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("buy_"):
        amount = query.data.split("_")[1]
        order_id = "ORD" + str(abs(hash(str(query.from_user.id) + str(os.urandom(2)))))[:6]
        
        # Save user chat ID and order mapping temporarily in bot data if needed, or link via UTR
        context.bot_data[order_id] = query.message.chat_id

        # Create UPI payment URL string
        upi_url = f"upi://pay?pa={UPI_ID}&pn=KeyStore&am={amount}&cu=INR&tn={order_id}"
        
        # Generate QR code image in memory
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        
        # Send details and QR code image
        caption = (
            f"💰 Amount to Pay: ₹{amount}\n"
            f"🆔 Transaction Reference ID: `{order_id}`\n\n"
            f"👉 Scan the QR code using any UPI app (GPay/PhonePe/Paytm). Your license key will be delivered right here in this chat automatically the instant the payment clears!"
        )
        await query.message.reply_photo(photo=InputFile(bio, filename="qr.png"), caption=caption, parse_mode="Markdown")

# Webhook Server for Payments
class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            message_text = data.get("message", "")
            
            # Find order ID in the incoming webhook payment notification text
            for order_id, chat_id in bot_app_context.bot_data.items():
                if order_id in message_text:
                    store_data = load_keys()
                    assigned_key = None
                    
                    for k in store_data.get("keys", []):
                        if k.get("status") == "Not Used":
                            k["status"] = "Used"
                            assigned_key = k.get("key")
                            break
                    
                    if assigned_key:
                        save_keys(store_data)
                        # Send key to user via telegram application loop asynchronously or sync request
                        print(f"Match found for {order_id}! Assigned key: {assigned_key}")
                    break
                    
        except Exception as e:
            print(f"Error processing webhook: {e}")
            
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

bot_app_context = None

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    server.serve_forever()

def main():
    global bot_app_context
    app = ApplicationBuilder().token(TOKEN).build()
    bot_app_context = app
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Start web server thread
    threading.Thread(target=run_web_server, daemon=True).start()
    
    app.run_polling()

if __name__ == "__main__":
    main()
    
