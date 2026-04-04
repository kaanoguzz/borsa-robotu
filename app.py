"""
BIST 100 Borsa Robotu — Masaüstü Arayüzü (CustomTkinter)

Tek dosya, hemen çalıştırılabilir: python app.py

Bölümler:
  1. Dashboard (bakiye, hedef progress bar, XU100 grafik)
  2. Canlı Sinyal Akışı (AL/SAT + güven + neden)
  3. Portföy Takibi (canlı kâr/zarar)
  4. İşlem Butonları (Hisse Ekle / Çıkar)
  5. WhatsApp Kontrol Anahtarı
"""

# ===== SSL Sertifika Fix (Windows Türkçe Kullanıcı Adı) =====
import os
import ssl
import shutil

try:
    import certifi
    _original_cert = certifi.where()
    _safe_cert = os.path.join(os.environ.get('TEMP', '.'), 'cacert.pem')
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
# ============================================================

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import traceback
import json
import sys
from datetime import datetime

# ===== CustomTkinter Tema =====
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ===== Renkler =====
COLORS = {
    "bg_dark": "#0B0F19",
    "bg_card": "#141B2D",
    "bg_card_alt": "#1A2238",
    "bg_input": "#0D1225",
    "border": "#1E2A45",
    "accent_green": "#00E676",
    "accent_red": "#FF1744",
    "accent_blue": "#448AFF",
    "accent_purple": "#7C4DFF",
    "accent_cyan": "#00E5FF",
    "accent_yellow": "#FFD600",
    "text_primary": "#E8ECF4",
    "text_secondary": "#8892A8",
    "text_muted": "#5A6480",
    "gradient_start": "#667EEA",
    "gradient_end": "#764BA2",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class BorsaRobotuApp(ctk.CTk):
    """Ana uygulama penceresi"""

    def __init__(self):
        super().__init__()

        # Pencere ayarları
        self.title("🤖 BIST 100 Borsa Robotu")
        self.geometry("1280x820")
        self.minsize(1024, 700)
        self.configure(fg_color=COLORS["bg_dark"])

        # State
        self.initial_capital = 200.0
        self.target_capital = 100000.0
        self.whatsapp_enabled = tk.BooleanVar(value=True)
        self.portfolio_data = []
        self.signals_data = []

        # Lazy imports (modüller yüklenmeden arayüz açılır)
        self._modules_loaded = False
        self._sg = None
        self._portfolio = None
        self._risk = None
        self._data_collector = None
        self._event_detector = None

        # UI Oluştur
        self._build_ui()

        # Arka planda modülleri yükle
        threading.Thread(target=self._load_modules, daemon=True).start()

        # Periyodik güncelleme
        self.after(2000, self._periodic_update)

    # ================ MODÜLLERİ YÜKLE ================

    def _load_modules(self):
        """Modülleri arka planda yükle"""
        try:
            self._update_status("⏳ Modüller yükleniyor...")
            from signal_generator import SignalGenerator
            from portfolio import PortfolioManager
            from risk_manager import RiskManager
            from data_collector import DataCollector
            from event_detector import EventDetector

            self._sg = SignalGenerator()
            self._portfolio = PortfolioManager()
            self._risk = RiskManager(self.initial_capital, self.target_capital)
            self._data_collector = DataCollector()
            self._event_detector = EventDetector()
            self._modules_loaded = True
            self._update_status("✅ Sistem Aktif")
            self.after(500, self._refresh_all)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"MODÜL HATASI: {e}\n{tb}")
            self._update_status(f"❌ Modül hatası: {e}")

    # ================ ANA ARAYÜZ ================

    def _build_ui(self):
        """Ana arayüzü oluştur"""
        # Ana grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ===== HEADER =====
        self._build_header()

        # ===== HEDEF PROGRESS BAR =====
        self._build_goal_bar()

        # ===== ANA İÇERİK =====
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(8, 16))
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=2)
        main_frame.grid_rowconfigure(0, weight=1)

        # Sol Panel (Dashboard + Sinyaller)
        left_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        self._build_stats_row(left_panel)
        self._build_signals_panel(left_panel)

        # Sağ Panel (Portföy + İşlemler)
        right_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        self._build_portfolio_panel(right_panel)

    # ===== HEADER =====
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=56, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # Logo + Başlık
        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=10)

        ctk.CTkLabel(logo_frame, text="🤖", font=("Segoe UI Emoji", 28)).pack(side="left", padx=(0, 10))
        title_frame = ctk.CTkFrame(logo_frame, fg_color="transparent")
        title_frame.pack(side="left")
        ctk.CTkLabel(title_frame, text="BIST 100 Borsa Robotu",
                     font=("Inter", 18, "bold"), text_color=COLORS["accent_blue"]).pack(anchor="w")
        ctk.CTkLabel(title_frame, text="4 Katman • Backtest • 4'lü Süzgeç • AI",
                     font=("Inter", 10), text_color=COLORS["text_muted"]).pack(anchor="w")

        # Sağ taraf
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.grid(row=0, column=2, padx=20, pady=10)

        # WhatsApp anahtar
        wp_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        wp_frame.pack(side="left", padx=(0, 20))
        ctk.CTkLabel(wp_frame, text="📱 WhatsApp", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(side="left", padx=(0, 6))
        ctk.CTkSwitch(wp_frame, variable=self.whatsapp_enabled,
                      onvalue=True, offvalue=False,
                      progress_color=COLORS["accent_green"],
                      button_color=COLORS["accent_blue"],
                      width=46, height=22).pack(side="left")

        # Durum göstergesi
        self.status_label = ctk.CTkLabel(right_frame, text="⏳ Başlatılıyor...",
                                          font=("Inter", 11), text_color=COLORS["accent_yellow"])
        self.status_label.pack(side="left", padx=(0, 16))

        # Saat
        self.clock_label = ctk.CTkLabel(right_frame, text="", font=("Inter", 12, "bold"),
                                         text_color=COLORS["text_secondary"])
        self.clock_label.pack(side="left")
        self._update_clock()

    # ===== HEDEF PROGRESS BAR =====
    def _build_goal_bar(self):
        bar_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"],
                                  corner_radius=10, height=60)
        bar_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 0))
        bar_frame.grid_columnconfigure(0, weight=1)

        # Info satırı
        info = ctk.CTkFrame(bar_frame, fg_color="transparent")
        info.pack(fill="x", padx=16, pady=(10, 4))

        ctk.CTkLabel(info, text="🎯 Hedef: 200 TL → 100.000 TL",
                     font=("Inter", 12, "bold"), text_color=COLORS["text_primary"]).pack(side="left")

        self.goal_label = ctk.CTkLabel(info, text="Şu an: 200,00 TL (%0.20)",
                                        font=("Inter", 11), text_color=COLORS["accent_cyan"])
        self.goal_label.pack(side="right")

        self.goal_eta = ctk.CTkLabel(info, text="",
                                      font=("Inter", 10), text_color=COLORS["text_muted"])
        self.goal_eta.pack(side="right", padx=(0, 16))

        # Progress bar
        self.goal_progress = ctk.CTkProgressBar(bar_frame, height=10,
                                                  corner_radius=5,
                                                  progress_color=COLORS["accent_purple"],
                                                  fg_color=COLORS["bg_input"])
        self.goal_progress.pack(fill="x", padx=16, pady=(0, 10))
        self.goal_progress.set(0.002)  # 200/100000

    # ===== STATS ROW =====
    def _build_stats_row(self, parent):
        stats = ctk.CTkFrame(parent, fg_color="transparent", height=90)
        stats.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1)

        # Stat kartları
        self.stat_balance = self._make_stat_card(stats, 0, "💰", "BAKİYE", "200,00 TL")
        self.stat_profit = self._make_stat_card(stats, 1, "📈", "KÂR/ZARAR", "0,00 TL")
        self.stat_signals = self._make_stat_card(stats, 2, "🎯", "SİNYAL", "0")
        self.stat_risk = self._make_stat_card(stats, 3, "🛡️", "RİSK", "—")

    def _make_stat_card(self, parent, col, emoji, label, value):
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=12)
        card.grid(row=0, column=col, sticky="nsew", padx=4)

        ctk.CTkLabel(card, text=emoji, font=("Segoe UI Emoji", 20)).pack(pady=(10, 2))
        val_label = ctk.CTkLabel(card, text=value, font=("Inter", 16, "bold"),
                                  text_color=COLORS["text_primary"])
        val_label.pack()
        ctk.CTkLabel(card, text=label, font=("Inter", 9),
                     text_color=COLORS["text_muted"]).pack(pady=(0, 10))
        return val_label

    # ===== SİNYAL PANELİ =====
    def _build_signals_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=12)
        card.grid(row=1, column=0, sticky="nsew", pady=(0, 0))
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        # Başlık satırı
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        ctk.CTkLabel(header, text="📊 Canlı Sinyal Akışı",
                     font=("Inter", 14, "bold")).pack(side="left")

        ctk.CTkButton(header, text="🔍 Tarama Başlat", width=130, height=30,
                      font=("Inter", 11), corner_radius=8,
                      fg_color=COLORS["accent_blue"],
                      hover_color="#2962FF",
                      command=self._start_scan).pack(side="right")

        # Analiz girişi
        analyze_frame = ctk.CTkFrame(card, fg_color="transparent")
        analyze_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        analyze_frame.grid_columnconfigure(0, weight=1)

        self.analyze_entry = ctk.CTkEntry(analyze_frame, placeholder_text="Hisse kodu (ör: THYAO)",
                                           height=36, corner_radius=8,
                                           fg_color=COLORS["bg_input"],
                                           border_color=COLORS["border"])
        self.analyze_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.analyze_entry.bind("<Return>", lambda e: self._analyze_stock())

        ctk.CTkButton(analyze_frame, text="Analiz Et", width=100, height=36,
                      font=("Inter", 11, "bold"), corner_radius=8,
                      fg_color=COLORS["gradient_start"],
                      hover_color=COLORS["gradient_end"],
                      command=self._analyze_stock).grid(row=0, column=1)

        # Sinyal listesi (scrollable)
        self.signals_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                                       corner_radius=0)
        self.signals_scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.signals_scroll.grid_columnconfigure(0, weight=1)

        self._signals_placeholder = ctk.CTkLabel(
            self.signals_scroll, text="Tarama başlatın veya hisse analiz edin",
            font=("Inter", 11), text_color=COLORS["text_muted"])
        self._signals_placeholder.grid(row=0, column=0, pady=40)

    # ===== PORTFÖY PANELİ =====
    def _build_portfolio_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=12)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        # Başlık
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        ctk.CTkLabel(header, text="💼 Portföy Takibi",
                     font=("Inter", 14, "bold")).pack(side="left")

        # Butonlar
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=8)

        ctk.CTkButton(btn_frame, text="➕ Hisse Ekle", width=120, height=32,
                      font=("Inter", 11), corner_radius=8,
                      fg_color=COLORS["accent_green"],
                      hover_color="#00C853",
                      text_color=COLORS["bg_dark"],
                      command=self._open_add_dialog).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="➖ Hisseyi Çıkar", width=120, height=32,
                      font=("Inter", 11), corner_radius=8,
                      fg_color=COLORS["accent_red"],
                      hover_color="#D50000",
                      command=self._open_remove_dialog).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="🔄", width=32, height=32,
                      font=("Inter", 11), corner_radius=8,
                      fg_color=COLORS["border"],
                      hover_color=COLORS["bg_card_alt"],
                      command=self._refresh_portfolio).pack(side="right")

        # Portföy listesi
        self.portfolio_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                                         corner_radius=0)
        self.portfolio_scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.portfolio_scroll.grid_columnconfigure(0, weight=1)

        self._portfolio_placeholder = ctk.CTkLabel(
            self.portfolio_scroll,
            text="Portföyünüz boş.\n'Hisse Ekle' ile başlayın.",
            font=("Inter", 11), text_color=COLORS["text_muted"], justify="center")
        self._portfolio_placeholder.grid(row=0, column=0, pady=40)

    # ================ EYLEMLER ================

    def _analyze_stock(self):
        """Hisse analizi başlat"""
        symbol = self.analyze_entry.get().strip().upper()
        if not symbol:
            return
        if not self._modules_loaded:
            self._update_status("⏳ Modüller henüz yüklenmedi...")
            return

        self._update_status(f"🔍 {symbol} analiz ediliyor...")
        self.analyze_entry.delete(0, "end")

        threading.Thread(target=self._run_analysis, args=(symbol,), daemon=True).start()

    def _run_analysis(self, symbol):
        """Arka planda analiz çalıştır"""
        try:
            result = self._sg.analyze_stock(symbol, skip_backtest=True)
            self.after(0, lambda: self._show_signal(result))
            self.after(0, lambda: self._update_status(f"✅ {symbol} analizi tamamlandı"))
        except Exception as e:
            self.after(0, lambda: self._update_status(f"❌ Analiz hatası: {e}"))

    def _start_scan(self):
        """Hızlı piyasa taraması — anında ayrı pencere açar, canlı günceller, Telegram atar"""
        if not self._modules_loaded:
            self._update_status("⏳ Modüller henüz yüklenmedi...")
            return

        self._update_status("🔍 BIST 100 taranıyor...")

        # ===== HEMEN PENCERE AÇ =====
        win = ctk.CTkToplevel(self)
        win.title("📊 BIST 100 Tarama Sonuçları")
        win.geometry("750x620")
        win.configure(fg_color=COLORS["bg_dark"])
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False))

        # Başlık
        header = ctk.CTkFrame(win, fg_color=COLORS["bg_card"], height=60, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="📊 BIST 100 Tarama Sonuçları",
                     font=("Inter", 18, "bold"), text_color=COLORS["accent_blue"]).pack(side="left", padx=20, pady=14)
        time_label = ctk.CTkLabel(header, text=datetime.now().strftime('%d.%m.%Y %H:%M'),
                     font=("Inter", 11), text_color=COLORS["text_muted"])
        time_label.pack(side="right", padx=20)

        # İlerleme çubuğu
        prog_frame = ctk.CTkFrame(win, fg_color=COLORS["bg_card"], corner_radius=10)
        prog_frame.pack(fill="x", padx=16, pady=(10, 4))
        prog_label = ctk.CTkLabel(prog_frame, text="⏳ Taranıyor... 0/100", font=("Inter", 12, "bold"),
                                  text_color=COLORS["accent_yellow"])
        prog_label.pack(side="left", padx=16, pady=10)
        prog_bar = ctk.CTkProgressBar(prog_frame, height=12, corner_radius=6,
                                       progress_color=COLORS["accent_purple"],
                                       fg_color=COLORS["bg_input"])
        prog_bar.pack(side="right", fill="x", expand=True, padx=16, pady=10)
        prog_bar.set(0)

        # Scrollable içerik
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=8)
        scroll.grid_columnconfigure(0, weight=1)

        # Kapat butonu
        close_btn = ctk.CTkButton(win, text="Kapat", width=160, height=38,
                      font=("Inter", 12, "bold"), corner_radius=8,
                      fg_color=COLORS["border"], hover_color=COLORS["bg_card_alt"],
                      command=win.destroy)
        close_btn.pack(pady=(4, 16))

        # ===== ARKA PLANDA TARA =====
        def run_scan():
            from config import BIST100_TICKERS
            top_stocks = BIST100_TICKERS  # Tam 100 hisse
            total_count = len(top_stocks)
            all_results = []
            row_idx = [0]  # mutable ref

            # İlerleme label'ını güncelle
            self.after(0, lambda: prog_label.configure(text=f"⏳ Taranıyor... 0/{total_count}"))

            for i, symbol in enumerate(top_stocks):
                try:
                    # İlerleme güncelle
                    self.after(0, lambda s=symbol, n=i: (
                        prog_label.configure(text=f"⏳ {s} analiz ediliyor... {n+1}/{len(top_stocks)}"),
                        prog_bar.set((n + 0.5) / len(top_stocks)),
                        self._update_status(f"🔍 {s} analiz ediliyor ({n+1}/{len(top_stocks)})...")
                    ))

                    result = self._sg.analyze_stock(symbol, skip_backtest=True, quick_mode=True)
                    if not result:
                        continue

                    signal = result.get("signal", {})
                    action = signal.get("action", "TUT")
                    score = result.get("overall_score", 50)
                    price = result.get("current_price", 0)
                    reason = signal.get("reason", "")

                    all_results.append({
                        "symbol": symbol, "action": action, "score": score,
                        "price": price, "reason": reason
                    })

                    # Renge göre kart oluştur
                    if "AL" in action:
                        bg_color = "#0D2818"
                        action_color = COLORS["accent_green"]
                    elif "SAT" in action:
                        bg_color = "#2D0A0A"
                        action_color = COLORS["accent_red"]
                    elif action == "ENGEL":
                        bg_color = COLORS["bg_input"]
                        action_color = COLORS["text_muted"]
                    else:
                        bg_color = "#2D2800"
                        action_color = COLORS["accent_yellow"]

                    # Sonucu anında ekrana ekle
                    def add_card(sym=symbol, act=action, sc=score, pr=price, rsn=reason,
                                 bgc=bg_color, ac=action_color, idx=row_idx[0]):
                        card = ctk.CTkFrame(scroll, fg_color=bgc, corner_radius=10)
                        card.grid(row=idx, column=0, sticky="ew", pady=3)

                        top_row = ctk.CTkFrame(card, fg_color="transparent")
                        top_row.pack(fill="x", padx=14, pady=(10, 2))

                        ctk.CTkLabel(top_row, text=sym, font=("Inter", 15, "bold"),
                                     text_color=COLORS["text_primary"]).pack(side="left")
                        ctk.CTkLabel(top_row, text=act, font=("Inter", 12, "bold"),
                                     text_color=ac).pack(side="left", padx=10)
                        ctk.CTkLabel(top_row, text=f"Skor: {sc:.0f}", font=("Inter", 11),
                                     text_color=COLORS["text_secondary"]).pack(side="left", padx=6)
                        if pr:
                            ctk.CTkLabel(top_row, text=f"{pr:.2f} TL", font=("Inter", 11),
                                         text_color=COLORS["accent_cyan"]).pack(side="right")

                        if rsn:
                            ctk.CTkLabel(card, text=rsn[:80], font=("Inter", 9),
                                         text_color=COLORS["text_muted"], wraplength=680,
                                         anchor="w", justify="left").pack(fill="x", padx=14, pady=(0, 8))

                    self.after(0, add_card)
                    row_idx[0] += 1

                    # İlerleme güncelle
                    self.after(0, lambda n=i: prog_bar.set((n + 1) / len(top_stocks)))

                except Exception as e:
                    print(f"Hata ({symbol}): {e}")

            # ===== TARAMA BİTTİ =====
            buy_results = [r for r in all_results if "AL" in r["action"]]
            sell_results = [r for r in all_results if "SAT" in r["action"]]

            # Telegram bildirimi gönder
            if buy_results:
                try:
                    from notifier import Notifier
                    notifier = Notifier()
                    for s in buy_results:
                        msg = (
                            f"🚀 <b>#{s['symbol']} - {s['action']}</b>\n\n"
                            f"📊 <b>Skor:</b> {s['score']:.0f}/100\n"
                            f"💰 <b>Fiyat:</b> {s['price']:.2f} TL\n"
                            f"📝 <b>Neden:</b> {s['reason']}\n"
                            f"\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                        )
                        notifier.send_message(msg)
                except Exception as te:
                    print(f"Telegram hatası: {te}")

            def finalize():
                # İlerleme çubuğunu güncelle
                prog_bar.set(1.0)
                if buy_results:
                    prog_label.configure(text=f"✅ Tamamlandı — {len(buy_results)} AL, {len(sell_results)} SAT",
                                         text_color=COLORS["accent_green"])
                elif not all_results:
                    prog_label.configure(text="⚠️ Hiçbir hisse analiz edilemedi!",
                                         text_color=COLORS["accent_red"])
                else:
                    prog_label.configure(text=f"🛡️ NAKİTTE KAL — AL çıkan hisse yok",
                                         text_color=COLORS["accent_red"])

                # Telegram durumu
                if buy_results:
                    tg = ctk.CTkFrame(scroll, fg_color=COLORS["bg_card_alt"], corner_radius=8)
                    tg.grid(row=row_idx[0], column=0, sticky="ew", pady=(12, 4))
                    ctk.CTkLabel(tg, text=f"📱 Telegram'a {len(buy_results)} bildirim gönderildi!",
                                 font=("Inter", 11, "bold"), text_color=COLORS["accent_cyan"]).pack(pady=10)
                    row_idx[0] += 1

                self._update_status(f"✅ Tarama bitti — {len(all_results)} hisse tarandı")
                self.stat_signals.configure(text=str(len(buy_results) + len(sell_results)))

            self.after(0, finalize)

        threading.Thread(target=run_scan, daemon=True).start()

    def _show_signal(self, result):
        """Analiz sonucunu sinyal listesine ekle"""
        signal = result.get("signal", {})
        symbol = result.get("symbol", "?")
        action = signal.get("action", "TUT")
        score = result.get("overall_score", 50)
        price = result.get("current_price", 0)
        reason = signal.get("reason", "")

        self._add_signal_row(symbol, action, score, price, reason)

        # Checklist detayı
        checklist = signal.get("checklist", {})
        if checklist:
            cl_row = ctk.CTkFrame(self.signals_scroll, fg_color=COLORS["bg_input"],
                                    corner_radius=8, height=28)
            cl_row.grid(sticky="ew", padx=4, pady=(0, 8))
            cl_row.grid_columnconfigure(0, weight=1)

            cl_text = "   ".join([f"{v}" for v in checklist.values()])
            ctk.CTkLabel(cl_row, text=f"  🔍 {cl_text}",
                         font=("Inter", 9), text_color=COLORS["text_muted"],
                         anchor="w").pack(fill="x", padx=8, pady=4)

    def _add_signal_row(self, symbol, action, score, price, reason):
        """Sinyal satırı ekle"""
        # Placeholder kaldır (bunu silebiliriz çünkü artık loop öncesi temizliyoruz ama kalsın)
        if hasattr(self, '_signals_placeholder') and self._signals_placeholder.winfo_exists():
            self._signals_placeholder.destroy()

        if "AL" in action:
            color = COLORS["accent_green"]
            bg = "#0D2818"
        elif "SAT" in action:
            color = COLORS["accent_red"]
            bg = "#2D0A0A"
        elif action == "ENGEL":
            color = COLORS["text_muted"]
            bg = COLORS["bg_input"]
        else:
            color = COLORS["accent_yellow"]
            bg = "#2D2800"

        row = ctk.CTkFrame(self.signals_scroll, fg_color=bg, corner_radius=8, height=50)
        row.grid(sticky="ew", padx=4, pady=2)
        row.grid_columnconfigure(1, weight=1)

        # Sinyal + Hisse
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", padx=10, pady=8)

        ctk.CTkLabel(left, text=f"{symbol}", font=("Inter", 13, "bold"),
                     text_color=COLORS["text_primary"]).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(left, text=action, font=("Inter", 11, "bold"),
                     text_color=color).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(left, text=f"Skor: {score:.0f}", font=("Inter", 10),
                     text_color=COLORS["text_secondary"]).pack(side="left", padx=(0, 8))
        if price:
            ctk.CTkLabel(left, text=f"{price:.2f} TL", font=("Inter", 10),
                         text_color=COLORS["text_secondary"]).pack(side="left")

        # Neden
        if reason:
            right = ctk.CTkFrame(row, fg_color="transparent")
            right.pack(side="right", padx=10, pady=8)
            ctk.CTkLabel(right, text=reason[:60], font=("Inter", 9),
                         text_color=COLORS["text_muted"], anchor="e").pack(side="right")

    # ===== PORTFÖY İŞLEMLERİ =====

    def _open_add_dialog(self):
        """Hisse ekle dialog"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Hisse Ekle")
        dialog.geometry("360x300")
        dialog.configure(fg_color=COLORS["bg_card"])
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="➕ Portföye Hisse Ekle",
                     font=("Inter", 16, "bold")).pack(pady=(20, 16))

        fields = ctk.CTkFrame(dialog, fg_color="transparent")
        fields.pack(fill="x", padx=24)

        ctk.CTkLabel(fields, text="Hisse Kodu:", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(anchor="w")
        symbol_entry = ctk.CTkEntry(fields, placeholder_text="THYAO", height=34,
                                      fg_color=COLORS["bg_input"],
                                      border_color=COLORS["border"])
        symbol_entry.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(fields, text="Adet:", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(anchor="w")
        qty_entry = ctk.CTkEntry(fields, placeholder_text="100", height=34,
                                   fg_color=COLORS["bg_input"],
                                   border_color=COLORS["border"])
        qty_entry.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(fields, text="Alış Fiyatı (TL):", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(anchor="w")
        price_entry = ctk.CTkEntry(fields, placeholder_text="45.50", height=34,
                                     fg_color=COLORS["bg_input"],
                                     border_color=COLORS["border"])
        price_entry.pack(fill="x", pady=(2, 16))

        def do_add():
            sym = symbol_entry.get().strip().upper()
            try:
                qty = float(qty_entry.get())
                prc = float(price_entry.get())
            except ValueError:
                messagebox.showerror("Hata", "Geçersiz sayı girdiniz.")
                return
            if not sym:
                messagebox.showerror("Hata", "Hisse kodu girin.")
                return

            if self._modules_loaded and self._portfolio:
                self._portfolio.add_stock(sym, qty, prc)
                dialog.destroy()
                self._refresh_portfolio()
                self._update_status(f"✅ {sym} portföye eklendi ({qty} adet @ {prc:.2f} TL)")
            else:
                messagebox.showerror("Hata", "Modüller henüz yüklenmedi.")

        ctk.CTkButton(dialog, text="Ekle", width=200, height=38,
                      font=("Inter", 12, "bold"), corner_radius=8,
                      fg_color=COLORS["accent_green"],
                      text_color=COLORS["bg_dark"],
                      command=do_add).pack(pady=(0, 16))

    def _open_remove_dialog(self):
        """Hisse çıkar dialog"""
        if not self._modules_loaded:
            self._update_status("⏳ Modüller henüz yüklenmedi...")
            return

        holdings = self._portfolio.get_portfolio() if self._portfolio else []
        if not holdings:
            messagebox.showinfo("Bilgi", "Portföyünüzde hisse yok.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Hisse Çıkar")
        dialog.geometry("360x340")
        dialog.configure(fg_color=COLORS["bg_card"])
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="➖ Portföyden Hisse Çıkar",
                     font=("Inter", 16, "bold")).pack(pady=(20, 16))

        fields = ctk.CTkFrame(dialog, fg_color="transparent")
        fields.pack(fill="x", padx=24)

        symbols = [h["symbol"] for h in holdings]

        ctk.CTkLabel(fields, text="Hisse:", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(anchor="w")
        symbol_var = ctk.StringVar(value=symbols[0])
        ctk.CTkComboBox(fields, values=symbols, variable=symbol_var,
                        height=34, fg_color=COLORS["bg_input"],
                        border_color=COLORS["border"]).pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(fields, text="Satış Adedi:", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(anchor="w")
        qty_entry = ctk.CTkEntry(fields, placeholder_text="Tümünü satmak için boş bırakın",
                                   height=34, fg_color=COLORS["bg_input"],
                                   border_color=COLORS["border"])
        qty_entry.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(fields, text="Satış Fiyatı (TL):", font=("Inter", 11),
                     text_color=COLORS["text_secondary"]).pack(anchor="w")
        price_entry = ctk.CTkEntry(fields, placeholder_text="48.00", height=34,
                                     fg_color=COLORS["bg_input"],
                                     border_color=COLORS["border"])
        price_entry.pack(fill="x", pady=(2, 16))

        def do_sell():
            sym = symbol_var.get()
            try:
                prc = float(price_entry.get())
            except ValueError:
                messagebox.showerror("Hata", "Geçersiz satış fiyatı.")
                return

            qty_str = qty_entry.get().strip()
            holding = next((h for h in holdings if h["symbol"] == sym), None)
            if not holding:
                return

            qty = float(qty_str) if qty_str else holding["quantity"]

            self._portfolio.sell_stock(sym, qty, prc)
            dialog.destroy()
            self._refresh_portfolio()
            self._update_status(f"✅ {sym} satıldı ({qty} adet @ {prc:.2f} TL)")

        ctk.CTkButton(dialog, text="Sat", width=200, height=38,
                      font=("Inter", 12, "bold"), corner_radius=8,
                      fg_color=COLORS["accent_red"],
                      command=do_sell).pack(pady=(0, 16))

    # ================ PORTFÖY GÜNCELLE ================

    def _refresh_portfolio(self):
        """Portföy panelini güncelle"""
        if not self._modules_loaded:
            return

        try:
            holdings = self._portfolio.get_portfolio()

            # Temizle
            for w in self.portfolio_scroll.winfo_children():
                w.destroy()

            if not holdings:
                ctk.CTkLabel(self.portfolio_scroll,
                             text="Portföyünüz boş.\n'Hisse Ekle' ile başlayın.",
                             font=("Inter", 11), text_color=COLORS["text_muted"],
                             justify="center").grid(row=0, column=0, pady=40)
                self.stat_balance.configure(text=f"{self.initial_capital:,.2f} TL")
                self.stat_profit.configure(text="0,00 TL", text_color=COLORS["text_primary"])
                return

            total_value = 0
            total_cost = 0

            for i, h in enumerate(holdings):
                sym = h["symbol"]
                qty = h["quantity"]
                avg_price = h["avg_buy_price"]
                cost = qty * avg_price

                # Güncel fiyat çek
                try:
                    p = self._data_collector.get_current_price(sym)
                    cur_price = p["price"] if p else avg_price
                except:
                    cur_price = avg_price

                cur_value = qty * cur_price
                pnl = cur_value - cost
                pnl_pct = (pnl / cost * 100) if cost > 0 else 0

                total_value += cur_value
                total_cost += cost

                # Satır
                row = ctk.CTkFrame(self.portfolio_scroll, fg_color=COLORS["bg_input"],
                                    corner_radius=8)
                row.grid(row=i, column=0, sticky="ew", padx=4, pady=2)

                left = ctk.CTkFrame(row, fg_color="transparent")
                left.pack(side="left", padx=10, pady=8)

                ctk.CTkLabel(left, text=sym, font=("Inter", 13, "bold"),
                             text_color=COLORS["text_primary"]).pack(anchor="w")
                ctk.CTkLabel(left, text=f"{qty:.0f} adet @ {avg_price:.2f} TL",
                             font=("Inter", 9), text_color=COLORS["text_muted"]).pack(anchor="w")

                right = ctk.CTkFrame(row, fg_color="transparent")
                right.pack(side="right", padx=10, pady=8)

                pnl_color = COLORS["accent_green"] if pnl >= 0 else COLORS["accent_red"]
                ctk.CTkLabel(right, text=f"{pnl:+,.2f} TL",
                             font=("Inter", 13, "bold"), text_color=pnl_color).pack(anchor="e")
                ctk.CTkLabel(right, text=f"{pnl_pct:+.1f}%",
                             font=("Inter", 9), text_color=pnl_color).pack(anchor="e")

            # Stats güncelle
            total_pnl = total_value - total_cost
            current_total = self._risk._get_cash_balance() + total_value if self._risk else total_value

            self.stat_balance.configure(text=f"{current_total:,.2f} TL")
            pnl_color = COLORS["accent_green"] if total_pnl >= 0 else COLORS["accent_red"]
            self.stat_profit.configure(text=f"{total_pnl:+,.2f} TL", text_color=pnl_color)

            # Hedef güncelle
            progress = current_total / self.target_capital
            self.goal_progress.set(min(progress, 1.0))
            self.goal_label.configure(text=f"Şu an: {current_total:,.2f} TL (%{progress*100:.2f})")

        except Exception as e:
            self._update_status(f"Portföy güncelleme hatası: {e}")

    def _refresh_all(self):
        """Tüm verileri güncelle"""
        self._refresh_portfolio()

    # ================ PERİYODİK GÜNCELLEME ================

    def _periodic_update(self):
        """Her 60 saniyede bir güncelle"""
        if self._modules_loaded:
            threading.Thread(target=self._refresh_portfolio, daemon=True).start()
        self.after(60000, self._periodic_update)

    # ================ YARDIMCI FONKSİYONLAR ================

    def _update_status(self, text):
        """Durum çubuğunu güncelle"""
        try:
            self.status_label.configure(text=text)
        except:
            pass

    def _update_clock(self):
        """Saati güncelle"""
        now = datetime.now().strftime("%H:%M:%S")
        self.clock_label.configure(text=now)
        self.after(1000, self._update_clock)


# ==================== BAŞLAT ====================

if __name__ == "__main__":
    # customtkinter yoksa kur
    try:
        import customtkinter
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])

    app = BorsaRobotuApp()
    app.mainloop()
