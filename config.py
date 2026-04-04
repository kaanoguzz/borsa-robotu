"""
BIST 100 Hisse Listesi
Borsa İstanbul 100 endeksindeki tüm hisse kodları
"""

BIST100_TICKERS = [
    "ACSEL", "ADEL", "AEFES", "AFYON", "AGESA", "AGHOL", "AHGAZ", "AKBNK",
    "AKCNS", "AKFGY", "AKFYE", "AKGRT", "AKMGY", "AKSA", "AKSEN", "AKSGY",
    "ALARK", "ALFAS", "ALKIM", "ANACM", "ARCLK", "ARDYZ", "ASELS", "ASTOR",
    "ASUZU", "BERA", "BFREN", "BIMAS", "BIOEN", "BLCYT", "BRISA", "BRYAT",
    "BTCIM", "BUCIM", "CANTE", "CCOLA", "CEMTS", "CIMSA", "CWENE", "DOAS",
    "DOHOL", "ECILC", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL", "EUPWR",
    "EUREN", "FROTO", "GARAN", "GESAN", "GLYHO", "GOLTS", "GUBRF", "HALKB",
    "HEKTS", "ISCTR", "ISGYO", "ISMEN", "IZENR", "KARSN", "KAYSE", "KCAER",
    "KCHOL", "KMPUR", "KONTR", "KONYA", "KOZAA", "KOZAL", "KRDMD", "LMKDC",
    "MAVI", "MGROS", "MIATK", "ODAS", "OTKAR", "OYAKC", "PETKM", "PGSUS",
    "QUAGR", "SAHOL", "SASA", "SDTTR", "SISE", "SKBNK", "SMRTG", "SOKM",
    "TAVHL", "TCELL", "THYAO", "TKFEN", "TKNSA", "TOASO", "TRGYO", "TTKOM",
    "TTRAK", "TUKAS", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE", "VESTL",
    "YEOTK", "YKBNK", "YYLGD", "ZOREN"
]

# Sektör sınıflandırması
SECTORS = {
    "Bankacılık": ["AKBNK", "GARAN", "HALKB", "ISCTR", "SKBNK", "VAKBN", "YKBNK"],
    "Holding": ["AGHOL", "DOHOL", "GLYHO", "KCHOL", "SAHOL"],
    "Sanayi": ["ARCLK", "EREGL", "FROTO", "TOASO", "OTKAR", "VESTL", "VESBE"],
    "Enerji": ["AKSEN", "ENJSA", "EUPWR", "CWENE", "ZOREN", "IZENR", "AHGAZ"],
    "Perakende": ["BIMAS", "MGROS", "SOKM"],
    "Telekomünikasyon": ["TCELL", "TTKOM"],
    "Havacılık": ["THYAO", "PGSUS", "TAVHL"],
    "İnşaat & GYO": ["EKGYO", "ISGYO", "TRGYO", "ENKAI"],
    "Madencilik": ["KOZAL", "KOZAA"],
    "Teknoloji": ["ASELS", "ARDYZ"],
    "Gıda": ["AEFES", "CCOLA", "ULKER", "TUKAS"],
    "Kimya & Petrol": ["PETKM", "TUPRS", "SASA", "GUBRF"],
    "Otomotiv": ["DOAS", "FROTO", "TOASO", "ASUZU"],
    "Cam & Çimento": ["SISE", "AKCNS", "BTCIM", "BUCIM", "CIMSA", "ANACM"],
    "Sigorta": ["AGESA", "AKGRT", "TURSG"],
    "Tekstil": ["MAVI", "BRISA"],
}

# Her hisse için Yahoo Finance ticker formatı
def get_yahoo_ticker(symbol: str) -> str:
    """BIST sembolünü Yahoo Finance formatına çevirir"""
    return f"{symbol}.IS"

def get_all_yahoo_tickers() -> list:
    """Tüm BIST 100 hisselerini Yahoo Finance formatında döndürür"""
    return [get_yahoo_ticker(t) for t in BIST100_TICKERS]

def get_sector(symbol: str) -> str:
    """Bir hissenin sektörünü döndürür"""
    for sector, tickers in SECTORS.items():
        if symbol in tickers:
            return sector
    return "Diğer"
