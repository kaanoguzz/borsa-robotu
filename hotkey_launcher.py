import keyboard
import subprocess
import os
import sys
import time

# Ayarlar
HOTKEYS = ['*', 'shift+8', 'num *'] # Farklı klavye düzenleri için varyasyonlar
SCRIPT_TO_RUN = 'app.py'  # Arayüz dosyası
PYTHON_EXE = sys.executable

def launch_app():
    """Uygulamayi baslatir"""
    print(f"Kisayol algilandi: {HOTKEY}. Uygulama aciliyor...")
    try:
        # Arka planda yeni bir pencere olarak ac
        # 'py' komutunu kullandik
        subprocess.Popen(['py', SCRIPT_TO_RUN], 
                         creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
    except Exception as e:
        print(f"Hata olustu: {e}", flush=True)

def main():
    log_file = "hotkey_debug.log"
    with open(log_file, "a") as f:
        f.write(f"[{time.ctime()}] Kayit baslatildi. Tuslar: {HOTKEYS}\n")
        f.flush()
    
    print(f"Klavye dinleyicisi baslatildi. {HOTKEYS} tuslarından birine bastiginizda Borsa Robotu acilacak.", flush=True)
    
    # Kisayollari ata
    for hk in HOTKEYS:
        keyboard.add_hotkey(hk, launch_app)
    
    # Dinlemeye devam et
    keyboard.wait()

if __name__ == "__main__":
    # Çalışma dizinini bu dosyanın olduğu klasör yap
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
