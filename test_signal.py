from notifier import Notifier

def test():
    bot = Notifier()
    # Örnek bir 6/6 Tam Onay mesajı
    symbol = "THYAO"
    price = 285.50
    target = 312.00
    stop = 278.00
    onay_notu = "✅ Teknik ✅ Hacim ✅ AKD ✅ Haber ✅ Makro ✅ Risk\n📝 Güçlü alış hacmi ve RSI desteği ile kırılım onaylandı."
    
    print("Telegram'a örnek mesaj gönderiliyor...")
    bot.send_buy_signal(symbol, price, target, stop, onay_notu)
    print("Gönderildi! Lütfen Telegram'ı kontrol edin.")

if __name__ == "__main__":
    test()
