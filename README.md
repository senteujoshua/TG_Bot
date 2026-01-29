# Telegram Escrow Bot

A secure peer-to-peer marketplace bot for Telegram with M-Pesa payment integration and escrow protection.

## Features

- **Escrow Protection**: Buyer pays (Product Price + KSh 10 fee), funds held until delivery confirmed
- **M-Pesa Integration**: STK Push for payments, B2C for seller disbursements
- **Seller Dashboard**: Add products, manage orders, set payment methods
- **Buyer Experience**: Browse products, secure checkout, order tracking
- **Age Verification**: Required before accessing the marketplace
- **Dispute Resolution**: Admin tools for handling disputes

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- M-Pesa Daraja API credentials (optional, for automated payments)

### 2. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd TG_Bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_TELEGRAM_ID=your_telegram_id
MPESA_CONSUMER_KEY=your_key  # Optional
MPESA_CONSUMER_SECRET=your_secret  # Optional
# ... other settings
```

### 4. Run Locally

```bash
python bot.py
```

## Bot Commands

### For Everyone
- `/start` - Start the bot and verify age
- `/shop` - Browse available products
- `/orders` - View your purchase history
- `/help` - Show help information

### For Sellers
- `/sell` - Register or login as a seller
- Use the seller menu to:
  - Add products
  - View your products
  - Manage pending orders
  - Set payment method

### For Admin
- `/admin_trades` - View all pending trades
- `/resolve <order_id> <refund|release>` - Resolve disputes

## How Escrow Works

1. **Buyer Purchases**: Pays Product Price + KSh 10 fee via M-Pesa
2. **Payment Held**: Funds held in escrow (your Paybill account)
3. **Seller Ships**: Marks order as shipped, buyer notified
4. **Buyer Confirms**: Confirms receipt of item
5. **Funds Released**: Product Price sent to seller via B2C

### Dispute Flow
- Buyer can report issues instead of confirming
- Admin investigates and decides: refund buyer OR release to seller
- Manual disbursement for dispute resolutions

## M-Pesa Setup

### 1. Get Daraja API Credentials

1. Register at [Safaricom Developer Portal](https://developer.safaricom.co.ke/)
2. Create an app to get Consumer Key and Secret
3. For STK Push: Get Lipa Na M-Pesa passkey
4. For B2C: Apply for B2C API access

### 2. Sandbox Testing

Use sandbox credentials first:
- Set `MPESA_ENV=sandbox` in `.env`
- Use test phone numbers provided by Safaricom

### 3. Production

- Apply for production credentials
- Set `MPESA_ENV=production`
- Ensure callback URLs are publicly accessible

## Deployment to Heroku

### 1. Create Heroku App

```bash
heroku login
heroku create your-app-name
```

### 2. Set Environment Variables

```bash
heroku config:set BOT_TOKEN=your_token
heroku config:set ADMIN_TELEGRAM_ID=your_id
heroku config:set MPESA_CONSUMER_KEY=your_key
# ... set all other variables
```

### 3. Deploy

```bash
git push heroku main
```

### 4. Scale Worker

```bash
heroku ps:scale worker=1
```

### 5. For M-Pesa Callbacks

If using M-Pesa API, you need a web server for callbacks. Options:

1. **Separate Web Dyno**: Add `web: python webhook_server.py` to Procfile
2. **External Webhook Service**: Use a service like ngrok for testing

## Database

Uses SQLite for simplicity. For production with multiple dynos, consider:
- PostgreSQL with Heroku Postgres addon
- Update database.py to use psycopg2

## Project Structure

```
TG_Bot/
├── bot.py              # Main bot application
├── database.py         # SQLite database operations
├── mpesa.py            # M-Pesa Daraja API integration
├── webhook_server.py   # Webhook server for M-Pesa callbacks
├── requirements.txt    # Python dependencies
├── Procfile           # Heroku process file
├── runtime.txt        # Python version for Heroku
├── .env.example       # Example environment variables
├── .gitignore         # Git ignore file
└── README.md          # This file
```

## Security Considerations

- Passwords are hashed with SHA-256
- Age verification required
- Input validation on all user inputs
- Sensitive data stored in environment variables
- Admin commands restricted by Telegram ID

## Customization

### Change Escrow Fee
Edit `database.py` line with `fee INTEGER DEFAULT 10`

### Add More Payment Methods
Extend the `mpesa.py` module or add new payment providers

### Modify Product Categories
Add a `category` field to the products table

## Troubleshooting

### Bot not responding
- Check BOT_TOKEN is correct
- Ensure bot is running: `heroku logs --tail`

### M-Pesa not working
- Verify all M-Pesa credentials
- Check callback URL is accessible
- Start with sandbox mode

### Database errors
- Delete `bot.db` to reset (loses all data)
- Check file permissions

## License

MIT License - feel free to use and modify for your needs.

## Support

For issues, create a GitHub issue or contact the admin via the bot.
