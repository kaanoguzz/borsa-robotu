import os
import sys
import logging
from datetime import datetime, timezone, timedelta

# Mock market hours to allow test when closed
def run_mini_test():
    from signal_generator import SignalGenerator
    from notifier import Notifier
    from data_collector import DataCollector
    
    print("--- THYAO mini-test taramasi baslatiliyor ---")
    sg = SignalGenerator()
    notifier = Notifier()
    dc = DataCollector()
    
    # Analyze THYAO (Deep Analyze but skip market hour check)
    result = sg.analyze_stock("THYAO", skip_backtest=True, quick_mode=False)
    
    if result:
        print(f"✅ Analiz Başarılı! Skor: {result.get('overall_score')}")
        # Send a result to telegram as a test report
        notifier.send_analysis_report({
            "symbol": "THYAO",
            "price": result.get("current_price", 0),
            "overall_score": result.get("overall_score", 0),
            "reason": "Bu bir TEST taramasıdır. Sistem sağlıklı çalışıyor.",
            "target": result.get("current_price", 0) * 1.05,
            "stop": result.get("current_price", 0) * 0.97,
            "rsi": result.get("technical_analysis", {}).get("rsi", {}).get("value", 0),
            "trend": result.get("technical_analysis", {}).get("signal", "Nötr")
        })
        print("🚀 Analiz raporu Telegram'a gönderildi!")
    else:
        print("❌ Analiz başarısız oldu.")

if __name__ == "__main__":
    run_mini_test()
