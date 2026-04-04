"""
Telegram Bot Modülü — Profesyonel Bildirim Şablonları
AL/SAT sinyalleri, portföy komutları, hedef takibi
"""

import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "200"))
TARGET_CAPITAL = float(os.getenv("TARGET_CAPITAL", "100000"))


class TelegramNotifier:
    """Telegram üzerinden profesyonel bildirim gönderici"""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.bot = None
        self._initialized = False

    async def _ensure_initialized(self):
        if not self._initialized and self.token and self.token != "your_bot_token_here":
            try:
                from telegram import Bot
                self.bot = Bot(token=self.token)
                self._initialized = True
                logger.info("Telegram bot bağlantısı kuruldu")
            except ImportError:
                logger.warning("python-telegram-bot yüklü değil.")
            except Exception as e:
                logger.error(f"Telegram bot başlatma hatası: {e}")

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        await self._ensure_initialized()

        if not self.bot:
            logger.warning("Telegram bot yapılandırılmamış.")
            logger.info(f"[TELEGRAM]: {text}")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
            logger.info(f"Telegram mesajı gönderildi ({len(text)} karakter)")
            return True
        except Exception as e:
            logger.error(f"Telegram mesaj hatası: {e}")
            # Markdown hata verirse düz gönder
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text
                )
                return True
            except:
                return False

    def send_message_sync(self, text: str) -> bool:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send_message(text))
                return True
            else:
                return loop.run_until_complete(self.send_message(text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.send_message(text))

    # ==================== AL SİNYALİ ====================
    async def send_buy_signal(self, symbol: str, price: float, score: float,
                               reason: str, risk_level: str = "ORTA",
                               target_price: float = None, stop_price: float = None,
                               technical_summary: str = None, volume_status: str = None,
                               social_score: float = None) -> bool:
        """
        Profesyonel AL sinyali şablonu
        """
        # Hedef ve stop hesapla (verilmediyse otomatik)
        if not target_price:
            target_price = price * 1.05  # %5 kâr hedefi
        if not stop_price:
            stop_price = price * 0.97   # %3 zarar kes

        tech_text = technical_summary or "RSI & EMA onaylı"
        vol_text = volume_status or "Ortalama üzeri hacim"
        social = social_score or 50

        message = f"""🚀 *#{symbol} \\- GÜÇLÜ AL SİNYALİ*

📊 Güven Skoru: *%{score:.0f}* (AI Onayı)
🛡️ Risk Oranı: {risk_level}
💰 Giriş Fiyatı: *{price:.2f} TL*
🎯 Kâr Hedefi: {target_price:.2f} TL
🛑 Zarar Kes (Stop): {stop_price:.2f} TL

🧠 *Analiz Özeti:*
• Teknik: {tech_text}
• Hacim: {vol_text}
• Duygu: Sosyal Medyada %{social:.0f} pozitif hava

🏦 Aksiyon: Yapı Kredi'den alımı yap, robot arayüzünden işlemi onayla!

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"""

        return await self.send_message(message)

    # ==================== SAT SİNYALİ ====================
    async def send_sell_signal(self, symbol: str, price: float, score: float,
                                reason: str, in_portfolio: bool = False,
                                buy_price: float = None,
                                current_capital: float = None) -> bool:
        """
        Profesyonel SAT sinyali şablonu
        """
        # Kâr/zarar hesapla
        pnl_text = ""
        if buy_price and buy_price > 0:
            pnl_pct = ((price - buy_price) / buy_price) * 100
            pnl_text = f"\n📈 Gerçekleşen Kâr/Zarar: *%{pnl_pct:+.1f}*"

        # Hedef takibi
        capital = current_capital or INITIAL_CAPITAL
        progress = (capital / TARGET_CAPITAL) * 100

        portfolio_tag = "\n⚠️ *DİKKAT: Bu hisse portföyünde!*" if in_portfolio else ""

        message = f"""⚠️ *#{symbol} \\- ACİL SAT SİNYALİ*

💰 Satış Fiyatı: *{price:.2f} TL*
📉 Neden: {reason}{pnl_text}{portfolio_tag}

🏁 *HEDEF TAKİBİ:*
200 TL ➜ 100.000 TL yolunda *%{progress:.1f}* tamamlandı!
Nakit gücünü koru, yeni sinyali bekle.

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"""

        return await self.send_message(message)

    # ==================== PORTFÖY ÖZETİ ====================
    async def send_portfolio_summary(self, portfolio_data: dict) -> bool:
        if not portfolio_data.get("holdings"):
            return await self.send_message("📭 Portföyünüz boş.")

        holdings_text = ""
        for h in portfolio_data["holdings"]:
            emoji = "🟢" if h.get("profit_pct", 0) >= 0 else "🔴"
            holdings_text += f"  {emoji} *{h['symbol']}*: {h['quantity']} adet @ {h.get('current_price', 0):.2f} TL ({h.get('profit_pct', 0):+.1f}%)\n"

        profit_emoji = "📈" if portfolio_data.get("total_profit_loss", 0) > 0 else "📉"
        total_value = portfolio_data.get('total_value', 0)
        progress = (total_value / TARGET_CAPITAL) * 100

        message = f"""💼 *PORTFÖY ÖZETİ*

{holdings_text}
━━━━━━━━━━━━━━━━━━━━
💰 Toplam Maliyet: {portfolio_data.get('total_cost', 0):,.2f} TL
💎 Güncel Değer: *{total_value:,.2f} TL*
{profit_emoji} Kâr/Zarar: *{portfolio_data.get('total_profit_loss', 0):+,.2f} TL* ({portfolio_data.get('total_profit_pct', 0):+.1f}%)

🏁 Hedef: %{progress:.1f} tamamlandı

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"""

        return await self.send_message(message)

    # ==================== PİYASA TARAMASI ====================
    async def send_market_scan_results(self, scan_results: dict) -> bool:
        buy_text = ""
        for s in scan_results.get("buy_signals", [])[:5]:
            buy_text += f"  🟢 *{s['symbol']}*: {s['price']:.2f} TL (Skor: {s['score']:.0f})\n"

        sell_text = ""
        for s in scan_results.get("sell_signals", [])[:5]:
            sell_text += f"  🔴 *{s['symbol']}*: {s['price']:.2f} TL (Skor: {s['score']:.0f})\n"

        message = f"""🔍 *PİYASA TARAMASI*

📊 Taranan: {scan_results.get('total_scanned', 0)} hisse
🚫 Engellenen: {scan_results.get('blocked_count', 0)}

🟢 *AL Sinyalleri:*
{buy_text or '  Yok'}
🔴 *SAT Sinyalleri:*
{sell_text or '  Yok'}

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"""

        return await self.send_message(message)

    # ==================== GÜNLÜK RAPOR ====================
    async def send_daily_report(self, portfolio_analysis: list, market_scan: dict) -> bool:
        alerts = [a for a in portfolio_analysis if a.get("portfolio_alert")]

        alert_text = ""
        if alerts:
            for a in alerts:
                alert_text += f"  ⚠️ *{a['symbol']}*: {a['signal']['action']} (Skor: {a['overall_score']:.0f})\n"

        buy_opps = market_scan.get("buy_signals", [])[:3]
        opp_text = ""
        for o in buy_opps:
            opp_text += f"  🟢 *{o['symbol']}*: {o['price']:.2f} TL (Skor: {o['score']:.0f})\n"

        message = f"""📋 *GÜNLÜK RAPOR*
📅 {datetime.now().strftime('%d.%m.%Y')}

{'⚠️ *PORTFÖY UYARILARI:*' + chr(10) + alert_text if alert_text else '✅ Portföyde uyarı yok.'}

🎯 *EN İYİ FIRSATLAR:*
{opp_text or '  Bugün güçlü fırsat bulunamadı.'}

_Detaylar için app.py'ı çalıştırın._"""

        return await self.send_message(message)

    # ==================== OLAY BİLDİRİMİ ====================
    async def send_event_alert(self, event: dict) -> bool:
        etype = event.get("type", "?")
        symbol = event.get("symbol", "?")
        price = event.get("price", 0)
        desc = event.get("description", "")

        message = f"""🚨 *KRİTİK OLAY TESPİT EDİLDİ*

📊 *{symbol}* \\- {etype}
💰 Fiyat: {price:.2f} TL
📝 {desc}

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"""

        return await self.send_message(message)


class TelegramBotHandler:
    """Telegram bot komutlarını işleyen sınıf"""

    def __init__(self):
        self.notifier = TelegramNotifier()

    async def start_bot(self):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
            logger.warning("Telegram bot token ayarlanmamış.")
            return

        try:
            from telegram.ext import Application, CommandHandler, MessageHandler, filters

            app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

            app.add_handler(CommandHandler("start", self._cmd_start))
            app.add_handler(CommandHandler("portfoy", self._cmd_portfolio))
            app.add_handler(CommandHandler("analiz", self._cmd_analyze))
            app.add_handler(CommandHandler("ekle", self._cmd_add_stock))
            app.add_handler(CommandHandler("cikar", self._cmd_remove_stock))
            app.add_handler(CommandHandler("sinyaller", self._cmd_signals))
            app.add_handler(CommandHandler("tara", self._cmd_scan))
            app.add_handler(CommandHandler("yardim", self._cmd_help))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))

            logger.info("Telegram bot başlatılıyor...")
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            logger.info("✅ Telegram bot aktif")

        except ImportError:
            logger.warning("python-telegram-bot yüklü değil.")
        except Exception as e:
            logger.error(f"Telegram bot başlatma hatası: {e}")

    async def _cmd_start(self, update, context):
        welcome = """🤖 *BIST 100 Borsa Robotu*

Merhaba! Ben borsa analizlerinizi yapacak ve AL/SAT sinyalleri gönderecek botunuzum.

*Komutlar:*
/portfoy \\- Portföyünüzü görün
/analiz THYAO \\- Hisse analiz edin
/ekle THYAO 100 45.50 \\- Hisse ekleyin
/cikar THYAO 100 55.00 \\- Hisse çıkarın
/sinyaller \\- Son sinyaller
/tara \\- Piyasa taraması
/yardim \\- Yardım

📊 Analiz her 15 dakikada bir otomatik çalışır."""
        await update.message.reply_text(welcome, parse_mode="Markdown")

    async def _cmd_portfolio(self, update, context):
        from portfolio import PortfolioManager
        from data_collector import DataCollector

        pm = PortfolioManager()
        dc = DataCollector()

        holdings = pm.get_portfolio()
        if not holdings:
            await update.message.reply_text("📭 Portföyünüz boş. /ekle ile hisse ekleyin.")
            return

        prices = {}
        for h in holdings:
            price_info = dc.get_current_price(h["symbol"])
            if price_info:
                prices[h["symbol"]] = price_info["price"]

        portfolio_value = pm.get_portfolio_value(prices)
        await self.notifier.send_portfolio_summary(portfolio_value)

    async def _cmd_analyze(self, update, context):
        if not context.args:
            await update.message.reply_text("❌ Kullanım: /analiz THYAO")
            return

        symbol = context.args[0].upper()
        await update.message.reply_text(f"🔍 {symbol} analiz ediliyor...")

        from signal_generator import SignalGenerator
        sg = SignalGenerator()
        result = sg.analyze_stock(symbol)

        signal = result.get("signal", {})
        action = signal.get("action", "TUT")
        score = result.get("overall_score", 50)
        price = result.get("current_price", 0)
        reason = signal.get("reason", "")

        if "AL" in action:
            await self.notifier.send_buy_signal(
                symbol, price, score, reason,
                technical_summary=f"Teknik skor: {result.get('technical_score', 50):.0f}",
                volume_status=f"Hacim skoru: {result.get('fundamental_score', 50):.0f}",
                social_score=result.get("social_score", 50)
            )
        elif "SAT" in action:
            await self.notifier.send_sell_signal(symbol, price, score, reason)
        else:
            checklist = signal.get("checklist", {})
            cl_text = "\n".join([f"• {k}: {v}" for k, v in checklist.items()]) if checklist else ""

            msg = f"""📊 *{symbol} ANALİZ SONUCU*

📈 Skor: *{score:.0f}/100*
💰 Fiyat: {price:.2f} TL
🎯 Karar: *{action}*

🔍 *4'lü Süzgeç:*
{cl_text}

📝 {reason}"""
            await self.notifier.send_message(msg)

    async def _cmd_add_stock(self, update, context):
        if len(context.args) < 3:
            await update.message.reply_text("❌ Kullanım: /ekle THYAO 100 45.50")
            return
        try:
            symbol = context.args[0].upper()
            quantity = float(context.args[1])
            price = float(context.args[2])
            from portfolio import PortfolioManager
            pm = PortfolioManager()
            result = pm.add_stock(symbol, quantity, price)
            await update.message.reply_text(f"✅ {symbol} portföye eklendi ({quantity} adet @ {price:.2f} TL)")
        except ValueError:
            await update.message.reply_text("❌ Geçersiz miktar veya fiyat")

    async def _cmd_remove_stock(self, update, context):
        if len(context.args) < 3:
            await update.message.reply_text("❌ Kullanım: /cikar THYAO 100 55.00")
            return
        try:
            symbol = context.args[0].upper()
            quantity = float(context.args[1])
            price = float(context.args[2])
            from portfolio import PortfolioManager
            pm = PortfolioManager()
            result = pm.sell_stock(symbol, quantity, price)
            await update.message.reply_text(f"✅ {symbol} satıldı ({quantity} adet @ {price:.2f} TL)")
        except ValueError:
            await update.message.reply_text("❌ Geçersiz miktar veya fiyat")

    async def _cmd_signals(self, update, context):
        from portfolio import PortfolioManager
        pm = PortfolioManager()
        signals = pm.get_signals(limit=10)
        if not signals:
            await update.message.reply_text("📭 Henüz sinyal yok.")
            return

        text = "📊 *Son Sinyaller:*\n\n"
        for s in signals:
            emoji = "🟢" if "AL" in s["signal_type"] else ("🔴" if "SAT" in s["signal_type"] else "🟡")
            text += f"{emoji} *{s['symbol']}*: {s['signal_type']} (Skor: {s['score']:.0f}) \\- {s['date'][:16]}\n"
        await self.notifier.send_message(text)

    async def _cmd_scan(self, update, context):
        await update.message.reply_text("🔍 Piyasa taranıyor... Bu biraz sürebilir.")
        from signal_generator import SignalGenerator
        sg = SignalGenerator()
        quick_symbols = ["THYAO", "GARAN", "AKBNK", "EREGL", "SISE", "BIMAS", "ASELS",
                         "TCELL", "TUPRS", "SAHOL", "KCHOL", "FROTO", "TOASO", "PGSUS"]
        results = sg.scan_market(quick_symbols)
        await self.notifier.send_market_scan_results(results)

    async def _cmd_help(self, update, context):
        await self._cmd_start(update, context)

    async def _handle_text(self, update, context):
        text = update.message.text.upper().strip()
        from config import BIST100_TICKERS
        if text in BIST100_TICKERS:
            context.args = [text]
            await self._cmd_analyze(update, context)
        else:
            await update.message.reply_text(
                "❓ Anlamadım. /yardim yazarak komutları görebilirsiniz.\n"
                "Hisse analizi için doğrudan hisse kodunu yazın (örn: THYAO)"
            )
