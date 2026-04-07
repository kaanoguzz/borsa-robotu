"""
Sinyal Üretici Modülü — v3 (Final)

4'lü Süzgeç Sistemi:
1. Haber Temiz mi? (KAP + Genel haberler)
2. Para Girişi Var mı? (Hacim onayı + OBV)
3. Matematik Onaylıyor mu? (Teknik + ML)
4. Sosyal Medya Modu Nasıl? (Sentiment + Google Trends)

Kapılar:
- Backtest doğruluğu <%90 → Sinyal üretilmez
- Güven skoru <%95 → Bildirim gönderilmez
- XU100 düşüş trendinde → AL sinyali engellenir
- Sektör düşüşte → AL sinyali engellenir
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from data_collector import DataCollector
from technical_analysis import TechnicalAnalyzer
from news_analyzer import NewsAnalyzer
from predictor import StockPredictor
from portfolio import PortfolioManager
from backtester import Backtester
from macro_analyzer import MacroAnalyzer
from social_sentiment import SocialSentimentAnalyzer

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Tüm 4 katman analizi birleştirerek sinyal üreten ana modül"""

    def __init__(self):
        self.data_collector = DataCollector()
        self.technical_analyzer = TechnicalAnalyzer()
        self.news_analyzer = NewsAnalyzer()
        self.predictor = StockPredictor()
        self.portfolio = PortfolioManager()
        self.backtester = Backtester()
        self.macro_analyzer = MacroAnalyzer()
        self.social_sentiment = SocialSentimentAnalyzer()
        self.executor = ThreadPoolExecutor(max_workers=8) # 8 hisseyi aynı anda derin tara

        # Analiz ağırlıkları
        self.weights = {
            "technical": 0.30,
            "news": 0.15,
            "ml_prediction": 0.20,
            "fundamental": 0.10,
            "macro": 0.15,
            "social": 0.10,
        }

        # Kapı eşikleri
        self.min_backtest_accuracy = 50.0
        self.min_confidence_score = 50.0

    def analyze_stock(self, symbol: str, skip_backtest: bool = False, quick_mode: bool = False, external_df: pd.DataFrame = None) -> dict:
        """
        Bir hisseyi tüm katmanlarla analiz eder.
        quick_mode=True: Sadece teknik analiz + hızlı kontroller (sürekli döngü için)
        external_df: Dışarıdan hazır veri beslemesi (Bulk download için)
        """
        logger.info(f"🔍 {symbol} analizi başlatılıyor...")
        result = {
            "symbol": symbol,
            "analyzed_at": datetime.now().isoformat(),
            "errors": [],
            "checklist": {
                "news_clean": None,
                "money_flowing_in": None,
                "math_confirms": None,
                "social_positive": None,
            }
        }

        # ========== BACKTEST KAPISI ==========
        if not skip_backtest:
            try:
                backtest_result = self.backtester.run_backtest(symbol)
                result["backtest"] = {
                    "accuracy": backtest_result.get("accuracy", 0),
                    "confidence_score": backtest_result.get("confidence_score", 0),
                    "signal_allowed": backtest_result.get("signal_allowed", False),
                    "notification_allowed": backtest_result.get("notification_allowed", False),
                    "total_signals_tested": backtest_result.get("total_signals", 0),
                    "backtest_period": backtest_result.get("backtest_period", "N/A"),
                }

                if not backtest_result.get("signal_allowed", False):
                    accuracy = backtest_result.get("accuracy", 0)
                    result["overall_score"] = 50
                    result["signal"] = {
                        "action": "ENGEL",
                        "emoji": "🚫",
                        "confidence": "Backtest başarısız",
                        "reason": f"Backtest doğruluğu %{accuracy:.1f} < %{self.min_backtest_accuracy:.0f}. Sinyal engellendi.",
                        "signal_blocked": True,
                        "notification_blocked": True,
                    }
                    result["report"] = self._generate_report(result)
                    logger.warning(f"🚫 {symbol}: Backtest kapısı kapalı (%{accuracy:.1f})")
                    return result
            except Exception as e:
                result["errors"].append(f"Backtest hatası: {e}")
                result["backtest"] = {"skipped": True, "error": str(e)}
        else:
            result["backtest"] = {"skipped": True}

        # ========== MAKRO KAPISI (XU100 + SEKTÖR) ==========
        try:
            macro_risk = self.macro_analyzer.calculate_risk_score(symbol)
            result["macro_analysis"] = macro_risk
            macro_score = macro_risk.get("risk_score", 50)
            result["macro_score"] = macro_score

            market_bullish = macro_risk.get("market_gate_open", True)
            sector_healthy = macro_risk.get("sector_healthy", True)
            result["market_gate_open"] = market_bullish
            result["sector_healthy"] = sector_healthy
        except Exception as e:
            result["errors"].append(f"Makro analiz hatası: {e}")
            macro_score = 50
            result["macro_score"] = 50
            market_bullish = True
            sector_healthy = True

        # ========== VERİ ÇEK ==========
        try:
            if external_df is not None:
                df = external_df
            else:
                df = self.data_collector.get_stock_data(symbol, period="1y")

            if df is None or df.empty:
                result["errors"].append("Fiyat verisi bulunamadı")
                result["overall_score"] = 50
                result["signal"] = {"action": "TUT", "emoji": "⚠️", "confidence": "Veri yok"}
                return result
            result["current_price"] = round(df['Close'].iloc[-1], 2)
        except Exception as e:
            result["errors"].append(f"Veri çekme hatası: {e}")
            result["overall_score"] = 50
            result["signal"] = {"action": "TUT", "emoji": "⚠️", "confidence": "Hata"}
            return result

        # ========== KATMAN 1: HABER + KAP ==========
        try:
            news = self.news_analyzer.calculate_news_score(symbol)
            result["news_analysis"] = news
            news_score = news.get("score", 50)
            result["news_score"] = news_score
        except Exception as e:
            result["errors"].append(f"Haber analizi hatası: {e}")
            news_score = 50
            result["news_score"] = 50

        # KAP kontrolü (Haber temiz mi?)
        try:
            kap = self.social_sentiment.check_kap_news(symbol)
            result["kap_analysis"] = kap
            result["checklist"]["news_clean"] = kap.get("news_clean", True)
        except Exception as e:
            result["errors"].append(f"KAP kontrolü hatası: {e}")
            result["checklist"]["news_clean"] = True

        # ========== KATMAN 2: TEKNİK ANALİZ ==========
        try:
            technical = self.technical_analyzer.calculate_all_indicators(df)
            result["technical_analysis"] = technical
            technical_score = technical.get("overall_score", 50)
            result["technical_score"] = technical_score
        except Exception as e:
            result["errors"].append(f"Teknik analiz hatası: {e}")
            technical_score = 50
            result["technical_score"] = 50

        # ========== KATMAN 2 & 3: HACİM VE AKD / TAKAS (SMART MONEY) ==========
        try:
            obv_data = technical.get("obv_trend", {})
            volume_data = self._check_volume_confirmation(df)
            result["volume_confirmation"] = volume_data
            money_flowing = volume_data.get("confirmed", False)
            result["checklist"]["money_flowing_in"] = money_flowing
            
            smart_money = self.technical_analyzer.calculate_smart_money(df)
            result["smart_money"] = smart_money
            akd_approved = smart_money.get("approved", False)
            result["checklist"]["akd_approved"] = akd_approved
        except Exception as e:
            result["checklist"]["money_flowing_in"] = False
            result["checklist"]["akd_approved"] = False
            money_flowing = False
            akd_approved = False

        # ========== KATMAN 3: ML TAHMİN ==========
        if not quick_mode:
            try:
                df_2y = self.data_collector.get_stock_data(symbol, period="2y")
                if not df_2y.empty and len(df_2y) >= 100:
                    ml_prediction = self.predictor.predict(symbol, df_2y)
                    result["ml_prediction"] = ml_prediction
                    ml_score = ml_prediction.get("score", 50)
                else:
                    ml_score = 50
                    result["ml_prediction"] = {"prediction": "TUT", "confidence": 0, "score": 50}
                result["ml_score"] = ml_score
            except Exception as e:
                result["errors"].append(f"ML tahmin hatası: {e}")
                ml_score = 50
                result["ml_score"] = 50
        else:
            ml_score = 50
            result["ml_score"] = 50
            result["ml_prediction"] = {"prediction": "N/A", "note": "Hızlı mod — ML atlandı"}

        # Matematik onaylıyor mu?
        math_confirms = (technical_score >= 60 and ml_score >= 55) or (technical_score >= 70)
        result["checklist"]["math_confirms"] = math_confirms

        # ========== KATMAN 4: SOSYAL SENTIMENT ==========
        if not quick_mode:
            try:
                social = self.social_sentiment.get_combined_social_score(symbol)
                result["social_analysis"] = social
                social_score = social.get("combined_score", 50)
                result["social_score"] = social_score
                result["checklist"]["social_positive"] = social.get("mood") == "POZİTİF"
            except Exception as e:
                result["errors"].append(f"Sosyal sentiment hatası: {e}")
                social_score = 50
                result["social_score"] = 50
                result["checklist"]["social_positive"] = None
        else:
            social_score = 50
            result["social_score"] = 50
            result["checklist"]["social_positive"] = None

        # ========== TEMEL ANALİZ ==========
        if not quick_mode:
            try:
                fundamental_score = self._calculate_fundamental_score(symbol)
                result["fundamental_score"] = fundamental_score
            except Exception as e:
                result["errors"].append(f"Temel analiz hatası: {e}")
                fundamental_score = 50
                result["fundamental_score"] = 50
        else:
            fundamental_score = 50
            result["fundamental_score"] = 50

        # ========== BİRLEŞİK SKOR ==========
        overall_score = (
            technical_score * self.weights["technical"] +
            news_score * self.weights["news"] +
            ml_score * self.weights["ml_prediction"] +
            fundamental_score * self.weights["fundamental"] +
            macro_score * self.weights["macro"] +
            social_score * self.weights["social"]
        )
        result["overall_score"] = round(overall_score, 2)

        # ========== VETO SİSTEMİ (6/6 ONAY KONTROLÜ) ==========
        veto_akd = result["checklist"].get("akd_approved", False)
        veto_hacim = result["checklist"].get("money_flowing_in", False)
        veto_makro = market_bullish
        veto_duygu = social_score < 85  # Aşırı Pump (85 üstü) riskli sayılır
        veto_haber = result["checklist"].get("news_clean", True)
        veto_teknik = technical_score >= 60

        # VETO ESNETME: Eğer genel skor çok yüksekse (%75+) ve teknik onaylıysa, 
        # bir ufak parametre (sosyal veya haber) eksik olsa bile B-Sınıfı olarak geçebilir.
        veto_passed = veto_akd and veto_hacim and veto_makro and veto_duygu and veto_haber and veto_teknik
        
        # B-Sınıfı Onayı (🥈): 6/6 değil ama 5/6 ve skor yüksek
        is_b_class = False
        if not veto_passed and overall_score >= 65:
            # Kritik olanlar (AKD, Hacim, Teknik, Makro) MUTLAKA olmalı
            if veto_akd and veto_hacim and veto_teknik and veto_makro:
                is_b_class = True

        failed_params = []
        if not veto_teknik: failed_params.append("Teknik")
        if not veto_hacim: failed_params.append("Hacim")
        if not veto_akd: failed_params.append("AKD/Takas")
        if not veto_haber: failed_params.append("Haber")
        if not veto_makro: failed_params.append("Makro")
        if not veto_duygu: failed_params.append("Risk (Pump)")

        if overall_score >= 60 and veto_passed:
            raw_action = "GÜÇLÜ AL"
            emoji = "🟢"
            onay_notu = "✅ Teknik ✅ Hacim ✅ AKD ✅ Haber ✅ Makro ✅ Risk"
            balina_notu = result.get("smart_money", {}).get("balina_notu", "")
            if balina_notu:
                onay_notu += f"\n\n{balina_notu}"
            reason = onay_notu
        elif is_b_class:
            raw_action = "AL (B-SINIFI)"
            emoji = "🥈"
            onay_notu = "🥈 5/6 Onay (B-Sınıfı Fırsat)\n"
            onay_notu += "✅ Teknik ✅ Hacim ✅ AKD ✅ Makro"
            reason = onay_notu
        elif overall_score <= 40 or (overall_score >= 60 and not veto_passed and not is_b_class):
            raw_action = "SAT"
            emoji = "🔴"
            reason = "❌ Bozulan Parametreler: " + ", ".join(failed_params)
        else:
            raw_action = "TUT"
            emoji = "🟡"
            reason = "Nötr pozisyon."

        signal = {
            "action": raw_action,
            "emoji": emoji,
            "confidence": "Yüksek" if veto_passed else "Düşük",
            "reason": reason,
            "checklist": result["checklist"],
            "all_clear": veto_passed,
            "failed_params": failed_params,
            "onay_notu": onay_notu if veto_passed else ""
        }

        # Güven skoru kontrolü
        confidence_score = result.get("backtest", {}).get("confidence_score", 0)
        
        # KRİTİK DÜZELTME: Bulut modunda backtest atlandığı için confidence_score 0 gelir.
        # Eğer backtest atlanmışsa, overall_score üzerinden güven tazele.
        if result.get("backtest", {}).get("skipped"):
            effective_confidence = overall_score 
        else:
            effective_confidence = confidence_score

        notification_allowed = effective_confidence >= self.min_confidence_score and (veto_passed or is_b_class)
        signal["notification_allowed"] = notification_allowed
        signal["confidence_score"] = effective_confidence
        signal["is_b_class"] = is_b_class
        
        if not notification_allowed and not result.get("backtest", {}).get("skipped"):
            signal["notification_blocked_reason"] = f"VETO'ya takıldı veya Güven Skoru yetersiz."

        result["signal"] = signal

        # ========== KAYDET ==========
        try:
            signal_id = self.portfolio.save_signal(
                symbol=symbol,
                signal_type=signal["action"],
                score=overall_score,
                technical_score=technical_score,
                news_score=news_score,
                ml_score=ml_score,
                price=result.get("current_price", 0),
                description=signal.get("reason", "")
            )
            result["signal_id"] = signal_id
        except Exception as e:
            result["errors"].append(f"Sinyal kayıt hatası: {e}")

        # ========== RAPOR ==========
        result["report"] = self._generate_report(result)

        logger.info(f"✅ {symbol}: {signal['action']} (Skor: {overall_score:.1f})")
        return result

    def _check_volume_confirmation(self, df) -> dict:
        """Hacim onayı: fiyat artışı hacim artışıyla onaylanıyor mu?"""
        if len(df) < 21:
            return {"confirmed": False, "reason": "Yetersiz veri"}

        current_volume = df['Volume'].iloc[-1]
        avg_volume = df['Volume'].rolling(20).mean().iloc[-2]
        price_change = ((df['Close'].iloc[-1] / df['Close'].iloc[-2]) - 1) * 100

        if avg_volume == 0:
            return {"confirmed": False, "reason": "Hacim verisi yok"}

        volume_ratio = current_volume / avg_volume

        # Fiyat yükseliyorsa ve hacim ortalamanın üzerindeyse = para girişi var
        if price_change > 0 and volume_ratio > 1.2:
            confirmed = True
            desc = f"✅ Para girişi var: Hacim {volume_ratio:.1f}x ortalama, fiyat %{price_change:+.1f}"
        elif price_change > 0 and volume_ratio < 0.8:
            confirmed = False
            desc = f"❌ YALANCI YÜKSELİŞ: Fiyat %{price_change:+.1f} ama hacim düşük ({volume_ratio:.1f}x)"
        else:
            confirmed = price_change <= 0  # Düşüşte hacim kontrolü farklı
            desc = f"Hacim: {volume_ratio:.1f}x ortalama, fiyat %{price_change:+.1f}"

        return {
            "confirmed": confirmed,
            "volume_ratio": round(volume_ratio, 2),
            "price_change_pct": round(price_change, 2),
            "description": desc
        }

    def analyze_portfolio(self) -> list:
        """Portföydeki tüm hisseleri analiz eder"""
        portfolio_symbols = self.portfolio.get_portfolio_symbols()
        if not portfolio_symbols:
            return []

        results = []
        for symbol in portfolio_symbols:
            try:
                analysis = self.analyze_stock(symbol)
                if analysis["signal"]["action"] in ["SAT", "GÜÇLÜ SAT"]:
                    analysis["portfolio_alert"] = True
                    analysis["alert_type"] = "SELL_WARNING"
                    analysis["alert_message"] = f"⚠️ {symbol} portföyünüzde ve SAT sinyali veriyor!"
                elif analysis["signal"]["action"] == "ENGEL":
                    analysis["portfolio_alert"] = False
                else:
                    analysis["portfolio_alert"] = False
                results.append(analysis)
            except Exception as e:
                logger.error(f"Portföy analizi hatası ({symbol}): {e}")

        return results

    def scan_market(self, symbols: list = None, quick_mode: bool = False) -> dict:
        """Piyasayı tarar"""
        from config import BIST100_TICKERS
        if symbols is None:
            symbols = BIST100_TICKERS

        buy_signals = []
        sell_signals = []
        blocked_signals = []

        futures = {self.executor.submit(self.analyze_stock, symbol, skip_backtest=quick_mode, quick_mode=quick_mode): symbol for symbol in symbols}
        
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                analysis = future.result()
                action = analysis.get("signal", {}).get("action", "TUT")
                score = analysis.get("overall_score", 50)

                if action == "ENGEL":
                    blocked_signals.append({"symbol": symbol, "reason": analysis["signal"].get("reason")})
                elif action in ["AL", "GÜÇLÜ AL"] and score >= 65:
                    buy_signals.append({
                        "symbol": symbol, "score": score, "signal": action,
                        "price": analysis.get("current_price", 0),
                        "reason": analysis["signal"].get("reason", ""),
                        "checklist": analysis.get("checklist"),
                        "notification_allowed": analysis["signal"].get("notification_allowed", False),
                    })
                elif action in ["SAT", "GÜÇLÜ SAT"] and score <= 35:
                    sell_signals.append({
                        "symbol": symbol, "score": score, "signal": action,
                        "price": analysis.get("current_price", 0),
                        "reason": analysis["signal"].get("reason", ""),
                        "checklist": analysis.get("checklist"),
                        "notification_allowed": analysis["signal"].get("notification_allowed", False),
                    })
            except Exception as e:
                logger.error(f"Tarama hatası ({symbol}): {e}")

        buy_signals.sort(key=lambda x: x["score"], reverse=True)
        sell_signals.sort(key=lambda x: x["score"])

        return {
            "scan_time": datetime.now().isoformat(),
            "total_scanned": len(symbols),
            "buy_signals": buy_signals[:10],
            "sell_signals": sell_signals[:10],
            "blocked_count": len(blocked_signals),
            "blocked_signals": blocked_signals,
        }

    def _calculate_fundamental_score(self, symbol: str) -> float:
        """Temel analiz — F/K, PD/DD sektör kıyaslaması dahil"""
        try:
            info = self.data_collector.get_stock_info(symbol)
            if "error" in info:
                return 50

            score = 50
            pe = info.get("pe_ratio")
            if pe is not None and pe > 0:
                if pe < 8: score += 10
                elif pe < 15: score += 5
                elif pe > 30: score -= 10
                elif pe > 20: score -= 5

            pb = info.get("pb_ratio")
            if pb is not None and pb > 0:
                if pb < 1: score += 10
                elif pb < 2: score += 5
                elif pb > 5: score -= 10

            pm = info.get("profit_margin")
            if pm is not None:
                if pm > 0.2: score += 8
                elif pm > 0.1: score += 4
                elif pm < 0: score -= 10

            roe = info.get("roe")
            if roe is not None:
                if roe > 0.2: score += 8
                elif roe > 0.1: score += 4
                elif roe < 0: score -= 10

            div = info.get("dividend_yield")
            if div and div > 0:
                if div > 0.05: score += 5
                elif div > 0.03: score += 3

            de = info.get("debt_to_equity")
            if de is not None:
                if de < 50: score += 5
                elif de > 200: score -= 8

            return max(0, min(100, score))
        except Exception as e:
            logger.error(f"Temel analiz hatası: {e}")
            return 50

    def _generate_final_signal(self, overall_score, tech_score, news_score, ml_score,
                                checklist, market_bullish, sector_healthy) -> dict:
        """
        4'lü süzgeç kontrolü ile final sinyal üretir.
        Tüm kapılar EVET ise sinyal verilir.
        """
        # Ham sinyal belirle
        if overall_score >= 75:
            raw_action = "GÜÇLÜ AL"
        elif overall_score >= 60:
            raw_action = "AL"
        elif overall_score <= 25:
            raw_action = "GÜÇLÜ SAT"
        elif overall_score <= 40:
            raw_action = "SAT"
        else:
            raw_action = "TUT"

        # ====== 4'LÜ SÜZGEÇ ======
        news_ok = checklist.get("news_clean", True)
        money_ok = checklist.get("money_flowing_in", False)
        math_ok = checklist.get("math_confirms", False)
        social_ok = checklist.get("social_positive") is not False  # None = bilinmiyor = geçir

        checklist_result = {
            "haber_temiz_mi": "EVET ✅" if news_ok else "HAYIR ❌",
            "para_girisi_var_mi": "EVET ✅" if money_ok else "HAYIR ❌",
            "matematik_onayliyor_mu": "EVET ✅" if math_ok else "HAYIR ❌",
            "sosyal_medya_modu": "POZİTİF ✅" if social_ok else "NEGATİF ❌",
        }

        all_clear = news_ok and money_ok and math_ok and social_ok

        # AL sinyali kontrolleri
        if raw_action in ["AL", "GÜÇLÜ AL"]:
            # XU100 düşüş kontrolü uyarısı eklendi ama ENGEL kaldırıldı
            xu100_warning = " (⚠️ Piyasa Düşüş Trendinde)" if not market_bullish else ""
            sector_warning = " (⚠️ Sektör Düşüşte)" if not sector_healthy else ""
            
            # 4'lü süzgeç tam onay
            if all_clear:
                emoji = "🟢🟢" if raw_action == "GÜÇLÜ AL" else "🟢"
                return {
                    "action": raw_action,
                    "emoji": emoji,
                    "confidence": "Yüksek — 4/4 onay",
                    "reason": self._build_reason(tech_score, news_score, ml_score) + xu100_warning + sector_warning,
                    "checklist": checklist_result,
                    "all_clear": True,
                }
            else:
                # Süzgeçlerden geçemedi
                failed = [k for k, v in checklist_result.items() if "❌" in v]
                return {
                    "action": raw_action, # "AL" olarak kalsın ki arayüzde görünsün
                    "emoji": "🟡",
                    "confidence": f"Düşük — süzgeç başarısız ({len(failed)}/4)",
                    "reason": f"Skor {raw_action} diyor ama 4'lü Süzgeçte Fire Var: {', '.join(failed)}" + xu100_warning,
                    "checklist": checklist_result,
                    "all_clear": False,
                    "original_action": raw_action,
                }

        elif raw_action in ["SAT", "GÜÇLÜ SAT"]:
            emoji = "🔴🔴" if raw_action == "GÜÇLÜ SAT" else "🔴"
            return {
                "action": raw_action,
                "emoji": emoji,
                "confidence": "Yüksek" if overall_score <= 25 else "Orta",
                "reason": self._build_reason(tech_score, news_score, ml_score),
                "checklist": checklist_result,
                "all_clear": False,
            }

        else:
            return {
                "action": "TUT",
                "emoji": "🟡",
                "confidence": "Düşük",
                "reason": "Nötr pozisyon",
                "checklist": checklist_result,
                "all_clear": False,
            }

    def _build_reason(self, tech, news, ml) -> str:
        reasons = []
        if tech >= 65: reasons.append("Teknik olumlu")
        elif tech <= 35: reasons.append("Teknik olumsuz")
        if news >= 65: reasons.append("Haberler olumlu")
        elif news <= 35: reasons.append("Haberler olumsuz")
        if ml >= 65: reasons.append("ML: yükseliş")
        elif ml <= 35: reasons.append("ML: düşüş")
        return " | ".join(reasons) if reasons else "Nötr"

    def _generate_report(self, analysis: dict) -> str:
        """Detaylı rapor + 4'lü süzgeç çıktısı"""
        symbol = analysis["symbol"]
        signal = analysis["signal"]
        score = analysis.get("overall_score", 50)
        bt = analysis.get("backtest", {})
        cl = signal.get("checklist", analysis.get("checklist", {}))

        report = f"""
{'='*50}
📊 {symbol} ANALİZ RAPORU
{'='*50}
📅 {analysis['analyzed_at'][:16]}
💰 Fiyat: {analysis.get('current_price', 'N/A')} TL

🎯 SİNYAL: {signal['emoji']} {signal['action']}
📈 Skor: {score:.1f}/100
🎯 Güven: {signal.get('confidence', 'N/A')}
"""
        if not bt.get("skipped"):
            report += f"""
📋 BACKTEST:
  Doğruluk: %{bt.get('accuracy', 0):.1f} | Güven: %{bt.get('confidence_score', 0):.1f}
  Sinyal: {'✅' if bt.get('signal_allowed') else '❌'} | Bildirim: {'✅' if bt.get('notification_allowed') else '❌'}
"""
        if cl:
            report += f"""
🔍 4'LÜ SÜZGEÇ:
  📰 Haber Temiz mi?          {cl.get('haber_temiz_mi', 'N/A')}
  💰 Para Girişi Var mı?      {cl.get('para_girisi_var_mi', 'N/A')}
  📐 Matematik Onaylıyor mu?  {cl.get('matematik_onayliyor_mu', 'N/A')}
  📱 Sosyal Medya Modu?        {cl.get('sosyal_medya_modu', 'N/A')}
"""

        report += f"""
📊 SKORLAR:
  Teknik: {analysis.get('technical_score', 50):.1f} | Haber: {analysis.get('news_score', 50):.1f}
  ML: {analysis.get('ml_score', 50):.1f} | Temel: {analysis.get('fundamental_score', 50):.1f}
  Makro: {analysis.get('macro_score', 50):.1f} | Sosyal: {analysis.get('social_score', 50):.1f}

📝 {signal.get('reason', 'N/A')}
"""
        if signal.get("notification_blocked_reason"):
            report += f"\n🔇 {signal['notification_blocked_reason']}"
        if analysis.get("errors"):
            report += f"\n⚠️ {', '.join(analysis['errors'])}"

        return report
