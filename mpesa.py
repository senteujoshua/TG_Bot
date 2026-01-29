"""
M-Pesa Daraja API Integration Module.
Handles STK Push for payments and B2C for disbursements.
"""

import os
import base64
import requests
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# M-Pesa Configuration
MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY', '')
MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET', '')
MPESA_SHORTCODE = os.getenv('MPESA_SHORTCODE', '')  # Your Paybill/Till
MPESA_PASSKEY = os.getenv('MPESA_PASSKEY', '')
MPESA_B2C_INITIATOR = os.getenv('MPESA_B2C_INITIATOR', '')
MPESA_B2C_PASSWORD = os.getenv('MPESA_B2C_PASSWORD', '')
MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL', '')

# Use sandbox for testing, production for live
MPESA_ENV = os.getenv('MPESA_ENV', 'sandbox')

if MPESA_ENV == 'production':
    BASE_URL = 'https://api.safaricom.co.ke'
else:
    BASE_URL = 'https://sandbox.safaricom.co.ke'


class MpesaError(Exception):
    """Custom exception for M-Pesa errors."""
    pass


def get_access_token() -> Optional[str]:
    """
    Get OAuth access token from M-Pesa API.
    Returns the access token or None if failed.
    """
    if not MPESA_CONSUMER_KEY or not MPESA_CONSUMER_SECRET:
        logger.warning("M-Pesa credentials not configured")
        return None

    url = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"

    # Create basic auth header
    credentials = f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        'Authorization': f'Basic {encoded_credentials}'
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get('access_token')
    except requests.RequestException as e:
        logger.error(f"Failed to get M-Pesa access token: {e}")
        return None


def generate_password() -> tuple:
    """
    Generate the password for STK push.
    Returns (password, timestamp).
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    data_to_encode = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(data_to_encode.encode()).decode()
    return password, timestamp


def format_phone_number(phone: str) -> str:
    """
    Format phone number to M-Pesa format (254XXXXXXXXX).
    Handles various input formats.
    """
    phone = phone.strip().replace(' ', '').replace('-', '')

    if phone.startswith('+'):
        phone = phone[1:]
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    if not phone.startswith('254'):
        phone = '254' + phone

    return phone


def stk_push(phone: str, amount: int, order_id: str,
             description: str = "Payment for order") -> Dict[str, Any]:
    """
    Initiate STK Push (Lipa Na M-Pesa Online).
    Prompts the user to enter their M-Pesa PIN on their phone.

    Args:
        phone: Customer phone number
        amount: Amount in KSh
        order_id: Unique order reference
        description: Transaction description

    Returns:
        Dict with success status and response data
    """
    access_token = get_access_token()
    if not access_token:
        return {
            'success': False,
            'error': 'Failed to authenticate with M-Pesa',
            'manual_required': True
        }

    url = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"

    password, timestamp = generate_password()
    formatted_phone = format_phone_number(phone)

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": formatted_phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": formatted_phone,
        "CallBackURL": f"{MPESA_CALLBACK_URL}/mpesa/callback",
        "AccountReference": order_id,
        "TransactionDesc": description[:20]  # Max 20 chars
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        data = response.json()

        if data.get('ResponseCode') == '0':
            return {
                'success': True,
                'checkout_request_id': data.get('CheckoutRequestID'),
                'merchant_request_id': data.get('MerchantRequestID'),
                'message': 'STK push sent. Check your phone.'
            }
        else:
            return {
                'success': False,
                'error': data.get('ResponseDescription', 'STK Push failed'),
                'error_code': data.get('ResponseCode')
            }
    except requests.RequestException as e:
        logger.error(f"STK Push request failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'manual_required': True
        }


def query_stk_status(checkout_request_id: str) -> Dict[str, Any]:
    """
    Query the status of an STK Push request.

    Args:
        checkout_request_id: The CheckoutRequestID from STK push response

    Returns:
        Dict with status information
    """
    access_token = get_access_token()
    if not access_token:
        return {'success': False, 'error': 'Auth failed'}

    url = f"{BASE_URL}/mpesa/stkpushquery/v1/query"

    password, timestamp = generate_password()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        data = response.json()

        result_code = data.get('ResultCode')
        if result_code == '0':
            return {
                'success': True,
                'paid': True,
                'message': 'Payment successful'
            }
        elif result_code == '1032':
            return {
                'success': True,
                'paid': False,
                'message': 'Transaction cancelled by user'
            }
        elif result_code == '1037':
            return {
                'success': True,
                'paid': False,
                'message': 'Timeout - user did not respond'
            }
        else:
            return {
                'success': True,
                'paid': False,
                'message': data.get('ResultDesc', 'Payment not completed'),
                'result_code': result_code
            }
    except requests.RequestException as e:
        logger.error(f"STK query failed: {e}")
        return {'success': False, 'error': str(e)}


def b2c_payment(phone: str, amount: int, remarks: str = "Payment") -> Dict[str, Any]:
    """
    Send money to a customer (B2C - Business to Customer).
    Used for disbursing funds to sellers.

    Args:
        phone: Recipient phone number
        amount: Amount in KSh
        remarks: Transaction remarks

    Returns:
        Dict with success status and response data
    """
    access_token = get_access_token()
    if not access_token:
        return {
            'success': False,
            'error': 'Failed to authenticate with M-Pesa',
            'manual_required': True
        }

    url = f"{BASE_URL}/mpesa/b2c/v1/paymentrequest"

    formatted_phone = format_phone_number(phone)

    payload = {
        "InitiatorName": MPESA_B2C_INITIATOR,
        "SecurityCredential": MPESA_B2C_PASSWORD,  # Encrypted password
        "CommandID": "BusinessPayment",
        "Amount": amount,
        "PartyA": MPESA_SHORTCODE,
        "PartyB": formatted_phone,
        "Remarks": remarks[:100],
        "QueueTimeOutURL": f"{MPESA_CALLBACK_URL}/mpesa/b2c/timeout",
        "ResultURL": f"{MPESA_CALLBACK_URL}/mpesa/b2c/result",
        "Occasion": "Escrow Payment"
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        data = response.json()

        if data.get('ResponseCode') == '0':
            return {
                'success': True,
                'conversation_id': data.get('ConversationID'),
                'originator_conversation_id': data.get('OriginatorConversationID'),
                'message': 'B2C payment initiated'
            }
        else:
            return {
                'success': False,
                'error': data.get('ResponseDescription', 'B2C payment failed'),
                'error_code': data.get('ResponseCode')
            }
    except requests.RequestException as e:
        logger.error(f"B2C payment request failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'manual_required': True
        }


def process_stk_callback(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the callback from M-Pesa after STK push.

    Args:
        data: Callback data from M-Pesa

    Returns:
        Dict with parsed callback information
    """
    try:
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        merchant_request_id = stk_callback.get('MerchantRequestID')
        checkout_request_id = stk_callback.get('CheckoutRequestID')

        if result_code == 0:
            # Payment successful - extract metadata
            metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            meta_dict = {}
            for item in metadata:
                meta_dict[item.get('Name')] = item.get('Value')

            return {
                'success': True,
                'paid': True,
                'merchant_request_id': merchant_request_id,
                'checkout_request_id': checkout_request_id,
                'amount': meta_dict.get('Amount'),
                'mpesa_receipt': meta_dict.get('MpesaReceiptNumber'),
                'phone': meta_dict.get('PhoneNumber'),
                'transaction_date': meta_dict.get('TransactionDate')
            }
        else:
            return {
                'success': True,
                'paid': False,
                'result_code': result_code,
                'result_desc': result_desc,
                'merchant_request_id': merchant_request_id,
                'checkout_request_id': checkout_request_id
            }
    except Exception as e:
        logger.error(f"Error processing STK callback: {e}")
        return {'success': False, 'error': str(e)}


