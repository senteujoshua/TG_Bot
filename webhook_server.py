"""
Webhook Server for M-Pesa Callbacks.
Run this alongside the bot for production M-Pesa integration.
"""

import os
import logging
from aiohttp import web

import database as db
import mpesa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot instance will be set from main bot
bot_app = None


def set_bot_application(app):
    """Set the bot application for sending notifications."""
    global bot_app
    bot_app = app


async def mpesa_stk_callback(request):
    """
    Handle M-Pesa STK Push callback.
    Called by M-Pesa when payment is completed or fails.
    """
    try:
        data = await request.json()
        logger.info(f"STK Callback received: {data}")

        result = mpesa.process_stk_callback(data)

        if result.get('paid'):
            # Find trade by checking recent pending trades
            # In production, store checkout_request_id in trade
            mpesa_receipt = result.get('mpesa_receipt')

            # Update trade if found
            # Note: In a full implementation, you'd store the
            # checkout_request_id when initiating STK push
            # and look it up here

            logger.info(f"Payment successful: {mpesa_receipt}")

            # Notify via bot if available
            if bot_app:
                # Could send admin notification here
                pass

        return web.json_response({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })
    except Exception as e:
        logger.error(f"Error processing STK callback: {e}")
        return web.json_response({
            "ResultCode": 1,
            "ResultDesc": "Error"
        })


async def mpesa_b2c_result(request):
    """
    Handle M-Pesa B2C result callback.
    Called when B2C disbursement completes.
    """
    try:
        data = await request.json()
        logger.info(f"B2C Result received: {data}")

        result = mpesa.process_b2c_callback(data)

        if result.get('paid'):
            logger.info(f"B2C payment successful: {result}")
        else:
            logger.warning(f"B2C payment failed: {result}")

        return web.json_response({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })
    except Exception as e:
        logger.error(f"Error processing B2C callback: {e}")
        return web.json_response({
            "ResultCode": 1,
            "ResultDesc": "Error"
        })


async def mpesa_b2c_timeout(request):
    """Handle M-Pesa B2C timeout callback."""
    try:
        data = await request.json()
        logger.warning(f"B2C Timeout: {data}")
        return web.json_response({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })
    except Exception as e:
        logger.error(f"Error processing B2C timeout: {e}")
        return web.json_response({
            "ResultCode": 1,
            "ResultDesc": "Error"
        })


async def health_check(request):
    """Health check endpoint."""
    return web.json_response({"status": "healthy"})


def create_webhook_app():
    """Create and configure the webhook web application."""
    app = web.Application()

    app.router.add_post('/mpesa/callback', mpesa_stk_callback)
    app.router.add_post('/mpesa/b2c/result', mpesa_b2c_result)
    app.router.add_post('/mpesa/b2c/timeout', mpesa_b2c_timeout)
    app.router.add_get('/health', health_check)

    return app


if __name__ == '__main__':
    # Run standalone webhook server (for testing)
    port = int(os.getenv('PORT', 8080))
    app = create_webhook_app()
    web.run_app(app, port=port)
