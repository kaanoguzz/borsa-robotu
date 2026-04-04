"""
Makro Analiz Modülü
VIX (Korku Endeksi), USD/TRY, BIST 100 Endeks Trendi, Sektörel Korelasyon

Önemli Kural: BIST 100 endeksi düşüş trendindeyse hiçbir hisse için AL sinyali üretilmez.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MacroAnalyzer:
    """Makro ekonomik veriler ve endeks trend analizi"""

    def __init__(self):
        self.cache = {}
        self.cache_ts = {}
        self.cache_duration = 900  # 15 dk

    def _get_cached(self, key):
        """Cache'den veri al (15 dk geçerli)"""
        import time
        if key in self.cache and key in self.cache_ts:
            if time.time() - self.cache_ts[key] < self.cache_duration:
                return self.cache[key]
        return None

    def _set_cached(self, key, value):
        import time
        self.cache[key] = value
        self.cache_ts[key] = time.time()

    # ==================== XU100 ENDEKS KAPISI ====================

    def is_market_bullish(self) -> dict:
        """
        BIST 100 (XU100) endeksinin trend durumunu kontrol eder.
        Kural: SMA20 > SMA50 ve fiyat SMA20 üzerinde → Boğa piyasası
        """
        cached = self._get_cached("xu100")
        if cached:
            return cached
        try:
            xu100 = yf.Ticker("XU100.IS")
            df = xu100.history(period="6mo", interval="1d")

            if df.empty or len(df) < 50:
                logger.warning("XU100 verisi yetersiz, piyasa kontrolü atlanıyor")
                return {
                    "bullish": True,  # Veri yoksa engelleme
                    "reason": "XU100 verisi yetersiz — kontrol atlandı",
                    "trend": "BİLİNMEYEN"
                }

            sma20 = df['Close'].rolling(20).mean().iloc[-1]
            sma50 = df['Close'].rolling(50).mean().iloc[-1]
            current = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]

            daily_change = ((current / prev_close) - 1) * 100

            # Trend belirleme
            if current > sma20 and sma20 > sma50:
                trend = "GÜÇLÜ YÜKSELİŞ"
                bullish = True
            elif current > sma20:
                trend = "YÜKSELİŞ"
                bullish = True
            elif current < sma20 and sma20 < sma50:
                trend = "GÜÇLÜ DÜŞÜŞ"
                bullish = False
            elif current < sma20:
                trend = "DÜŞÜŞ"
                bullish = False
            else:
                trend = "YATAY"
                bullish = True  # Yatay piyasada engelleme

            result = {
                "bullish": bullish,
                "trend": trend,
                "xu100_price": round(current, 2),
                "sma20": round(sma20, 2),
                "sma50": round(sma50, 2),
                "daily_change_pct": round(daily_change, 2),
                "reason": f"XU100: {current:.0f} | SMA20: {sma20:.0f} | SMA50: {sma50:.0f} | Trend: {trend}",
                "gate_open": bullish,  # AL sinyali geçebilir mi?
                "checked_at": datetime.now().isoformat()
            }

            if not bullish:
                result["warning"] = (
                    f"⚠️ BIST 100 düşüş trendinde ({trend}). "
                    f"Hiçbir hisse için AL sinyali üretilmeyecek!"
                )
                logger.warning(f"🚫 XU100 KAPISI KAPALI: {trend} ({current:.0f})")

            self._set_cached("xu100", result)
            return result

        except Exception as e:
            logger.error(f"XU100 trend kontrolü hatası: {e}")
            return {"bullish": True, "reason": f"Hata: {e}", "trend": "HATA", "gate_open": True}

    # ==================== VIX (KORKU ENDEKSİ) ====================

    def get_vix(self) -> dict:
        """
        VIX (CBOE Volatility Index) - Küresel korku endeksi.
        VIX > 30: Yüksek korku → riskli ortam
        VIX < 20: Düşük korku → olumlu ortam
        """
        cached = self._get_cached("vix")
        if cached:
            return cached
        try:
            vix = yf.Ticker("^VIX")
            df = vix.history(period="1mo", interval="1d")

            if df.empty:
                return {"vix": None, "risk_level": "BİLİNMEYEN", "score": 50}

            current_vix = df['Close'].iloc[-1]
            avg_vix = df['Close'].mean()

            if current_vix > 35:
                risk_level = "ÇOK YÜKSEK"
                score = 15  # Olumsuz
                desc = "Piyasalarda panik — yüksek risk"
            elif current_vix > 25:
                risk_level = "YÜKSEK"
                score = 30
                desc = "Piyasalarda tedirginlik"
            elif current_vix > 20:
                risk_level = "ORTA"
                score = 50
                desc = "Normal volatilite"
            elif current_vix > 15:
                risk_level = "DÜŞÜK"
                score = 70
                desc = "Sakin piyasa"
            else:
                risk_level = "ÇOK DÜŞÜK"
                score = 80
                desc = "Aşırı sakin — complacency riski"

            result = {
                "vix": round(current_vix, 2),
                "avg_vix_30d": round(avg_vix, 2),
                "risk_level": risk_level,
                "score": score,
                "description": desc
            }
            self._set_cached("vix", result)
            return result

        except Exception as e:
            logger.error(f"VIX verisi hatası: {e}")
            return {"vix": None, "risk_level": "HATA", "score": 50}

    # ==================== USD/TRY ====================

    def get_usdtry(self) -> dict:
        """
        USD/TRY kuru analizi.
        Dolar yükselişi genelde BIST için olumsuz.
        """
        cached = self._get_cached("usdtry")
        if cached:
            return cached
        try:
            usdtry = yf.Ticker("USDTRY=X")
            df = usdtry.history(period="3mo", interval="1d")

            if df.empty:
                return {"usdtry": None, "trend": "BİLİNMEYEN", "score": 50}

            current = df['Close'].iloc[-1]
            sma20 = df['Close'].rolling(20).mean().iloc[-1]
            change_1m = ((current / df['Close'].iloc[-22]) - 1) * 100 if len(df) > 22 else 0
            change_1w = ((current / df['Close'].iloc[-5]) - 1) * 100 if len(df) > 5 else 0

            # Dolar/TL yükselişi → BIST için olumsuz
            if change_1w > 3:
                trend = "HIZLI YÜKSELİŞ"
                score = 20
                desc = "Dolar/TL hızla yükseliyor — BIST için olumsuz"
            elif change_1w > 1:
                trend = "YÜKSELİŞ"
                score = 35
                desc = "Dolar/TL yükselişte"
            elif change_1w < -1:
                trend = "DÜŞÜŞ"
                score = 70
                desc = "Dolar/TL düşüyor — BIST için olumlu"
            else:
                trend = "YATAY"
                score = 55
                desc = "Dolar/TL stabil"

            result = {
                "usdtry": round(current, 4),
                "sma20": round(sma20, 4),
                "change_1w_pct": round(change_1w, 2),
                "change_1m_pct": round(change_1m, 2),
                "trend": trend,
                "score": score,
                "description": desc
            }
            self._set_cached("usdtry", result)
            return result

        except Exception as e:
            logger.error(f"USD/TRY verisi hatası: {e}")
            return {"usdtry": None, "trend": "HATA", "score": 50}

    # ==================== SEKTÖREL KORELASYON ====================

    def check_sector_health(self, symbol: str) -> dict:
        """
        Sektör devlerinin performansını kontrol eder.
        Sektör genelinde düşüş varsa tekil hisseye girme.
        """
        from config import SECTORS, get_sector

        sector = get_sector(symbol)
        sector_stocks = SECTORS.get(sector, [])

        if not sector_stocks or len(sector_stocks) < 2:
            return {
                "sector": sector,
                "healthy": True,
                "score": 50,
                "reason": "Sektör verisi yetersiz"
            }

        gains = 0
        losses = 0
        total_change = 0
        checked = 0

        for stock in sector_stocks:
            if stock == symbol:
                continue  # Kendisini sayma
            try:
                ticker = yf.Ticker(f"{stock}.IS")
                hist = ticker.history(period="5d")
                if len(hist) >= 2:
                    change = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-2]) - 1) * 100
                    total_change += change
                    checked += 1
                    if change > 0:
                        gains += 1
                    else:
                        losses += 1
            except:
                continue

        if checked == 0:
            return {"sector": sector, "healthy": True, "score": 50, "reason": "Sektör verisi okunamadı"}

        avg_change = total_change / checked
        gain_ratio = gains / checked

        if gain_ratio >= 0.6 and avg_change > 0:
            healthy = True
            score = min(80, 50 + avg_change * 10)
            desc = f"Sektör sağlıklı: {gains}/{checked} hisse yükselişte (ort. %{avg_change:.1f})"
        elif gain_ratio <= 0.3 and avg_change < -1:
            healthy = False
            score = max(20, 50 + avg_change * 10)
            desc = f"⚠️ SEKTÖR DÜŞÜŞTE: {losses}/{checked} hisse düşüşte (ort. %{avg_change:.1f}) — TEKİL HİSSEYE GİRME"
        else:
            healthy = True
            score = 50
            desc = f"Sektör karışık: {gains}/{checked} yükseliş (ort. %{avg_change:.1f})"

        return {
            "sector": sector,
            "sector_stocks": sector_stocks,
            "healthy": healthy,
            "gain_ratio": round(gain_ratio, 2),
            "avg_change_pct": round(avg_change, 2),
            "score": round(score, 2),
            "description": desc,
            "checked_count": checked
        }

    # ==================== GENEL RİSK PUANI ====================

    def calculate_risk_score(self, symbol: str = None) -> dict:
        """
        Tüm makro verileri birleştirerek Genel Risk Puanı hesaplar.
        0 = Çok Riskli, 100 = Çok Güvenli
        """
        # 1. XU100 Trend
        market = self.is_market_bullish()
        market_score = 80 if market["bullish"] else 20

        # 2. VIX
        vix = self.get_vix()
        vix_score = vix.get("score", 50)

        # 3. USD/TRY
        usdtry = self.get_usdtry()
        usdtry_score = usdtry.get("score", 50)

        # 4. Sektör Sağlığı
        if symbol:
            sector = self.check_sector_health(symbol)
            sector_score = sector.get("score", 50)
        else:
            sector_score = 50
            sector = {"healthy": True, "description": "Sektör kontrolü yapılmadı"}

        # Ağırlıklı risk puanı
        risk_score = (
            market_score * 0.35 +   # XU100 trendi en önemli
            vix_score * 0.20 +       # Küresel korku
            usdtry_score * 0.25 +    # Döviz kuru
            sector_score * 0.20      # Sektör sağlığı
        )

        if risk_score >= 70:
            risk_level = "DÜŞÜK RİSK"
            emoji = "🟢"
        elif risk_score >= 50:
            risk_level = "ORTA RİSK"
            emoji = "🟡"
        elif risk_score >= 30:
            risk_level = "YÜKSEK RİSK"
            emoji = "🟠"
        else:
            risk_level = "ÇOK YÜKSEK RİSK"
            emoji = "🔴"

        return {
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "emoji": emoji,
            "market_gate_open": market["bullish"],
            "sector_healthy": sector.get("healthy", True),
            "components": {
                "xu100": {"score": market_score, "trend": market.get("trend"), "detail": market.get("reason")},
                "vix": {"score": vix_score, "vix_value": vix.get("vix"), "risk": vix.get("risk_level")},
                "usdtry": {"score": usdtry_score, "rate": usdtry.get("usdtry"), "trend": usdtry.get("trend")},
                "sector": {"score": sector_score, "healthy": sector.get("healthy"), "detail": sector.get("description")},
            },
            "calculated_at": datetime.now().isoformat()
        }