def process_b2c_callback(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the callback from M-Pesa after B2C payment.

    Args:
        data: Callback data from M-Pesa

    Returns:
        Dict with parsed callback information
    """
    try:
        result = data.get('Result', {})
        result_code = result.get('ResultCode')
        result_desc = result.get('ResultDesc')
        conversation_id = result.get('ConversationID')

        if result_code == 0:
            # Payment successful
            params = result.get('ResultParameters', {}).get('ResultParameter', [])
            param_dict = {}
            for param in params:
                param_dict[param.get('Key')] = param.get('Value')

            return {
                'success': True,
                'paid': True,
                'conversation_id': conversation_id,
                'transaction_id': param_dict.get('TransactionID'),
                'amount': param_dict.get('TransactionAmount'),
                'recipient': param_dict.get('ReceiverPartyPublicName')
            }
        else:
            return {
                'success': True,
                'paid': False,
                'result_code': result_code,
                'result_desc': result_desc,
                'conversation_id': conversation_id
            }
    except Exception as e:
        logger.error(f"Error processing B2C callback: {e}")
        return {'success': False, 'error': str(e)}


def is_mpesa_configured() -> bool:
    """Check if M-Pesa credentials are configured."""
    return bool(MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET and MPESA_SHORTCODE)


def get_manual_payment_instructions(amount: int, order_id: str) -> str:
    """
    Get manual payment instructions when API is not configured.

    Args:
        amount: Amount to pay in KSh
        order_id: Order reference number

    Returns:
        Formatted payment instructions string
    """
    shortcode = MPESA_SHORTCODE or "[PAYBILL]"
    return f"""
*Manual Payment Instructions:*

1. Go to M-Pesa on your phone
2. Select "Lipa na M-Pesa"
3. Select "Pay Bill"
4. Enter Business No: `{shortcode}`
5. Enter Account No: `{order_id}`
6. Enter Amount: KSh {amount:,}
7. Enter your M-Pesa PIN
8. Confirm the transaction

After payment, tap "I've Paid" button below.
"""
