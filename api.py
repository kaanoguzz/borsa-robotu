"""
Flask API ve Web Dashboard
Borsa robotu için REST API ve web arayüzü
"""

from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='dashboard', static_url_path='')
CORS(app)

# Lazy imports - modüller ihtiyaç halinde yüklenir
_signal_generator = None
_portfolio_manager = None
_data_collector = None
_news_analyzer = None


def get_signal_generator():
    global _signal_generator
    if _signal_generator is None:
        from signal_generator import SignalGenerator
        _signal_generator = SignalGenerator()
    return _signal_generator


def get_portfolio():
    global _portfolio_manager
    if _portfolio_manager is None:
        from portfolio import PortfolioManager
        _portfolio_manager = PortfolioManager()
    return _portfolio_manager


def get_data_collector():
    global _data_collector
    if _data_collector is None:
        from data_collector import DataCollector
        _data_collector = DataCollector()
    return _data_collector


def get_news_analyzer():
    global _news_analyzer
    if _news_analyzer is None:
        from news_analyzer import NewsAnalyzer
        _news_analyzer = NewsAnalyzer()
    return _news_analyzer


# ==================== DASHBOARD ====================

@app.route('/')
def serve_dashboard():
    """Dashboard ana sayfası"""
    return send_from_directory('dashboard', 'index.html')


# ==================== API ENDPOINTS ====================

@app.route('/api/status')
def api_status():
    """Sistem durumu"""
    return jsonify({
        "status": "active",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "market_hours": "10:00-18:00 (TSI)"
    })


@app.route('/api/analyze/<symbol>')
def api_analyze(symbol):
    """Hisse analizi"""
    try:
        sg = get_signal_generator()
        result = sg.analyze_stock(symbol.upper())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/price/<symbol>')
def api_price(symbol):
    """Anlık fiyat"""
    try:
        dc = get_data_collector()
        price = dc.get_current_price(symbol.upper())
        if price:
            return jsonify(price)
        return jsonify({"error": "Fiyat bulunamadı"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/stock-info/<symbol>')
def api_stock_info(symbol):
    """Hisse bilgileri"""
    try:
        dc = get_data_collector()
        info = dc.get_stock_info(symbol.upper())
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/history/<symbol>')
def api_history(symbol):
    """Fiyat geçmişi"""
    period = request.args.get('period', '6mo')
    try:
        dc = get_data_collector()
        df = dc.get_stock_data(symbol.upper(), period=period)
        if df.empty:
            return jsonify({"error": "Veri bulunamadı"}), 404
        
        history = []
        for idx, row in df.iterrows():
            history.append({
                "date": idx.strftime('%Y-%m-%d'),
                "open": round(row['Open'], 2),
                "high": round(row['High'], 2),
                "low": round(row['Low'], 2),
                "close": round(row['Close'], 2),
                "volume": int(row['Volume'])
            })
        
        return jsonify({"symbol": symbol.upper(), "period": period, "data": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/news/<symbol>')
def api_news(symbol):
    """Hisse haberleri"""
    try:
        na = get_news_analyzer()
        news = na.get_stock_news(symbol.upper())
        return jsonify({"symbol": symbol.upper(), "news": news})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/market-news')
def api_market_news():
    """Piyasa haberleri"""
    try:
        na = get_news_analyzer()
        news = na.get_market_news()
        return jsonify({"news": news})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== PORTFÖY API ====================

@app.route('/api/portfolio')
def api_get_portfolio():
    """Portföyü getir"""
    try:
        pm = get_portfolio()
        dc = get_data_collector()
        
        holdings = pm.get_portfolio()
        prices = {}
        
        for h in holdings:
            price_info = dc.get_current_price(h["symbol"])
            if price_info:
                prices[h["symbol"]] = price_info["price"]
        
        portfolio_value = pm.get_portfolio_value(prices)
        return jsonify(portfolio_value)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/portfolio/add', methods=['POST'])
def api_add_to_portfolio():
    """Portföye hisse ekle"""
    try:
        data = request.json
        pm = get_portfolio()
        result = pm.add_stock(
            data['symbol'].upper(),
            float(data['quantity']),
            float(data['buy_price']),
            data.get('notes', '')
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/portfolio/remove', methods=['POST'])
def api_remove_from_portfolio():
    """Portföyden hisse çıkar"""
    try:
        data = request.json
        pm = get_portfolio()
        result = pm.remove_stock(
            data['symbol'].upper(),
            float(data['quantity']),
            float(data['sell_price']),
            data.get('reason', '')
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/transactions')
def api_transactions():
    """İşlem geçmişi"""
    try:
        symbol = request.args.get('symbol')
        pm = get_portfolio()
        transactions = pm.get_transactions(symbol)
        return jsonify({"transactions": transactions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== SİNYAL API ====================

@app.route('/api/signals')
def api_signals():
    """Sinyal geçmişi"""
    try:
        symbol = request.args.get('symbol')
        pm = get_portfolio()
        signals = pm.get_signals(symbol)
        return jsonify({"signals": signals})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def api_scan():
    """Piyasa taraması"""
    try:
        data = request.json or {}
        symbols = data.get('symbols')
        sg = get_signal_generator()
        results = sg.scan_market(symbols)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== WATCHLIST API ====================

@app.route('/api/watchlist')
def api_watchlist():
    """Takip listesi"""
    try:
        pm = get_portfolio()
        watchlist = pm.get_watchlist()
        return jsonify({"watchlist": watchlist})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/watchlist/add', methods=['POST'])
def api_add_watchlist():
    """Takip listesine ekle"""
    try:
        data = request.json
        pm = get_portfolio()
        result = pm.add_to_watchlist(
            data['symbol'].upper(),
            data.get('target_buy', 0),
            data.get('target_sell', 0),
            data.get('notes', '')
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/watchlist/remove/<symbol>', methods=['DELETE'])
def api_remove_watchlist(symbol):
    """Takip listesinden çıkar"""
    try:
        pm = get_portfolio()
        result = pm.remove_from_watchlist(symbol.upper())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== BIST 100 ====================

@app.route('/api/bist100')
def api_bist100():
    """BIST 100 listesi"""
    from config import BIST100_TICKERS, SECTORS, get_sector
    
    stocks = []
    for ticker in BIST100_TICKERS:
        stocks.append({
            "symbol": ticker,
            "sector": get_sector(ticker)
        })
    
    return jsonify({
        "stocks": stocks,
        "sectors": list(SECTORS.keys()),
        "total": len(BIST100_TICKERS)
    })


def start_dashboard(port: int = 5000):
    """Dashboard'u başlat"""
    app.run(host='0.0.0.0', port=port, debug=False)
