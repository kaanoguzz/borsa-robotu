"""
Veri Toplama Modülü
Yahoo Finance üzerinden BIST hisse verilerini çeker
"""

# ===== SSL Sertifika Fix (Windows Türkçe Kullanıcı Adı) =====
import os
import ssl
import shutil
import certifi

# Türkçe karakter (ğ,ş,ı vb.) içeren path'ler curl_cffi'yi kırıyor.
# cacert.pem'i TEMP dizinine kopyalayıp o yolu kullanıyoruz.
_original_cert = certifi.where()
_safe_cert = os.path.join(os.environ.get('TEMP', '.'), 'cacert.pem')
try:
    shutil.copy2(_original_cert, _safe_cert)
    os.environ['CURL_CA_BUNDLE'] = _safe_cert
    os.environ['SSL_CERT_FILE'] = _safe_cert
    os.environ['REQUESTS_CA_BUNDLE'] = _safe_cert
    certifi.where = lambda: _safe_cert
except Exception:
    pass

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass
# ============================================================

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import get_yahoo_ticker, BIST100_TICKERS
import logging
import time

logger = logging.getLogger(__name__)


class DataCollector:
    """BIST 100 hisse verilerini Yahoo Finance üzerinden toplar"""

    def __init__(self):
        self.cache = {}
        self.cache_expiry = {}
        self.cache_duration = 900  # 15 dakika cache

    def get_stock_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Bir hissenin fiyat geçmişini çeker
        
        Args:
            symbol: BIST sembolü (örn: THYAO)
            period: Veri periyodu (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)
            interval: Veri aralığı (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo)
        
        Returns:
            DataFrame: OHLCV verileri
        """
        cache_key = f"{symbol}_{period}_{interval}"
        
        # Cache kontrolü
        if cache_key in self.cache:
            if datetime.now().timestamp() < self.cache_expiry.get(cache_key, 0):
                return self.cache[cache_key]

        try:
            ticker = yf.Ticker(get_yahoo_ticker(symbol))
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                logger.warning(f"{symbol} için veri bulunamadı")
                return pd.DataFrame()
            
            # Cache'e kaydet
            self.cache[cache_key] = df
            self.cache_expiry[cache_key] = datetime.now().timestamp() + self.cache_duration
            
            return df

        except Exception as e:
            logger.error(f"{symbol} verisi çekilirken hata: {e}")
            return pd.DataFrame()

    def get_stock_info(self, symbol: str) -> dict:
        """Hisse bilgilerini çeker (F/K, PD/DD, temettü vs.)"""
        try:
            ticker = yf.Ticker(get_yahoo_ticker(symbol))
            info = ticker.info
            
            return {
                "symbol": symbol,
                "name": info.get("longName", symbol),
                "sector": info.get("sector", "Bilinmeyen"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", None),
                "pb_ratio": info.get("priceToBook", None),
                "dividend_yield": info.get("dividendYield", 0),
                "revenue": info.get("totalRevenue", 0),
                "profit_margin": info.get("profitMargins", 0),
                "debt_to_equity": info.get("debtToEquity", None),
                "current_ratio": info.get("currentRatio", None),
                "roe": info.get("returnOnEquity", None),
                "roa": info.get("returnOnAssets", None),
                "52w_high": info.get("fiftyTwoWeekHigh", 0),
                "52w_low": info.get("fiftyTwoWeekLow", 0),
                "avg_volume": info.get("averageVolume", 0),
                "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
                "previous_close": info.get("previousClose", 0),
                "beta": info.get("beta", None),
            }
        except Exception as e:
            logger.error(f"{symbol} bilgisi çekilirken hata: {e}")
            return {"symbol": symbol, "name": symbol, "error": str(e)}

    def get_multiple_stocks(self, symbols: list = None, period: str = "6mo") -> dict:
        """Birden fazla hissenin verisini toplu çeker"""
        if symbols is None:
            symbols = BIST100_TICKERS
        
        results = {}
        total = len(symbols)
        
        for i, symbol in enumerate(symbols):
            try:
                df = self.get_stock_data(symbol, period=period)
                if not df.empty:
                    results[symbol] = df
                    logger.info(f"[{i+1}/{total}] {symbol} verisi çekildi")
                else:
                    logger.warning(f"[{i+1}/{total}] {symbol} verisi boş")
            except Exception as e:
                logger.error(f"[{i+1}/{total}] {symbol} hata: {e}")
            
            # Rate limiting - Yahoo Finance'i aşırı yüklememek için
            if (i + 1) % 10 == 0:
                time.sleep(2)
        
        return results

    def get_current_price(self, symbol: str) -> dict:
        """Anlık fiyat bilgisini çeker"""
        try:
            ticker = yf.Ticker(get_yahoo_ticker(symbol))
            hist = ticker.history(period="2d")
            
            if hist.empty:
                return None
            
            current = hist.iloc[-1]
            previous = hist.iloc[-2] if len(hist) > 1 else current
            
            change = current['Close'] - previous['Close']
            change_pct = (change / previous['Close']) * 100
            
            return {
                "symbol": symbol,
                "price": round(current['Close'], 2),
                "open": round(current['Open'], 2),
                "high": round(current['High'], 2),
                "low": round(current['Low'], 2),
                "volume": int(current['Volume']),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"{symbol} anlık fiyat hatası: {e}")
            return None

    def get_financial_data(self, symbol: str) -> dict:
        """Finansal tablo verilerini çeker"""
        try:
            ticker = yf.Ticker(get_yahoo_ticker(symbol))
            
            financials = {}
            
            # Gelir tablosu
            income = ticker.income_stmt
            if income is not None and not income.empty:
                financials["income_statement"] = income.to_dict()
            
            # Bilanço
            balance = ticker.balance_sheet
            if balance is not None and not balance.empty:
                financials["balance_sheet"] = balance.to_dict()
            
            # Nakit akış
            cashflow = ticker.cashflow
            if cashflow is not None and not cashflow.empty:
                financials["cashflow"] = cashflow.to_dict()
            
            return financials
        except Exception as e:
            logger.error(f"{symbol} finansal veri hatası: {e}")
            return {}

    def clear_cache(self):
        """Cache'i temizler"""
        self.cache.clear()
        self.cache_expiry.clear()
        logger.info("Cache temizlendi")
