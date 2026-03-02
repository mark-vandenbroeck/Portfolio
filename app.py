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
            'profit_pct': profit_pct
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
    
    if trans_type in ['CASH_IN', 'CASH_OUT']:
        ticker = 'CASH'
        currency = 'EUR'
        price_per_share = 1.0
        
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO transactions (portfolio_id, ticker, type, shares, price_per_share, currency, broker_cost_euro)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (id, ticker, trans_type, shares, price_per_share, currency, broker_cost_euro))
    conn.commit()
    conn.close()
    
    flash('Transactie succesvol toegevoegd.')
    return redirect(url_for('portfolio_detail', id=id))

@app.route('/portfolio/<int:id>/history')
def history(id):
    conn = get_db_connection()
    portfolio = conn.execute('SELECT * FROM portfolios WHERE id = ?', (id,)).fetchone()
    transactions = conn.execute('SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY date DESC', (id,)).fetchall()
    conn.close()
    return render_template('history.html', portfolio=portfolio, transactions=transactions)

@app.route('/exchange_rates')
def exchange_rates():
    conn = get_db_connection()
    # Zorg dat we effectieve rates hebben.
    rates = conn.execute('SELECT * FROM exchange_rates ORDER BY date DESC, currency ASC').fetchall()
    conn.close()
    return render_template('exchange_rates.html', rates=rates)

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
            'summary': info.get('longBusinessSummary', 'Geen samenvatting beschikbaar.'),
            'marketCap': info.get('marketCap', 'N/B'),
            'currency': info.get('currency', 'EUR'),
            'price': price,
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
