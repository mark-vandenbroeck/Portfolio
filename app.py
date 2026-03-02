from flask import Flask, render_template, request, redirect, url_for, flash
from database import get_db_connection, init_db
from finance import get_stock_info, get_exchange_rate, sync_stock_splits
import os

app = Flask(__name__)
app.secret_key = 'super_secret_portfolio_key'

# Zorg ervoor dat de DB bestaat bij opstarten
if not os.path.exists('portfolio.db'):
    init_db()

@app.route('/')
def index():
    conn = get_db_connection()
    portfolios = conn.execute('SELECT * FROM portfolios').fetchall()
    conn.close()
    return render_template('index.html', portfolios=portfolios)

@app.route('/portfolio/add', methods=('POST',))
def add_portfolio():
    name = request.form['name']
    if not name:
        flash('Naam is verplicht!')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('INSERT INTO portfolios (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/portfolio/<int:id>')
def portfolio_detail(id):
    conn = get_db_connection()
    portfolio = conn.execute('SELECT * FROM portfolios WHERE id = ?', (id,)).fetchone()
    if portfolio is None:
        conn.close()
        flash('Portefeuille niet gevonden.')
        return redirect(url_for('index'))
        
    transactions_cursor = conn.execute('SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY date ASC', (id,))
    transactions = [dict(row) for row in transactions_cursor.fetchall()]
    conn.close()
    
    # Sync splits voor alle actieve tickers in de portfeuille
    from finance import sync_stock_splits
    tickers = list(set([t['ticker'] for t in transactions if t['ticker'] != 'CASH']))
    for tk in tickers:
        sync_stock_splits(tk)
        
    # Haal bewaarde splits op voor deze tickers
    events = []
    events.extend(transactions)
    
    if tickers:
        conn = get_db_connection()
        placeholders = ','.join('?' for _ in tickers)
        splits = conn.execute(f'SELECT * FROM stock_splits WHERE ticker IN ({placeholders})', tickers).fetchall()
        for s in splits:
            # We zetten type op SPLIT en sturen de datum een fictieve tijd mee "00:00:00" zodat deze in strings kan sorteren
            events.append({
                'type': 'SPLIT',
                'ticker': s['ticker'],
                'date': s['date'] + ' 00:00:00',
                'ratio': s['ratio'],
                'shares': 0 # Dummy fields to prevent key errors
            })
        conn.close()
        
    # Sorteer alle gebeurtenissen chronologisch
    events.sort(key=lambda x: str(x['date']))

    # Bereken posities
    holdings = {}
    invested_curr = {}
    cash_eur = 0.0
    
    for e in events:
        ticker = e['ticker']
        if e['type'] == 'CASH_IN':
            cash_eur += e['shares']
        elif e['type'] == 'CASH_OUT':
            cash_eur -= e['shares']
        elif e['type'] == 'DIVIDEND':
            cash_eur += e['shares']
        elif e['type'] == 'BUY':
            if ticker not in holdings:
                holdings[ticker] = 0
                invested_curr[ticker] = 0.0
            holdings[ticker] += e['shares']
            
            # Deduct the total cost of the purchase from cash balance
            cost_curr = e['shares'] * e.get('price_per_share', 0.0)
            exch_rate = get_exchange_rate(e.get('currency', 'EUR'))
            cost_eur = cost_curr * exch_rate + e.get('broker_cost_euro', 0.0)
            cash_eur -= cost_eur
            
            invested_curr[ticker] += cost_curr
        elif e['type'] == 'SELL':
            if ticker in holdings and holdings[ticker] > 0:
                # Add the revenue of the sale to cash balance
                revenue_curr = e['shares'] * e.get('price_per_share', 0.0)
                exch_rate = get_exchange_rate(e.get('currency', 'EUR'))
                revenue_eur = revenue_curr * exch_rate - e.get('broker_cost_euro', 0.0)
                cash_eur += revenue_eur
                
                # Verminder de geïnvesteerde waarde proportioneel met de verkochte fractie
                ratio = e['shares'] / holdings[ticker]
                invested_curr[ticker] -= invested_curr[ticker] * ratio
                holdings[ticker] -= e['shares']
        elif e['type'] == 'SPLIT':
            if ticker in holdings and holdings[ticker] > 0:
                holdings[ticker] *= e['ratio']
                
    # Verwijder lege posities
    active_tickers = [k for k, v in holdings.items() if v > 0]
    
    # Haal actuele data op
    holdings_data = []
    total_portfolio_value_eur = cash_eur
    
    total_holdings_net_value = 0.0
    total_holdings_profit_eur = 0.0
    total_holdings_invested = 0.0
    
    for ticker in active_tickers:
        shares = holdings[ticker]
        info = get_stock_info(ticker)
        current_price = info['price']
        currency = info['currency']
        exch_rate = get_exchange_rate(currency)
        
        avg_purchase_price = invested_curr[ticker] / shares if shares > 0 else 0.0
        
        # We berekenen brokerkosten (totaal historisch per aandeel)
        total_broker_cost = sum([t['broker_cost_euro'] for t in transactions if t['ticker'] == ticker])
        
        gross_value_curr = current_price * shares
        gross_value_eur = gross_value_curr * exch_rate
        net_value_eur = gross_value_eur - total_broker_cost
        
        # Profit calculations
        invested_eur = invested_curr[ticker] * exch_rate
        profit_eur = net_value_eur - invested_eur
        profit_pct = (profit_eur / (invested_eur + total_broker_cost)) * 100 if (invested_eur + total_broker_cost) > 0 else 0.0
        
        holdings_data.append({
            'ticker': ticker,
            'name': info['name'],
            'shares': shares,
            'currency': currency,
            'avg_purchase_price': avg_purchase_price,
            'current_price': current_price,
            'broker_cost': total_broker_cost,
            'gross_value_curr': gross_value_curr,
            'net_value_eur': net_value_eur,
            'profit_eur': profit_eur,
            'profit_pct': profit_pct,
            'dividend_yield': info.get('dividend_yield', 'N/B')
        })
        total_portfolio_value_eur += net_value_eur
        
        total_holdings_net_value += net_value_eur
        total_holdings_profit_eur += profit_eur
        total_holdings_invested += (invested_eur + total_broker_cost)

    total_holdings_profit_pct = (total_holdings_profit_eur / total_holdings_invested) * 100 if total_holdings_invested > 0 else 0.0

    return render_template('portfolio.html', 
                           portfolio=portfolio, 
                           holdings=holdings_data, 
                           cash_eur=cash_eur,
                           total_value=total_portfolio_value_eur,
                           total_holdings_net_value=total_holdings_net_value,
                           total_holdings_profit_eur=total_holdings_profit_eur,
                           total_holdings_profit_pct=total_holdings_profit_pct)

