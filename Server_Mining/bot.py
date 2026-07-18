import logging
import os
import asyncio
import psycopg2
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, JobQueue
import requests
import uuid

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================== CONFIG ==================
# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Webhook Settings
WEBHOOK_URL = os.getenv("WEBHOOK_URL")          # Example: https://yourdomain.com
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8443))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# Check required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing!")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing!")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID is missing!")

if not PAYSTACK_SECRET_KEY:
    raise ValueError("PAYSTACK_SECRET_KEY is missing!")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is missing!")

if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID is missing!")

# Convert values after checking
ADMIN_ID = int(ADMIN_ID)
CHANNEL_ID = int(CHANNEL_ID)

MINERS = {
    "basic": {
        "name": "Basic Miner", 
        "price": 5000, 
        "gen": 500, 
        "image": "https://ibb.co/sdX78xnR"  # Basic mining rig
    },
    "transistor": {
        "name": "Transistor Miner", 
        "price": 12000, 
        "gen": 1500, 
        "image": "https://ibb.co/qLNCZFfF"  # Replace if needed
    },
    "diamond": {
        "name": "Diamond Miner", 
        "price": 25000, 
        "gen": 4000, 
        "image": "https://ibb.co/B5jWyqG3"
    },
    "micro": {
        "name": "Microprocessor Miner", 
        "price": 50000, 
        "gen": 10000, 
        "image": "https://ibb.co/qM9m0HgZ"
    },
    "ai": {
        "name": "AI Miner", 
        "price": 100000, 
        "gen": 25000, 
        "image": "https://ibb.co/zTYfTPXF"
    },
    "super": {
        "name": "Super Miner", 
        "price": 250000, 
        "gen": 70000, 
        "image": "https://ibb.co/vvXyv193"
    },
    "elite": {
        "name": "Elite Super Miner", 
        "price": 500000, 
        "gen": 150000, 
        "image": "https://ibb.co/whStTsJ9"
    }
}
# ============================================



conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    balance DOUBLE PRECISION DEFAULT 0,
    has_paid_entry INTEGER DEFAULT 0,
    referral_code TEXT,
    referred_by BIGINT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS user_miners (
    user_id BIGINT,
    miner_type TEXT,
    quantity INTEGER DEFAULT 1,
    last_claim TIMESTAMP
)
""")

c.execute("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'unique_miner'
    ) THEN
        ALTER TABLE user_miners
        ADD CONSTRAINT unique_miner
        UNIQUE(user_id, miner_type);
    END IF;
END $$;
""")

c.execute("""
CREATE TABLE IF NOT EXISTS pending_payments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    amount DOUBLE PRECISION,
    payment_type TEXT,
    miner_type TEXT,
    status TEXT DEFAULT 'pending',
    reference TEXT UNIQUE
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    amount DOUBLE PRECISION,
    bank_details TEXT,
    status TEXT DEFAULT 'pending'
)
""")

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    return c.fetchone()

def create_user(user_id, username, referred_by=None):
    ref_code = f"ref_{user_id}"
    c.execute("""
        INSERT INTO users (user_id, username, referral_code, referred_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
    """, (user_id, username, ref_code, referred_by))

def entry_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("💰 Pay Entry Fee ₦1000")]], resize_keyboard=True)

def full_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛒 Server Store")],
        [KeyboardButton("💰 Balance")],
        [KeyboardButton("📊 My Miners")],
        [KeyboardButton("👥 Referrals")],
        [KeyboardButton("⛏️ Claim Mining")],
        [KeyboardButton("💸 Withdraw")],
        [KeyboardButton("ℹ️ About")]
    ], resize_keyboard=True)

# ================== PAYSTACK HELPERS ==================
def initialize_paystack_payment(email: str, amount: int, metadata: dict = None, payment_type: str = None, miner_type: str = None):
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "email": email,
        "amount": amount * 100,  # Convert to kobo
        "reference": str(uuid.uuid4()),
        "metadata": metadata or {}
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Paystack init failed: {response.text}")
        return None

