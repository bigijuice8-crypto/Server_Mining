import logging
import os
import psycopg2
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, JobQueue

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================== CONFIG ==================
# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
BANK_DETAILS = os.getenv("BANK_DETAILS")
DATABASE_URL = os.getenv("DATABASE_URL")

# Check required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing!")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing!")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID is missing!")

if not BANK_DETAILS:
    raise ValueError("BANK_DETAILS is missing!")

# Convert values after checking
ADMIN_ID = int(ADMIN_ID)
BANK_DETAILS = BANK_DETAILS.replace("\\n", "\n")

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
CREATE TABLE IF NOT EXISTS pending_payments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    amount DOUBLE PRECISION,
    payment_type TEXT,
    miner_type TEXT,
    status TEXT DEFAULT 'pending'
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
    return ReplyKeyboardMarkup([[KeyboardButton("💰 Pay Entry Fee ₦4000")]], resize_keyboard=True)

def full_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛒 Shop")],
        [KeyboardButton("💰 Balance")],
        [KeyboardButton("📊 My Miners")],
        [KeyboardButton("👥 Referrals")],
        [KeyboardButton("✋ Claim Daily")],
        [KeyboardButton("💸 Withdraw")],
        [KeyboardButton("ℹ️ About")]
    ], resize_keyboard=True)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None
    create_user(user.id, user.username, referred_by)
    
    user_data = get_user(user.id)
    if user_data and user_data[3] == 1:
        await update.message.reply_text("Welcome back! Use the menu below.", reply_markup=full_menu_keyboard())
    else:
        await update.message.reply_text(
            "Welcome to Server_Mining where your success is our No.1 priority. We tend to lead you to financial freedom as your invest in the passive! 🚀\n\nPay the ₦4000 entry fee to begin.", 
            reply_markup=entry_keyboard()
        )

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 ADD THIS HERE (TOP OF FUNCTION)
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
        elif "Claim Daily" in text:
            await claim_daily(update, context)
        elif "Withdraw" in text:
            await withdraw(update, context)
        elif "About" in text:
            await about(update, context)
    else:
        await update.message.reply_text("Complete entry payment first.", reply_markup=entry_keyboard())

