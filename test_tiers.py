from notifier import Notifier

def test_tiers():
    bot = Notifier()
    
    # 1. A-SINIFI TEST
    print("A-Sinifi (Gunes) testi gonderiliyor...")
    bot.send_buy_signal(
        symbol="THYAO",
        current_price=285.50,
        target_price=310.00,
        stop_price=275.00,
        onay_notu="✅ Teknik ✅ Hacim ✅ AKD ✅ Haber ✅ Makro ✅ Risk\n📝 4 Saatlik trend onayi ve yuksek hacim."
    )

    # 2. B-SINIFI TEST
    print("B-Sinifi (Gumus) testi gonderiliyor...")
    bot.send_b_class_signal(
        symbol="ASELS",
        current_price=62.40,
        target_price=65.50,
        stop_price=60.50,
        onay_notu="✅ Teknik ✅ Hacim ✅ AKD ✅ Haber ✅ Makro ✅ Risk\n📝 Kar marji %4.8 olsa da 6/6 onayli guclu yapı."
    )

    print("Testler tamamlandI! Lutfen Telegram'I kontrol edin.")

if __name__ == "__main__":
    test_tiers()