def verify_paystack_payment(reference: str):
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None
    create_user(user.id, user.username, referred_by)
    
    user_data = get_user(user.id)
    
    # Admin gets full access immediately (bypass payment)
    if user.id == ADMIN_ID:
        c.execute("UPDATE users SET has_paid_entry = 1 WHERE user_id = %s", (user.id,))
        await update.message.reply_text(
            "👑 Welcome Admin!\nYou have full access.", 
            reply_markup=full_menu_keyboard()
        )
        return
    
    # New users (never paid) get voice message + payment prompt
    if not user_data or user_data[3] == 0:
        
        await update.message.reply_voice(
                voice=open("welcome.mpeg", "rb"),
                caption="🎙️ Welcome to Server Mining"
            )
        
             

        await update.message.reply_text(
    """🚀 Welcome to Server Mining!

The future of virtual mining starts here. Turn your investment into a growing passive income stream, no much work needed.

With Server Mining, you can:
💰 Purchase powerful mining servers.
📈 Earn daily mining income rewards.
🚀 Upgrade to higher-performing servers.
👥 Earn referral bonuses by inviting friends.
💳 Withdraw your available earnings when eligible.
💵 We are expected to generate over $1.5M in the next two years from now

It only takes a one-time ₦1,000 registration fee to unlock your account and start building your mining business.

✨ The earlier you start, the faster you can grow, secure your financial future

👇 Tap the button below to pay your registration fee and get started!""",
    reply_markup=entry_keyboard()
)
    else:
        await update.message.reply_text("Welcome back! Use the menu below.", reply_markup=full_menu_keyboard())

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_amount") or context.user_data.get("waiting_for_bank"):
        return

    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)

    if "Pay Entry" in text:
        await pay_entry(update, context)
    elif user and user[3] == 1:
        if "Server Store" in text:
            await show_shop(update, context)
        elif "Balance" in text:
            await balance(update, context)
        elif "My Miners" in text:
            await my_miners(update, context)
        elif "Referrals" in text:
            await refer(update, context)
        elif "Claim Mining" in text:
            await claim_mining(update, context)
        elif "Withdraw" in text:
            await withdraw(update, context)
        elif "About" in text:
            await about(update, context)
    else:
        await update.message.reply_text("Complete entry payment first.", reply_markup=entry_keyboard())

async def pay_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    email = f"user_{user_id}@example.com"

    metadata = {
        "user_id": user_id,
        "payment_type": "entry"
    }

    result = initialize_paystack_payment(email, 1000, metadata)

    if result and result.get("status"):
        ref = result["data"]["reference"]
        auth_url = result["data"]["authorization_url"]

        c.execute(
            "INSERT INTO pending_payments (user_id, amount, payment_type, reference) VALUES (%s, %s, %s, %s)",
            (user_id, 1000, "entry", ref)
        )

        await update.message.reply_text(
            f"✅ Pay ₦1,000 Entry Fee via Paystack:\n\n"
            f"Click the link below to pay securely:\n{auth_url}\n\n"
            f"After payment, send /verify {ref} to confirm.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pay Now", url=auth_url)]])
        )
    else:
        await update.message.reply_text("❌ Failed to initialize payment. Try again.")

