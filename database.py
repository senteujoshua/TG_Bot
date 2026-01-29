"""
Database module for the Telegram Escrow Bot.
Handles SQLite database operations for sellers, products, and trades.
"""

import sqlite3
import hashlib
import os
from datetime import datetime
from typing import Optional, List, Tuple, Any

DATABASE_PATH = os.getenv('DATABASE_PATH', 'bot.db')


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Sellers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            payment_method TEXT DEFAULT 'till',
            payment_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            image_file_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES sellers(id)
        )
    ''')

    # Trades/Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            buyer_telegram_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            fee INTEGER DEFAULT 10,
            total_paid INTEGER NOT NULL,
            status TEXT DEFAULT 'pending_payment',
            buyer_phone TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            shipped_at TIMESTAMP,
            confirmed_at TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES sellers(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    # Age verification table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS age_verified (
            telegram_id INTEGER PRIMARY KEY,
            verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash


# ============== Seller Operations ==============

def create_seller(telegram_id: int, username: str, password: str) -> Optional[int]:
    """Create a new seller account. Returns seller ID or None if failed."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO sellers (telegram_id, username, password_hash)
            VALUES (?, ?, ?)
        ''', (telegram_id, username, hash_password(password)))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_seller_by_username(username: str) -> Optional[sqlite3.Row]:
    """Get seller by username."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sellers WHERE username = ?', (username,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_seller_by_telegram_id(telegram_id: int) -> Optional[sqlite3.Row]:
    """Get seller by Telegram ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sellers WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_seller_by_id(seller_id: int) -> Optional[sqlite3.Row]:
    """Get seller by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sellers WHERE id = ?', (seller_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def update_seller_payment(seller_id: int, payment_method: str, payment_number: str) -> bool:
    """Update seller's payment method."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sellers SET payment_method = ?, payment_number = ?
        WHERE id = ?
    ''', (payment_method, payment_number, seller_id))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def login_seller(username: str, password: str) -> Optional[sqlite3.Row]:
    """Authenticate a seller. Returns seller row if successful."""
    seller = get_seller_by_username(username)
    if seller and verify_password(password, seller['password_hash']):
        return seller
    return None


# ============== Product Operations ==============

def create_product(seller_id: int, name: str, description: str, price: int,
                   image_file_id: Optional[str] = None) -> int:
    """Create a new product. Returns product ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (seller_id, name, description, price, image_file_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (seller_id, name, description, price, image_file_id))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id


def get_product_by_id(product_id: int) -> Optional[sqlite3.Row]:
    """Get product by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_products_by_seller(seller_id: int) -> List[sqlite3.Row]:
    """Get all products for a seller."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products WHERE seller_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (seller_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def get_all_active_products() -> List[sqlite3.Row]:
    """Get all active products."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, s.username as seller_username
        FROM products p
        JOIN sellers s ON p.seller_id = s.id
        WHERE p.is_active = 1 AND s.is_active = 1
        ORDER BY p.created_at DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return results


def deactivate_product(product_id: int, seller_id: int) -> bool:
    """Deactivate a product (soft delete)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE products SET is_active = 0
        WHERE id = ? AND seller_id = ?
    ''', (product_id, seller_id))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# ============== Trade/Order Operations ==============

def generate_order_id() -> str:
    """Generate a unique order ID."""
    import uuid
    return f"ORD{uuid.uuid4().hex[:8].upper()}"


def create_trade(buyer_telegram_id: int, seller_id: int, product_id: int,
                 amount: int, fee: int = 10) -> Tuple[int, str]:
    """Create a new trade. Returns (trade_id, order_id)."""
    conn = get_connection()
    cursor = conn.cursor()
    order_id = generate_order_id()
    total_paid = amount + fee

    cursor.execute('''
        INSERT INTO trades (order_id, buyer_telegram_id, seller_id, product_id,
                           amount, fee, total_paid, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_payment')
    ''', (order_id, buyer_telegram_id, seller_id, product_id, amount, fee, total_paid))
    conn.commit()
    trade_id = cursor.lastrowid
    conn.close()
    return trade_id, order_id


def get_trade_by_id(trade_id: int) -> Optional[sqlite3.Row]:
    """Get trade by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_trade_by_order_id(order_id: str) -> Optional[sqlite3.Row]:
    """Get trade by order ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM trades WHERE order_id = ?', (order_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_trades_by_buyer(buyer_telegram_id: int) -> List[sqlite3.Row]:
    """Get all trades for a buyer."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, p.name as product_name, s.username as seller_username
        FROM trades t
        JOIN products p ON t.product_id = p.id
        JOIN sellers s ON t.seller_id = s.id
        WHERE t.buyer_telegram_id = ?
        ORDER BY t.created_at DESC
    ''', (buyer_telegram_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def get_trades_by_seller(seller_id: int, status: Optional[str] = None) -> List[sqlite3.Row]:
    """Get all trades for a seller, optionally filtered by status."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute('''
            SELECT t.*, p.name as product_name
            FROM trades t
            JOIN products p ON t.product_id = p.id
            WHERE t.seller_id = ? AND t.status = ?
            ORDER BY t.created_at DESC
        ''', (seller_id, status))
    else:
        cursor.execute('''
            SELECT t.*, p.name as product_name
            FROM trades t
            JOIN products p ON t.product_id = p.id
            WHERE t.seller_id = ?
            ORDER BY t.created_at DESC
        ''', (seller_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def update_trade_status(trade_id: int, status: str, **kwargs) -> bool:
    """Update trade status and optional fields."""
    conn = get_connection()
    cursor = conn.cursor()

    # Build dynamic update query
    fields = ['status = ?']
    values = [status]

    timestamp_fields = {
        'paid': 'paid_at',
        'shipped': 'shipped_at',
        'confirmed': 'confirmed_at'
    }

    if status in timestamp_fields:
        fields.append(f'{timestamp_fields[status]} = ?')
        values.append(datetime.now().isoformat())

    for key, value in kwargs.items():
        if key in ['mpesa_receipt', 'buyer_phone']:
            fields.append(f'{key} = ?')
            values.append(value)

    values.append(trade_id)
    query = f"UPDATE trades SET {', '.join(fields)} WHERE id = ?"

    cursor.execute(query, values)
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def get_pending_trades() -> List[sqlite3.Row]:
    """Get all pending trades (for admin)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, p.name as product_name, s.username as seller_username
        FROM trades t
        JOIN products p ON t.product_id = p.id
        JOIN sellers s ON t.seller_id = s.id
        WHERE t.status IN ('pending_payment', 'paid', 'shipped', 'disputed')
        ORDER BY t.created_at DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return results


# ============== Age Verification ==============

def is_age_verified(telegram_id: int) -> bool:
    """Check if user has verified their age."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM age_verified WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def set_age_verified(telegram_id: int) -> bool:
    """Mark user as age verified."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO age_verified (telegram_id) VALUES (?)
        ''', (telegram_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()


# Initialize database on module import
init_database()
