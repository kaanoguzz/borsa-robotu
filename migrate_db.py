import sqlite3

def migrate():
    conn = sqlite3.connect('portfolio.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE portfolio ADD COLUMN max_peak_price REAL DEFAULT 0")
        print("max_peak_price added")
    except Exception as e:
        print("max_peak_price exists or error:", e)

    try:
        cursor.execute("ALTER TABLE portfolio ADD COLUMN previous_close REAL DEFAULT 0")
        print("previous_close added")
    except Exception as e:
        print("previous_close exists or error:", e)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate()
