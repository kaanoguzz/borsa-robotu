"""
ML Tahmin Modülü
RandomForest + XGBoost ensemble ile hisse fiyat tahmini
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
import ta
import joblib
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


class StockPredictor:
    """Machine Learning ile hisse tahmin modülü"""

    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.model_scores = {}
        os.makedirs(MODEL_DIR, exist_ok=True)

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Teknik indikatörlerden feature'lar oluşturur"""
        if df.empty or len(df) < 60:
            return pd.DataFrame()

        features = pd.DataFrame(index=df.index)

        try:
            # RSI
            features['rsi'] = ta.momentum.RSIIndicator(df['Close']).rsi()
            features['rsi_change'] = features['rsi'].diff()

            # MACD
            macd = ta.trend.MACD(df['Close'])
            features['macd'] = macd.macd()
            features['macd_signal'] = macd.macd_signal()
            features['macd_diff'] = macd.macd_diff()
            features['macd_cross'] = (features['macd'] > features['macd_signal']).astype(int)

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(df['Close'])
            features['bb_upper'] = bb.bollinger_hband()
            features['bb_lower'] = bb.bollinger_lband()
            features['bb_width'] = (features['bb_upper'] - features['bb_lower']) / bb.bollinger_mavg()
            features['bb_position'] = (df['Close'] - features['bb_lower']) / (features['bb_upper'] - features['bb_lower'])

            # Hareketli Ortalamalar
            features['sma_5'] = df['Close'].rolling(5).mean()
            features['sma_10'] = df['Close'].rolling(10).mean()
            features['sma_20'] = df['Close'].rolling(20).mean()
            features['sma_50'] = df['Close'].rolling(50).mean()

            # EMA
            features['ema_12'] = ta.trend.EMAIndicator(df['Close'], 12).ema_indicator()
            features['ema_26'] = ta.trend.EMAIndicator(df['Close'], 26).ema_indicator()
            features['ema_cross'] = (features['ema_12'] > features['ema_26']).astype(int)

            # Fiyat ortalamadan sapma
            features['price_sma20_ratio'] = df['Close'] / features['sma_20']
            features['price_sma50_ratio'] = df['Close'] / features['sma_50']

            # Stochastic
            stoch = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close'])
            features['stoch_k'] = stoch.stoch()
            features['stoch_d'] = stoch.stoch_signal()

            # ADX
            adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'])
            features['adx'] = adx.adx()
            features['adx_pos'] = adx.adx_pos()
            features['adx_neg'] = adx.adx_neg()
            features['di_diff'] = features['adx_pos'] - features['adx_neg']

            # Williams %R
            features['williams_r'] = ta.momentum.WilliamsRIndicator(df['High'], df['Low'], df['Close']).williams_r()

            # CCI
            features['cci'] = ta.trend.CCIIndicator(df['High'], df['Low'], df['Close']).cci()

            # ATR
            features['atr'] = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range()
            features['atr_pct'] = features['atr'] / df['Close']

            # OBV trendi
            obv = ta.volume.OnBalanceVolumeIndicator(df['Close'], df['Volume']).on_balance_volume()
            features['obv_change'] = obv.pct_change()

            # Hacim
            features['volume_sma'] = df['Volume'].rolling(20).mean()
            features['volume_ratio'] = df['Volume'] / features['volume_sma']

            # Fiyat değişim oranları
            features['return_1d'] = df['Close'].pct_change(1)
            features['return_5d'] = df['Close'].pct_change(5)
            features['return_10d'] = df['Close'].pct_change(10)
            features['return_20d'] = df['Close'].pct_change(20)

            # Volatilite
            features['volatility_5'] = df['Close'].rolling(5).std() / df['Close']
            features['volatility_20'] = df['Close'].rolling(20).std() / df['Close']

            # Momentum
            features['momentum_10'] = df['Close'] / df['Close'].shift(10) - 1
            features['momentum_20'] = df['Close'] / df['Close'].shift(20) - 1

            # Mum formasyonları
            features['body_size'] = abs(df['Close'] - df['Open']) / df['Open']
            features['upper_shadow'] = (df['High'] - df[['Close', 'Open']].max(axis=1)) / df['Open']
            features['lower_shadow'] = (df[['Close', 'Open']].min(axis=1) - df['Low']) / df['Open']
            features['is_bullish'] = (df['Close'] > df['Open']).astype(int)

            # Gün bazlı özellikler
            if hasattr(df.index, 'dayofweek'):
                features['day_of_week'] = df.index.dayofweek
            
        except Exception as e:
            logger.error(f"Feature oluşturma hatası: {e}")

        return features

    def create_labels(self, df: pd.DataFrame, forward_days: int = 5, threshold: float = 0.02) -> pd.Series:
        """
        Hedef etiketleri oluşturur
        
        Args:
            df: Fiyat verisi
            forward_days: Kaç gün sonrasına bakılacak
            threshold: AL/SAT için minimum fiyat değişimi
        
        Returns:
            Series: 0=SAT, 1=TUT, 2=AL
        """
        future_return = df['Close'].shift(-forward_days) / df['Close'] - 1
        
        labels = pd.Series(1, index=df.index)  # Default: TUT
        labels[future_return >= threshold] = 2   # AL
        labels[future_return <= -threshold] = 0  # SAT
        
        return labels

    def train_model(self, symbol: str, df: pd.DataFrame, forward_days: int = 5) -> dict:
        """Bir hisse için model eğitir"""
        logger.info(f"{symbol} için model eğitiliyor...")
        
        features = self.prepare_features(df)
        labels = self.create_labels(df, forward_days=forward_days)

        if features.empty:
            return {"error": "Yetersiz veri"}

        # NaN temizle
        valid_mask = features.notna().all(axis=1) & labels.notna()
        features = features[valid_mask]
        labels = labels[valid_mask]

        if len(features) < 100:
            return {"error": f"Yetersiz eğitim verisi ({len(features)} satır)"}

        # Train/Test split
        X_train, X_test, y_train, y_test = train_test_split(
            features, labels, test_size=0.2, shuffle=False
        )

        # Ölçeklendirme
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Model 1: Random Forest
        rf_model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        rf_model.fit(X_train_scaled, y_train)
        rf_score = accuracy_score(y_test, rf_model.predict(X_test_scaled))

        # Model 2: Gradient Boosting
        gb_model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=10,
            subsample=0.8,
            random_state=42
        )
        gb_model.fit(X_train_scaled, y_train)
        gb_score = accuracy_score(y_test, gb_model.predict(X_test_scaled))

        # En iyi modeli seç
        if rf_score >= gb_score:
            best_model = rf_model
            best_name = "RandomForest"
            best_score = rf_score
        else:
            best_model = gb_model
            best_name = "GradientBoosting"
            best_score = gb_score

        # Feature importance
        feature_importance = dict(zip(
            features.columns,
            best_model.feature_importances_
        ))
        top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]

        # Modeli kaydet
        model_path = os.path.join(MODEL_DIR, f"{symbol}_model.joblib")
        scaler_path = os.path.join(MODEL_DIR, f"{symbol}_scaler.joblib")
        
        joblib.dump(best_model, model_path)
        joblib.dump(scaler, scaler_path)

        # Belleğe yükle
        self.models[symbol] = best_model
        self.scalers[symbol] = scaler
        self.model_scores[symbol] = best_score

        report = classification_report(y_test, best_model.predict(X_test_scaled), output_dict=True, zero_division=0)

        result = {
            "symbol": symbol,
            "model_type": best_name,
            "accuracy": round(best_score, 4),
            "rf_accuracy": round(rf_score, 4),
            "gb_accuracy": round(gb_score, 4),
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "top_features": top_features,
            "classification_report": report,
            "trained_at": datetime.now().isoformat()
        }

        logger.info(f"{symbol} model eğitildi: {best_name} (%{best_score*100:.1f})")
        return result

    def predict(self, symbol: str, df: pd.DataFrame) -> dict:
        """Bir hisse için tahmin yapar"""
        # Model yüklü mü kontrol et
        if symbol not in self.models:
            model_path = os.path.join(MODEL_DIR, f"{symbol}_model.joblib")
            scaler_path = os.path.join(MODEL_DIR, f"{symbol}_scaler.joblib")

            if os.path.exists(model_path) and os.path.exists(scaler_path):
                self.models[symbol] = joblib.load(model_path)
                self.scalers[symbol] = joblib.load(scaler_path)
            else:
                # Model yok, eğit
                logger.info(f"{symbol} için model bulunamadı, eğitim başlatılıyor...")
                train_result = self.train_model(symbol, df)
                if "error" in train_result:
                    return {
                        "symbol": symbol,
                        "prediction": "TUT",
                        "confidence": 0,
                        "score": 50,
                        "error": train_result["error"]
                    }

        features = self.prepare_features(df)
        if features.empty:
            return {
                "symbol": symbol,
                "prediction": "TUT",
                "confidence": 0,
                "score": 50,
                "error": "Feature oluşturulamadı"
            }

        # Son satır (güncel veri)
        latest = features.iloc[[-1]]
        
        # NaN kontrolü
        if latest.isna().any().any():
            latest = latest.fillna(0)

        try:
            scaled = self.scalers[symbol].transform(latest)
            prediction = self.models[symbol].predict(scaled)[0]
            probabilities = self.models[symbol].predict_proba(scaled)[0]

            label_map = {0: "SAT", 1: "TUT", 2: "AL"}
            pred_label = label_map[prediction]
            confidence = max(probabilities)
            
            # Skor hesapla (0-100)
            if prediction == 2:  # AL
                score = 50 + confidence * 50
            elif prediction == 0:  # SAT
                score = 50 - confidence * 50
            else:  # TUT
                score = 50

            return {
                "symbol": symbol,
                "prediction": pred_label,
                "confidence": round(confidence, 4),
                "score": round(score, 2),
                "probabilities": {
                    "SAT": round(probabilities[0], 4) if len(probabilities) > 0 else 0,
                    "TUT": round(probabilities[1], 4) if len(probabilities) > 1 else 0,
                    "AL": round(probabilities[2], 4) if len(probabilities) > 2 else 0,
                },
                "model_accuracy": round(self.model_scores.get(symbol, 0), 4),
                "description": f"ML Tahmin: {pred_label} (Güven: %{confidence*100:.1f})"
            }

        except Exception as e:
            logger.error(f"{symbol} tahmin hatası: {e}")
            return {
                "symbol": symbol,
                "prediction": "TUT",
                "confidence": 0,
                "score": 50,
                "error": str(e)
            }

    def retrain_all(self, stock_data: dict) -> dict:
        """Tüm modelleri yeniden eğitir"""
        results = {}
        for symbol, df in stock_data.items():
            if len(df) >= 100:
                result = self.train_model(symbol, df)
                results[symbol] = result
                logger.info(f"{symbol}: {result.get('accuracy', 'HATA')}")
            else:
                results[symbol] = {"error": f"Yetersiz veri ({len(df)} satır)"}
        
        return results
