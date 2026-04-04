"""
Teknik Analiz Modülü
15+ teknik indikatör ile kapsamlı analiz
"""

import pandas as pd
import numpy as np
import ta
import logging

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Teknik analiz indikatörlerini hesaplar ve yorumlar"""

    def __init__(self):
        self.indicator_weights = {
            "rsi": 10,
            "macd": 12,
            "bollinger": 8,
            "sma_cross": 10,
            "ema_cross": 10,
            "stochastic": 7,
            "adx": 8,
            "williams_r": 5,
            "cci": 5,
            "obv_trend": 7,
            "vwap": 5,
            "atr": 3,
            "ichimoku": 5,
            "parabolic_sar": 5,
        }

    def calculate_all_indicators(self, df: pd.DataFrame) -> dict:
        """Tüm teknik indikatörleri hesaplar"""
        if df.empty or len(df) < 50:
            return {"error": "Yetersiz veri (en az 50 mum gerekli)"}

        indicators = {}

        try:
            # 1. RSI (Relative Strength Index)
            indicators["rsi"] = self._calc_rsi(df)

            # 2. MACD
            indicators["macd"] = self._calc_macd(df)

            # 3. Bollinger Bands
            indicators["bollinger"] = self._calc_bollinger(df)

            # 4. SMA Crosses
            indicators["sma_cross"] = self._calc_sma_cross(df)

            # 5. EMA Crosses
            indicators["ema_cross"] = self._calc_ema_cross(df)

            # 6. Stochastic
            indicators["stochastic"] = self._calc_stochastic(df)

            # 7. ADX
            indicators["adx"] = self._calc_adx(df)

            # 8. Williams %R
            indicators["williams_r"] = self._calc_williams_r(df)

            # 9. CCI
            indicators["cci"] = self._calc_cci(df)

            # 10. OBV
            indicators["obv_trend"] = self._calc_obv(df)

            # 11. VWAP
            indicators["vwap"] = self._calc_vwap(df)

            # 12. ATR (Average True Range)
            indicators["atr"] = self._calc_atr(df)

            # 13. Ichimoku Cloud
            indicators["ichimoku"] = self._calc_ichimoku(df)

            # 14. Parabolic SAR
            indicators["parabolic_sar"] = self._calc_parabolic_sar(df)

            # 15. Fibonacci Levels
            indicators["fibonacci"] = self._calc_fibonacci(df)

            # 16. Support & Resistance
            indicators["support_resistance"] = self._calc_support_resistance(df)

            # Genel skor hesapla
            indicators["overall_score"] = self._calculate_overall_score(indicators)
            indicators["signal"] = self._generate_signal(indicators["overall_score"])

        except Exception as e:
            logger.error(f"Teknik analiz hatası: {e}")
            indicators["error"] = str(e)

        return indicators

    def _calc_rsi(self, df: pd.DataFrame) -> dict:
        """RSI hesapla"""
        rsi = ta.momentum.RSIIndicator(df['Close'], window=14)
        rsi_value = rsi.rsi().iloc[-1]

        if rsi_value < 30:
            signal = "AL"
            score = min(100, (30 - rsi_value) * 3 + 60)
            desc = f"RSI {rsi_value:.1f} - Aşırı satım bölgesi, GÜÇLÜ AL sinyali"
        elif rsi_value < 40:
            signal = "AL"
            score = 60
            desc = f"RSI {rsi_value:.1f} - Satım bölgesinden çıkış, AL sinyali"
        elif rsi_value > 70:
            signal = "SAT"
            score = max(0, (rsi_value - 70) * 3)
            desc = f"RSI {rsi_value:.1f} - Aşırı alım bölgesi, GÜÇLÜ SAT sinyali"
        elif rsi_value > 60:
            signal = "SAT"
            score = 35
            desc = f"RSI {rsi_value:.1f} - Alım bölgesine yaklaşıyor, dikkatli ol"
        else:
            signal = "TUT"
            score = 50
            desc = f"RSI {rsi_value:.1f} - Nötr bölge"

        return {
            "value": round(rsi_value, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_macd(self, df: pd.DataFrame) -> dict:
        """MACD hesapla"""
        macd_indicator = ta.trend.MACD(df['Close'])
        macd_line = macd_indicator.macd().iloc[-1]
        signal_line = macd_indicator.macd_signal().iloc[-1]
        histogram = macd_indicator.macd_diff().iloc[-1]

        # Önceki histogram değerini kontrol et
        prev_histogram = macd_indicator.macd_diff().iloc[-2]

        if macd_line > signal_line and histogram > 0:
            if histogram > prev_histogram:
                signal = "AL"
                score = 80
                desc = "MACD sinyal çizgisinin üzerinde ve güçleniyor - GÜÇLÜ AL"
            else:
                signal = "AL"
                score = 65
                desc = "MACD sinyal çizgisinin üzerinde ama zayıflıyor"
        elif macd_line < signal_line and histogram < 0:
            if histogram < prev_histogram:
                signal = "SAT"
                score = 20
                desc = "MACD sinyal çizgisinin altında ve zayıflıyor - GÜÇLÜ SAT"
            else:
                signal = "SAT"
                score = 35
                desc = "MACD sinyal çizgisinin altında ama toparlanıyor"
        elif macd_line > signal_line and prev_histogram <= 0:
            signal = "AL"
            score = 85
            desc = "MACD yukarı kesişim! - GÜÇLÜ AL"
        elif macd_line < signal_line and prev_histogram >= 0:
            signal = "SAT"
            score = 15
            desc = "MACD aşağı kesişim! - GÜÇLÜ SAT"
        else:
            signal = "TUT"
            score = 50
            desc = "MACD nötr bölge"

        return {
            "macd": round(macd_line, 4),
            "signal_line": round(signal_line, 4),
            "histogram": round(histogram, 4),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_bollinger(self, df: pd.DataFrame) -> dict:
        """Bollinger Bands hesapla"""
        bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
        upper = bb.bollinger_hband().iloc[-1]
        middle = bb.bollinger_mavg().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        current_price = df['Close'].iloc[-1]

        band_width = upper - lower
        position = (current_price - lower) / band_width if band_width > 0 else 0.5

        if current_price <= lower:
            signal = "AL"
            score = 85
            desc = f"Fiyat alt bandın altında ({current_price:.2f} < {lower:.2f}) - GÜÇLÜ AL"
        elif current_price < middle and position < 0.3:
            signal = "AL"
            score = 65
            desc = f"Fiyat alt bant yakınında - AL sinyali"
        elif current_price >= upper:
            signal = "SAT"
            score = 15
            desc = f"Fiyat üst bandın üzerinde ({current_price:.2f} > {upper:.2f}) - GÜÇLÜ SAT"
        elif current_price > middle and position > 0.7:
            signal = "SAT"
            score = 35
            desc = f"Fiyat üst bant yakınında - SAT sinyali"
        else:
            signal = "TUT"
            score = 50
            desc = f"Fiyat bantların ortasında - Nötr"

        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "position": round(position, 4),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_sma_cross(self, df: pd.DataFrame) -> dict:
        """SMA Crossover hesapla"""
        sma_20 = df['Close'].rolling(window=20).mean()
        sma_50 = df['Close'].rolling(window=50).mean()
        sma_200 = df['Close'].rolling(window=200).mean() if len(df) >= 200 else pd.Series([np.nan])

        current_price = df['Close'].iloc[-1]
        sma20_val = sma_20.iloc[-1]
        sma50_val = sma_50.iloc[-1]

        score = 50
        signals = []

        # Golden Cross / Death Cross
        if sma_20.iloc[-1] > sma_50.iloc[-1] and sma_20.iloc[-2] <= sma_50.iloc[-2]:
            signals.append("GOLDEN CROSS (SMA20 > SMA50)")
            score = 85
        elif sma_20.iloc[-1] < sma_50.iloc[-1] and sma_20.iloc[-2] >= sma_50.iloc[-2]:
            signals.append("DEATH CROSS (SMA20 < SMA50)")
            score = 15
        
        # Fiyat pozisyonu
        if current_price > sma20_val and current_price > sma50_val:
            signals.append("Fiyat tüm SMA'ların üzerinde - Yükseliş trendi")
            if score == 50:
                score = 70
        elif current_price < sma20_val and current_price < sma50_val:
            signals.append("Fiyat tüm SMA'ların altında - Düşüş trendi")
            if score == 50:
                score = 30

        # 200 günlük SMA
        if len(df) >= 200:
            sma200_val = sma_200.iloc[-1]
            if not np.isnan(sma200_val):
                if current_price > sma200_val:
                    signals.append("Fiyat SMA200 üzerinde - Uzun vadeli yükseliş")
                    score = min(score + 10, 100)
                else:
                    signals.append("Fiyat SMA200 altında - Uzun vadeli düşüş")
                    score = max(score - 10, 0)

        signal_str = "AL" if score > 60 else ("SAT" if score < 40 else "TUT")

        return {
            "sma_20": round(sma20_val, 2),
            "sma_50": round(sma50_val, 2),
            "sma_200": round(sma_200.iloc[-1], 2) if len(df) >= 200 and not np.isnan(sma_200.iloc[-1]) else None,
            "signal": signal_str,
            "score": score,
            "description": " | ".join(signals) if signals else "SMA'lar nötr"
        }

    def _calc_ema_cross(self, df: pd.DataFrame) -> dict:
        """EMA Crossover hesapla"""
        ema_12 = ta.trend.EMAIndicator(df['Close'], window=12).ema_indicator()
        ema_26 = ta.trend.EMAIndicator(df['Close'], window=26).ema_indicator()

        ema12_val = ema_12.iloc[-1]
        ema26_val = ema_26.iloc[-1]

        if ema12_val > ema26_val and ema_12.iloc[-2] <= ema_26.iloc[-2]:
            signal = "AL"
            score = 85
            desc = "EMA12 yukarı kesişim - GÜÇLÜ AL"
        elif ema12_val < ema26_val and ema_12.iloc[-2] >= ema_26.iloc[-2]:
            signal = "SAT"
            score = 15
            desc = "EMA12 aşağı kesişim - GÜÇLÜ SAT"
        elif ema12_val > ema26_val:
            diff_pct = ((ema12_val - ema26_val) / ema26_val) * 100
            signal = "AL"
            score = min(70, 55 + diff_pct * 5)
            desc = f"EMA12 > EMA26 (fark: %{diff_pct:.2f}) - Yükseliş trendi"
        else:
            diff_pct = ((ema26_val - ema12_val) / ema26_val) * 100
            signal = "SAT"
            score = max(30, 45 - diff_pct * 5)
            desc = f"EMA12 < EMA26 (fark: %{diff_pct:.2f}) - Düşüş trendi"

        return {
            "ema_12": round(ema12_val, 2),
            "ema_26": round(ema26_val, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_stochastic(self, df: pd.DataFrame) -> dict:
        """Stochastic Oscillator hesapla"""
        stoch = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close'])
        k_value = stoch.stoch().iloc[-1]
        d_value = stoch.stoch_signal().iloc[-1]

        if k_value < 20 and d_value < 20:
            signal = "AL"
            score = 80
            desc = f"Stochastic aşırı satım bölgesi (K:{k_value:.1f}, D:{d_value:.1f})"
        elif k_value > 80 and d_value > 80:
            signal = "SAT"
            score = 20
            desc = f"Stochastic aşırı alım bölgesi (K:{k_value:.1f}, D:{d_value:.1f})"
        elif k_value > d_value and stoch.stoch().iloc[-2] <= stoch.stoch_signal().iloc[-2]:
            signal = "AL"
            score = 70
            desc = "Stochastic yukarı kesişim"
        elif k_value < d_value and stoch.stoch().iloc[-2] >= stoch.stoch_signal().iloc[-2]:
            signal = "SAT"
            score = 30
            desc = "Stochastic aşağı kesişim"
        else:
            signal = "TUT"
            score = 50
            desc = f"Stochastic nötr (K:{k_value:.1f}, D:{d_value:.1f})"

        return {
            "k": round(k_value, 2),
            "d": round(d_value, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_adx(self, df: pd.DataFrame) -> dict:
        """ADX (Average Directional Index) hesapla"""
        adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'])
        adx_value = adx_indicator.adx().iloc[-1]
        plus_di = adx_indicator.adx_pos().iloc[-1]
        minus_di = adx_indicator.adx_neg().iloc[-1]

        if adx_value > 25:
            if plus_di > minus_di:
                signal = "AL"
                score = min(90, 60 + adx_value)
                desc = f"Güçlü yükseliş trendi (ADX:{adx_value:.1f}, +DI:{plus_di:.1f} > -DI:{minus_di:.1f})"
            else:
                signal = "SAT"
                score = max(10, 40 - adx_value)
                desc = f"Güçlü düşüş trendi (ADX:{adx_value:.1f}, -DI:{minus_di:.1f} > +DI:{plus_di:.1f})"
        else:
            signal = "TUT"
            score = 50
            desc = f"Zayıf trend (ADX:{adx_value:.1f}) - Yatay hareket"

        return {
            "adx": round(adx_value, 2),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_williams_r(self, df: pd.DataFrame) -> dict:
        """Williams %R hesapla"""
        wr = ta.momentum.WilliamsRIndicator(df['High'], df['Low'], df['Close'])
        wr_value = wr.williams_r().iloc[-1]

        if wr_value < -80:
            signal = "AL"
            score = 75
            desc = f"Williams %R {wr_value:.1f} - Aşırı satım"
        elif wr_value > -20:
            signal = "SAT"
            score = 25
            desc = f"Williams %R {wr_value:.1f} - Aşırı alım"
        else:
            signal = "TUT"
            score = 50
            desc = f"Williams %R {wr_value:.1f} - Nötr"

        return {
            "value": round(wr_value, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_cci(self, df: pd.DataFrame) -> dict:
        """CCI (Commodity Channel Index) hesapla"""
        cci = ta.trend.CCIIndicator(df['High'], df['Low'], df['Close'])
        cci_value = cci.cci().iloc[-1]

        if cci_value < -100:
            signal = "AL"
            score = 75
            desc = f"CCI {cci_value:.1f} - Aşırı satım bölgesi"
        elif cci_value > 100:
            signal = "SAT"
            score = 25
            desc = f"CCI {cci_value:.1f} - Aşırı alım bölgesi"
        elif cci_value < -50:
            signal = "AL"
            score = 60
            desc = f"CCI {cci_value:.1f} - Satım bölgesine yakın"
        elif cci_value > 50:
            signal = "SAT"
            score = 40
            desc = f"CCI {cci_value:.1f} - Alım bölgesine yakın"
        else:
            signal = "TUT"
            score = 50
            desc = f"CCI {cci_value:.1f} - Nötr"

        return {
            "value": round(cci_value, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_obv(self, df: pd.DataFrame) -> dict:
        """OBV (On Balance Volume) hesapla"""
        obv = ta.volume.OnBalanceVolumeIndicator(df['Close'], df['Volume'])
        obv_values = obv.on_balance_volume()
        
        # OBV trendi hesapla (son 10 gün)
        obv_sma = obv_values.rolling(window=10).mean()
        current_obv = obv_values.iloc[-1]
        obv_sma_val = obv_sma.iloc[-1]

        # OBV eğimi
        obv_slope = (obv_values.iloc[-1] - obv_values.iloc[-5]) / abs(obv_values.iloc[-5]) * 100 if obv_values.iloc[-5] != 0 else 0

        if current_obv > obv_sma_val and obv_slope > 0:
            signal = "AL"
            score = 70
            desc = "OBV yükseliyor ve ortalamasının üzerinde - Alım baskısı"
        elif current_obv < obv_sma_val and obv_slope < 0:
            signal = "SAT"
            score = 30
            desc = "OBV düşüyor ve ortalamasının altında - Satış baskısı"
        else:
            signal = "TUT"
            score = 50
            desc = "OBV nötr"

        return {
            "obv": round(current_obv, 0),
            "obv_sma": round(obv_sma_val, 0),
            "slope_pct": round(obv_slope, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_vwap(self, df: pd.DataFrame) -> dict:
        """VWAP (Volume Weighted Average Price) hesapla"""
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        vwap = (typical_price * df['Volume']).cumsum() / df['Volume'].cumsum()
        
        current_price = df['Close'].iloc[-1]
        vwap_value = vwap.iloc[-1]

        if current_price > vwap_value * 1.02:
            signal = "SAT"
            score = 35
            desc = f"Fiyat VWAP'ın %{((current_price/vwap_value)-1)*100:.1f} üzerinde"
        elif current_price < vwap_value * 0.98:
            signal = "AL"
            score = 65
            desc = f"Fiyat VWAP'ın %{((vwap_value/current_price)-1)*100:.1f} altında"
        else:
            signal = "TUT"
            score = 50
            desc = f"Fiyat VWAP civarında ({current_price:.2f} vs {vwap_value:.2f})"

        return {
            "vwap": round(vwap_value, 2),
            "price": round(current_price, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_atr(self, df: pd.DataFrame) -> dict:
        """ATR (Average True Range) hesapla"""
        atr = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close'])
        atr_value = atr.average_true_range().iloc[-1]
        current_price = df['Close'].iloc[-1]
        atr_pct = (atr_value / current_price) * 100

        if atr_pct > 5:
            volatility = "Çok Yüksek"
            score = 40
        elif atr_pct > 3:
            volatility = "Yüksek"
            score = 45
        elif atr_pct > 1.5:
            volatility = "Orta"
            score = 50
        else:
            volatility = "Düşük"
            score = 55

        return {
            "atr": round(atr_value, 2),
            "atr_pct": round(atr_pct, 2),
            "volatility": volatility,
            "signal": "TUT",
            "score": score,
            "description": f"ATR: {atr_value:.2f} (%{atr_pct:.2f}) - Volatilite: {volatility}"
        }

    def _calc_ichimoku(self, df: pd.DataFrame) -> dict:
        """Ichimoku Cloud hesapla"""
        ichimoku = ta.trend.IchimokuIndicator(df['High'], df['Low'])
        
        tenkan = ichimoku.ichimoku_conversion_line().iloc[-1]
        kijun = ichimoku.ichimoku_base_line().iloc[-1]
        senkou_a = ichimoku.ichimoku_a().iloc[-1]
        senkou_b = ichimoku.ichimoku_b().iloc[-1]
        current_price = df['Close'].iloc[-1]

        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)

        if current_price > cloud_top and tenkan > kijun:
            signal = "AL"
            score = 80
            desc = "Fiyat bulutun üzerinde, Tenkan > Kijun - GÜÇLÜ AL"
        elif current_price > cloud_top:
            signal = "AL"
            score = 65
            desc = "Fiyat bulutun üzerinde"
        elif current_price < cloud_bottom and tenkan < kijun:
            signal = "SAT"
            score = 20
            desc = "Fiyat bulutun altında, Tenkan < Kijun - GÜÇLÜ SAT"
        elif current_price < cloud_bottom:
            signal = "SAT"
            score = 35
            desc = "Fiyat bulutun altında"
        else:
            signal = "TUT"
            score = 50
            desc = "Fiyat bulut içinde - Belirsiz bölge"

        return {
            "tenkan": round(tenkan, 2),
            "kijun": round(kijun, 2),
            "senkou_a": round(senkou_a, 2),
            "senkou_b": round(senkou_b, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_parabolic_sar(self, df: pd.DataFrame) -> dict:
        """Parabolic SAR hesapla"""
        psar = ta.trend.PSARIndicator(df['High'], df['Low'], df['Close'])
        psar_val = psar.psar().iloc[-1]
        current_price = df['Close'].iloc[-1]

        if current_price > psar_val:
            signal = "AL"
            score = 65
            desc = f"SAR fiyatın altında ({psar_val:.2f}) - Yükseliş trendi"
        else:
            signal = "SAT"
            score = 35
            desc = f"SAR fiyatın üzerinde ({psar_val:.2f}) - Düşüş trendi"

        return {
            "psar": round(psar_val, 2),
            "price": round(current_price, 2),
            "signal": signal,
            "score": score,
            "description": desc
        }

    def _calc_fibonacci(self, df: pd.DataFrame) -> dict:
        """Fibonacci retracement seviyeleri"""
        high = df['High'].max()
        low = df['Low'].min()
        diff = high - low
        current_price = df['Close'].iloc[-1]

        levels = {
            "0.0": high,
            "0.236": high - diff * 0.236,
            "0.382": high - diff * 0.382,
            "0.5": high - diff * 0.5,
            "0.618": high - diff * 0.618,
            "0.786": high - diff * 0.786,
            "1.0": low
        }

        # En yakın destek ve direnç
        support = None
        resistance = None
        for level_name, level_price in sorted(levels.items(), key=lambda x: x[1], reverse=True):
            if level_price < current_price:
                if support is None:
                    support = {"level": level_name, "price": round(level_price, 2)}
            else:
                resistance = {"level": level_name, "price": round(level_price, 2)}

        return {
            "levels": {k: round(v, 2) for k, v in levels.items()},
            "nearest_support": support,
            "nearest_resistance": resistance,
            "signal": "TUT",
            "score": 50,
            "description": f"Destek: {support['price'] if support else 'N/A'} | Direnç: {resistance['price'] if resistance else 'N/A'}"
        }

    def _calc_support_resistance(self, df: pd.DataFrame) -> dict:
        """Destek ve direnç seviyeleri"""
        pivot = (df['High'].iloc[-1] + df['Low'].iloc[-1] + df['Close'].iloc[-1]) / 3
        
        s1 = 2 * pivot - df['High'].iloc[-1]
        s2 = pivot - (df['High'].iloc[-1] - df['Low'].iloc[-1])
        r1 = 2 * pivot - df['Low'].iloc[-1]
        r2 = pivot + (df['High'].iloc[-1] - df['Low'].iloc[-1])

        current_price = df['Close'].iloc[-1]

        return {
            "pivot": round(pivot, 2),
            "support_1": round(s1, 2),
            "support_2": round(s2, 2),
            "resistance_1": round(r1, 2),
            "resistance_2": round(r2, 2),
            "current_price": round(current_price, 2),
            "signal": "TUT",
            "score": 50,
            "description": f"Pivot: {pivot:.2f} | S1: {s1:.2f} | R1: {r1:.2f}"
        }

    def _calculate_overall_score(self, indicators: dict) -> float:
        """Tüm indikatörlerin ağırlıklı ortalama skorunu hesaplar"""
        total_weight = 0
        weighted_score = 0

        for indicator_name, weight in self.indicator_weights.items():
            if indicator_name in indicators and "score" in indicators[indicator_name]:
                score = indicators[indicator_name]["score"]
                weighted_score += score * weight
                total_weight += weight

        if total_weight == 0:
            return 50.0

        return round(weighted_score / total_weight, 2)

    def _generate_signal(self, score: float) -> dict:
        """Skora göre sinyal üretir"""
        if score >= 75:
            return {"action": "GÜÇLÜ AL", "emoji": "🟢🟢", "confidence": "Yüksek"}
        elif score >= 60:
            return {"action": "AL", "emoji": "🟢", "confidence": "Orta"}
        elif score <= 25:
            return {"action": "GÜÇLÜ SAT", "emoji": "🔴🔴", "confidence": "Yüksek"}
        elif score <= 40:
            return {"action": "SAT", "emoji": "🔴", "confidence": "Orta"}
        else:
            return {"action": "TUT", "emoji": "🟡", "confidence": "Düşük"}
