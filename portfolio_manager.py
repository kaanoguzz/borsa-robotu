import os
import json
import logging
from datetime import datetime

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")

class Portfolio:
    def __init__(self):
        self.file = PORTFOLIO_FILE
        self.target = 100000.0
        self.load()

    def load(self):
        if os.path.exists(self.file):
            with open(self.file, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "bakiye": 200.0,
                "hisseler": {},
                "islem_gecmisi": []
            }
            self.save()

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.data, f, indent=4)

    def buy(self, symbol, price, previous_close=0):
        komisyon_orani = 0.002
        # Tüm bakiye ile alım
        islem_tutari = self.data["bakiye"]
        if islem_tutari <= 0:
            return False, "Yetersiz bakiye"

        komisyon = islem_tutari * komisyon_orani
        net_tutar = islem_tutari - komisyon
        
        adet = net_tutar / price
        
        self.data["bakiye"] = 0
        self.data["hisseler"][symbol] = {
            "adet": adet,
            "maliyet": price,
            "en_yuksek_fiyat": price, # İzleyen stop için
            "previous_close": previous_close, # Tavan kilidi için
            "stop_loss": price * 0.97, # Acil Stop
            "alim_tarihi": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self.data["islem_gecmisi"].append({
            "tip": "AL",
            "symbol": symbol,
            "fiyat": price,
            "adet": adet,
            "komisyon": komisyon,
            "tarih": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        self.save()
        return True, "Başarılı"

    def sell(self, symbol, price, neden=""):
        if symbol not in self.data["hisseler"]:
            return False, "Hisse portföyde yok"
            
        hisse = self.data["hisseler"][symbol]
        adet = hisse["adet"]
        maliyet = hisse["maliyet"]
        brut_gelir = adet * price
        
        komisyon_orani = 0.002
        komisyon = brut_gelir * komisyon_orani
        net_gelir = brut_gelir - komisyon
        
        kar_zarar_orani = ((price - maliyet) / maliyet) * 100
        
        self.data["bakiye"] += net_gelir
        del self.data["hisseler"][symbol]
        
        self.data["islem_gecmisi"].append({
            "tip": "SAT",
            "symbol": symbol,
            "fiyat": price,
            "adet": adet,
            "komisyon": komisyon,
            "kar_zarar_orani": kar_zarar_orani,
            "neden": neden,
            "tarih": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        self.save()
        
        ilerleme = (self.data["bakiye"] / self.target) * 100
        return True, net_gelir, kar_zarar_orani, ilerleme
        
    def update_peak_price(self, symbol, current_price):
        if symbol not in self.data["hisseler"]:
            return {"max_peak": current_price, "previous_close": 0}
            
        hisse = self.data["hisseler"][symbol]
        
        if current_price > hisse.get("en_yuksek_fiyat", 0):
            hisse["en_yuksek_fiyat"] = current_price
            self.save()
            
        return {
            "max_peak": hisse["en_yuksek_fiyat"], 
            "previous_close": hisse.get("previous_close", 0)
        }
            
        return False, ""
        
    def get_progress(self):
        # Eğer hissede isek tahmini değeri bakiye olarak hesapla
        toplam_deger = self.data["bakiye"]
        # Tahmini olarak maliyetten değer biçelim, ama canlı veri için dışarıdan güncel fiyat gelebilir
        return (toplam_deger / self.target) * 100
