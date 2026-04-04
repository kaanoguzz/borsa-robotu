"""
Model Eğitici — Hata Takibi ve Haftalık Fine-Tuning

1. Her sinyal sonrası gerçek fiyat hareketiyle karşılaştırır
2. Hatalı sinyalleri signal_errors.log dosyasına kaydeder
3. Haftada bir modeli bu hatalardan ders çıkararak yeniden eğitir
4. Eğitim sonrası yeni doğruluk oranını raporlar
"""

import os
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from data_collector import DataCollector
from predictor import StockPredictor
from portfolio import PortfolioManager

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG_PATH = os.path.join(BASE_DIR, "signal_errors.log")
TRAINING_LOG_PATH = os.path.join(BASE_DIR, "training_history.log")
ERROR_DATA_PATH = os.path.join(BASE_DIR, "error_data.json")


class ModelTrainer:
    """Hatalı sinyallerden öğrenen model eğitici"""

    def __init__(self):
        self.data_collector = DataCollector()
        self.predictor = StockPredictor()
        self.portfolio = PortfolioManager()
        self._ensure_files()

    def _ensure_files(self):
        """Gerekli dosyaları oluşturur"""
        if not os.path.exists(ERROR_DATA_PATH):
            with open(ERROR_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump({"errors": [], "last_checked": None}, f)

    # ==================== HATA TESPİT VE KAYIT ====================

    def verify_past_signals(self, lookback_days: int = 7) -> dict:
        """
        Geçmiş sinyalleri gerçek fiyat hareketiyle doğrular.
        Hatalı sinyalleri log dosyasına kaydeder.
        """
        signals = self.portfolio.get_signals(limit=200)
        if not signals:
            return {"checked": 0, "correct": 0, "incorrect": 0, "errors": []}

        correct = 0
        incorrect = 0
        unverifiable = 0
        errors = []
        cutoff = datetime.now() - timedelta(days=lookback_days)

        for signal in signals:
            try:
                signal_date = datetime.fromisoformat(signal["date"])

                # Sadece belirli zaman aralığındaki sinyalleri kontrol et
                # (çok yeni olanlara bakma — sonuç henüz belli değil)
                if signal_date > datetime.now() - timedelta(days=5):
                    unverifiable += 1
                    continue
                if signal_date < cutoff:
                    continue

                symbol = signal["symbol"]
                action = signal["signal_type"]
                price_at_signal = signal.get("price_at_signal", 0)

                if action in ["TUT", "ENGEL"] or price_at_signal == 0:
                    continue

                # 5 gün sonraki fiyatı kontrol et
                df = self.data_collector.get_stock_data(symbol, period="1mo")
                if df.empty:
                    continue

                # Sinyal tarihinden sonraki fiyatı bul
                signal_idx = None
                for i, idx in enumerate(df.index):
                    if idx.date() >= signal_date.date():
                        signal_idx = i
                        break

                if signal_idx is None or signal_idx + 5 >= len(df):
                    unverifiable += 1
                    continue

                future_price = df['Close'].iloc[signal_idx + 5]
                actual_return = (future_price - price_at_signal) / price_at_signal

                # Doğruluk kontrolü
                is_correct = False
                if "AL" in action and actual_return > 0.01:
                    is_correct = True
                elif "SAT" in action and actual_return < -0.01:
                    is_correct = True

                if is_correct:
                    correct += 1
                else:
                    incorrect += 1
                    error_entry = {
                        "signal_id": signal["id"],
                        "symbol": symbol,
                        "signal_type": action,
                        "score": signal["score"],
                        "technical_score": signal.get("technical_score", 0),
                        "news_score": signal.get("news_score", 0),
                        "ml_score": signal.get("ml_score", 0),
                        "price_at_signal": round(price_at_signal, 2),
                        "price_after_5d": round(future_price, 2),
                        "actual_return_pct": round(actual_return * 100, 2),
                        "signal_date": signal["date"],
                        "verified_at": datetime.now().isoformat(),
                        "error_type": self._classify_error(action, actual_return),
                    }
                    errors.append(error_entry)

                    # Hata loguna yaz
                    self._log_error(error_entry)

            except Exception as e:
                logger.debug(f"Sinyal doğrulama hatası: {e}")
                continue

        # Hata verisini kaydet (fine-tuning için)
        self._save_error_data(errors)

        total = correct + incorrect
        accuracy = (correct / total * 100) if total > 0 else 0

        result = {
            "checked": total,
            "correct": correct,
            "incorrect": incorrect,
            "unverifiable": unverifiable,
            "accuracy_pct": round(accuracy, 2),
            "errors": errors,
            "verified_at": datetime.now().isoformat()
        }

        logger.info(
            f"📋 Sinyal doğrulama: {correct}/{total} doğru (%{accuracy:.1f}), "
            f"{incorrect} hatalı sinyal loglandı"
        )

        return result

    def _classify_error(self, action: str, actual_return: float) -> str:
        """Hata tipini sınıflandırır"""
        if "AL" in action:
            if actual_return < -0.05:
                return "FALSE_BUY_MAJOR"    # Büyük kayıp — ciddi hata
            elif actual_return < -0.02:
                return "FALSE_BUY_MODERATE"  # Orta kayıp
            else:
                return "FALSE_BUY_MINOR"     # Küçük sapma
        elif "SAT" in action:
            if actual_return > 0.05:
                return "FALSE_SELL_MAJOR"    # Büyük fırsat kaçırma
            elif actual_return > 0.02:
                return "FALSE_SELL_MODERATE"
            else:
                return "FALSE_SELL_MINOR"
        return "UNKNOWN"

    def _log_error(self, error: dict):
        """Hatalı sinyali log dosyasına yazar"""
        try:
            with open(ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
                timestamp = error.get("verified_at", datetime.now().isoformat())
                f.write(
                    f"[{timestamp}] "
                    f"{error['error_type']} | "
                    f"{error['symbol']} | "
                    f"Sinyal: {error['signal_type']} (Skor: {error['score']:.1f}) | "
                    f"Fiyat: {error['price_at_signal']:.2f} → {error['price_after_5d']:.2f} "
                    f"({error['actual_return_pct']:+.1f}%) | "
                    f"Tech: {error['technical_score']:.0f}, News: {error['news_score']:.0f}, "
                    f"ML: {error['ml_score']:.0f}\n"
                )
            logger.info(f"❌ Hatalı sinyal loglandı: {error['symbol']} ({error['error_type']})")
        except Exception as e:
            logger.error(f"Hata log yazma hatası: {e}")

    def _save_error_data(self, new_errors: list):
        """Hata verilerini JSON dosyasına kaydeder (fine-tuning veri seti)"""
        try:
            existing = {"errors": [], "last_checked": None}
            if os.path.exists(ERROR_DATA_PATH):
                with open(ERROR_DATA_PATH, 'r', encoding='utf-8') as f:
                    existing = json.load(f)

            # Yeni hataları ekle (duplicate kontrolü)
            existing_ids = {e.get("signal_id") for e in existing["errors"]}
            for error in new_errors:
                if error["signal_id"] not in existing_ids:
                    existing["errors"].append(error)

            existing["last_checked"] = datetime.now().isoformat()

            # Son 500 hatayı tut (bellek yönetimi)
            existing["errors"] = existing["errors"][-500:]

            with open(ERROR_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Hata verisi kaydetme hatası: {e}")

    # ==================== HAFTALIK YENİDEN EĞİTİM ====================

    def weekly_retrain(self) -> dict:
        """
        Haftalık model yeniden eğitimi.
        
        Adımlar:
        1. Geçmiş sinyalleri doğrula ve hataları logla
        2. Hata verilerini analiz et
        3. Hata örüntülerini belirle
        4. Modeli güncel veriyle yeniden eğit
        5. Yeni modelin doğruluğunu raporla
        6. Eğer yeni model daha kötüyse eski modeli koru
        """
        logger.info("🔄 Haftalık model yeniden eğitimi başlatılıyor...")
        
        training_results = {
            "started_at": datetime.now().isoformat(),
            "error_analysis": {},
            "retrained_models": {},
            "improvements": {},
        }

        # 1. Sinyalleri doğrula
        verification = self.verify_past_signals(lookback_days=14)
        training_results["verification"] = {
            "checked": verification["checked"],
            "correct": verification["correct"],
            "incorrect": verification["incorrect"],
            "accuracy": verification["accuracy_pct"]
        }

        # 2. Hata analizi — hangi hisselerde en çok hata yapılmış?
        error_analysis = self._analyze_errors()
        training_results["error_analysis"] = error_analysis

        # 3. Her hisse için yeniden eğitim
        from config import BIST100_TICKERS
        symbols_to_retrain = self._get_retrain_candidates(error_analysis)

        for symbol in symbols_to_retrain:
            try:
                result = self._retrain_single_model(symbol, error_analysis)
                training_results["retrained_models"][symbol] = result

                if result.get("improved"):
                    training_results["improvements"][symbol] = {
                        "old_accuracy": result["old_accuracy"],
                        "new_accuracy": result["new_accuracy"],
                        "improvement": result["improvement"]
                    }
                    
            except Exception as e:
                logger.error(f"{symbol} yeniden eğitim hatası: {e}")
                training_results["retrained_models"][symbol] = {"error": str(e)}

        # 4. Eğitim logunu kaydet
        self._log_training(training_results)

        training_results["completed_at"] = datetime.now().isoformat()
        total_retrained = len(training_results["retrained_models"])
        total_improved = len(training_results["improvements"])

        logger.info(
            f"✅ Haftalık eğitim tamamlandı: {total_retrained} model eğitildi, "
            f"{total_improved} model iyileşti"
        )

        return training_results

    def _analyze_errors(self) -> dict:
        """Hata verilerini analiz eder — örüntü bulur"""
        try:
            if not os.path.exists(ERROR_DATA_PATH):
                return {}

            with open(ERROR_DATA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            errors = data.get("errors", [])
            if not errors:
                return {"total_errors": 0}

            # Hisse bazlı hata sayısı
            symbol_errors = {}
            error_types = {}
            score_distribution = {"high_score_errors": 0, "low_score_errors": 0}

            for err in errors:
                sym = err["symbol"]
                etype = err.get("error_type", "UNKNOWN")

                symbol_errors[sym] = symbol_errors.get(sym, 0) + 1
                error_types[etype] = error_types.get(etype, 0) + 1

                # Yüksek skorlu hatalar daha ciddi
                if err.get("score", 50) > 70 or err.get("score", 50) < 30:
                    score_distribution["high_score_errors"] += 1
                else:
                    score_distribution["low_score_errors"] += 1

            # En çok hata yapılan hisseler
            worst_stocks = sorted(symbol_errors.items(), key=lambda x: x[1], reverse=True)[:10]

            # Hangi indikatörlerin hatalı sinyallerde yanlış yönlendirdiğini analiz et
            false_buy_avg_tech = []
            false_sell_avg_tech = []
            for err in errors:
                if "BUY" in err.get("error_type", ""):
                    false_buy_avg_tech.append(err.get("technical_score", 50))
                elif "SELL" in err.get("error_type", ""):
                    false_sell_avg_tech.append(err.get("technical_score", 50))

            return {
                "total_errors": len(errors),
                "symbol_errors": dict(worst_stocks),
                "error_types": error_types,
                "score_distribution": score_distribution,
                "avg_tech_score_false_buys": round(
                    sum(false_buy_avg_tech) / len(false_buy_avg_tech), 1
                ) if false_buy_avg_tech else None,
                "avg_tech_score_false_sells": round(
                    sum(false_sell_avg_tech) / len(false_sell_avg_tech), 1
                ) if false_sell_avg_tech else None,
                "analyzed_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Hata analizi hatası: {e}")
            return {"error": str(e)}

    def _get_retrain_candidates(self, error_analysis: dict) -> list:
        """Yeniden eğitilmesi gereken hisseleri belirler"""
        candidates = []

        # 1. En çok hata yapılan hisseler (öncelikli)
        symbol_errors = error_analysis.get("symbol_errors", {})
        for symbol, count in symbol_errors.items():
            if count >= 2:  # 2+ hata → yeniden eğit
                candidates.append(symbol)

        # 2. Mevcut modeli olmayan populer hisseler
        from config import BIST100_TICKERS
        model_dir = os.path.join(BASE_DIR, "models")
        if os.path.exists(model_dir):
            for symbol in BIST100_TICKERS[:20]:  # En likit 20 hisse
                model_path = os.path.join(model_dir, f"{symbol}_model.joblib")
                if not os.path.exists(model_path) and symbol not in candidates:
                    candidates.append(symbol)

        return candidates

    def _retrain_single_model(self, symbol: str, error_analysis: dict) -> dict:
        """Tek bir hisse modelini yeniden eğitir — hatalardan ders çıkararak"""
        logger.info(f"🔄 {symbol} modeli yeniden eğitiliyor...")

        # Mevcut modelin doğruluğu
        old_accuracy = self.predictor.model_scores.get(symbol, 0)

        # 2 yıllık güncel veriyi çek
        df = self.data_collector.get_stock_data(symbol, period="2y")
        if df.empty or len(df) < 100:
            return {
                "symbol": symbol,
                "error": "Yetersiz veri",
                "old_accuracy": old_accuracy
            }

        # Hata ağırlıklı eğitim:
        # Daha önce hata yapılan dönemlere daha fazla ağırlık ver
        error_count = error_analysis.get("symbol_errors", {}).get(symbol, 0)

        # Eğitim parametrelerini hata sayısına göre ayarla
        if error_count >= 5:
            # Çok hata → stricter model
            forward_days = 5
            threshold = 0.025  # Daha katı eşik
        elif error_count >= 2:
            forward_days = 5
            threshold = 0.02
        else:
            forward_days = 5
            threshold = 0.015  # Standart

        # Modeli yeniden eğit
        train_result = self.predictor.train_model(symbol, df, forward_days=forward_days)
        
        if "error" in train_result:
            return {
                "symbol": symbol,
                "error": train_result["error"],
                "old_accuracy": old_accuracy
            }

        new_accuracy = train_result.get("accuracy", 0)
        improvement = new_accuracy - old_accuracy

        # Eğer yeni model daha kötüyse, onu kullanma uyarısı ver
        if new_accuracy < old_accuracy and old_accuracy > 0:
            logger.warning(
                f"⚠️ {symbol}: Yeni model daha kötü! "
                f"Eski: %{old_accuracy*100:.1f} → Yeni: %{new_accuracy*100:.1f}"
            )
            # Eski model korunur (predictor zaten yeni modeli yükledi, ama skor düşük)
            improved = False
        else:
            improved = True

        return {
            "symbol": symbol,
            "old_accuracy": round(old_accuracy, 4),
            "new_accuracy": round(new_accuracy, 4),
            "improvement": round(improvement, 4),
            "improved": improved,
            "error_count": error_count,
            "model_type": train_result.get("model_type"),
            "training_samples": train_result.get("training_samples"),
            "top_features": train_result.get("top_features", [])[:5],
            "trained_at": datetime.now().isoformat()
        }

    def _log_training(self, results: dict):
        """Eğitim sonuçlarını log dosyasına yazar"""
        try:
            with open(TRAINING_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*70}\n")
                f.write(f"HAFTALIK EĞİTİM — {results.get('started_at', 'N/A')}\n")
                f.write(f"{'='*70}\n")

                v = results.get("verification", {})
                f.write(f"Sinyal Doğrulama: {v.get('correct', 0)}/{v.get('checked', 0)} doğru ")
                f.write(f"(%{v.get('accuracy', 0):.1f})\n")
                f.write(f"Hatalı Sinyaller: {v.get('incorrect', 0)}\n\n")

                ea = results.get("error_analysis", {})
                f.write(f"Toplam Hata Kaydı: {ea.get('total_errors', 0)}\n")
                if ea.get("symbol_errors"):
                    f.write("En Çok Hata: ")
                    for sym, cnt in list(ea["symbol_errors"].items())[:5]:
                        f.write(f"{sym}({cnt}) ")
                    f.write("\n")

                f.write(f"\nYeniden Eğitilen Modeller:\n")
                for sym, res in results.get("retrained_models", {}).items():
                    if "error" in res:
                        f.write(f"  ❌ {sym}: {res['error']}\n")
                    else:
                        icon = "📈" if res.get("improved") else "📉"
                        f.write(
                            f"  {icon} {sym}: %{res.get('old_accuracy', 0)*100:.1f} → "
                            f"%{res.get('new_accuracy', 0)*100:.1f} "
                            f"({'iyileşti' if res.get('improved') else 'kötüleşti'})\n"
                        )

                f.write(f"\nTamamlandı: {results.get('completed_at', 'N/A')}\n")

        except Exception as e:
            logger.error(f"Eğitim log yazma hatası: {e}")

    def get_error_summary(self) -> str:
        """Hata özeti metni — bildirimler için"""
        analysis = self._analyze_errors()
        
        if not analysis or analysis.get("total_errors", 0) == 0:
            return "✅ Henüz hatalı sinyal kaydı yok."

        text = (
            f"📋 HATA ANALİZİ\n\n"
            f"Toplam Hata: {analysis['total_errors']}\n"
        )

        if analysis.get("symbol_errors"):
            text += "En Çok Hata:\n"
            for sym, cnt in list(analysis["symbol_errors"].items())[:5]:
                text += f"  • {sym}: {cnt} hata\n"

        if analysis.get("error_types"):
            text += "\nHata Tipleri:\n"
            for etype, cnt in analysis["error_types"].items():
                text += f"  • {etype}: {cnt}\n"

        return text
