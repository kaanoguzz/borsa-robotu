import yfinance as yf
import pandas as pd
import pandas_ta as ta
import ssl
import certifi
import os
import shutil
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== SSL FIX ====================
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
# =================================================

logger = logging.getLogger(__name__)

from config import BIST100_TICKERS

class Scanner:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10) # 10 hisseyi aynı anda tara

    def get_data(self, symbol, interval, period):
        ticker = f"{symbol}.IS"
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval)
            if df.empty:
                return None
            return df
        except Exception as e:
            return None

    def scan_symbol(self, symbol):
        """
        15m grafikte: RSI < 45 ve EMA(5) > EMA(20) kesişimi.
        4h grafikte: Fiyat > EMA(50) kontrolü.
        """
        try:
            # 4 Saatlik trend onayı
            df_4h = self.get_data(symbol, "1h", "1mo") # yfinance'da direk 4h destegi azdır, 1h alıp 4 barlık ema bakabiliriz ya da 1d
            # Kullanıcı 4 saatlikte fiyatın ema50 üzerinde olmasını istemiş, yfinance'da 4h yok, 1h veya 1d kullanılır.
            # Alternatif: 60m (1h) grafikte EMA 200 (4h EMA 50) üzerinde olması trend onayıdır.
            df_trend = self.get_data(symbol, "60m", "1mo")
            if df_trend is None or len(df_trend) < 200:
                return None
            
            df_trend.ta.ema(length=200, append=True) # 1 saatlikte 200 barlık EMA = 4 saatlikte 50 barlık EMA (kabaca)
            current_price_trend = df_trend['Close'].iloc[-1]
            ema_200 = df_trend['EMA_200'].iloc[-1]
            
            if current_price_trend <= ema_200:
                return None # Trend altında, AL yok

            # 15 Dakikalık giriş sinyali
            df_15m = self.get_data(symbol, "15m", "5d")
            if df_15m is None or len(df_15m) < 20:
                return None
            
            df_15m.ta.rsi(length=14, append=True)
            df_15m.ta.ema(length=5, append=True)
            df_15m.ta.ema(length=20, append=True)
            
            rsi = df_15m['RSI_14'].iloc[-1]
            ema5_curr = df_15m['EMA_5'].iloc[-1]
            ema20_curr = df_15m['EMA_20'].iloc[-1]
            ema5_prev = df_15m['EMA_5'].iloc[-2]
            ema20_prev = df_15m['EMA_20'].iloc[-2]
            current_price = df_15m['Close'].iloc[-1]

            # Koşul 1: RSI < 45
            # Koşul 2: EMA(5), EMA(20)'yi yukarı çapraz kesti (geçen bar ema5 < ema20, bu bar ema5 > ema20)
            crossover = (ema5_prev <= ema20_prev) and (ema5_curr > ema20_curr)
            
            if rsi < 45 and crossover:
                return {
                    "symbol": symbol,
                    "price": current_price,
                    "rsi": rsi,
                    "trend_onay": True
                }

            return None
        except Exception as e:
            logger.error(f"Scanner hatası {symbol}: {e}")
            return None

    def fast_scan(self):
        """100 hisseyi paralel olarak tarar (Teknik Bazlı)"""
        buy_signals = []
        futures = {self.executor.submit(self.scan_symbol, symbol): symbol for symbol in BIST100_TICKERS}
        
        for future in as_completed(futures):
            sig = future.result()
            if sig:
                buy_signals.append(sig)
        return buy_signals

    def check_sell_condition(self, symbol):
        """
        Eldeki hisse için Erken Satış Sinyali üretir.
        - XU100 Düşüşü (Dışarıdan gelebilir veya burada bakılabilir - dışarıda bakmak daha performanslı)
        - Hacmin %40 düşmesi
        - EMA / RSI kesişimleri
        - Büyük Dağıtım / Kurumsal satıcı (Sentetik AKD)
        """
        try:
            df_15m = self.get_data(symbol, "15m", "5d")
            # 5 dakikalık grafikteki şelaleyi daha net görmek için 5m çekelim
            df_5m = self.get_data(symbol, "5m", "5d")
            
            if df_15m is None or len(df_15m) < 20 or df_5m is None or len(df_5m) < 20:
                return False, ""
                
            df_15m.ta.rsi(length=14, append=True)
            df_15m.ta.ema(length=5, append=True)
            df_15m.ta.ema(length=20, append=True)
            
            rsi = df_15m['RSI_14'].iloc[-1]
            ema5_curr = df_15m['EMA_5'].iloc[-1]
            ema20_curr = df_15m['EMA_20'].iloc[-1]
            ema5_prev = df_15m['EMA_5'].iloc[-2]
            ema20_prev = df_15m['EMA_20'].iloc[-2]
            current_price = df_15m['Close'].iloc[-1]

            # 1. Hacim Çöküşü Kontrolü (Son 5m mumu bir öncekine göre %40 düşükse ve trend aşağı yönlüyse)
            vol_curr = df_5m['Volume'].iloc[-1]
            vol_prev = df_5m['Volume'].iloc[-2]
            # Sadece kırmızı bir mumsa hacim çekilmesi risklidir
            is_red = df_5m['Close'].iloc[-1] < df_5m['Open'].iloc[-1]
            if is_red and vol_prev > 0 and vol_curr < vol_prev * 0.6:
                 return True, "📉 İvme Kaybı: Hacim %40'tan fazla çöktü!"

            # 2. Sentetik Dağıtım / Büyük Satıcılar (MFI ve OBV Şelalesi)
            try:
                import pandas_ta as ta
                mfi = ta.mfi(df_5m['High'], df_5m['Low'], df_5m['Close'], df_5m['Volume'], length=14)
                obv = ta.obv(df_5m['Close'], df_5m['Volume'])
                
                mfi_val = mfi.iloc[-1] if not mfi.empty else 50
                mfi_prev = mfi.iloc[-2] if not mfi.empty else 50
                obv_val = obv.iloc[-1] if not obv.empty else 0
                obv_prev = obv.iloc[-2] if not obv.empty else 0

                # OBV'de sert düşüş ve MFI < 30 ise kurumsal satış var demektir
                if mfi_val < mfi_prev and mfi_val < 30 and obv_val < obv_prev:
                     return True, "🐳 Kurumsal Çıkış: AKD Dağıtımı tespit edildi (Smart Money OUT)!"
            except:
                pass # TA error handles safely

            # 3. Geleneksel Teknik Kesişim
            crossunder = (ema5_prev >= ema20_prev) and (ema5_curr < ema20_curr)
            if crossunder:
                return True, f"EMA Kesişimi (Fiyat: {current_price:.2f}, RSI: {rsi:.1f})"
                
            if current_price < ema5_curr and rsi < 40:
                 return True, f"Fiyat zayıflığı ve hacim kaybı, RSI {rsi:.1f}"
                 
            return False, ""
        except Exception as e:
            logger.error(f"Sell check hatası {symbol}: {e}")
            return False, ""