async def pay_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute(
    "INSERT INTO pending_payments (user_id, amount, payment_type) VALUES (%s, %s, %s) RETURNING id",
    (user_id, 4000, "entry")
    )
    payment_id = c.fetchone()[0]
    
    keyboard = [[InlineKeyboardButton("✅ I've Paid", callback_data=f"paid_entry_{payment_id}")]]
    
    await update.message.reply_text(
        f"Send ₦4000 to:\n{BANK_DETAILS}\n\nAfter sending, click the button below.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Paid button handler
async def paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    payment_id = int(parts[-1])
    
    c.execute(
    "SELECT user_id, amount, payment_type, miner_type FROM pending_payments WHERE id=%s",
    (payment_id,)
    )
    payment = c.fetchone()
    if not payment:
       return

    user_id = payment[0]
    amount = payment[1]
    ptype = payment[2]
    miner_type = payment[3]
    
    keyboard = [
        [InlineKeyboardButton("✅ Accept", callback_data=f"accept_{payment_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_{payment_id}")]
    ]
    
    if ptype == "entry":
       await context.bot.send_message(
          ADMIN_ID,
          f"🔔 New Entry Payment\n"
          f"User: {user_id}\n"
          f"Amount: ₦{amount:,.0f}",
        reply_markup=InlineKeyboardMarkup(keyboard)
       )
       await query.edit_message_text("✅ Sent to admin for approval.")
    else:
        miner = MINERS.get(miner_type)

        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 Miner Purchase\n"
            f"User: {user_id}\n"
            f"{miner['name'] if miner else 'Unknown'}\n"
            f"Amount: ₦{amount:,.0f}",
            reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await query.edit_message_text("✅ Sent to admin.")

# Admin
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 🔒 SECURITY CHECK (ADD THIS HERE)
    if update.effective_user.id != ADMIN_ID:
        await query.answer("Not authorized", show_alert=True)
        return

    action, pid = query.data.split("_")
    pid = int(pid)
    
    c.execute("SELECT user_id, amount, payment_type, miner_type FROM pending_payments WHERE id=%s", (pid,))
    p = c.fetchone()
    if not p:
        return
    
    user_id, amount, ptype, mtype = p
    
    if action == "accept":
        if ptype == "entry":
            c.execute("UPDATE users SET has_paid_entry=1 WHERE user_id=%s", (user_id,))
            await context.bot.send_message(
                user_id,
                "✅ Entry approved! Full menu unlocked.",
                reply_markup=full_menu_keyboard()
            )
        else:
            c.execute(
                "INSERT INTO user_miners (user_id, miner_type, quantity) VALUES (%s, %s, %s)",
                (user_id, mtype, 1)
            )
            await context.bot.send_message(
                user_id,
                f"✅ {MINERS[mtype]['name']} added!",
                reply_markup=full_menu_keyboard()
            )

        await query.edit_message_text("✅ Approved")

    else:
        await context.bot.send_message(user_id, "❌ Request rejected.")
        await query.edit_message_text("❌ Rejected")
    
    c.execute("DELETE FROM pending_payments WHERE id=%s", (pid,))

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
    miner_key = query.data.split("_")[1]
    miner = MINERS[miner_key]
    user_id = query.from_user.id
    
    c.execute(
    "INSERT INTO pending_payments (user_id, amount, payment_type, miner_type) VALUES (%s, %s, %s, %s) RETURNING id",
    (user_id, miner["price"], "miner", miner_key)
    )
    payment_id = c.fetchone()[0]
    
    keyboard = [[InlineKeyboardButton("✅ I've Paid", callback_data=f"paid_miner_{payment_id}")]]
    
    await context.bot.send_message(user_id,
        f"Send ₦{miner['price']:,} for **{miner['name']}**\n\n{BANK_DETAILS}\n\nClick button after payment.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
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
        "ℹ️ *About Mining Empire*\n\n"
        "Welcome to *Mining Empire*, a virtual mining platform where you can build your own mining business and earn daily virtual income.\n\n"

        "🚀 *How It Works*\n"
        "• Pay the one-time ₦4,000 entry fee.\n"
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

    # 🔒 SAFETY GUARD (ADD THIS HERE)
    if not (context.user_data.get("waiting_for_amount") or context.user_data.get("waiting_for_bank")):
        return

    # STEP 1: USER IS ENTERING AMOUNT
    if context.user_data.get("waiting_for_amount"):
        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid amount.")
            return

        db_user = get_user(user.id)

        # BALANCE CHECK
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

    # STEP 2: USER IS ENTERING BANK DETAILS
    if context.user_data.get("waiting_for_bank"):
        amount = context.user_data.get("amount")
        details = text

        c.execute("""
            INSERT INTO withdrawals (user_id, amount, bank_details)
            VALUES (%s, %s, %s)
        """, (user.id, amount, details))

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

async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def claim_mining(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()

    c.execute("SELECT user_id, miner_type, quantity, last_claim FROM user_miners")

    for row in c.fetchall():
        if not row[3] or (now - row[3]) >= timedelta(hours=24):
            miner = MINERS.get(row[1])

            if miner:
                c.execute(
                    "UPDATE users SET balance = balance + %s WHERE user_id=%s",
                    (miner["gen"] * row[2], row[0])
                )

                c.execute(
                    "UPDATE user_miners SET last_claim=%s WHERE user_id=%s AND miner_type=%s",
                    (now, row[0], row[1])
                )

    conn.commit()

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(paid_callback, pattern="^paid_"))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(accept|reject)_"))

    app.add_handler(MessageHandler(filters.Regex("^(💰 Pay Entry Fee ₦4000|🛒 Server Store|💰 Balance|👥 Referrals|📊 My Miners|✋ Claim Daily|💸 Withdraw|ℹ️ About)$"), handle_menu))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bank_details))
    
    app.job_queue.run_repeating(claim_mining, interval=3600, first=60)
    
    print("✅ Connected to PostgreSQL successfully!")
    app.run_polling()

if __name__ == '__main__':
    main()