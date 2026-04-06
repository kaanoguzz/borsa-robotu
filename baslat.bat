@echo off
setlocal
cd /d "%~dp0"

echo 🤖 BIST 100 Borsa Robotu Başlatılıyor...
echo.

echo [1/3] 📊 Terminal takip sistemi başlatılıyor...
:: Terminali ayrı ve küçültülmüş pencerede aç (Zengin içerik için ayrı konsol)
start "Borsa Robotu Monitor" /min python main.py

echo [2/3] ⌨️ Hızlı etkileşim (Hotkey) servisi başlatılıyor...
:: VBS üzerinden gizli modda çalıştır (Yıldız tuşu "*" kontrolü için)
if exist run_hidden.vbs (
    start wscript.exe run_hidden.vbs
) else (
    start /B python hotkey_launcher.py
)

echo [3/3] 🖥️ Ana kontrol paneli açılıyor...
echo.
:: Dashboard'u ana pencerede aç
python app.py

echo.
echo ⚠️ Uygulama kapatıldı. Arka plan servislerini durdurmak için konsolu kapatabilirsiniz.
pause
