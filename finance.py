import yfinance as yf
from database import get_db_connection
import datetime

def get_stock_info(ticker):
    """
    Haalt actuele koersinformatie op via yfinance.
    :param ticker: ticker symbool (bijv. 'AAPL')
    :return: dict met 'price', 'name', 'currency'
    """
    if ticker.upper() == 'CASH':
        return {'price': 1.0, 'name': 'Euro Cash', 'currency': 'EUR'}
        
    try:
        stock = yf.Ticker(ticker)
        # Gebruik fast_info voor snelheid as preferred door yfinance recent
        info = stock.fast_info
        
        # We halen de "longName" of "shortName" uit het volledige info dictionary als fallback
        full_info = stock.info
        name = full_info.get('longName', full_info.get('shortName', ticker))
        currency = full_info.get('currency', 'EUR')
        price = info.get('last_price', full_info.get('currentPrice', 0.0))
        
        return {
            'price': float(price),
            'name': name,
            'currency': currency
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {'price': 0.0, 'name': ticker, 'currency': 'EUR'}

def get_exchange_rate(currency):
    """
    Haalt de wisselkoers (naar EUR) op voor de opgegeven valuta.
    Als de valuta al EUR is, retourneer 1.0.
    Cacht de koers in de database per dag.
    """
    currency = currency.upper()
    if currency == 'EUR':
        return 1.0
        
    today = datetime.date.today().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check cache in DB
    c.execute('SELECT rate_to_eur FROM exchange_rates WHERE currency = ? AND date = ?', (currency, today))
    row = c.fetchone()
    
    if row:
        conn.close()
        return row['rate_to_eur']
        
    # As rate is not cached, fetch via yfinance
    # Pair format in yfinance for e.g., USD to EUR is 'EUR=X' (which means USD per 1 EUR, wait, no.
    # Actually, EURUSD=X gives the amount of USD for 1 EUR.
    # We want how many EUR for 1 unit of `currency`. E.g., for USD, we want EUR per USD.
    # The ticker for that is `USDEUR=X`.
    ticker = f"{currency}EUR=X"
    try:
        rate_ticker = yf.Ticker(ticker)
        # Soms heeft fast_info geen current price voor fx, fallback naar history
        history = rate_ticker.history(period="1d")
        if not history.empty:
            rate = float(history['Close'].iloc[-1])
            # Opslaan in cache
            c.execute('INSERT INTO exchange_rates (currency, date, rate_to_eur) VALUES (?, ?, ?)',
                      (currency, today, rate))
            conn.commit()
            conn.close()
            return rate
    except Exception as e:
        print(f"Error fetching exchange rate for {currency}: {e}")
    
    conn.close()
    return 1.0 # Fallback safety

def sync_stock_splits(ticker):
    """
    Controleert op stock splits via yfinance en slaat deze historisch op in de database.
    We cachen dit maximaal 1x per dag per aandeel.
    """
    if ticker.upper() == 'CASH':
        return
        
    today = datetime.date.today().isoformat()
    conn = get_db_connection()
    
    # Check if synced today
    log = conn.execute('SELECT last_sync_date FROM split_sync_log WHERE ticker = ?', (ticker,)).fetchone()
    if log and log['last_sync_date'] == today:
        conn.close()
        return

    try:
        stock = yf.Ticker(ticker)
        splits = stock.splits
        if not splits.empty:
            for date, ratio in splits.items():
                split_date = date.strftime('%Y-%m-%d')
                try:
                    conn.execute('INSERT OR IGNORE INTO stock_splits (ticker, date, ratio) VALUES (?, ?, ?)',
                                 (ticker, split_date, float(ratio)))
                except Exception as e:
                    pass # Ignore issues if split is already added
        
        # Update log
        conn.execute('INSERT OR REPLACE INTO split_sync_log (ticker, last_sync_date) VALUES (?, ?)', (ticker, today))
        conn.commit()
    except Exception as e:
        print(f"Error syncing splits for {ticker}: {e}")
    finally:
        conn.close()
