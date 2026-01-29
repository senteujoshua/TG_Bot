"""
Telegram Escrow Bot
A bot for secure peer-to-peer transactions with M-Pesa integration.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import database as db
import mpesa

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = os.getenv('BOT_TOKEN')

# Parse admin ID safely (must be numeric Telegram ID, not username)
_admin_id_str = os.getenv('ADMIN_TELEGRAM_ID', '0')
try:
    ADMIN_ID = int(_admin_id_str)
except ValueError:
    ADMIN_ID = 0
    logging.warning(
        f"ADMIN_TELEGRAM_ID '{_admin_id_str}' is not a valid numeric ID. "
        "Use /start with the bot to get your Telegram ID."
    )

# Conversation states
(
    AGE_VERIFY,
    # Seller registration
    SELLER_USERNAME,
    SELLER_PASSWORD,
    SELLER_CONFIRM_PASSWORD,
    # Seller login
    LOGIN_USERNAME,
    LOGIN_PASSWORD,
    # Add product
    PRODUCT_NAME,
    PRODUCT_DESC,
    PRODUCT_PRICE,
    PRODUCT_IMAGE,
    # Payment setup
    PAYMENT_METHOD,
    PAYMENT_NUMBER,
    # Buy flow
    BUYER_PHONE,
    # Confirm payment
    CONFIRM_PAYMENT,
) = range(14)

# Main menu keyboard
MAIN_MENU = ReplyKeyboardMarkup(
    [["Shop", "Sell"],
     ["My Orders", "Help"]],
    resize_keyboard=True
)

SELLER_MENU = ReplyKeyboardMarkup(
    [["Add Product", "My Products"],
     ["Pending Orders", "Payment Settings"],
     ["Back to Main"]],
    resize_keyboard=True
)


# ============== Helper Functions ==============

def get_user_context(context: ContextTypes.DEFAULT_TYPE, key: str, default=None):
    """Get value from user context."""
    return context.user_data.get(key, default)


def set_user_context(context: ContextTypes.DEFAULT_TYPE, key: str, value):
    """Set value in user context."""
    context.user_data[key] = value


def clear_user_context(context: ContextTypes.DEFAULT_TYPE):
    """Clear user context."""
    context.user_data.clear()


async def require_age_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user needs age verification."""
    user_id = update.effective_user.id
    if not db.is_age_verified(user_id):
        keyboard = [[
            InlineKeyboardButton("I confirm I'm 18+", callback_data="age_verify_yes"),
            InlineKeyboardButton("Exit", callback_data="age_verify_no")
        ]]
        await update.message.reply_text(
            "*Age Verification Required*\n\n"
            "This marketplace contains adult products. "
            "You must be 18 years or older to continue.\n\n"
            "By clicking 'I confirm I'm 18+', you verify that you are "
            "of legal age in your jurisdiction.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return False
    return True


# ============== Command Handlers ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")

    # Check age verification
    if not db.is_age_verified(user.id):
        keyboard = [[
            InlineKeyboardButton("I confirm I'm 18+", callback_data="age_verify_yes"),
            InlineKeyboardButton("Exit", callback_data="age_verify_no")
        ]]
        await update.message.reply_text(
            f"Welcome to the Escrow Marketplace!\n\n"
            "*Age Verification Required*\n\n"
            "This marketplace contains wellness products. "
            "You must be 18 years or older to continue.\n\n"
            "By clicking 'I confirm I'm 18+', you verify that you are "
            "of legal age in your jurisdiction.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return AGE_VERIFY

    await show_main_menu(update, context)
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the main menu."""
    await update.message.reply_text(
        "*Welcome to Escrow Marketplace!*\n\n"
        "Buy and sell securely with our escrow protection.\n\n"
        "Choose an option:",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
*Escrow Marketplace Help*

*For Buyers:*
- Tap "Shop" to browse products
- Select a product and pay through M-Pesa
- Your payment is held safely until you confirm receipt
- Tap "My Orders" to track your purchases

*For Sellers:*
- Tap "Sell" to register/login as a seller
- Add your products with photos and prices
- Get notified when someone buys
- Receive payment after buyer confirms

*Escrow Protection:*
- Buyer pays Product Price + KSh 10 fee
- Money is held until delivery confirmed
- Seller receives Product Price after confirmation
- Disputes are handled by admin

*Commands:*
/start - Start the bot
/shop - Browse products
/sell - Seller dashboard
/orders - View your orders
/help - Show this help

Need support? Contact admin.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /myid command - shows user their Telegram ID."""
    user = update.effective_user
    await update.message.reply_text(
        f"*Your Telegram ID:* `{user.id}`\n\n"
        f"Username: @{user.username or 'not set'}\n"
        f"Name: {user.full_name}\n\n"
        f"Copy the numeric ID above to use as ADMIN_TELEGRAM_ID in your .env file.",
        parse_mode='Markdown'
    )


# ============== Age Verification ==============

async def age_verification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle age verification callback."""
    query = update.callback_query
    await query.answer()

    if query.data == "age_verify_yes":
        db.set_age_verified(query.from_user.id)
        await query.edit_message_text(
            "Age verified! Welcome to the marketplace."
        )
        await query.message.reply_text(
            "*Welcome to Escrow Marketplace!*\n\n"
            "Buy and sell securely with our escrow protection.\n\n"
            "Choose an option:",
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    else:
        await query.edit_message_text(
            "You must be 18+ to use this service. Goodbye!"
        )
        return ConversationHandler.END


# ============== Shop (Buyer) Features ==============

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show shop with all products."""
    if not await require_age_verification(update, context):
        return

    products = db.get_all_active_products()

    if not products:
        await update.message.reply_text(
            "No products available yet.\n"
            "Check back later or become a seller!",
            reply_markup=MAIN_MENU
        )
        return

    await update.message.reply_text(
        "*Available Products*\n\n"
        "Select a product to view details:",
        parse_mode='Markdown'
    )

    # Show products as inline buttons (max 10 per message)
    for i in range(0, len(products), 10):
        batch = products[i:i+10]
        keyboard = []
        for product in batch:
            button_text = f"{product['name']} - KSh {product['price']:,}"
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"prod_{product['id']}"
                )
            ])
        await update.message.reply_text(
            "Products:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection callback."""
    query = update.callback_query
    await query.answer()

    # Extract product ID from callback data
    callback_data = query.data
    if callback_data.startswith("prod_"):
        product_id = int(callback_data.split("_")[1])
        product = db.get_product_by_id(product_id)

        if not product:
            await query.edit_message_text("Product not found.")
            return

        seller = db.get_seller_by_id(product['seller_id'])
        total_price = product['price'] + 10  # Add escrow fee

        details = (
            f"*{product['name']}*\n\n"
            f"{product['description'] or 'No description'}\n\n"
            f"*Price:* KSh {product['price']:,}\n"
            f"*Escrow Fee:* KSh 10\n"
            f"*Total to Pay:* KSh {total_price:,}\n\n"
            f"Seller: @{seller['username'] if seller else 'Unknown'}\n\n"
            f"Your payment is protected by escrow."
        )

        keyboard = [
            [InlineKeyboardButton("Buy Now", callback_data=f"buy_{product_id}")],
            [InlineKeyboardButton("Back to Shop", callback_data="back_shop")]
        ]

        # If product has image, send with photo
        if product['image_file_id']:
            await query.message.reply_photo(
                photo=product['image_file_id'],
                caption=details,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            await query.delete_message()
        else:
            await query.edit_message_text(
                details,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle buy button callback."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    product = db.get_product_by_id(product_id)

    if not product:
        await query.edit_message_text("Product no longer available.")
        return ConversationHandler.END

    # Store product info in context for the buy flow
    set_user_context(context, 'buying_product_id', product_id)
    set_user_context(context, 'buying_product', dict(product))

    total = product['price'] + 10

    # Check if M-Pesa is configured for STK push
    if mpesa.is_mpesa_configured():
        await query.message.reply_text(
            f"*Step 1/2: Enter Phone Number*\n\n"
            f"Product: {product['name']}\n"
            f"Total: KSh {total:,}\n\n"
            f"Enter your M-Pesa phone number (e.g., 0712345678):",
            parse_mode='Markdown'
        )
        return BUYER_PHONE
    else:
        # Manual payment flow
        trade_id, order_id = db.create_trade(
            buyer_telegram_id=query.from_user.id,
            seller_id=product['seller_id'],
            product_id=product_id,
            amount=product['price']
        )

        set_user_context(context, 'current_trade_id', trade_id)
        set_user_context(context, 'current_order_id', order_id)

        instructions = mpesa.get_manual_payment_instructions(total, order_id)

        keyboard = [
            [InlineKeyboardButton("I've Paid", callback_data=f"paid_{trade_id}")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_order")]
        ]

        await query.message.reply_text(
            f"*Order Created!*\n\n"
            f"Order ID: `{order_id}`\n"
            f"Product: {product['name']}\n"
            f"Total: KSh {total:,}\n\n"
            f"{instructions}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return CONFIRM_PAYMENT


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive buyer's phone number for M-Pesa."""
    phone = update.message.text.strip()

    # Basic validation
    phone_clean = phone.replace(' ', '').replace('-', '')
    if not phone_clean.replace('+', '').isdigit() or len(phone_clean) < 9:
        await update.message.reply_text(
            "Invalid phone number. Please enter a valid M-Pesa number.\n"
            "Example: 0712345678 or 254712345678"
        )
        return BUYER_PHONE

    product_id = get_user_context(context, 'buying_product_id')
    product = db.get_product_by_id(product_id)

    if not product:
        await update.message.reply_text("Product no longer available.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    # Create the trade
    trade_id, order_id = db.create_trade(
        buyer_telegram_id=update.effective_user.id,
        seller_id=product['seller_id'],
        product_id=product_id,
        amount=product['price']
    )

    total = product['price'] + 10

    set_user_context(context, 'current_trade_id', trade_id)
    set_user_context(context, 'current_order_id', order_id)
    set_user_context(context, 'buyer_phone', phone)

    # Initiate STK Push
    await update.message.reply_text(
        f"*Step 2/2: Confirm Payment*\n\n"
        f"Sending payment request to {phone}...\n"
        f"Please check your phone and enter your M-Pesa PIN.",
        parse_mode='Markdown'
    )

    result = mpesa.stk_push(phone, total, order_id, f"Order {order_id}")

    if result['success']:
        set_user_context(context, 'checkout_request_id', result.get('checkout_request_id'))

        keyboard = [
            [InlineKeyboardButton("I've Paid", callback_data=f"paid_{trade_id}")],
            [InlineKeyboardButton("Retry Payment", callback_data=f"retry_{trade_id}")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_order")]
        ]

        await update.message.reply_text(
            f"*Payment Request Sent!*\n\n"
            f"Order ID: `{order_id}`\n\n"
            f"Check your phone for the M-Pesa prompt.\n"
            f"Enter your PIN to complete payment.\n\n"
            f"After paying, tap 'I've Paid' below.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        # STK Push failed, show manual instructions
        instructions = mpesa.get_manual_payment_instructions(total, order_id)

        keyboard = [
            [InlineKeyboardButton("I've Paid", callback_data=f"paid_{trade_id}")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_order")]
        ]

        await update.message.reply_text(
            f"*Automatic payment failed.*\n\n"
            f"Please pay manually:\n"
            f"{instructions}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    return CONFIRM_PAYMENT


async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment confirmation callbacks."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("paid_"):
        trade_id = int(query.data.split("_")[1])
        trade = db.get_trade_by_id(trade_id)

        if not trade:
            await query.edit_message_text("Order not found.")
            return ConversationHandler.END

        # Update status to paid (in production, verify with M-Pesa callback)
        db.update_trade_status(trade_id, 'paid')

        await query.edit_message_text(
            f"*Payment Received!*\n\n"
            f"Order ID: `{trade['order_id']}`\n\n"
            f"Your payment is now held in escrow.\n"
            f"The seller has been notified.\n\n"
            f"You'll receive a notification when the item is shipped.\n"
            f"Use /orders to track your order.",
            parse_mode='Markdown'
        )

        # Notify seller
        seller = db.get_seller_by_id(trade['seller_id'])
        product = db.get_product_by_id(trade['product_id'])
        if seller:
            try:
                await context.bot.send_message(
                    chat_id=seller['telegram_id'],
                    text=f"*New Order!*\n\n"
                         f"Order ID: `{trade['order_id']}`\n"
                         f"Product: {product['name']}\n"
                         f"Amount: KSh {trade['amount']:,}\n\n"
                         f"Please ship the item and mark as shipped.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify seller: {e}")

        # Notify admin
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"*New Payment*\n\n"
                         f"Order: `{trade['order_id']}`\n"
                         f"Amount: KSh {trade['total_paid']:,}\n"
                         f"Status: Paid",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")

        return ConversationHandler.END

    elif query.data == "cancel_order":
        trade_id = get_user_context(context, 'current_trade_id')
        if trade_id:
            db.update_trade_status(trade_id, 'cancelled')

        await query.edit_message_text(
            "Order cancelled. No payment was processed.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    elif query.data.startswith("retry_"):
        trade_id = int(query.data.split("_")[1])
        trade = db.get_trade_by_id(trade_id)

        if trade:
            await query.edit_message_text(
                "Enter your M-Pesa phone number to retry payment:"
            )
            set_user_context(context, 'current_trade_id', trade_id)
            return BUYER_PHONE

    return ConversationHandler.END


async def back_to_shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to shop callback."""
    query = update.callback_query
    await query.answer()

    products = db.get_all_active_products()

    if not products:
        await query.edit_message_text("No products available.")
        return

    keyboard = []
    for product in products[:10]:
        button_text = f"{product['name']} - KSh {product['price']:,}"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"prod_{product['id']}")
        ])

    await query.edit_message_text(
        "*Available Products*\n\nSelect a product:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


# ============== My Orders (Buyer) ==============

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show buyer's orders."""
    if not await require_age_verification(update, context):
        return

    user_id = update.effective_user.id
    trades = db.get_trades_by_buyer(user_id)

    if not trades:
        await update.message.reply_text(
            "You haven't made any purchases yet.\n"
            "Use /shop to browse products!",
            reply_markup=MAIN_MENU
        )
        return

    status_emoji = {
        'pending_payment': '⏳',
        'paid': '💰',
        'shipped': '📦',
        'confirmed': '✅',
        'disputed': '⚠️',
        'cancelled': '❌',
        'refunded': '💸'
    }

    orders_text = "*Your Orders*\n\n"
    for trade in trades[:10]:
        emoji = status_emoji.get(trade['status'], '❓')
        orders_text += (
            f"{emoji} `{trade['order_id']}`\n"
            f"   {trade['product_name']} - KSh {trade['amount']:,}\n"
            f"   Status: {trade['status'].replace('_', ' ').title()}\n\n"
        )

    # Add action buttons for shipped orders
    keyboard = []
    for trade in trades[:5]:
        if trade['status'] == 'shipped':
            keyboard.append([
                InlineKeyboardButton(
                    f"Confirm Received: {trade['order_id']}",
                    callback_data=f"confirm_{trade['id']}"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"Report Issue: {trade['order_id']}",
                    callback_data=f"dispute_{trade['id']}"
                )
            ])

    if keyboard:
        orders_text += "\n*Action Required:*\nConfirm receipt or report issues below."

    await update.message.reply_text(
        orders_text,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else MAIN_MENU,
        parse_mode='Markdown'
    )


async def confirm_delivery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle buyer confirming delivery."""
    query = update.callback_query
    await query.answer()

    trade_id = int(query.data.split("_")[1])
    trade = db.get_trade_by_id(trade_id)

    if not trade or trade['buyer_telegram_id'] != query.from_user.id:
        await query.edit_message_text("Order not found or unauthorized.")
        return

    if trade['status'] != 'shipped':
        await query.edit_message_text(
            f"Cannot confirm. Order status is: {trade['status']}"
        )
        return

    # Update status to confirmed
    db.update_trade_status(trade_id, 'confirmed')

    # Get seller info for disbursement
    seller = db.get_seller_by_id(trade['seller_id'])

    await query.edit_message_text(
        f"*Delivery Confirmed!*\n\n"
        f"Order: `{trade['order_id']}`\n\n"
        f"Thank you for confirming!\n"
        f"Payment of KSh {trade['amount']:,} will be released to the seller.",
        parse_mode='Markdown'
    )

    # Attempt to disburse funds to seller
    if seller and seller['payment_number']:
        result = mpesa.b2c_payment(
            seller['payment_number'],
            trade['amount'],
            f"Payment for order {trade['order_id']}"
        )

        if result['success']:
            logger.info(f"Disbursement initiated for trade {trade_id}")
        else:
            logger.warning(f"Auto-disbursement failed for trade {trade_id}: {result.get('error')}")
            # Notify admin for manual disbursement
            if ADMIN_ID:
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"*Manual Disbursement Required*\n\n"
                             f"Order: `{trade['order_id']}`\n"
                             f"Amount: KSh {trade['amount']:,}\n"
                             f"Seller: @{seller['username']}\n"
                             f"Payment: {seller['payment_method']} {seller['payment_number']}",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin: {e}")

    # Notify seller
    if seller:
        try:
            await context.bot.send_message(
                chat_id=seller['telegram_id'],
                text=f"*Payment Released!*\n\n"
                     f"Order `{trade['order_id']}` confirmed by buyer.\n"
                     f"KSh {trade['amount']:,} will be sent to your {seller['payment_method']}.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify seller: {e}")


async def dispute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle buyer reporting a dispute."""
    query = update.callback_query
    await query.answer()

    trade_id = int(query.data.split("_")[1])
    trade = db.get_trade_by_id(trade_id)

    if not trade or trade['buyer_telegram_id'] != query.from_user.id:
        await query.edit_message_text("Order not found or unauthorized.")
        return

    # Update status to disputed
    db.update_trade_status(trade_id, 'disputed')

    await query.edit_message_text(
        f"*Dispute Opened*\n\n"
        f"Order: `{trade['order_id']}`\n\n"
        f"Your dispute has been recorded.\n"
        f"An admin will review and contact you.\n\n"
        f"Payment remains in escrow until resolved.",
        parse_mode='Markdown'
    )

    # Notify admin
    if ADMIN_ID:
        seller = db.get_seller_by_id(trade['seller_id'])
        product = db.get_product_by_id(trade['product_id'])
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"*DISPUTE ALERT*\n\n"
                     f"Order: `{trade['order_id']}`\n"
                     f"Product: {product['name'] if product else 'Unknown'}\n"
                     f"Amount: KSh {trade['amount']:,}\n"
                     f"Buyer: {query.from_user.id}\n"
                     f"Seller: @{seller['username'] if seller else 'Unknown'}\n\n"
                     f"Please investigate and resolve.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify admin of dispute: {e}")


# ============== Seller Features ==============

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /sell command - seller registration/login."""
    if not await require_age_verification(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id
    seller = db.get_seller_by_telegram_id(user_id)

    if seller:
        # Already registered, show seller menu
        set_user_context(context, 'seller_id', seller['id'])
        await update.message.reply_text(
            f"*Welcome back, @{seller['username']}!*\n\n"
            f"What would you like to do?",
            reply_markup=SELLER_MENU,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    else:
        # New seller registration
        keyboard = [
            [InlineKeyboardButton("Register as Seller", callback_data="seller_register")],
            [InlineKeyboardButton("Login", callback_data="seller_login")],
            [InlineKeyboardButton("Back", callback_data="back_main")]
        ]
        await update.message.reply_text(
            "*Become a Seller*\n\n"
            "Sell your products securely with escrow protection.\n\n"
            "New seller? Register below.\n"
            "Already have an account? Login.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ConversationHandler.END


async def seller_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle seller registration/login callbacks."""
    query = update.callback_query
    await query.answer()

    if query.data == "seller_register":
        await query.edit_message_text(
            "*Seller Registration (Step 1/3)*\n\n"
            "Enter a username for your seller account:",
            parse_mode='Markdown'
        )
        return SELLER_USERNAME

    elif query.data == "seller_login":
        await query.edit_message_text(
            "*Seller Login*\n\n"
            "Enter your username:",
            parse_mode='Markdown'
        )
        return LOGIN_USERNAME

    elif query.data == "back_main":
        await query.delete_message()
        await query.message.reply_text(
            "Main menu:",
            reply_markup=MAIN_MENU
        )
        return ConversationHandler.END

    return ConversationHandler.END


async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle seller username input during registration."""
    username = update.message.text.strip()

    # Validate username
    if len(username) < 3 or len(username) > 20:
        await update.message.reply_text(
            "Username must be 3-20 characters. Try again:"
        )
        return SELLER_USERNAME

    if not username.isalnum():
        await update.message.reply_text(
            "Username must contain only letters and numbers. Try again:"
        )
        return SELLER_USERNAME

    # Check if username exists
    if db.get_seller_by_username(username):
        await update.message.reply_text(
            "Username already taken. Choose another:"
        )
        return SELLER_USERNAME

    set_user_context(context, 'reg_username', username)

    await update.message.reply_text(
        f"*Registration (Step 2/3)*\n\n"
        f"Username: @{username}\n\n"
        f"Enter a password (min 6 characters):",
        parse_mode='Markdown'
    )
    return SELLER_PASSWORD


async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle seller password input during registration."""
    password = update.message.text.strip()

    # Delete the password message for security
    try:
        await update.message.delete()
    except:
        pass

    if len(password) < 6:
        await update.message.reply_text(
            "Password must be at least 6 characters. Try again:"
        )
        return SELLER_PASSWORD

    set_user_context(context, 'reg_password', password)

    await update.message.reply_text(
        "*Registration (Step 3/3)*\n\n"
        "Confirm your password:",
        parse_mode='Markdown'
    )
    return SELLER_CONFIRM_PASSWORD


async def register_confirm_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle password confirmation during registration."""
    confirm_password = update.message.text.strip()

    # Delete the password message
    try:
        await update.message.delete()
    except:
        pass

    password = get_user_context(context, 'reg_password')

    if confirm_password != password:
        await update.message.reply_text(
            "Passwords don't match. Enter password again:"
        )
        return SELLER_PASSWORD

    username = get_user_context(context, 'reg_username')
    telegram_id = update.effective_user.id

    # Create seller account
    seller_id = db.create_seller(telegram_id, username, password)

    if seller_id:
        set_user_context(context, 'seller_id', seller_id)
        await update.message.reply_text(
            f"*Registration Successful!*\n\n"
            f"Welcome, @{username}!\n\n"
            f"Next steps:\n"
            f"1. Set up your payment method\n"
            f"2. Add your first product\n\n"
            f"Use the menu below:",
            reply_markup=SELLER_MENU,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "Registration failed. Please try again with /sell",
            reply_markup=MAIN_MENU
        )

    return ConversationHandler.END


async def login_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle username input during login."""
    username = update.message.text.strip()
    set_user_context(context, 'login_username', username)

    await update.message.reply_text("Enter your password:")
    return LOGIN_PASSWORD


async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle password input during login."""
    password = update.message.text.strip()

    # Delete password message
    try:
        await update.message.delete()
    except:
        pass

    username = get_user_context(context, 'login_username')
    seller = db.login_seller(username, password)

    if seller:
        # Update telegram_id if different (in case of login from new device)
        set_user_context(context, 'seller_id', seller['id'])

        await update.message.reply_text(
            f"*Login Successful!*\n\n"
            f"Welcome back, @{seller['username']}!",
            reply_markup=SELLER_MENU,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "Invalid username or password.\n"
            "Try again with /sell",
            reply_markup=MAIN_MENU
        )

    return ConversationHandler.END


# ============== Seller Product Management ==============

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add product flow."""
    seller_id = get_user_context(context, 'seller_id')

    if not seller_id:
        # Check if user is a registered seller
        seller = db.get_seller_by_telegram_id(update.effective_user.id)
        if seller:
            set_user_context(context, 'seller_id', seller['id'])
        else:
            await update.message.reply_text(
                "You need to register as a seller first.\n"
                "Use /sell to register.",
                reply_markup=MAIN_MENU
            )
            return ConversationHandler.END

    await update.message.reply_text(
        "*Add New Product (Step 1/4)*\n\n"
        "Enter the product name:",
        parse_mode='Markdown'
    )
    return PRODUCT_NAME


async def product_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product name input."""
    name = update.message.text.strip()

    if len(name) < 2 or len(name) > 100:
        await update.message.reply_text(
            "Product name must be 2-100 characters. Try again:"
        )
        return PRODUCT_NAME

    set_user_context(context, 'product_name', name)

    await update.message.reply_text(
        f"*Add Product (Step 2/4)*\n\n"
        f"Name: {name}\n\n"
        f"Enter a description (or 'skip' to skip):",
        parse_mode='Markdown'
    )
    return PRODUCT_DESC


async def product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product description input."""
    desc = update.message.text.strip()

    if desc.lower() == 'skip':
        desc = ''

    set_user_context(context, 'product_desc', desc)

    await update.message.reply_text(
        f"*Add Product (Step 3/4)*\n\n"
        f"Enter the price in KSh (numbers only):",
        parse_mode='Markdown'
    )
    return PRODUCT_PRICE


async def product_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product price input."""
    price_text = update.message.text.strip().replace(',', '')

    try:
        price = int(price_text)
        if price <= 0:
            raise ValueError("Price must be positive")
        if price > 1000000:
            raise ValueError("Price too high")
    except ValueError:
        await update.message.reply_text(
            "Invalid price. Enter a number between 1 and 1,000,000:"
        )
        return PRODUCT_PRICE

    set_user_context(context, 'product_price', price)

    keyboard = [[InlineKeyboardButton("Skip Image", callback_data="skip_image")]]

    await update.message.reply_text(
        f"*Add Product (Step 4/4)*\n\n"
        f"Send a product photo, or tap 'Skip Image':",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PRODUCT_IMAGE


async def product_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product image upload."""
    image_file_id = None

    if update.message.photo:
        # Get the largest photo
        image_file_id = update.message.photo[-1].file_id
    elif update.callback_query and update.callback_query.data == "skip_image":
        await update.callback_query.answer()

    set_user_context(context, 'product_image', image_file_id)

    # Save the product
    seller_id = get_user_context(context, 'seller_id')
    name = get_user_context(context, 'product_name')
    desc = get_user_context(context, 'product_desc')
    price = get_user_context(context, 'product_price')

    product_id = db.create_product(
        seller_id=seller_id,
        name=name,
        description=desc,
        price=price,
        image_file_id=image_file_id
    )

    message = update.message if update.message else update.callback_query.message

    await message.reply_text(
        f"*Product Added!*\n\n"
        f"Name: {name}\n"
        f"Price: KSh {price:,}\n"
        f"Product ID: {product_id}\n\n"
        f"Your product is now live in the shop!",
        reply_markup=SELLER_MENU,
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def skip_image_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skip image callback."""
    return await product_image(update, context)


async def my_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show seller's products."""
    seller = db.get_seller_by_telegram_id(update.effective_user.id)

    if not seller:
        await update.message.reply_text(
            "You need to register as a seller first.\n"
            "Use /sell to register.",
            reply_markup=MAIN_MENU
        )
        return

    products = db.get_products_by_seller(seller['id'])

    if not products:
        await update.message.reply_text(
            "You haven't added any products yet.\n"
            "Tap 'Add Product' to list your first item!",
            reply_markup=SELLER_MENU
        )
        return

    text = f"*Your Products ({len(products)})*\n\n"
    keyboard = []

    for product in products:
        text += f"• {product['name']} - KSh {product['price']:,}\n"
        keyboard.append([
            InlineKeyboardButton(
                f"Delete: {product['name'][:20]}",
                callback_data=f"del_prod_{product['id']}"
            )
        ])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def delete_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product deletion callback."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[2])
    seller = db.get_seller_by_telegram_id(query.from_user.id)

    if seller and db.deactivate_product(product_id, seller['id']):
        await query.edit_message_text(
            "Product deleted successfully.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text("Failed to delete product.")


# ============== Seller Orders Management ==============

async def pending_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show seller's pending orders."""
    seller = db.get_seller_by_telegram_id(update.effective_user.id)

    if not seller:
        await update.message.reply_text(
            "You need to register as a seller first.",
            reply_markup=MAIN_MENU
        )
        return

    # Get orders that need attention
    trades = db.get_trades_by_seller(seller['id'])
    pending = [t for t in trades if t['status'] in ('paid', 'shipped')]

    if not pending:
        await update.message.reply_text(
            "No pending orders.\n"
            "You'll be notified when someone makes a purchase!",
            reply_markup=SELLER_MENU
        )
        return

    text = "*Pending Orders*\n\n"
    keyboard = []

    for trade in pending:
        status_emoji = '💰' if trade['status'] == 'paid' else '📦'
        text += (
            f"{status_emoji} `{trade['order_id']}`\n"
            f"   {trade['product_name']} - KSh {trade['amount']:,}\n"
            f"   Status: {trade['status'].title()}\n\n"
        )

        if trade['status'] == 'paid':
            keyboard.append([
                InlineKeyboardButton(
                    f"Mark Shipped: {trade['order_id']}",
                    callback_data=f"ship_{trade['id']}"
                )
            ])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else SELLER_MENU,
        parse_mode='Markdown'
    )


async def ship_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seller marking order as shipped."""
    query = update.callback_query
    await query.answer()

    trade_id = int(query.data.split("_")[1])
    trade = db.get_trade_by_id(trade_id)
    seller = db.get_seller_by_telegram_id(query.from_user.id)

    if not trade or not seller or trade['seller_id'] != seller['id']:
        await query.edit_message_text("Order not found or unauthorized.")
        return

    if trade['status'] != 'paid':
        await query.edit_message_text(
            f"Cannot mark as shipped. Order status is: {trade['status']}"
        )
        return

    # Update status
    db.update_trade_status(trade_id, 'shipped')

    await query.edit_message_text(
        f"*Order Shipped!*\n\n"
        f"Order: `{trade['order_id']}`\n\n"
        f"The buyer has been notified.\n"
        f"Payment will be released when they confirm receipt.",
        parse_mode='Markdown'
    )

    # Notify buyer
    product = db.get_product_by_id(trade['product_id'])
    try:
        keyboard = [
            [InlineKeyboardButton("Confirm Received", callback_data=f"confirm_{trade_id}")],
            [InlineKeyboardButton("Report Issue", callback_data=f"dispute_{trade_id}")]
        ]
        await context.bot.send_message(
            chat_id=trade['buyer_telegram_id'],
            text=f"*Order Shipped!*\n\n"
                 f"Order: `{trade['order_id']}`\n"
                 f"Product: {product['name'] if product else 'Item'}\n\n"
                 f"Your order has been shipped!\n"
                 f"Please confirm when you receive it.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify buyer: {e}")


# ============== Payment Settings ==============

async def payment_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start payment settings flow."""
    seller = db.get_seller_by_telegram_id(update.effective_user.id)

    if not seller:
        await update.message.reply_text(
            "You need to register as a seller first.",
            reply_markup=MAIN_MENU
        )
        return ConversationHandler.END

    set_user_context(context, 'seller_id', seller['id'])

    current = f"\nCurrent: {seller['payment_method']} - {seller['payment_number']}" if seller['payment_number'] else ""

    keyboard = [
        [InlineKeyboardButton("Till Number", callback_data="pay_till")],
        [InlineKeyboardButton("Paybill", callback_data="pay_paybill")],
        [InlineKeyboardButton("Phone (M-Pesa)", callback_data="pay_phone")],
        [InlineKeyboardButton("Cancel", callback_data="pay_cancel")]
    ]

    await update.message.reply_text(
        f"*Payment Settings*{current}\n\n"
        f"How would you like to receive payments?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYMENT_METHOD


async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment method selection."""
    query = update.callback_query
    await query.answer()

    if query.data == "pay_cancel":
        await query.edit_message_text("Payment settings cancelled.")
        return ConversationHandler.END

    method_map = {
        "pay_till": "till",
        "pay_paybill": "paybill",
        "pay_phone": "phone"
    }

    method = method_map.get(query.data, "phone")
    set_user_context(context, 'payment_method', method)

    prompts = {
        "till": "Enter your Till Number:",
        "paybill": "Enter your Paybill Number:",
        "phone": "Enter your M-Pesa phone number:"
    }

    await query.edit_message_text(prompts[method])
    return PAYMENT_NUMBER


async def payment_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment number input."""
    number = update.message.text.strip()
    method = get_user_context(context, 'payment_method')
    seller_id = get_user_context(context, 'seller_id')

    # Basic validation
    if method == "phone":
        number = number.replace(' ', '').replace('-', '')
        if not number.replace('+', '').isdigit() or len(number) < 9:
            await update.message.reply_text(
                "Invalid phone number. Enter a valid M-Pesa number:"
            )
            return PAYMENT_NUMBER
    else:
        if not number.isdigit() or len(number) < 5:
            await update.message.reply_text(
                f"Invalid {method} number. Try again:"
            )
            return PAYMENT_NUMBER

    # Save payment settings
    if db.update_seller_payment(seller_id, method, number):
        await update.message.reply_text(
            f"*Payment Settings Updated!*\n\n"
            f"Method: {method.title()}\n"
            f"Number: {number}\n\n"
            f"You'll receive payments to this account.",
            reply_markup=SELLER_MENU,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "Failed to update settings. Try again.",
            reply_markup=SELLER_MENU
        )

    return ConversationHandler.END


# ============== Menu Handlers ==============

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handle main menu button presses."""
    text = update.message.text

    if text == "Shop":
        await shop(update, context)
    elif text == "Sell":
        return await sell(update, context)
    elif text == "My Orders":
        await my_orders(update, context)
    elif text == "Help":
        await help_command(update, context)
    elif text == "Add Product":
        return await add_product_start(update, context)
    elif text == "My Products":
        await my_products(update, context)
    elif text == "Pending Orders":
        await pending_orders(update, context)
    elif text == "Payment Settings":
        return await payment_settings(update, context)
    elif text == "Back to Main":
        clear_user_context(context)
        await update.message.reply_text(
            "Main menu:",
            reply_markup=MAIN_MENU
        )

    return None


# ============== Admin Commands ==============

async def admin_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view all pending trades."""
    if update.effective_user.id != ADMIN_ID:
        return

    trades = db.get_pending_trades()

    if not trades:
        await update.message.reply_text("No pending trades.")
        return

    text = "*All Pending Trades*\n\n"
    for trade in trades[:20]:
        text += (
            f"`{trade['order_id']}` - {trade['status']}\n"
            f"  Product: {trade['product_name']}\n"
            f"  Amount: KSh {trade['total_paid']:,}\n"
            f"  Seller: @{trade['seller_username']}\n\n"
        )

    await update.message.reply_text(text, parse_mode='Markdown')


async def admin_resolve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to resolve a dispute."""
    if update.effective_user.id != ADMIN_ID:
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /resolve <order_id> <refund|release>"
        )
        return

    order_id = args[0]
    action = args[1].lower()

    trade = db.get_trade_by_order_id(order_id)
    if not trade:
        await update.message.reply_text("Trade not found.")
        return

    if action == "refund":
        db.update_trade_status(trade['id'], 'refunded')
        await update.message.reply_text(
            f"Trade {order_id} marked as refunded.\n"
            f"Please manually refund KSh {trade['total_paid']:,} to buyer."
        )
    elif action == "release":
        db.update_trade_status(trade['id'], 'confirmed')
        seller = db.get_seller_by_id(trade['seller_id'])
        await update.message.reply_text(
            f"Trade {order_id} resolved - funds released.\n"
            f"Please disburse KSh {trade['amount']:,} to seller "
            f"({seller['payment_method']} {seller['payment_number']})."
        )
    else:
        await update.message.reply_text("Action must be 'refund' or 'release'.")


# ============== Error Handler ==============

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Exception: {context.error}", exc_info=context.error)

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "An error occurred. Please try again or use /start."
        )


# ============== Main ==============

def main():
    """Start the bot."""
    if not TOKEN:
        logger.error("BOT_TOKEN not set!")
        return

    # Create application
    application = Application.builder().token(TOKEN).build()

    # Conversation handler for buyer flow
    buy_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(buy_callback, pattern=r'^buy_\d+$')
        ],
        states={
            BUYER_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)
            ],
            CONFIRM_PAYMENT: [
                CallbackQueryHandler(payment_callback, pattern=r'^(paid_|retry_|cancel_)')
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CommandHandler('cancel', start)
        ],
        per_message=False
    )

    # Conversation handler for seller registration
    seller_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(seller_auth_callback, pattern=r'^seller_')
        ],
        states={
            SELLER_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)
            ],
            SELLER_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)
            ],
            SELLER_CONFIRM_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm_password)
            ],
            LOGIN_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_username)
            ],
            LOGIN_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CommandHandler('cancel', start)
        ],
        per_message=False
    )

    # Conversation handler for adding products
    product_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^Add Product$'), add_product_start)
        ],
        states={
            PRODUCT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_name)
            ],
            PRODUCT_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_desc)
            ],
            PRODUCT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_price)
            ],
            PRODUCT_IMAGE: [
                MessageHandler(filters.PHOTO, product_image),
                CallbackQueryHandler(skip_image_callback, pattern=r'^skip_image$')
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CommandHandler('cancel', start)
        ],
        per_message=False
    )

    # Conversation handler for payment settings
    payment_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^Payment Settings$'), payment_settings)
        ],
        states={
            PAYMENT_METHOD: [
                CallbackQueryHandler(payment_method_callback, pattern=r'^pay_')
            ],
            PAYMENT_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, payment_number)
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CommandHandler('cancel', start)
        ],
        per_message=False
    )

    # Start conversation handler (for age verification)
    start_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start)
        ],
        states={
            AGE_VERIFY: [
                CallbackQueryHandler(age_verification_callback, pattern=r'^age_verify_')
            ]
        },
        fallbacks=[],
        per_message=False
    )

    # Add handlers in order of priority
    application.add_handler(start_conv_handler)
    application.add_handler(buy_conv_handler)
    application.add_handler(seller_conv_handler)
    application.add_handler(product_conv_handler)
    application.add_handler(payment_conv_handler)

    # Command handlers
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('myid', myid_command))
    application.add_handler(CommandHandler('shop', shop))
    application.add_handler(CommandHandler('sell', sell))
    application.add_handler(CommandHandler('orders', my_orders))

    # Admin commands
    application.add_handler(CommandHandler('admin_trades', admin_trades))
    application.add_handler(CommandHandler('resolve', admin_resolve))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(product_callback, pattern=r'^prod_\d+$'))
    application.add_handler(CallbackQueryHandler(back_to_shop_callback, pattern=r'^back_shop$'))
    application.add_handler(CallbackQueryHandler(confirm_delivery_callback, pattern=r'^confirm_\d+$'))
    application.add_handler(CallbackQueryHandler(dispute_callback, pattern=r'^dispute_\d+$'))
    application.add_handler(CallbackQueryHandler(ship_order_callback, pattern=r'^ship_\d+$'))
    application.add_handler(CallbackQueryHandler(delete_product_callback, pattern=r'^del_prod_\d+$'))

    # Menu button handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_menu_buttons
    ))

    # Error handler
    application.add_error_handler(error_handler)

    # Start polling
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
