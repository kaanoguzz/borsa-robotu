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
from portfolio_manager import Portfolio
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
        bakiye = self.portfolio.data['bakiye']
        aktif_hisseler = list(self.portfolio.data['hisseler'].keys())
        
        # Canlı Fiyat Güncelleme
        aktif_deger = 0
        hisse_durumlari = ""
        for h in aktif_hisseler:
            # Canlı fiyat al
            try:
                curr_price_data = self.dc.get_current_price(h)
                if curr_price_data:
                    curr_price = curr_price_data["price"]
                    # Trailing Stop Kontrolü
                    satis_durumu, neden = self.portfolio.update_trailing_stop(h, curr_price)
                    if satis_durumu:
                        self.add_log(f"🚨 {h} SATIŞ: {neden}", "bold red")
                        basari, net, kzo, ilerleme = self.portfolio.sell(h, curr_price, neden)
                        if basari:
                            self.notifier.send_sell_signal(h, curr_price, neden, kzo, ilerleme)
                    else:
                        maliyet = self.portfolio.data["hisseler"][h]["maliyet"]
                        kz = ((curr_price - maliyet)/maliyet)*100
                        renk = "green" if kz >= 0 else "red"
                        hisse_durumlari += f"[{renk}]{h} : {curr_price:.2f} TL (%{kz:+.2f})[/{renk}] "
                        aktif_deger += curr_price * self.portfolio.data['hisseler'][h]['adet']
            except Exception:
                pass
                
        toplam_varlik = bakiye + aktif_deger
        ilerleme = (toplam_varlik / self.portfolio.target) * 100
        
        hedef_text = f"🎯 Hedef: 100,000 TL | 💰 Varlık: {toplam_varlik:,.2f} TL | İlerleme: %{ilerleme:.2f}"
        if hisse_durumlari:
            hedef_text += f"\n💼 Portföy: {hisse_durumlari}"
        else:
            hedef_text += f"\n💼 Portföy: NAKİT ({bakiye:,.2f} TL)"

        grid.add_row(Panel(hedef_text, title="HEDEF TAKİBİ", border_style="cyan"))

        # Log Tablosu
        log_table = Table(show_header=False, expand=True, border_style="dim")
        log_table.add_column()
        for log in self.logs:
            log_table.add_row(log)
        
        grid.add_row(Panel(log_table, title="CANLI İŞLEM GÜNLÜĞÜ", border_style="yellow"))

        return grid

    def run(self):
        console.clear()
        self.add_log("🚀 Robot başlatıldı! Hedef 100.000 TL", "bold green")
        
        with Live(self.create_layout(), refresh_per_second=2, console=console) as live:
            while True:
                # Ekranda canlı akışı korurken tarama işlemi
                
                # Sadece NAKİT'te isek tarama yapacağız
                if len(self.portfolio.data['hisseler']) == 0:
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
                                
                                # Portföye Alım
                                success, _ = self.portfolio.buy(sym, price)
                                if success:
                                    self.add_log(f"🏦 {sym} SATIN ALINDI!", "bold green")
                                    # Bildirim Gönder
                                    self.notifier.send_buy_signal(
                                        symbol=sym,
                                        guven_skoru=round(skor, 1),
                                        risk_seviyesi="Düşük/Orta",
                                        fiyat=price,
                                        hedef_fiyat=price * 1.05,
                                        stop_fiyat=price * 0.97,
                                        teknik_ozet=f"RSI({rsi:.1f}) & EMA Kesişimi, 4S Trend Onaylı",
                                        hacim_durumu="Normal/Aşırı Değil",
                                        duygu_skoru=skor
                                    )
                                    break # Bir hisse aldık, beklemeye geç!
                            else:
                                self.add_log(f"❌ {sym} Duygu filtresine takıldı: {neden}", "red")
                    else:
                        self.add_log("💤 Uygun sinyal bulunamadı. Bekleniyor...", "dim")
                else:
                    self.add_log("🛡️ Hissedeyiz. Sadece İz Süren Stop kontrol ediliyor...", "cyan")

                live.update(self.create_layout())
                
                # 60 saniye boyunca canlı arayüzü güncel tutarak bekle
                for _ in range(60):
                    time.sleep(1)
                    live.update(self.create_layout())

if __name__ == "__main__":
    try:
        robot = BorsaRobotu()
        robot.run()
    except KeyboardInterrupt:
        console.print("\n[bold red]Terminated by user.[/bold red]")
        sys.exit(0)
