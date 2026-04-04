"""
Olay Dedektörü Modülü
Golden Cross (Altın Kesişim), Hacim Patlaması ve diğer kritik olayları algılar.
Sürekli döngü taramasında kullanılır — bu olaylar anında bildirilir.
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime
from data_collector import DataCollector

logger = logging.getLogger(__name__)


class EventDetector:
    """
    Kritik borsa olaylarını anlık tespit eder.
    
    Algılanan olaylar:
    - Golden Cross: SMA50 > SMA200 kesişimi (güçlü AL)
    - Death Cross: SMA50 < SMA200 kesişimi (güçlü SAT)
    - Hacim Patlaması: Günlük hacim > 20 günlük ortalama x 3
    - Fiyat Kırılımı: Fiyat 52-hafta zirvesini kırdı
    - Dip Testi: Fiyat 52-hafta dibi test ediyor
    - Bollinger Squeeze: Bollinger bantları daraldı (büyük hareket bekleniyor)
    """

    def __init__(self):
        self.data_collector = DataCollector()
        # Daha önce algılanan olaylar (aynı olayı tekrar bildirmemek için)
        self._seen_events = {}  # key: "symbol_event_date" -> True

    def scan_for_events(self, symbol: str) -> list:
        """
        Bir hisse için kritik olayları tarar.
        Sadece BUGÜN veya SON İŞLEM GÜNÜNDE gerçekleşen olayları döndürür.
        """
        events = []

        try:
            df = self.data_collector.get_stock_data(symbol, period="1y", interval="1d")
            if df.empty or len(df) < 201:
                return events

            # Golden Cross / Death Cross
            gc_event = self._detect_golden_cross(symbol, df)
            if gc_event:
                events.append(gc_event)

            dc_event = self._detect_death_cross(symbol, df)
            if dc_event:
                events.append(dc_event)

            # Hacim Patlaması
            vol_event = self._detect_volume_explosion(symbol, df)
            if vol_event:
                events.append(vol_event)

            # Fiyat Kırılımı (52-hafta zirve)
            breakout = self._detect_breakout(symbol, df)
            if breakout:
                events.append(breakout)

            # Dip Testi
            dip = self._detect_dip_test(symbol, df)
            if dip:
                events.append(dip)

            # Bollinger Squeeze
            squeeze = self._detect_bollinger_squeeze(symbol, df)
            if squeeze:
                events.append(squeeze)

        except Exception as e:
            logger.error(f"{symbol} olay tarama hatası: {e}")

        return events

    def scan_all(self, symbols: list) -> dict:
        """Tüm hisseleri olay için tarar"""
        all_events = []
        golden_crosses = []
        death_crosses = []
        volume_explosions = []
        breakouts = []
        other_events = []

        for symbol in symbols:
            events = self.scan_for_events(symbol)
            for event in events:
                all_events.append(event)

                if event["type"] == "GOLDEN_CROSS":
                    golden_crosses.append(event)
                elif event["type"] == "DEATH_CROSS":
                    death_crosses.append(event)
                elif event["type"] == "VOLUME_EXPLOSION":
                    volume_explosions.append(event)
                elif event["type"] == "BREAKOUT":
                    breakouts.append(event)
                else:
                    other_events.append(event)

        return {
            "scan_time": datetime.now().isoformat(),
            "total_scanned": len(symbols),
            "total_events": len(all_events),
            "golden_crosses": golden_crosses,
            "death_crosses": death_crosses,
            "volume_explosions": volume_explosions,
            "breakouts": breakouts,
            "other_events": other_events,
            "all_events": all_events
        }

    def _is_new_event(self, symbol: str, event_type: str) -> bool:
        """Bu olay daha önce bildirildi mi kontrol eder"""
        today = datetime.now().strftime('%Y-%m-%d')
        key = f"{symbol}_{event_type}_{today}"
        if key in self._seen_events:
            return False
        self._seen_events[key] = True
        return True

    def _detect_golden_cross(self, symbol: str, df: pd.DataFrame) -> dict:
        """Golden Cross tespit: SMA50 > SMA200 kesişimi"""
        sma50 = df['Close'].rolling(50).mean()
        sma200 = df['Close'].rolling(200).mean()

        # Son 2 mum kontrolü (bugün veya dün kesişme oldu mu)
        if len(sma50) < 2 or len(sma200) < 2:
            return None

        current_50 = sma50.iloc[-1]
        current_200 = sma200.iloc[-1]
        prev_50 = sma50.iloc[-2]
        prev_200 = sma200.iloc[-2]

        if np.isnan(current_50) or np.isnan(current_200) or np.isnan(prev_50) or np.isnan(prev_200):
            return None

        # Golden Cross: SMA50 bugün SMA200'ün üzerine çıktı
        if current_50 > current_200 and prev_50 <= prev_200:
            if not self._is_new_event(symbol, "GOLDEN_CROSS"):
                return None

            price = df['Close'].iloc[-1]
            logger.info(f"⭐ GOLDEN CROSS: {symbol} @ {price:.2f} TL")

            return {
                "type": "GOLDEN_CROSS",
                "symbol": symbol,
                "emoji": "⭐🟢",
                "title": "ALTIN KESİŞİM (Golden Cross)",
                "description": (
                    f"{symbol} hissesinde 50 günlük hareketli ortalama, "
                    f"200 günlük ortalamayı yukarı kesti! "
                    f"Bu güçlü bir uzun vadeli AL sinyalidir."
                ),
                "price": round(price, 2),
                "sma50": round(current_50, 2),
                "sma200": round(current_200, 2),
                "severity": "CRITICAL",
                "action": "AL",
                "detected_at": datetime.now().isoformat()
            }

        return None

    def _detect_death_cross(self, symbol: str, df: pd.DataFrame) -> dict:
        """Death Cross tespit: SMA50 < SMA200 kesişimi"""
        sma50 = df['Close'].rolling(50).mean()
        sma200 = df['Close'].rolling(200).mean()

        if len(sma50) < 2 or len(sma200) < 2:
            return None

        current_50 = sma50.iloc[-1]
        current_200 = sma200.iloc[-1]
        prev_50 = sma50.iloc[-2]
        prev_200 = sma200.iloc[-2]

        if np.isnan(current_50) or np.isnan(current_200) or np.isnan(prev_50) or np.isnan(prev_200):
            return None

        if current_50 < current_200 and prev_50 >= prev_200:
            if not self._is_new_event(symbol, "DEATH_CROSS"):
                return None

            price = df['Close'].iloc[-1]
            logger.info(f"💀 DEATH CROSS: {symbol} @ {price:.2f} TL")

            return {
                "type": "DEATH_CROSS",
                "symbol": symbol,
                "emoji": "💀🔴",
                "title": "ÖLÜM KESİŞİMİ (Death Cross)",
                "description": (
                    f"{symbol} hissesinde 50 günlük hareketli ortalama, "
                    f"200 günlük ortalamayı aşağı kesti! "
                    f"Bu güçlü bir düşüş sinyalidir."
                ),
                "price": round(price, 2),
                "sma50": round(current_50, 2),
                "sma200": round(current_200, 2),
                "severity": "CRITICAL",
                "action": "SAT",
                "detected_at": datetime.now().isoformat()
            }

        return None

    def _detect_volume_explosion(self, symbol: str, df: pd.DataFrame) -> dict:
        """Hacim Patlaması: Günlük hacim > 20-gün ortalaması x 3"""
        if len(df) < 21:
            return None

        current_volume = df['Volume'].iloc[-1]
        avg_volume_20 = df['Volume'].rolling(20).mean().iloc[-2]  # Dünün ortalaması (bugünü dahil etme)

        if np.isnan(avg_volume_20) or avg_volume_20 == 0:
            return None

        volume_ratio = current_volume / avg_volume_20

        if volume_ratio >= 3.0:
            if not self._is_new_event(symbol, "VOLUME_EXPLOSION"):
                return None

            price = df['Close'].iloc[-1]
            price_change = ((df['Close'].iloc[-1] / df['Close'].iloc[-2]) - 1) * 100

            # Hacim artışı + fiyat yükselişi = AL, düşüşü = SAT
            if price_change > 0:
                action = "AL"
                direction = "yükselişle"
            else:
                action = "SAT"
                direction = "düşüşle"

            logger.info(f"💥 HACİM PATLAMASI: {symbol} x{volume_ratio:.1f} ({direction})")

            return {
                "type": "VOLUME_EXPLOSION",
                "symbol": symbol,
                "emoji": "💥📊",
                "title": "HACİM PATLAMASI",
                "description": (
                    f"{symbol} hissesinde hacim patlaması! "
                    f"Günlük hacim 20 günlük ortalamanın {volume_ratio:.1f} katı. "
                    f"Fiyat %{price_change:+.1f} değişimle {direction} birlikte."
                ),
                "price": round(price, 2),
                "current_volume": int(current_volume),
                "avg_volume": int(avg_volume_20),
                "volume_ratio": round(volume_ratio, 2),
                "price_change_pct": round(price_change, 2),
                "severity": "HIGH",
                "action": action,
                "detected_at": datetime.now().isoformat()
            }

        return None

    def _detect_breakout(self, symbol: str, df: pd.DataFrame) -> dict:
        """52-Hafta Zirve Kırılımı"""
        if len(df) < 252:  # ~1 yıl
            high_52w = df['High'].max()
        else:
            high_52w = df['High'].iloc[-252:].max()

        current_price = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]

        # Bugün 52 hafta zirvesini kırdıysa
        if current_price >= high_52w and prev_close < high_52w:
            if not self._is_new_event(symbol, "BREAKOUT"):
                return None

            logger.info(f"🚀 KIRILIM: {symbol} 52-hafta zirvesini kırdı! @ {current_price:.2f}")

            return {
                "type": "BREAKOUT",
                "symbol": symbol,
                "emoji": "🚀📈",
                "title": "52-HAFTA ZİRVE KIRILIMI",
                "description": (
                    f"{symbol} yeni 52 hafta zirvesine ulaştı! "
                    f"Fiyat: {current_price:.2f} TL (Eski zirve: {high_52w:.2f} TL)"
                ),
                "price": round(current_price, 2),
                "prev_high": round(high_52w, 2),
                "severity": "HIGH",
                "action": "AL",
                "detected_at": datetime.now().isoformat()
            }

        return None

    def _detect_dip_test(self, symbol: str, df: pd.DataFrame) -> dict:
        """52-Hafta Dip Testi"""
        if len(df) < 252:
            low_52w = df['Low'].min()
        else:
            low_52w = df['Low'].iloc[-252:].min()

        current_price = df['Close'].iloc[-1]

        # Fiyat 52 hafta dibinin %2'si içindeyse
        if current_price <= low_52w * 1.02:
            if not self._is_new_event(symbol, "DIP_TEST"):
                return None

            logger.info(f"📉 DİP TESTİ: {symbol} 52-hafta dibi test ediyor @ {current_price:.2f}")

            return {
                "type": "DIP_TEST",
                "symbol": symbol,
                "emoji": "📉⚠️",
                "title": "52-HAFTA DİP TESTİ",
                "description": (
                    f"{symbol} 52 hafta dibini test ediyor! "
                    f"Fiyat: {current_price:.2f} TL (Dip: {low_52w:.2f} TL)"
                ),
                "price": round(current_price, 2),
                "low_52w": round(low_52w, 2),
                "severity": "HIGH",
                "action": "DİKKAT",
                "detected_at": datetime.now().isoformat()
            }

        return None

    def _detect_bollinger_squeeze(self, symbol: str, df: pd.DataFrame) -> dict:
        """Bollinger Squeeze: Bantlar aşırı daraldıysa büyük hareket bekleniyor"""
        if len(df) < 100:
            return None

        import ta
        bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
        upper = bb.bollinger_hband()
        lower = bb.bollinger_lband()

        band_width = (upper - lower) / ((upper + lower) / 2) * 100
        current_width = band_width.iloc[-1]
        avg_width = band_width.rolling(100).mean().iloc[-1]

        if np.isnan(current_width) or np.isnan(avg_width):
            return None

        # Bant genişliği son 100 gün ortalamasının %40'ının altındaysa = squeeze
        if current_width < avg_width * 0.4:
            if not self._is_new_event(symbol, "BOLLINGER_SQUEEZE"):
                return None

            price = df['Close'].iloc[-1]
            logger.info(f"🔄 BOLLINGER SQUEEZE: {symbol} — büyük hareket bekleniyor")

            return {
                "type": "BOLLINGER_SQUEEZE",
                "symbol": symbol,
                "emoji": "🔄💎",
                "title": "BOLLINGER DARALMASI (Squeeze)",
                "description": (
                    f"{symbol} hissesinde Bollinger bantları aşırı daraldı. "
                    f"Bant genişliği %{current_width:.2f} (ortalama: %{avg_width:.2f}). "
                    f"Büyük bir fiyat hareketi bekleniyor!"
                ),
                "price": round(price, 2),
                "band_width": round(current_width, 2),
                "avg_band_width": round(avg_width, 2),
                "severity": "MEDIUM",
                "action": "DİKKAT",
                "detected_at": datetime.now().isoformat()
            }

        return None

    def format_event_notification(self, event: dict) -> str:
        """Bir olayı bildirim mesajına çevirir"""
        return (
            f"{event['emoji']} <b>{event['title']}</b>\n\n"
            f"📊 <b>Hisse:</b> #{event['symbol']}\n"
            f"💰 <b>Fiyat:</b> {event['price']:.2f} TL\n"
            f"🎯 <b>Aksiyon:</b> {event['action']}\n\n"
            f"📝 {event['description']}\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"<i>⚠️ Bu otomatik bir uyarıdır, yatırım tavsiyesi değildir.</i>"
        )
