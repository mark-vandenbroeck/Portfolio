import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', 'portfolio.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create portfolios table
    c.execute('''
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    ''')
    
    # Create transactions table
    # type: 'BUY', 'SELL', 'CASH_IN', 'CASH_OUT'
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            type TEXT NOT NULL,
            shares REAL,
            price_per_share REAL,
            currency TEXT,
            broker_cost_euro REAL DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(portfolio_id) REFERENCES portfolios(id)
        )
    ''')
    
    # Create exchange_rates table for caching
    c.execute('''
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT NOT NULL,
            date DATE NOT NULL,
            rate_to_eur REAL NOT NULL,
            UNIQUE(currency, date)
        )
    ''')
    
    # Create stock_splits table
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_splits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date DATE NOT NULL,
            ratio REAL NOT NULL,
            UNIQUE(ticker, date)
        )
    ''')
    
    # Create split_sync_log table
    c.execute('''
        CREATE TABLE IF NOT EXISTS split_sync_log (
            ticker TEXT PRIMARY KEY,
            last_sync_date DATE NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    print("Database wordt geïnitialiseerd...")
    init_db()
    print("Database initialisatie voltooid.")