@app.route('/portfolio/<int:id>/transaction', methods=('POST',))
def add_transaction(id):
    ticker = request.form.get('ticker', '').upper()
    trans_type = request.form['type']
    shares = float(request.form.get('shares', 0))
    price_per_share = float(request.form.get('price_per_share', 0))
    broker_cost_euro = float(request.form.get('broker_cost_euro', 0))
    currency = request.form.get('currency', 'EUR').upper()
    
    # Defaults for CASH transactions
    if trans_type in ['CASH_IN', 'CASH_OUT', 'DIVIDEND']:
        if trans_type in ['CASH_IN', 'CASH_OUT']:
            ticker = 'CASH'
        currency = 'EUR'
        price_per_share = 1.0
        
    # Prevent negative cash balances
    if trans_type in ['BUY', 'CASH_OUT']:
        conn = get_db_connection()
        transactions = conn.execute('SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY date ASC', (id,)).fetchall()
        conn.close()
        
        current_cash_eur = 0.0
        for t in transactions:
            e = dict(t)
            if e['type'] in ['CASH_IN', 'DIVIDEND']:
                current_cash_eur += e['shares']
            elif e['type'] == 'CASH_OUT':
                current_cash_eur -= e['shares']
            elif e['type'] == 'BUY':
                c_curr = e['shares'] * e.get('price_per_share', 0.0)
                e_rate = get_exchange_rate(e.get('currency', 'EUR'))
                c_eur = c_curr * e_rate + e.get('broker_cost_euro', 0.0)
                current_cash_eur -= c_eur
            elif e['type'] == 'SELL':
                r_curr = e['shares'] * e.get('price_per_share', 0.0)
                e_rate = get_exchange_rate(e.get('currency', 'EUR'))
                r_eur = r_curr * e_rate - e.get('broker_cost_euro', 0.0)
                current_cash_eur += r_eur
                
        # Calculate cost for the NEW transaction
        if trans_type == 'CASH_OUT':
            new_cost_eur = shares
        else: # BUY
            n_curr = shares * price_per_share
            n_rate = get_exchange_rate(currency)
            new_cost_eur = n_curr * n_rate + broker_cost_euro
            
        if current_cash_eur < new_cost_eur:
            flash(f'Onvoldoende cash beschikbaar! (Beschikbaar: € {current_cash_eur:.2f}, Nodig: € {new_cost_eur:.2f})')
            return redirect(url_for('portfolio_detail', id=id))
        
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO transactions (portfolio_id, ticker, type, shares, price_per_share, currency, broker_cost_euro)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (id, ticker, trans_type, shares, price_per_share, currency, broker_cost_euro))
    conn.commit()
    conn.close()
    
    flash('Transactie succesvol toegevoegd.')
    return redirect(url_for('portfolio_detail', id=id))

