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
        # Öncü (Leading) Göstergeler - Trend değişimini erken haber verir
        self.leading_weights = {
            "rsi": 15,
            "rsi_divergence": 20, # En güçlü öncü
            "stochastic": 10,
            "williams_r": 5,
            "cci": 5,
            "obv_trend": 10,
            "squeeze": 15, # Sıkışma kırılımı
            "volume_spike": 20 # Hacim patlaması
        }
        
        # Artçı (Lagging) Göstergeler - Trendi onaylar
        self.lagging_weights = {
            "macd": 15,
            "sma_cross": 10,
            "ema_cross": 10,
            "adx": 10,
            "ichimoku": 5,
            "parabolic_sar": 5,
            "vwap": 5
        }

        # Toplam ağırlık sözlüğü (Geriye uyumluluk için)
        self.indicator_weights = {**self.leading_weights, **self.lagging_weights}

    def calculate_all_indicators(self, df: pd.DataFrame) -> dict:
        """Tüm teknik indikatörleri hesaplar"""
        if df.empty or len(df) < 50:
            return {"error": "Yetersiz veri (en az 50 mum gerekli)"}

        indicators = {}

        try:
            # 1. ÖNCÜ (LEADING) GÖSTERGELER
            indicators["rsi"] = self._calc_rsi(df)
            indicators["rsi_divergence"] = self._calc_rsi_divergence(df)
            indicators["stochastic"] = self._calc_stochastic(df)
            indicators["williams_r"] = self._calc_williams_r(df)
            indicators["cci"] = self._calc_cci(df)
            indicators["obv_trend"] = self._calc_obv(df)
            indicators["squeeze"] = self._calc_squeeze(df)
            indicators["volume_spike"] = self._calc_volume_spike(df)

            # 2. ARTÇI (LAGGING) GÖSTERGELER
            indicators["macd"] = self._calc_macd(df)
            indicators["bollinger"] = self._calc_bollinger(df) # Lagging sayılır
            indicators["sma_cross"] = self._calc_sma_cross(df)
            indicators["ema_cross"] = self._calc_ema_cross(df)
            indicators["adx"] = self._calc_adx(df)
            indicators["vwap"] = self._calc_vwap(df)
            indicators["ichimoku"] = self._calc_ichimoku(df)
            indicators["parabolic_sar"] = self._calc_parabolic_sar(df)

            # 3. DİĞER (DESTEK/DİRENÇ & FİBO)
            indicators["atr"] = self._calc_atr(df)
            indicators["fibonacci"] = self._calc_fibonacci(df)
            indicators["support_resistance"] = self._calc_support_resistance(df)
            indicators["previous_close"] = df['Close'].iloc[-2] if len(df) > 1 else df['Close'].iloc[-1]
            
            # İlk kırılım kontrolü (v2'nin kalbi)
            indicators["first_breakout"] = self._check_first_breakout(df, indicators)

            # Sınıf Skorlarını Hesapla
            leading_score = self._calculate_group_score(indicators, self.leading_weights)
            lagging_score = self._calculate_group_score(indicators, self.lagging_weights)
            
            indicators["leading_score"] = leading_score
            indicators["lagging_score"] = lagging_score
            
            # Genel skor hesapla (Yeni ağırlıklı)
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

    def calculate_smart_money(self, df: pd.DataFrame) -> dict:
        """AKD / Takas Simülatörü: MFI, OBV ve Force Index üzerinden kurumsal para onayı"""
        if len(df) < 20:
             return {"approved": False, "reason": "Yetersiz veri"}
             
        # 1. MFI (Money Flow Index)
        try:
            mfi = ta.volume.MFIIndicator(df['High'], df['Low'], df['Close'], df['Volume']).money_flow_index()
            mfi_val = mfi.iloc[-1]
            mfi_prev = mfi.iloc[-5] if len(mfi) > 5 else mfi.iloc[-1]
        except:
            mfi_val, mfi_prev = 50, 50
            
        # 2. OBV Kırılımı
        try:
            obv = ta.volume.OnBalanceVolumeIndicator(df['Close'], df['Volume']).on_balance_volume()
            obv_sma = obv.rolling(10).mean()
            obv_breakout = obv.iloc[-1] > obv_sma.iloc[-1] and (obv.iloc[-1] > obv.iloc[-5])
        except:
            obv_breakout = False
            
        # 3. Force Index
        try:
            # $FI = (Kapanış_t - Kapanış_{t-1}) * Hacim
            close_diff = df['Close'].diff()
            force_index = close_diff * df['Volume']
            force_index_sma = force_index.rolling(13).mean()
            
            fi_current = force_index.iloc[-1]
            fi_sma_current = force_index_sma.iloc[-1]
            fi_strong = fi_current > fi_sma_current and fi_current > 0
        except:
            fi_strong = False

        # 4. Hacim anomalisi (Sentetik Balina Tespiti)
        try:
            # Son 1 saat (12 adet 5 dakikalık mum, veya veriye göre son 12 mum)
            last_vol = df['Volume'].iloc[-1]
            avg_vol_1h = df['Volume'].iloc[-13:-1].mean()
            price_change = abs((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100)
            
            balina_girisi = (last_vol > avg_vol_1h * 3) and (price_change <= 1.0)
        except:
            balina_girisi = False

        kurumsal_onay = False
        reason = ""
        balina_notu = ""

        if balina_girisi:
            kurumsal_onay = True
            reason = "Hacim Anomalisi Tespit Edildi - Sentetik AKD Onaylı"
            balina_notu = "🐳 BALİNA ANALİZİ: ✅ (Hacim Anomalisi Tespit Edildi - Sentetik AKD Onaylı)"
        elif obv_breakout and fi_strong:
            kurumsal_onay = True
            reason = "OBV direnci kırıldı ve Force Index hacimli kurumsal alımı onaylıyor."
        elif mfi_val > mfi_prev and fi_strong:
            kurumsal_onay = True
            reason = "MFI dikleşiyor (+Force), yatayda gizli balina toplaması (accumulation) saptandı."
        elif mfi_val > 60 and obv_breakout:
            kurumsal_onay = True
            reason = "Güçlü MFI ve OBV ile Kurumsal (Smart Para) girişi devam ediyor."
        else:
            kurumsal_onay = False
            reason = "Para çıkışı/Dağıtım veya Küçük yatırımcı (Diğer) ağırlıklı hacim."

        return {
            "approved": kurumsal_onay,
            "mfi": round(mfi_val, 2),
            "obv_breakout": obv_breakout,
            "force_index_strong": fi_strong,
            "balina_girisi": balina_girisi,
            "balina_notu": balina_notu,
            "reason": reason
        }

    def _calc_rsi_divergence(self, df: pd.DataFrame) -> dict:
        """RSI Uyumsuzluğu (Divergence) tespiti - Gelişmiş Öncü Gösterge"""
        try:
            rsi_series = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
            price_series = df['Close']
            
            # Son 20 barı inceleyelim
            window = 15
            if len(df) < window + 5:
                return {"score": 50, "signal": "TUT", "description": "Yetersiz veri"}

            # Boğa Uyumsuzluğu (Fiyat Yeni Dip, RSI Daha Yüksek Dip)
            price_min_idx = price_series.iloc[-window:].idxmin()
            rsi_min_idx = rsi_series.iloc[-window:].idxmin()
            
            # Eğer fiyatın en düşüğü ile RSI'ın en düşüğü farklı yerlerdeyse
            bullish_div = False
            if price_series.iloc[-1] <= price_series.iloc[price_min_idx] * 1.02: # Fiyat hala diplerde
                if rsi_series.iloc[-1] > rsi_series.iloc[rsi_min_idx] + 2: # RSI yükselmeye başlamış
                    bullish_div = True

            if bullish_div:
                return {"score": 85, "signal": "AL", "description": "🐂 POZİTİF UYUMSUZLUK (Boğa): Fiyat dipte, RSI yükseliyor!"}
            
            return {"score": 50, "signal": "TUT", "description": "Uyumsuzluk saptanmadı"}
        except:
            return {"score": 50, "signal": "TUT", "description": "Hata"}

    def _calc_squeeze(self, df: pd.DataFrame) -> dict:
        """Bollinger Sıkışması (Squeeze) - Patlama öncesi sessizlik"""
        try:
            bb = ta.volatility.BollingerBands(df['Close'])
            upper = bb.bollinger_hband()
            lower = bb.bollinger_lband()
            bandwidth = (upper - lower) / bb.bollinger_mavg()
            
            # Son 100 barın ortalama genişliğiyle karşılaştır
            avg_width = bandwidth.rolling(50).mean()
            current_width = bandwidth.iloc[-1]
            
            is_squeezed = current_width < avg_width.iloc[-1] * 0.8
            expanding = current_width > bandwidth.iloc[-2]
            
            if is_squeezed and expanding:
                return {"score": 80, "signal": "AL", "description": "💥 SIKIŞMA KIRILIMI: Fiyat patlamaya hazır!"}
            elif is_squeezed:
                return {"score": 60, "signal": "TUT", "description": "⏳ SIKIŞMA: Enerji toplanıyor, kırılım bekleniyor."}
            
            return {"score": 50, "signal": "TUT", "description": "Normal oynaklık"}
        except:
            return {"score": 50, "signal": "TUT", "description": "Hata"}

    def _calc_volume_spike(self, df: pd.DataFrame) -> dict:
        """Hacim Patlaması - Gerçek kırılım onayı"""
        try:
            current_vol = df['Volume'].iloc[-1]
            avg_vol = df['Volume'].iloc[-21:-1].mean()
            
            ratio = current_vol / avg_vol if avg_vol > 0 else 1
            
            if ratio > 3:
                return {"score": 90, "signal": "AL", "description": f"🔥 HACİM PATLAMASI: Ortalama x{ratio:.1f}!"}
            elif ratio > 1.5:
                return {"score": 65, "signal": "AL", "description": "📈 Hacim artıyor."}
            
            return {"score": 50, "signal": "TUT", "description": "Normal hacim"}
        except:
            return {"score": 50, "signal": "TUT", "description": "Hata"}

    def _check_first_breakout(self, df, indicators) -> dict:
        """İLK KIRILIM TAKİBİ: %2-3 yapmışları yakalar, %5'i geçmişleri ignore eder"""
        try:
            current_price = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            daily_pct = ((current_price / prev_close) - 1) * 100
            
            # Kırılım şartları:
            # 1. Hacim yüksek olmalı
            # 2. Öncü göstergeler (RSI, Squeeze vb) pozitif olmalı
            # 3. Yükseliş henüz çok taze (%1.5 - %3.5 arası)
            
            is_early = 1.0 <= daily_pct <= 3.8
            is_late = daily_pct > 5.0
            
            hacim_onay = indicators["volume_spike"]["score"] >= 65
            squeeze_onay = indicators["squeeze"]["score"] >= 60
            
            if is_early and (hacim_onay or squeeze_onay):
                return {"score": 95, "status": "EARLY", "description": f"🚀 İLK KIRILIM: %{daily_pct:.1f} yükselişle taze başlama!"}
            elif is_late:
                return {"score": 40, "status": "LATE", "description": "⚠️ GEÇ KALINDI: Hisse zaten %5+ gitmiş."}
            
            return {"score": 50, "status": "NONE"}
        except:
            return {"score": 50, "status": "NONE"}

    def _calculate_group_score(self, indicators: dict, weights: dict) -> float:
        """Grup bazlı (Leading/Lagging) skor hesaplar"""
        total_w = 0
        weighted_s = 0
        for name, w in weights.items():
            if name in indicators and "score" in indicators[name]:
                weighted_s += indicators[name]["score"] * w
                total_w += w
        return round(weighted_s / total_w, 2) if total_w > 0 else 50.0

    def _calculate_overall_score(self, indicators: dict) -> float:
        """Tüm indikatörlerin ağırlıklı ortalama skorunu hesaplar (v2: Öncü ağırlıklı)"""
        # Leading (Öncü) %65, Lagging (Artçı) %35 ağırlıklı
        leading = indicators.get("leading_score", 50)
        lagging = indicators.get("lagging_score", 50)
        
        # Eğer ilk kırılım varsa skoru yukarı çek
        breakout_bonus = 0
        if indicators.get("first_breakout", {}).get("status") == "EARLY":
            breakout_bonus = 10
        
        final_score = (leading * 0.65) + (lagging * 0.35) + breakout_bonus
        return round(min(100, final_score), 2)

    def _generate_signal(self, score: float) -> dict:
        """Skora göre sinyal üretir"""
        if score >= 80:
            return {"action": "GÜÇLÜ AL", "emoji": "🚀🚀", "confidence": "Çok Yüksek"}
        elif score >= 65:
            return {"action": "AL", "emoji": "🚀", "confidence": "Yüksek"}
        elif score <= 25:
            return {"action": "GÜÇLÜ SAT", "emoji": "🔴🔴", "confidence": "Yüksek"}
        elif score <= 40:
            return {"action": "SAT", "emoji": "🔴", "confidence": "Orta"}
        else:
            return {"action": "TUT", "emoji": "🟡", "confidence": "Düşük"}
