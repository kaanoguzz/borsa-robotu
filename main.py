import time
import os
import sys
import logging
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.align import Align
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn
from datetime import datetime

from scanner import Scanner
from brain import Brain
from notifier import Notifier
from portfolio import PortfolioManager as Portfolio
from data_collector import DataCollector

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("pandas_ta").setLevel(logging.CRITICAL)
logging.getLogger("ntscraper").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

console = Console()

class BorsaRobotu:
    def __init__(self):
        self.scanner = Scanner()
        self.brain = Brain()
        self.notifier = Notifier()
        self.portfolio = Portfolio()
        self.dc = DataCollector()
        self.logs = []
        
    def add_log(self, text, style="white"):
        time_str = datetime.now().strftime("%H:%M:%S")
        self.logs.insert(0, f"[{time_str}] {text}")
        if len(self.logs) > 10:
            self.logs.pop()

    def create_layout(self):
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_row(Align.center(
            Text("🤖 BIST 100 BORSA ROBOTU 🚀", style="bold green on black", justify="center")
        ))
        
        # Portfolio and Target
        bakiye = self.portfolio.get_balance()
        holdings = self.portfolio.get_holdings_dict()
        aktif_hisseler = list(holdings.keys())
        
        # XU100 5 Dakikalık şelale kontrolü
        index_crash = False
        import yfinance as yf
        try:
            xu_data = yf.Ticker("XU100.IS").history(period="1d", interval="5m")
            if len(xu_data) >= 2:
                if (xu_data['Close'].iloc[-1] - xu_data['Close'].iloc[-2]) / xu_data['Close'].iloc[-2] <= -0.005:
                    index_crash = True
        except:
            pass
        
        # Canlı Fiyat Güncelleme ve Stop Kontrolü
        aktif_deger = 0
        hisse_durumlari = ""
        for h in aktif_hisseler:
            # Canlı fiyat al
            try:
                curr_price_data = self.dc.get_current_price(h)
                if curr_price_data:
                    curr_price = curr_price_data["price"]
                    # Zirve ve Tavan Takibi
                    peak_data = self.portfolio.update_peak_price(h, curr_price)
                    max_peak = peak_data["max_peak"]
                    prev_close = peak_data["previous_close"]
                    
                    target = holdings[h].get("hedef", 0)
                    stop = holdings[h].get("stop", 0)
                    maliyet = holdings[h]["maliyet"]
                    
                    # Satış Kontrolü
                    satis_durumu = False
                    neden = ""
                    
                    if index_crash:
                        satis_durumu = True
                        neden = "Acil Çıkış: XU100 Şelale Çöküşü (-%0.5)!"
                    elif max_peak > maliyet and curr_price < max_peak * 0.985:
                        satis_durumu = True
                        neden = f"İzleyen Stop Patladı (Zirve: {max_peak:.2f}, Fiyat Düştü)"
                    elif stop > 0 and curr_price <= stop:
                        satis_durumu = True
                        neden = f"Acil Durum: Stop loss seviyesine indi ({stop} TL)"
                    elif target > 0 and curr_price >= target:
                        if prev_close > 0 and curr_price >= prev_close * 1.09:
                            self.add_log(f"🔒 Tavan Kilidi: {h} hedefe ulaştı ama kitlendi, satılmıyor!", "bold cyan")
                        else:
                            satis_durumu = True
                            neden = f"Hedef fiyata ulaştı ({target} TL)"
                    else:
                        from scanner import Scanner
                        sc = Scanner()
                        tech_sell_signal, tech_sell_reason = sc.check_sell_condition(h)
                        if tech_sell_signal:
                            satis_durumu = True
                            neden = f"Aktif Defans: {tech_sell_reason}"

                    if satis_durumu:
                        self.add_log(f"🚨 {h} SATIŞ: {neden}", "bold red")
                        qty = holdings[h]["adet"]
                        result = self.portfolio.remove_stock(h, qty, curr_price, neden)
                        if result["success"]:
                            tahmini_dip = curr_price * 0.97
                            self.notifier.send_sell_signal(
                                symbol=h, 
                                fiyat=curr_price, 
                                tahmini_dip=tahmini_dip, 
                                bozulan_parametreler=neden,
                                guncel_bakiye=self.portfolio.get_balance(),
                                kar_zarar=result["profit_loss"]
                            )
                    else:
                        kz = ((curr_price - maliyet)/maliyet)*100
                        renk = "green" if kz >= 0 else "red"
                        hisse_durumlari += f"[{renk}]{h} : {curr_price:.2f} TL (%{kz:+.2f})[/{renk}] "
                        aktif_deger += curr_price * holdings[h]['adet']
            except Exception:
                pass
                
        toplam_varlik = bakiye + aktif_deger
        ilerleme = (toplam_varlik / self.portfolio.target) * 100
        
        hedef_text = f"🎯 Hedef: 100,000 TL | 💰 Varlık: {toplam_varlik:,.2f} TL | İlerleme: %{ilerleme:.2f}"
        if hisse_durumlari:
            hedef_text += f"\n💼 Portföy: {hisse_durumlari}"
        else:
            hedef_text += f"\n💼 Portföy: NAKİT ({bakiye:,.2f} TL)"

        grid.add_row(Panel(log_table, title="CANLI İŞLEM GÜNLÜĞÜ", border_style="yellow"))

        # İşlem Geçmişi Paneli (Yeni!)
        history = self.portfolio.get_transactions(limit=6)
        if history:
            hist_table = Table(show_header=True, expand=True, border_style="dim", header_style="bold magenta")
            hist_table.add_column("Tarih", style="dim")
            hist_table.add_column("Sembol", style="bold cyan")
            hist_table.add_column("İşlem", justify="center")
            hist_table.add_column("Fiyat", justify="right")
            hist_table.add_column("K/Z", justify="right")

            for h in history:
                kz_val = h.get("profit_loss", 0)
                kz_str = f"{kz_val:+.2f} TL"
                kz_style = "green" if kz_val > 0 else "red" if kz_val < 0 else "white"
                
                # Tarih formatla (YYYY-MM-DD HH:MM:SS -> HH:MM)
                tarih_str = h["date"].split(" ")[-1][:5] if " " in h["date"] else h["date"][:5]
                
                hist_table.add_row(
                    tarih_str,
                    h["symbol"],
                    "[green]AL[/green]" if h["action"] == "AL" else "[red]SAT[/red]",
                    f"{h['price']:.2f}",
                    f"[{kz_style}]{kz_str}[/{kz_style}]" if h["action"] == "SAT" else "-"
                )
            grid.add_row(Panel(hist_table, title="SON İŞLEM GEÇMİŞİ", border_style="magenta"))

        return grid

    def run(self):
        console.clear()
        self.add_log("🚀 Robot başlatıldı! Hedef 100.000 TL", "bold green")
        
        with Live(self.create_layout(), refresh_per_second=2, console=console) as live:
            while True:
                # Ekranda canlı akışı korurken tarama işlemi
                
                # Sadece NAKİT'te isek tarama yapacağız
                holdings = self.portfolio.get_holdings_dict()
                if len(holdings) == 0:
                    self.add_log("🔍 Piyasa taranıyor... (RSI < 45, EMA5>20, 4H EMA50 Trend Onayı)", "cyan")
                    live.update(self.create_layout())
                    
                    buy_candidates = self.scanner.fast_scan()
                    
                    if buy_candidates:
                        for cand in buy_candidates:
                            sym = cand['symbol']
                            price = cand['price']
                            rsi = cand['rsi']
                            
                            self.add_log(f"💡 {sym} için TEKNİK AL bulundu! Fiyat: {price:.2f}, RSI: {rsi:.1f}", "yellow")
                            live.update(self.create_layout())
                            
                            # Duygu Analizi (Sıfır Maliyetli)
                            self.add_log(f"🧠 {sym} Haber/Duygu analizi yapılıyor (Sınır: %70)...", "magenta")
                            live.update(self.create_layout())
                            
                            onay, skor, neden = self.brain.confirm_trade(sym)
                            
                            if onay:
                                self.add_log(f"✅ {sym} YÜKSEK GÜVEN ONAYI! (%{skor:.1f})", "bold green")
                                
                                # Portföye Alım (SQLite methoduna göre adet hesaplama lojiği)
                                bakiye = self.portfolio.get_balance()
                                komisyon = bakiye * 0.002
                                net_bakiye = bakiye - komisyon
                                adet = net_bakiye / price
                                
                                result = self.portfolio.add_stock(sym, adet, price, target_price=price*1.05, stop_loss=price*0.97, notes="Otonom Alım")
                                if result["success"]:
                                    self.add_log(f"🏦 {sym} SATIN ALINDI!", "bold green")
                                    # Bildirim Gönder
                                    self.notifier.send_buy_signal(
                                        symbol=sym,
                                        current_price=price,
                                        target_price=price * 1.05,
                                        stop_price=price * 0.97,
                                        onay_notu="✅ Teknik ✅ Hacim ✅ AKD ✅ Haber ✅ Makro ✅ Risk"
                                    )
                                    break # Bir hisse aldık, beklemeye geç!
                            else:
                                self.add_log(f"❌ {sym} Duygu filtresine takıldı: {neden}", "red")
                    else:
                        self.add_log("💤 Uygun sinyal bulunamadı. Bekleniyor...", "dim")
                else:
                    self.add_log("🛡️ Hissedeyiz. Teknik SAT sinyalleri ve Portföy kontrol ediliyor...", "cyan")
                    live.update(self.create_layout())
                    
                    holdings_list = list(holdings.keys())
                    for h in holdings_list:
                        sell_signal, sell_reason = self.scanner.check_sell_condition(h)
                        if sell_signal:
                            curr_price_data = self.dc.get_current_price(h)
                            c_price = curr_price_data['price'] if curr_price_data else holdings[h]["maliyet"]
                            self.add_log(f"📉 {h} TEKNİK SAT: {sell_reason}", "bold red")
                            
                            qty = holdings[h]["adet"]
                            result = self.portfolio.remove_stock(h, qty, c_price, sell_reason)
                            if result["success"]:
                                tahmini_dip = c_price * 0.97
                                self.notifier.send_sell_signal(
                                    symbol=h, 
                                    fiyat=c_price, 
                                    tahmini_dip=tahmini_dip, 
                                    bozulan_parametreler=sell_reason,
                                    guncel_bakiye=self.portfolio.get_balance(),
                                    kar_zarar=result["profit_loss"]
                                )

                live.update(self.create_layout())
                
                # 300 saniye (5 dakika) boyunca canlı arayüzü güncel tutarak bekle
                for _ in range(300):
                    time.sleep(1)
                    live.update(self.create_layout())

if __name__ == "__main__":
    try:
        robot = BorsaRobotu()
        robot.run()
    except KeyboardInterrupt:
        console.print("\n[bold red]Terminated by user.[/bold red]")
        sys.exit(0)