@app.route('/portfolio/<int:id>/delete', methods=('POST',))
def delete_portfolio(id):
    conn = get_db_connection()
    # Verwijder eerst de bijbehorende transacties om integriteit te behouden
    conn.execute('DELETE FROM transactions WHERE portfolio_id = ?', (id,))
    # Verwijder de portefeuille
    conn.execute('DELETE FROM portfolios WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Portefeuille succesvol verwijderd.')
    return redirect(url_for('index'))

@app.route('/portfolio/<int:id>/history')
def history(id):
    conn = get_db_connection()
    portfolio = conn.execute('SELECT * FROM portfolios WHERE id = ?', (id,)).fetchone()
    transactions = conn.execute('SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY date DESC', (id,)).fetchall()
    conn.close()
    return render_template('history.html', portfolio=portfolio, transactions=transactions)

@app.route('/exchange_rates')
def exchange_rates():
    portfolio_id = request.args.get('portfolio_id')
    conn = get_db_connection()
    # Zorg dat we effectieve rates hebben.
    rates = conn.execute('SELECT * FROM exchange_rates ORDER BY date DESC, currency ASC').fetchall()
    conn.close()
    return render_template('exchange_rates.html', rates=rates, portfolio_id=portfolio_id)

@app.route('/api/ticker_info/<ticker>')
def api_ticker_info(ticker):
    import yfinance as yf
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        try:
            price = stock.fast_info.last_price
        except:
            price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
            
        # Extract interesting details, falling back to 'N/B' (Niet Beschikbaar)
        data = {
            'ticker': ticker,
            'name': info.get('longName', info.get('shortName', ticker)),
            'sector': info.get('sector', 'N/B'),
            'industry': info.get('industry', 'N/B'),
            'country': info.get('country', 'N/B'),
            'marketCap': info.get('marketCap', 'N/B'),
            'currency': info.get('currency', 'EUR'),
            'price': price,
            'dayHigh': info.get('dayHigh', 'N/B'),
            'dayLow': info.get('dayLow', 'N/B'),
            'fiftyTwoWeekHigh': info.get('fiftyTwoWeekHigh', 'N/B'),
            'fiftyTwoWeekLow': info.get('fiftyTwoWeekLow', 'N/B'),
            'dividendYield': round(float(info.get('dividendYield', 0)), 2) if info.get('dividendYield') else 'N/B',
            'website': info.get('website', '#')
        }
        
        # Ophalen van historische data voor de grafiek (laatste 1 jaar)
        try:
            hist = stock.history(period="1y")
            if not hist.empty:
                # Converteer datums naar string formaat ('YYYY-MM-DD') en waarden naar floats
                dates = hist.index.strftime('%Y-%m-%d').tolist()
                prices = [round(float(p), 2) for p in hist['Close'].tolist()]
                data['history'] = {
                    'dates': dates,
                    'prices': prices
                }
            else:
                data['history'] = None
        except Exception as e:
            print(f"Error fetching history for {ticker}: {e}")
            data['history'] = None
            
        return data
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/portfolio/<int:id>/history_chart')
def api_portfolio_history_chart(id):
    conn = get_db_connection()
    portfolio = conn.execute('SELECT * FROM portfolios WHERE id = ?', (id,)).fetchone()
    if not portfolio:
        conn.close()
        return {'error': 'Portfolio not found'}, 404
        
    transactions = [dict(row) for row in conn.execute('SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY date ASC', (id,)).fetchall()]
    conn.close()
    
    if not transactions:
        return {'dates': [], 'values': []}

    # Extract all unique tickers (excluding CASH)
    tickers = list(set([t['ticker'] for t in transactions if t['ticker'] != 'CASH']))
    
    # Sync splits first
    from finance import sync_stock_splits, get_exchange_rate
    for tk in tickers:
        sync_stock_splits(tk)
        
    # Get all splits for these tickers
    events = []
    events.extend(transactions)
    if tickers:
        conn = get_db_connection()
        placeholders = ','.join('?' for _ in tickers)
        splits = conn.execute(f'SELECT * FROM stock_splits WHERE ticker IN ({placeholders})', tickers).fetchall()
        for s in splits:
            events.append({
                'type': 'SPLIT',
                'ticker': s['ticker'],
                'date': s['date'] + ' 00:00:00',
                'ratio': s['ratio'],
                'shares': 0
            })
        conn.close()
        
    # Sort chronologically
    events.sort(key=lambda x: str(x['date']))
    
    # Download 1 year of data for all tickers to map historical prices
    import yfinance as yf
    import datetime
    
    hist_prices = {}
    ticker_currencies = {}
    
    if tickers:
        try:
            # We can download data in bulk via yf.download
            # Returns a multi-index dataframe if multiple tickers, or single index if 1 ticker.
            data = yf.download(tickers, period="1y", group_by="ticker", auto_adjust=False, actions=False, threads=True)
            
            for tk in tickers:
                # Store currency for the ticker using fast_info
                try:
                    tk_info = yf.Ticker(tk).fast_info
                    ticker_currencies[tk] = tk_info.get('currency', 'EUR')
                except:
                    ticker_currencies[tk] = 'EUR'
                    
                hist_prices[tk] = {}
                if len(tickers) == 1:
                    tk_data = data
                else:
                    try:
                        tk_data = data[tk]
                    except KeyError:
                        continue # Data missing
                
                if not tk_data.empty:
                    # Map date str to close price
                    for date_ts, row in tk_data.iterrows():
                        date_str = date_ts.strftime('%Y-%m-%d')
                        if 'Close' in tk_data.columns:
                            close_val = row['Close']
                            if not import_pandas_check_isnan(close_val):
                                hist_prices[tk][date_str] = float(close_val)
        except Exception as e:
            print(f"Error fetching bulk history: {e}")

    # Generate a timeline of dates for the last year (or from first transaction if later)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365)
    
    if events:
        first_event_date = datetime.datetime.strptime(events[0]['date'].split(' ')[0], '%Y-%m-%d').date()
        if first_event_date > start_date:
            start_date = first_event_date
            
    # Calculate exchange rates cache (use latest available as an approximation to avoid fetching 365 fx points)
    fx_cache = {}
    for tk, cur in ticker_currencies.items():
        if cur not in fx_cache:
            fx_cache[cur] = get_exchange_rate(cur)
            
    # Iterate through each day to build the timeline
    chart_dates = []
    chart_values = []
    
    current_holdings = {}
    current_cash_eur = 0.0
    event_idx = 0
    total_events = len(events)
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Process any events that happened on or before this day
        while event_idx < total_events:
            ev = events[event_idx]
            ev_date_str = ev['date'].split(' ')[0]
            if ev_date_str > date_str:
                break # Event happens in the future relative to our current loop date
                
            ticker = ev['ticker']
            if ev['type'] in ['CASH_IN', 'DIVIDEND']:
                current_cash_eur += ev['shares']
            elif ev['type'] == 'CASH_OUT':
                current_cash_eur -= ev['shares']
            elif ev['type'] == 'BUY':
                if ticker not in current_holdings:
                    current_holdings[ticker] = 0
                current_holdings[ticker] += ev['shares']
                
                # Deduct cost from cash
                cost_curr = ev['shares'] * ev.get('price_per_share', 0.0)
                e_rate = get_exchange_rate(ev.get('currency', 'EUR')) # Historical rate isn't perfectly simulated here, we use live
                cost_eur = cost_curr * e_rate + ev.get('broker_cost_euro', 0.0)
                current_cash_eur -= cost_eur
            elif ev['type'] == 'SELL':
                if ticker in current_holdings:
                    # Add revenue to cash
                    revenue_curr = ev['shares'] * ev.get('price_per_share', 0.0)
                    e_rate = get_exchange_rate(ev.get('currency', 'EUR'))
                    revenue_eur = revenue_curr * e_rate - ev.get('broker_cost_euro', 0.0)
                    current_cash_eur += revenue_eur
                    
                    current_holdings[ticker] -= ev['shares']
            elif ev['type'] == 'SPLIT':
                if ticker in current_holdings:
                    current_holdings[ticker] *= ev['ratio']
                    
            event_idx += 1
            
        # Calculate end-of-day portfolio value
        eod_value_eur = current_cash_eur
        
        for tk, shares in current_holdings.items():
            if shares > 0:
                # Find the closest historic price for this date
                price = None
                if tk in hist_prices:
                    # Try to get exact date, if weekend/holiday find previous valid date within 7 days
                    check_date = current_date
                    for _ in range(7):
                        check_str = check_date.strftime('%Y-%m-%d')
                        if check_str in hist_prices[tk]:
                            price = hist_prices[tk][check_str]
                            break
                        check_date -= datetime.timedelta(days=1)
                
                if price is not None:
                    # Convert to EUR using current exchange rate approximation
                    cur = ticker_currencies.get(tk, 'EUR')
                    fx = fx_cache.get(cur, 1.0)
                    eod_value_eur += (price * shares) * fx
                else:
                    # If we really can't find a price, we fall back to the buying price or 0 (rough approx)
                    pass
        
        # Only add to chart if we have data after the first deposit/transaction (prevent useless flat 0s at the start)
        if eod_value_eur != 0.0 or chart_values:
            chart_dates.append(date_str)
            chart_values.append(round(eod_value_eur, 2))
            
        current_date += datetime.timedelta(days=1)
        
    return {
        'dates': chart_dates,
        'values': chart_values
    }

def import_pandas_check_isnan(val):
    import math
    try:
        if math.isnan(val):
            return True
    except:
        pass
    import pandas as pd
    return pd.isna(val)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
