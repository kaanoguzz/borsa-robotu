"""
Portföy Yönetim Modülü
SQLite ile portföy takibi ve işlem geçmişi
"""

import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.db")


class PortfolioManager:
    """Portföy yönetimi ve işlem geçmişi"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Veritabanı tablolarını oluşturur"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Portföy tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                buy_price REAL NOT NULL,
                buy_date TEXT NOT NULL,
                target_price REAL DEFAULT 0,
                stop_loss REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                max_peak_price REAL DEFAULT 0,
                previous_close REAL DEFAULT 0
            )
        """)

        # İşlem geçmişi tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                total_value REAL NOT NULL,
                profit_loss REAL DEFAULT 0,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sinyal geçmişi tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                score REAL NOT NULL,
                technical_score REAL DEFAULT 0,
                news_score REAL DEFAULT 0,
                ml_score REAL DEFAULT 0,
                price_at_signal REAL DEFAULT 0,
                description TEXT DEFAULT '',
                notified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Watchlist tablosu (takip listesi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                target_buy_price REAL DEFAULT 0,
                target_sell_price REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Bakiye tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS balance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL DEFAULT 200.0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Eğer bakiye hiç yoksa başlangıç bakiyesini ekle
        cursor.execute("SELECT COUNT(*) FROM balance")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO balance (amount) VALUES (200.0)")

        conn.commit()
        conn.close()
        logger.info("Veritabanı hazır")

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    # ==================== NAKİT BAKİYE (AUTO-TRADER İÇİN) ====================

    def get_balance(self) -> float:
        """Mevcut nakit bakiyeyi döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT amount FROM balance ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.0

    def update_balance(self, amount_change: float) -> float:
        """Bakiyeyi günceller (alım için negatif, satım için pozitif amount_change)"""
        current = self.get_balance()
        return self.set_balance(current + amount_change)

    def set_balance(self, new_amount: float) -> float:
        """Bakiyeyi verilen değere doğrudan set eder"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE balance SET amount = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (new_amount,))
        conn.commit()
        conn.close()
        return new_amount

    # ==================== PORTFÖY İŞLEMLERİ ====================

    def add_stock(self, symbol: str, quantity: float, buy_price: float, target_price: float = 0, stop_loss: float = 0, notes: str = "", previous_close: float = 0) -> dict:
        """Portföye hisse ekler (Otomatik/Yarı otomatik)"""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO portfolio (symbol, quantity, buy_price, buy_date, target_price, stop_loss, notes, max_peak_price, previous_close) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol.upper(), quantity, buy_price, datetime.now().isoformat(), target_price, stop_loss, notes, buy_price, previous_close)
            )
            
            # İşlem geçmişine ekle
            cursor.execute(
                "INSERT INTO transactions (symbol, action, quantity, price, total_value, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (symbol.upper(), "AL", quantity, buy_price, quantity * buy_price, notes or "Manuel / Oto ekleme")
            )

            # BAKIYE GÜNCELLE
            cursor.execute("SELECT amount FROM balance WHERE id = 1")
            current_bal = cursor.fetchone()[0]
            new_bal = current_bal - (quantity * buy_price)
            cursor.execute("UPDATE balance SET amount = ? WHERE id = 1", (new_bal,))

            conn.commit()
            logger.info(f"Portföye eklendi: {quantity} adet {symbol} @ {buy_price} TL. Yeni Bakiye: {new_bal:.2f}")
            
            return {
                "success": True,
                "message": f"✅ {quantity} adet {symbol} portföye eklendi (Alış: {buy_price} TL)",
                "total_cost": round(quantity * buy_price, 2)
            }
        except Exception as e:
            logger.error(f"Hisse ekleme hatası: {e}")
            return {"success": False, "message": f"❌ Hata: {e}"}
        finally:
            conn.close()

    def remove_stock(self, symbol: str, quantity: float, sell_price: float, reason: str = "") -> dict:
        """Portföyden hisse çıkarır"""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Mevcut hisseleri kontrol et
            cursor.execute(
                "SELECT id, quantity, buy_price FROM portfolio WHERE symbol = ? ORDER BY buy_date ASC",
                (symbol.upper(),)
            )
            holdings = cursor.fetchall()

            if not holdings:
                return {"success": False, "message": f"❌ Portföyde {symbol} bulunamadı"}

            total_held = sum(h[1] for h in holdings)
            if quantity > total_held:
                return {"success": False, "message": f"❌ Yetersiz miktar. Portföyde {total_held} adet {symbol} var"}

            # FIFO yöntemiyle sat
            remaining = quantity
            total_profit = 0

            for holding_id, held_qty, buy_price in holdings:
                if remaining <= 0:
                    break

                sell_qty = min(remaining, held_qty)
                profit = (sell_price - buy_price) * sell_qty
                total_profit += profit

                if sell_qty >= held_qty:
                    cursor.execute("DELETE FROM portfolio WHERE id = ?", (holding_id,))
                else:
                    cursor.execute(
                        "UPDATE portfolio SET quantity = ? WHERE id = ?",
                        (held_qty - sell_qty, holding_id)
                    )

                remaining -= sell_qty

            # BAKIYE GÜNCELLE
            cursor.execute("SELECT amount FROM balance WHERE id = 1")
            current_bal = cursor.fetchone()[0]
            new_bal = current_bal + (quantity * sell_price)
            cursor.execute("UPDATE balance SET amount = ? WHERE id = 1", (new_bal,))

            conn.commit()

            profit_emoji = "📈" if total_profit > 0 else "📉"
            logger.info(f"Portföyden çıkarıldı: {quantity} adet {symbol} @ {sell_price} TL (K/Z: {total_profit:.2f}). Yeni Bakiye: {new_bal:.2f}")

            return {
                "success": True,
                "message": f"✅ {quantity} adet {symbol} satıldı (Satış: {sell_price} TL)\n{profit_emoji} Kâr/Zarar: {total_profit:+.2f} TL",
                "sell_value": round(quantity * sell_price, 2),
                "profit_loss": round(total_profit, 2)
            }
        except Exception as e:
            logger.error(f"Hisse çıkarma hatası: {e}")
            return {"success": False, "message": f"❌ Hata: {e}"}
        finally:
            conn.close()

    def update_peak_price(self, symbol: str, current_price: float) -> dict:
        """Eldeki hissenin en yüksek zirvesini (max_peak_price) günceller ve izleyen stop hesapları için döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, max_peak_price, previous_close FROM portfolio WHERE symbol = ?", (symbol.upper(),))
        holdings = cursor.fetchall()
        
        updated = False
        highest_peak = 0
        prev_close_val = 0
        
        for hid, max_peak, prev_close in holdings:
            prev_close_val = max(prev_close_val, prev_close or 0)
            highest_peak = max(highest_peak, max_peak or 0)
            if current_price > (max_peak or 0):
                cursor.execute("UPDATE portfolio SET max_peak_price = ? WHERE id = ?", (current_price, hid))
                updated = True
                highest_peak = current_price
        
        if updated:
            conn.commit()

        conn.close()
        
        return {"max_peak": highest_peak, "previous_close": prev_close_val}

    def get_portfolio(self) -> list:
        """Tüm portföyü döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol, SUM(quantity) as total_qty, 
                   AVG(buy_price) as avg_price,
                   MIN(buy_date) as first_buy,
                   AVG(target_price) as target_price,
                   AVG(stop_loss) as stop_loss,
                   GROUP_CONCAT(notes, '; ') as notes,
                   MAX(max_peak_price) as max_peak_price,
                   AVG(previous_close) as previous_close
            FROM portfolio 
            GROUP BY symbol
            ORDER BY symbol
        """)
        
        holdings = []
        for row in cursor.fetchall():
            holdings.append({
                "symbol": row[0],
                "quantity": row[1],
                "avg_buy_price": round(row[2], 2),
                "first_buy_date": row[3],
                "target_price": round(row[4] or 0, 2),
                "stop_loss": round(row[5] or 0, 2),
                "total_cost": round(row[1] * row[2], 2),
                "notes": row[6] or "",
                "max_peak_price": round(row[7] or 0, 2),
                "previous_close": round(row[8] or 0, 2)
            })

        conn.close()
        return holdings

    def get_portfolio_symbols(self) -> list:
        """Portföydeki hisse sembollerini döndürür"""
        holdings = self.get_portfolio()
        return [h["symbol"] for h in holdings]

    def get_holdings_dict(self) -> dict:
        """JSON portföy yapısıyla uyumluluk için sözlük döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT symbol, quantity, buy_price, target_price, stop_loss, max_peak_price, previous_close FROM portfolio")
        rows = cursor.fetchall()
        
        hisseler = {}
        for row in rows:
            hisseler[row[0]] = {
                "adet": row[1],
                "maliyet": row[2],
                "hedef": row[3],
                "stop": row[4],
                "en_yuksek_fiyat": row[5],
                "previous_close": row[6]
            }
        
        conn.close()
        return hisseler

    def get_portfolio_summary(self, current_prices: dict = None) -> dict:
        """Portföyün güncel değerini hesaplar"""
        holdings = self.get_portfolio()
        
        total_cost = 0
        total_value = 0
        details = []

        for h in holdings:
            symbol = h["symbol"]
            qty = h["quantity"]
            avg_price = h["avg_buy_price"]
            cost = h["total_cost"]
            total_cost += cost

            current_price = current_prices.get(symbol, avg_price)
            value = qty * current_price
            total_value += value

            profit_loss = value - cost
            profit_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0

            details.append({
                "symbol": symbol,
                "quantity": qty,
                "avg_buy_price": avg_price,
                "current_price": round(current_price, 2),
                "cost": round(cost, 2),
                "value": round(value, 2),
                "profit_loss": round(profit_loss, 2),
                "profit_pct": round(profit_pct, 2),
                "emoji": "📈" if profit_loss > 0 else "📉"
            })

        total_profit = total_value - total_cost
        total_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

        return {
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "total_profit_loss": round(total_profit, 2),
            "total_profit_pct": round(total_pct, 2),
            "holdings": details,
            "last_updated": datetime.now().isoformat()
        }

    # ==================== İŞLEM GEÇMİŞİ ====================

    def get_transactions(self, symbol: str = None, limit: int = 50) -> list:
        """İşlem geçmişini döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()

        if symbol:
            cursor.execute(
                "SELECT * FROM transactions WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol.upper(), limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )

        transactions = []
        for row in cursor.fetchall():
            transactions.append({
                "id": row[0],
                "symbol": row[1],
                "action": row[2],
                "quantity": row[3],
                "price": row[4],
                "total_value": row[5],
                "profit_loss": row[6],
                "reason": row[7],
                "date": row[8]
            })

        conn.close()
        return transactions

    # ==================== SİNYAL GEÇMİŞİ ====================

    def save_signal(self, symbol: str, signal_type: str, score: float,
                    technical_score: float = 0, news_score: float = 0,
                    ml_score: float = 0, price: float = 0, description: str = "") -> int:
        """Sinyal kaydeder"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO signals (symbol, signal_type, score, technical_score, 
               news_score, ml_score, price_at_signal, description) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, signal_type, score, technical_score, news_score, ml_score, price, description)
        )

        signal_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return signal_id

    def mark_signal_notified(self, signal_id: int):
        """Sinyali bildirildi olarak işaretle"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE signals SET notified = 1 WHERE id = ?", (signal_id,))
        conn.commit()
        conn.close()

    def get_signals(self, symbol: str = None, limit: int = 50) -> list:
        """Sinyal geçmişini döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()

        if symbol:
            cursor.execute(
                "SELECT * FROM signals WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol.upper(), limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )

        signals = []
        for row in cursor.fetchall():
            signals.append({
                "id": row[0],
                "symbol": row[1],
                "signal_type": row[2],
                "score": row[3],
                "technical_score": row[4],
                "news_score": row[5],
                "ml_score": row[6],
                "price_at_signal": row[7],
                "description": row[8],
                "notified": bool(row[9]),
                "date": row[10]
            })

        conn.close()
        return signals

    # ==================== WATCHLIST ====================

    def add_to_watchlist(self, symbol: str, target_buy: float = 0, target_sell: float = 0, notes: str = "") -> dict:
        """Takip listesine ekle"""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT OR REPLACE INTO watchlist (symbol, target_buy_price, target_sell_price, notes) VALUES (?, ?, ?, ?)",
                (symbol.upper(), target_buy, target_sell, notes)
            )
            conn.commit()
            return {"success": True, "message": f"✅ {symbol} takip listesine eklendi"}
        except Exception as e:
            return {"success": False, "message": f"❌ Hata: {e}"}
        finally:
            conn.close()

    def get_watchlist(self) -> list:
        """Takip listesini döndürür"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM watchlist ORDER BY symbol")
        
        items = []
        for row in cursor.fetchall():
            items.append({
                "id": row[0],
                "symbol": row[1],
                "target_buy_price": row[2],
                "target_sell_price": row[3],
                "notes": row[4],
                "created_at": row[5]
            })

        conn.close()
        return items

    def remove_from_watchlist(self, symbol: str) -> dict:
        """Takip listesinden çıkar"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
        conn.commit()
        conn.close()
        return {"success": True, "message": f"✅ {symbol} takip listesinden çıkarıldı"}
