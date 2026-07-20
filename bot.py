import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8790381588:AAFiGFwf5OhhyEkbRdvpbmhwuPx6QdRVVVQ"  # Replace with your fresh BotFather token
KEYS_FILE = "license_keys"

# Helper functions to read and write keys safely
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

# Telegram /start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔑 Purchase Key", callback_data="buy_key")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to Key Store Bot! Click below to buy a key:", reply_markup=reply_markup)

# Handle Button Clicks
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "buy_key":
        order_id = "ORD" + str(abs(hash(str(query.from_user.id))))[:6]
        await query.message.reply_text(
            f"Please make a payment of ₹18000.\nYour Order ID is: `{order_id}`\n\nOnce paid, your key will be delivered automatically!",
            parse_mode="Markdown"
        )

# Webhook Server for Payments (Runs alongside Telegram bot)
class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            message_text = data.get("message", "")
            
            # Check if payment message contains an order ID and UTR
            if "ORD" in message_text:
                # Find unused key
                store_data = load_keys()
                assigned_key = None
                
                for k in store_data.get("keys", []):
                    if k.get("status") == "Not Used":
                        k["status"] = "Used"
                        assigned_key = k.get("key")
                        break
                
                if assigned_key:
                    save_keys(store_data)
                    print(f"Successfully dispensed key: {assigned_key}")
                else:
                    print("Payment received, but out of stock!")
                    
        except Exception as e:
            print(f"Error processing webhook: {e}")
            
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"Webhook server running on port {port}")
    server.serve_forever()

def main():
    # Start the HTTP webhook server in a background thread
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    # Start Telegram Bot application
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Starting Telegram bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
