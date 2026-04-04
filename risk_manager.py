"""
Risk Yönetimi Modülü

1. Trailing Stop-Loss: Zirveyi takip, %3 sarkma → ACİL SAT
2. FOMO Filtresi: Gün içi %7+ yükseliş → AL engeli
3. Guardian Mode: Portföydeki hisselerin 7/24 korunması
4. Bileşik Getiri Takibi: 200 TL → 100.000 TL hedef ilerlemesi
"""

import logging
import json
import os
from datetime import datetime
from data_collector import DataCollector
from portfolio import PortfolioManager

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_LOSS_FILE = os.path.join(BASE_DIR, "stop_loss_tracker.json")
GOAL_FILE = os.path.join(BASE_DIR, "goal_tracker.json")


class RiskManager:
    """Portföy risk yönetimi ve koruma sistemi"""

    def __init__(self, initial_capital: float = 200.0, target_capital: float = 100000.0):
        self.data_collector = DataCollector()
        self.portfolio = PortfolioManager()
        self.initial_capital = initial_capital
        self.target_capital = target_capital

        # Trailing stop parametreleri
        self.trailing_pct = 0.02   # %2 iz süren stop
        self.drop_alert_pct = 0.03 # %3 sarkma → ACİL SAT

        # FOMO filtresi
        self.fomo_threshold = 0.07  # %7+ günlük yükseliş → AL engeli

        # Zirve takibi
        self.peak_prices = self._load_stop_data()

    # ==================== TRAILING STOP-LOSS ====================

    def update_trailing_stops(self) -> list:
        """
        Portföydeki tüm hisseler için trailing stop günceller.
        Fiyat yeni zirve yaparsa stop seviyesini yükseltir.
        Zirveden %3 düşerse ACİL SAT sinyali verir.
        """
        alerts = []
        holdings = self.portfolio.get_portfolio()

        for holding in holdings:
            symbol = holding["symbol"]
            try:
                price_info = self.data_collector.get_current_price(symbol)
                if not price_info:
                    continue

                current_price = price_info["price"]

                # Zirve takibi
                peak_key = symbol
                prev_peak = self.peak_prices.get(peak_key, holding["avg_buy_price"])

                # Yeni zirve
                if current_price > prev_peak:
                    self.peak_prices[peak_key] = current_price
                    prev_peak = current_price
                    logger.debug(f"📈 {symbol} yeni zirve: {current_price:.2f} TL")

                # Trailing stop seviyesi
                stop_level = prev_peak * (1 - self.trailing_pct)

                # Zirveden düşüş oranı
                drop_from_peak = (prev_peak - current_price) / prev_peak

                if drop_from_peak >= self.drop_alert_pct:
                    # ACİL SAT UYARISI
                    alert = {
                        "type": "TRAILING_STOP",
                        "symbol": symbol,
                        "severity": "CRITICAL",
                        "current_price": round(current_price, 2),
                        "peak_price": round(prev_peak, 2),
                        "stop_level": round(stop_level, 2),
                        "drop_pct": round(drop_from_peak * 100, 2),
                        "quantity": holding["quantity"],
                        "message": (
                            f"🚨 ACİL SAT — {symbol}\n\n"
                            f"Zirve: {prev_peak:.2f} TL\n"
                            f"Şu an: {current_price:.2f} TL\n"
                            f"Düşüş: %{drop_from_peak*100:.1f}\n"
                            f"Stop: {stop_level:.2f} TL\n\n"
                            f"Trailing stop tetiklendi! HEMEN SAT!"
                        ),
                        "timestamp": datetime.now().isoformat()
                    }
                    alerts.append(alert)
                    logger.warning(f"🚨 TRAILING STOP: {symbol} — %{drop_from_peak*100:.1f} düşüş!")

                elif drop_from_peak >= self.trailing_pct:
                    # Uyarı seviyesi
                    alert = {
                        "type": "TRAILING_WARNING",
                        "symbol": symbol,
                        "severity": "WARNING",
                        "current_price": round(current_price, 2),
                        "peak_price": round(prev_peak, 2),
                        "stop_level": round(stop_level, 2),
                        "drop_pct": round(drop_from_peak * 100, 2),
                        "message": (
                            f"⚠️ DİKKAT — {symbol}\n"
                            f"Zirveden %{drop_from_peak*100:.1f} geriledi. "
                            f"Stop: {stop_level:.2f} TL"
                        ),
                        "timestamp": datetime.now().isoformat()
                    }
                    alerts.append(alert)

            except Exception as e:
                logger.error(f"{symbol} trailing stop hatası: {e}")

        # Zirve verilerini kaydet
        self._save_stop_data()

        return alerts

    # ==================== FOMO FİLTRESİ ====================

    def check_fomo(self, symbol: str) -> dict:
        """
        FOMO Filtresi: Hisse bugün %7'den fazla yükseldiyse AL sinyali ENGELLENİR.
        'Tepeden alma riski yüksek'
        """
        try:
            price_info = self.data_collector.get_current_price(symbol)
            if not price_info:
                return {"fomo_triggered": False, "reason": "Fiyat verisi yok"}

            daily_change = price_info.get("change_pct", 0) / 100  # yüzdeyi orana çevir

            if daily_change >= self.fomo_threshold:
                return {
                    "fomo_triggered": True,
                    "daily_change_pct": round(daily_change * 100, 2),
                    "threshold_pct": self.fomo_threshold * 100,
                    "blocked": True,
                    "reason": (
                        f"🚫 FOMO FİLTRESİ: {symbol} bugün %{daily_change*100:.1f} yükseldi. "
                        f"Tepeden alma riski yüksek! AL sinyali ENGELLENDİ."
                    ),
                    "message": (
                        f"⚠️ FOMO UYARISI — {symbol}\n\n"
                        f"Bugünkü yükseliş: %{daily_change*100:.1f}\n"
                        f"Eşik: %{self.fomo_threshold*100:.0f}\n\n"
                        f"Tepeden alma, risk çok yüksek!\n"
                        f"İşlem ENGELLENDİ."
                    )
                }
            else:
                return {
                    "fomo_triggered": False,
                    "daily_change_pct": round(daily_change * 100, 2),
                    "blocked": False,
                    "reason": "Günlük değişim normal aralıkta"
                }

        except Exception as e:
            logger.error(f"FOMO kontrol hatası ({symbol}): {e}")
            return {"fomo_triggered": False, "reason": str(e)}

    # ==================== GUARDIAN MODE ====================

    def guardian_check(self) -> list:
        """
        Guardian Mode: Portföydeki tüm hisseleri kontrol eder.
        Riskli durumlar:
        - Trailing stop tetiklenmiş
        - Negatif haber düşmüş
        - Sektör çöküşte
        - Hacim anormalliği
        """
        from macro_analyzer import MacroAnalyzer
        from news_analyzer import NewsAnalyzer

        macro = MacroAnalyzer()
        news_analyzer = NewsAnalyzer()
        alerts = []

        holdings = self.portfolio.get_portfolio()
        if not holdings:
            return []

        logger.info(f"🛡️ Guardian Mode: {len(holdings)} hisse kontrol ediliyor...")

        # 1. Trailing stop kontrolleri
        stop_alerts = self.update_trailing_stops()
        alerts.extend(stop_alerts)

        # 2. Her hisse için haber ve makro kontrol
        for holding in holdings:
            symbol = holding["symbol"]
            try:
                # Negatif haber kontrolü
                news_score = news_analyzer.calculate_news_score(symbol)
                if news_score.get("score", 50) < 30:
                    alerts.append({
                        "type": "NEGATIVE_NEWS",
                        "symbol": symbol,
                        "severity": "HIGH",
                        "news_score": news_score["score"],
                        "message": (
                            f"📰 NEGATİF HABER — {symbol}\n\n"
                            f"Haber skoru: {news_score['score']:.0f}/100\n"
                            f"{news_score.get('description', '')}\n\n"
                            f"Nakde geçmeyi düşünün!"
                        ),
                        "timestamp": datetime.now().isoformat()
                    })

                # Sektör kontrolü
                sector = macro.check_sector_health(symbol)
                if not sector.get("healthy"):
                    alerts.append({
                        "type": "SECTOR_CRASH",
                        "symbol": symbol,
                        "severity": "HIGH",
                        "message": (
                            f"📉 SEKTÖR DÜŞÜŞTE — {symbol}\n\n"
                            f"{sector.get('description', '')}\n"
                            f"Dikkatli olun!"
                        ),
                        "timestamp": datetime.now().isoformat()
                    })

            except Exception as e:
                logger.error(f"Guardian kontrol hatası ({symbol}): {e}")

        if alerts:
            logger.warning(f"🚨 Guardian Mode: {len(alerts)} uyarı tespit edildi!")
        else:
            logger.info("🛡️ Guardian Mode: Tüm hisseler güvende ✅")

        return alerts

    # ==================== BİLEŞİK GETİRİ TAKİBİ ====================

    def get_goal_progress(self) -> dict:
        """
        200 TL → 100.000 TL hedef takibi.
        Bileşik getiri hesaplaması ve kalan süre tahmini.
        """
        try:
            # Portföy değeri
            holdings = self.portfolio.get_portfolio()
            prices = {}
            for h in holdings:
                p = self.data_collector.get_current_price(h["symbol"])
                if p:
                    prices[h["symbol"]] = p["price"]

            portfolio_value = self.portfolio.get_portfolio_value(prices)
            current_value = portfolio_value.get("total_value", 0) + self._get_cash_balance()

            if current_value <= 0:
                current_value = self.initial_capital

            # İlerleme
            progress_pct = (current_value / self.target_capital) * 100
            remaining = self.target_capital - current_value
            growth_so_far = ((current_value / self.initial_capital) - 1) * 100

            # İşlem geçmişinden günlük ortalama getiri hesapla
            transactions = self.portfolio.get_transactions(limit=100)
            total_profit = sum(t.get("profit_loss", 0) for t in transactions)
            
            if transactions:
                first_tx = transactions[-1].get("date", "")
                if first_tx:
                    try:
                        start_date = datetime.fromisoformat(first_tx)
                        days_active = max(1, (datetime.now() - start_date).days)
                        daily_return_pct = (growth_so_far / days_active) if growth_so_far > 0 else 0
                    except:
                        days_active = 1
                        daily_return_pct = 0
                else:
                    days_active = 1
                    daily_return_pct = 0
            else:
                days_active = 0
                daily_return_pct = 0

            # Hedefe kaç gün kaldı (mevcut hızla)
            if daily_return_pct > 0 and current_value > 0:
                import math
                # Bileşik büyüme formülü: target = current * (1 + r)^n → n = log(target/current) / log(1+r)
                daily_rate = daily_return_pct / 100
                if daily_rate > 0:
                    days_remaining = math.log(self.target_capital / current_value) / math.log(1 + daily_rate)
                    days_remaining = int(days_remaining)
                else:
                    days_remaining = None
            else:
                days_remaining = None

            result = {
                "initial_capital": self.initial_capital,
                "target_capital": self.target_capital,
                "current_value": round(current_value, 2),
                "progress_pct": round(progress_pct, 4),
                "remaining": round(remaining, 2),
                "total_growth_pct": round(growth_so_far, 2),
                "total_profit": round(total_profit, 2),
                "days_active": days_active,
                "daily_return_pct": round(daily_return_pct, 4),
                "estimated_days_to_goal": days_remaining,
                "on_track": daily_return_pct > 0,
                "last_updated": datetime.now().isoformat()
            }

            # Kaydet
            self._save_goal_data(result)

            return result

        except Exception as e:
            logger.error(f"Hedef takip hatası: {e}")
            return {
                "initial_capital": self.initial_capital,
                "target_capital": self.target_capital,
                "error": str(e)
            }

    def format_goal_message(self) -> str:
        """Hedef ilerlemesini WhatsApp/Telegram mesajı olarak formatlar"""
        goal = self.get_goal_progress()

        progress_bar = self._make_progress_bar(goal.get("progress_pct", 0))

        msg = (
            f"🎯 HEDEF TAKİBİ\n\n"
            f"Başlangıç: {goal['initial_capital']:,.0f} TL\n"
            f"Şu an: {goal.get('current_value', 0):,.2f} TL\n"
            f"Hedef: {goal['target_capital']:,.0f} TL\n\n"
            f"{progress_bar}\n"
            f"İlerleme: %{goal.get('progress_pct', 0):.2f}\n"
            f"Büyüme: %{goal.get('total_growth_pct', 0):+.1f}\n\n"
        )

        if goal.get("estimated_days_to_goal"):
            msg += f"⏰ Tahmini hedefe ulaşma: {goal['estimated_days_to_goal']} gün\n"
        else:
            msg += f"⏰ Henüz yeterli veri yok\n"

        msg += f"\n📅 Aktif gün: {goal.get('days_active', 0)}"

        return msg

    def format_signal_message(self, symbol: str, analysis: dict) -> str:
        """WhatsApp bildirim formatı — kullanıcının istediği şekilde"""
        signal = analysis.get("signal", {})
        score = analysis.get("overall_score", 0)
        price = analysis.get("current_price", 0)
        checklist = signal.get("checklist", {})
        confidence = signal.get("confidence_score", 0)

        # Hedef fiyat tahmini (teknik analiz + ATR bazlı)
        tech = analysis.get("technical_analysis", {})
        atr = tech.get("atr", {}).get("atr", 0)
        fib = tech.get("fibonacci", {})
        resistance = fib.get("nearest_resistance", {}).get("price", price * 1.05) if fib.get("nearest_resistance") else price * 1.05
        support = fib.get("nearest_support", {}).get("price", price * 0.95) if fib.get("nearest_support") else price * 0.95

        # Stop-loss seviyesi (ATR bazlı veya %3)
        stop_loss = max(price - (atr * 2 if atr > 0 else price * 0.03), support)
        target_price = resistance

        expected_profit = ((target_price / price) - 1) * 100
        risk_reward = abs(expected_profit / ((price - stop_loss) / price * 100)) if stop_loss < price else 0

        # Neden?
        reasons = []
        if checklist.get("haber_temiz_mi", "").startswith("EVET"):
            reasons.append("Haber ✅")
        if checklist.get("para_girisi_var_mi", "").startswith("EVET"):
            reasons.append("Hacim ✅")
        if checklist.get("matematik_onayliyor_mu", "").startswith("EVET"):
            reasons.append("RSI/MACD ✅")
        if checklist.get("sosyal_medya_modu", "").startswith("POZİTİF"):
            reasons.append("Sosyal ✅")

        action = signal.get("action", "TUT")
        if "AL" in action:
            emoji = "🚀"
            label = "FIRSAT"
        elif "SAT" in action:
            emoji = "🔴"
            label = "SAT"
        else:
            emoji = "🟡"
            label = "BİLGİ"

        msg = (
            f"{emoji} {label}: {symbol}\n\n"
            f"📊 Güven Skoru: %{confidence:.1f}\n"
            f"💰 Fiyat: {price:.2f} TL\n"
            f"🎯 Hedef: {target_price:.2f} TL (+%{expected_profit:.1f})\n"
            f"🛑 Stop: {stop_loss:.2f} TL\n"
            f"⚖️ Risk/Ödül: 1:{risk_reward:.1f}\n\n"
            f"🔎 Neden? {' | '.join(reasons)}\n\n"
            f"📋 4'lü Süzgeç:\n"
        )
        for key, val in checklist.items():
            msg += f"  {val}\n"

        return msg

    def _get_cash_balance(self) -> float:
        """Nakit bakiye (basit hesaplama)"""
        transactions = self.portfolio.get_transactions(limit=500)
        cash = self.initial_capital
        for t in transactions:
            if t["action"] == "AL":
                cash -= t["total_value"]
            elif t["action"] == "SAT":
                cash += t["total_value"]
        return max(0, cash)

    def _make_progress_bar(self, pct: float) -> str:
        """Görsel ilerleme çubuğu"""
        filled = int(min(pct, 100) / 5)
        empty = 20 - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] %{pct:.2f}"

    def _load_stop_data(self) -> dict:
        try:
            if os.path.exists(STOP_LOSS_FILE):
                with open(STOP_LOSS_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_stop_data(self):
        try:
            with open(STOP_LOSS_FILE, 'w') as f:
                json.dump(self.peak_prices, f, indent=2)
        except Exception as e:
            logger.error(f"Stop data kaydetme hatası: {e}")

    def _save_goal_data(self, data: dict):
        try:
            with open(GOAL_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Hedef verisi kaydetme hatası: {e}")