# [All functions below are 100% unchanged from your code]

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for key, data in MINERS.items():
        keyboard = [[InlineKeyboardButton("💰 Buy Now", callback_data=f"buy_{key}")]]
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=data["image"],
            caption=f"**{data['name']}**\n💰 Price: ₦{data['price']:,}\n📈 Daily Income: ₦{data['gen']:,}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        miner_key = query.data.split("_")[1]
        miner = MINERS[miner_key]
        user_id = query.from_user.id
        email = f"user_{user_id}@example.com"

        metadata = {
            "user_id": user_id,
            "payment_type": "miner",
            "miner_type": miner_key
        }

        result = initialize_paystack_payment(
            email,
            miner["price"],
            metadata
        )

        print(result)

        if result and result.get("status"):
            ref = result["data"]["reference"]
            auth_url = result["data"]["authorization_url"]

            c.execute(
                """
                INSERT INTO pending_payments
                (user_id, amount, payment_type, miner_type, reference)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    miner["price"],
                    "miner",
                    miner_key,
                    ref,
                ),
            )

            await query.message.reply_text(
                f"Pay here:\n{auth_url}"
            )

        else:
            await query.message.reply_text(
                f"Paystack Error:\n{result}"
            )

    except Exception as e:
        print(e)
        await query.message.reply_text(
            f"ERROR:\n{e}"
        )

async def verify_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /verify <reference>")
        return

    reference = context.args[0]

    # Verify payment with Paystack
    result = verify_paystack_payment(reference)

    if not result or not result.get("status") or result["data"]["status"] != "success":
        await update.message.reply_text("❌ Payment not verified or failed.")
        return

    data = result["data"]
    metadata = data.get("metadata", {})

    user_id = metadata.get("user_id")
    payment_type = metadata.get("payment_type")
    miner_type = metadata.get("miner_type")

    if not user_id:
        await update.message.reply_text("❌ Invalid transaction metadata.")
        return

    # Check that this payment exists and is still pending
    c.execute(
        """
        SELECT user_id, amount, payment_type, miner_type
        FROM pending_payments
        WHERE reference=%s AND status='pending'
        """,
        (reference,)
    )

    pending = c.fetchone()

    if not pending:
        await update.message.reply_text(
            "✅ Payment already processed or not found."
        )
        return

    pending_user_id, pending_amount, pending_type, pending_miner = pending

    # Prevent users verifying another person's payment
    if update.effective_user.id != pending_user_id:
        await update.message.reply_text(
            "❌ This payment does not belong to your account."
        )
        return

    # Confirm payment amount
    paid_amount = data["amount"] / 100

    if paid_amount != pending_amount:
        await update.message.reply_text(
            "❌ Payment amount mismatch."
        )
        return


    # ================= ENTRY PAYMENT =================

    if payment_type == "entry":

        c.execute(
            """
            UPDATE users
            SET has_paid_entry=1
            WHERE user_id=%s
            """,
            (user_id,)
        )


        # Referral reward
        c.execute(
            """
            SELECT referred_by
            FROM users
            WHERE user_id=%s
            """,
            (user_id,)
        )

        referral = c.fetchone()

        if referral and referral[0]:

            c.execute(
                """
                UPDATE users
                SET balance = balance + 1000
                WHERE user_id=%s
                """,
                (referral[0],)
            )


        await context.bot.send_message(
            user_id,
            "✅ Entry fee payment successful!\n\n"
            "Your account has been unlocked.",
            reply_markup=full_menu_keyboard()
        )


    # ================= MINER PURCHASE =================

    elif payment_type == "miner" and miner_type:

        if miner_type not in MINERS:
            await update.message.reply_text(
                "❌ Invalid miner type."
            )
            return


        c.execute(
            """
            INSERT INTO user_miners
            (user_id, miner_type, quantity)
            VALUES (%s,%s,1)

            ON CONFLICT(user_id, miner_type)
            DO UPDATE SET quantity = user_miners.quantity + 1
            """,
            (user_id, miner_type)
        )


        await context.bot.send_message(
            user_id,
            f"✅ {MINERS[miner_type]['name']} purchased successfully!",
            reply_markup=full_menu_keyboard()
        )


    else:
        await update.message.reply_text(
            "❌ Unknown payment type."
        )
        return


    # Mark payment as completed
    c.execute(
        """
        UPDATE pending_payments
        SET status='success'
        WHERE reference=%s
        """,
        (reference,)
    )


    await update.message.reply_text(
        "✅ Payment verified and processed automatically!"
    )
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    c.execute("SELECT COUNT(*) FROM user_miners WHERE user_id=%s", (user_id,))
    count = c.fetchone()[0]
    await update.message.reply_text(f"💰 Balance: ₦{user[2]:.2f}\nMiners Owned: {count}", 
                                  reply_markup=full_menu_keyboard())

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    bot = await context.bot.get_me()

    ref = user[4] if user and user[4] else user_id
    link = f"https://t.me/{bot.username}?start={ref}"

    await update.message.reply_text(
        f"👥 Your Referral Link:\n{link}\nEarn 10% bonus!",
        reply_markup=full_menu_keyboard()
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *About Server Mining*\n\n"
        "Welcome to *Server Mining*, a online mining platform where you build your own mining business and earn daily real withdrawable income.\n\n"

        "🚀 *How It Works*\n"
        "• Pay the one-time ₦1,000 entry fee.\n"
        "• Purchase mining servers from the Server Store.\n"
        "• Each miner generates daily income.\n"
        "• Claim your mining rewards every 24 hours.\n"
        "• Withdraw your available balance once you meet the withdrawal requirements.\n\n"
        "• All mining will be done on our backend with power computing power to maximise earning depending on the server purchased.\n\n"
        "• All pay out will be on the 30th and 31th of each to ensure flexibility.\n\n"

        "👥 *Referral Program*\n"
        "Invite friends using your referral link and earn a ₦1,000 referral bonus when they join.\n\n"
        "Referral earning can be with instantly the user sign up.\n\n"

        "📜 *Rules*\n"
        "• Payments are verified by the admin before activation.\n"
        "• Do not use multiple accounts.\n"
        "• Fake payment proofs will result in a permanent ban.\n"
        "• Be respectful when contacting support.\n"
        "• Mining income is generated once every 24 hours.\n\n"

        "💎 Build your Server, upgrade your miners, and grow your earnings over time.\n\n"
        "Thank you for being part of Server Mining!",
        parse_mode="Markdown",
        reply_markup=full_menu_keyboard()
    )
    
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_amount"] = True

    await update.message.reply_text(
        "💸 How much would you like to withdraw? (₦)"
    )

async def receive_bank_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if not (context.user_data.get("waiting_for_amount") or context.user_data.get("waiting_for_bank")):
        return

    if context.user_data.get("waiting_for_amount"):
        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid amount.")
            return

        db_user = get_user(user.id)

        if amount > db_user[2]:
            await update.message.reply_text("❌ Insufficient balance.")
            return

        context.user_data["amount"] = amount
        context.user_data["waiting_for_amount"] = False
        context.user_data["waiting_for_bank"] = True

        await update.message.reply_text(
            "📥 Now send your bank details:\n\n"
            "Bank Name:\nAccount Name:\nAccount Number:"
        )
        return

    if context.user_data.get("waiting_for_bank"):
        amount = context.user_data.get("amount")
        details = text

        c.execute("""
            INSERT INTO withdrawals (user_id, amount, bank_details)
            VALUES (%s, %s, %s)
        """, (user.id, amount, details))

         # Remove withdrawn amount from user's balance
        c.execute(
        """
        UPDATE users
        SET balance = balance - %s
        WHERE user_id=%s
        """,
        (amount, user.id)
    )

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 New Withdrawal Request\n\n"
            f"User ID: {user.id}\n"
            f"Username: @{user.username}\n"
            f"Amount: ₦{amount:,.2f}\n\n"
            f"Bank Details:\n{details}"
        )

        context.user_data["waiting_for_bank"] = False
        context.user_data.pop("amount", None)

        await update.message.reply_text(
            "✅ Your withdrawal request has been sent to admin.",
            reply_markup=full_menu_keyboard()
        )
        return

async def my_miners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT miner_type, quantity FROM user_miners WHERE user_id=%s", (user_id,))
    miners = c.fetchall()
    if not miners:
        await update.message.reply_text("You have no miners yet.")
        return
    text = "🖥️ **Your Miners**\n\n"
    for m in miners:
        data = MINERS.get(m[0])
        if data:
            text += f"• {data['name']} ×{m[1]} (₦{data['gen']*m[1]:,}/day)\n"
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=full_menu_keyboard())

async def claim_mining(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now()
    total = 0
    c.execute("SELECT miner_type, quantity, last_claim FROM user_miners WHERE user_id=%s", (user_id,))
    for m in c.fetchall():
        miner = MINERS.get(m[0])
        if miner and (not m[2] or (now - m[2]) >= timedelta(hours=24)):
            total += miner["gen"] * m[1]
            c.execute("UPDATE user_miners SET last_claim=%s WHERE user_id=%s AND miner_type=%s", (now, user_id, m[0]))
    if total > 0:
        c.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (total, user_id))
        await update.message.reply_text(f"✅ Claimed ₦{total:,} successfully!", reply_markup=full_menu_keyboard())
    else:
        await update.message.reply_text("No income ready to claim yet.", reply_markup=full_menu_keyboard())



def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verify", verify_payment))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern=r"^buy_"))
    app.add_handler(MessageHandler(filters.Regex("^(💰 Pay Entry Fee ₦1000|🛒 Server Store|💰 Balance|👥 Referrals|📊 My Miners|⛏️ Claim Mining|💸 Withdraw|ℹ️ About)$"), handle_menu))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bank_details))
    
    
    
    print("✅ Connected to PostgreSQL successfully!")
    print("✅ Paystack integrated for automated payments!")
    print("✅ Running with Telegram Webhook")

    # === TELEGRAM WEBHOOK MODE ===
    app.run_webhook(
        listen="0.0.0.0",
        port=WEBHOOK_PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    )

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
