# Portfolio Tracker

Een gebruiksvriendelijke, lokaal gehoste webapplicatie gebouwd met **Flask** voor het volgen en beheren van één of meerdere beleggingsportefeuilles.

## 🚀 Kenmerken

- **Meerdere portefeuilles beheren:** Maak verschillende portefeuilles aan (bijv. "Lange termijn", "Pensioen", "Opties") en verwijder ze indien nodig inclusief historie.
- **Transactie-ondersteuning:** Registreer stortingen (`CASH_IN`), opnames (`CASH_OUT`), aankopen (`BUY`) en verkopen (`SELL`). 
- **Cash Protectie:** Geavanceerde transactiecontroles voorkomen dat je cashbalans onder nul duikt bij aankopen of opnames.
- **Historische Grafieken:** Ingebouwde integratie met `Chart.js` via een interactieve modal om 1-jaars koersgrafieken direct op te roepen.
- **Globale Zoekfunctie:** Gebruik de snelle zoekbalk bovenaan elke pagina om direct de koers, dag-randen en 52-weken range van willekeurige tickers te bekijken zonder ze toe te voegen aan een portefeuille.
- **Live koersdata:** Integreert met de `yfinance` bibliotheek om actuele aandelenkoersen en bedrijfsinformatie op te halen.
- **Automatische wisselkoersen:** Alle investeringen (in USD, GBP, etc.) worden automatisch teruggerekend naar Euro (EUR) op basis van de meest recente wisselkoersen. Deze rates worden per dag lokaal gecached.
- **Stock Splits:** De applicatie detecteert automatisch stock splits via Yahoo Finance en verwerkt deze historisch met terugwerkende kracht in jouw portfolio om de positieaantallen kloppend te houden.
- **Winst- & Verliesberekening (P&L):** Berekening van de gemiddelde aankoopprijs, actuele posities en gecombineerde totaalwaardes van de portefeuille, inclusief rendement en valutaimpact.
- **Brokerkosten:** Houd de gemaakte brokerkosten bij per transactie voor een nauwkeuriger beeld van het werkelijke rendement.

## 🛠️ Technologie Stack

- **Backend:** Python 3, Flask
- **Database:** SQLite (vaste lokale opslag in `portfolio.db`)
- **Externe APIs / Data:** `yfinance`
- **Frontend:** HTML5, CSS3, Jinja2 templating

## 📁 Bestandsstructuur

- `app.py`: De hoofd Flask-applicatie. Ontvangt webverzoeken, bevat de routes (`/`) en berekent de actuele portfolio statistieken op basis van de opgeslagen gebeurtenissen.
- `database.py`: Functies voor de verbinding met de SQLite database en de opbouw van de tabellen (`portfolios`, `transactions`, `exchange_rates`, `stock_splits`, etc).
- `finance.py`: Modulen die externe communicatie afhandelen, waaronder het fetchen van koersinformatie, actuele wisselkoersen ophalen en stock splits synchroniseren in de achtergrond.
- `templates/`: Bevat alle Jinja2 HTML layouts  (`index.html`, `portfolio.html`, `history.html`, `exchange_rates.html`, `base.html`).
- `static/`: Map voor algemene asset styling, zoals het `style.css` bestand.

## ⚙️ Installatie & Gebruik

### Vereisten
Zorg ervoor dat **Python 3.x** op je machine geïnstalleerd is.

### 1. Repository lokaal voorbereiden
Open de terminal in je projectmap. We raden het gebruik van een _virtual environment_ aan om pakketversies geïsoleerd te houden:

```bash
python3 -m venv venv
source venv/bin/activate  # (Op Windows gebruik je: venv\Scripts\activate)
```

### 2. Afhankelijkheden installeren
Je hebt een aantal Python library's nodig. Omdat er in de originele opzet geen requirements list is, dien je deze hoofdpakketten direct te installeren:

```bash
pip install flask yfinance
```

### 3. Applicatie opstarten
Zodra de packages geïnstalleerd zijn kun je de app lokaal opstarten. De SQLite database zal de eerste keer automatisch geïnitialiseerd worden als het bestand `portfolio.db` ontbreekt.

```bash
python3 app.py
```

### 4. Applicatie bezoeken in de webbrowser
De server zal lokaal gestart worden en draait in development (debug) mode op poort 5000. Open je browser en ga naar:

```
http://127.0.0.1:5000
```

## 📊 Hoe werkt de portefeuille logica?

- **Cash Balans:** Alle `CASH_IN` events worden bij elkaar opgeteld en kosten voor aankopen (`BUY`) plus opnames (`CASH_OUT`) worden daarvan afgetrokken. Verkopen voegen netto cash toe. Verkeerde invoer waarbij je méér uitgeeft dan je bezit, wordt automatisch geblokkeerd!
- **Chronologische Volgorde:** Wanneer je een specifieke portefeuille bekijkt, dan worden alle transacties plus historisch relevante stock-splits in chronologische volgorde herleid om je positie exact op te bouwen. 
- **Profit berekening:** Het winstpercentage houdt rekening met verkochte elementen (via de rato van het aandelenvolume), koersschommelingen ten opzichte van aankoop in de vreemde valuta en de impact van berekende brokerkosten in euro's.

## 📝 Aandachtspunten
- Aandelentickers in de applicatie corresponderen verplicht met de beurssymbolen zoals ze op *Yahoo Finance* staan (bijvoorbeeld `AAPL` voor Apple, of `VOW3.DE` voor Volkswagen AG op de Duitse beurs).
