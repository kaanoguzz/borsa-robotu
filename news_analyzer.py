"""
Haber ve Sentiment Analiz Modülü
Google News RSS ile haber çekme ve NLP ile duygu analizi
"""

import feedparser
import re
import logging
from datetime import datetime, timedelta
from textblob import TextBlob
import requests
from urllib.parse import quote
from config import BIST100_TICKERS, SECTORS

logger = logging.getLogger(__name__)

# Hisse sembolü -> şirket adı eşleştirmesi
COMPANY_NAMES = {
    "THYAO": ["Türk Hava Yolları", "THY", "Turkish Airlines"],
    "GARAN": ["Garanti Bankası", "Garanti BBVA"],
    "AKBNK": ["Akbank"],
    "ISCTR": ["İş Bankası", "Türkiye İş Bankası"],
    "YKBNK": ["Yapı Kredi", "Yapı ve Kredi"],
    "HALKB": ["Halkbank", "Halk Bankası"],
    "VAKBN": ["Vakıfbank", "Vakıf Bankası"],
    "EREGL": ["Ereğli Demir Çelik", "Erdemir"],
    "SISE": ["Şişecam", "Türkiye Şişe"],
    "TUPRS": ["Tüpraş"],
    "SAHOL": ["Sabancı Holding"],
    "KCHOL": ["Koç Holding"],
    "BIMAS": ["BİM", "BİM Mağazaları"],
    "MGROS": ["Migros"],
    "ASELS": ["Aselsan", "ASELSAN"],
    "TCELL": ["Turkcell"],
    "TTKOM": ["Türk Telekom"],
    "ARCLK": ["Arçelik"],
    "FROTO": ["Ford Otosan"],
    "TOASO": ["Tofaş"],
    "EKGYO": ["Emlak Konut"],
    "PETKM": ["Petkim"],
    "PGSUS": ["Pegasus"],
    "TAVHL": ["TAV Havalimanları"],
    "SASA": ["SASA Polyester"],
    "ENKAI": ["Enka İnşaat"],
    "KOZAL": ["Koza Altın"],
    "KOZAA": ["Koza Anadolu Metal"],
    "DOHOL": ["Doğan Holding"],
    "AGHOL": ["Anadolu Grubu Holding"],
    "SOKM": ["Şok Market", "ŞOK"],
    "CCOLA": ["Coca Cola İçecek"],
    "ULKER": ["Ülker"],
    "VESTL": ["Vestel"],
    "VESBE": ["Vestel Beyaz Eşya"],
    "AKSEN": ["Aksa Enerji"],
    "DOAS": ["Doğuş Otomotiv"],
    "TTRAK": ["Türk Traktör"],
    "OTKAR": ["Otokar"],
}

# Pozitif/Negatif Türkçe kelimeler (sentiment analizi için)
POSITIVE_WORDS_TR = [
    "yükseldi", "yükseliş", "artış", "arttı", "kar", "kazanç", "büyüme", "büyüdü",
    "rekor", "pozitif", "olumlu", "güçlü", "güçlendi", "toparlanma", "toparlandı",
    "talep", "alım", "yatırım", "fırsat", "umut", "iyileşme", "ralli", "zirve",
    "beklentilerin üzerinde", "hedef yükseldi", "temettü", "kârlılık", "verimli",
    "ihracat artışı", "pazar payı", "genişleme", "inovasyon", "anlaşma", "ortaklık",
    "başarılı", "güvenilir", "istikrar", "performans"
]

NEGATIVE_WORDS_TR = [
    "düştü", "düşüş", "azaldı", "azalma", "zarar", "kayıp", "küçüldü", "daralma",
    "negatif", "olumsuz", "zayıf", "zayıfladı", "kriz", "risk", "tehlike", "endişe",
    "satış baskısı", "panik", "çöküş", "dip", "beklentilerin altında", "hedef düşürüldü",
    "borç", "temerrüt", "iflas", "ceza", "soruşturma", "dava", "kapatma",
    "ithalat artışı", "pazar kaybı", "daralma", "gerileme", "kaos", "belirsizlik",
    "faiz artışı", "enflasyon", "devalüasyon", "kur baskısı"
]


class NewsAnalyzer:
    """Haber ve sentiment analizi yapan modül"""

    def __init__(self):
        self.news_cache = {}
        self.cache_duration = 1800  # 30 dakika cache

    def get_stock_news(self, symbol: str, max_results: int = 20) -> list:
        """Bir hisse ile ilgili haberleri çeker"""
        cache_key = f"news_{symbol}"
        
        if cache_key in self.news_cache:
            cached_time, cached_data = self.news_cache[cache_key]
            if datetime.now().timestamp() - cached_time < self.cache_duration:
                return cached_data

        all_news = []

        # Şirket adları ile arama
        search_terms = [symbol]
        if symbol in COMPANY_NAMES:
            search_terms.extend(COMPANY_NAMES[symbol])

        for term in search_terms:
            try:
                news = self._search_google_news(term)
                all_news.extend(news)
            except Exception as e:
                logger.error(f"Haber çekme hatası ({term}): {e}")

        # Duplicate temizle
        seen_titles = set()
        unique_news = []
        for item in all_news:
            if item['title'] not in seen_titles:
                seen_titles.add(item['title'])
                unique_news.append(item)

        # Sentiment analizi yap
        for item in unique_news:
            sentiment = self._analyze_sentiment(item['title'] + " " + item.get('summary', ''))
            item['sentiment'] = sentiment

        unique_news = unique_news[:max_results]
        
        # Cache'e kaydet
        self.news_cache[cache_key] = (datetime.now().timestamp(), unique_news)

        return unique_news

    def get_market_news(self) -> list:
        """Genel borsa ve ekonomi haberlerini çeker"""
        search_terms = [
            "Borsa İstanbul",
            "BIST 100",
            "Türkiye ekonomi",
            "TCMB faiz",
            "döviz kuru TL"
        ]

        all_news = []
        for term in search_terms:
            try:
                news = self._search_google_news(term)
                all_news.extend(news)
            except Exception as e:
                logger.error(f"Piyasa haberi hatası ({term}): {e}")

        # Duplicate temizle
        seen_titles = set()
        unique_news = []
        for item in all_news:
            if item['title'] not in seen_titles:
                seen_titles.add(item['title'])
                item['sentiment'] = self._analyze_sentiment(item['title'] + " " + item.get('summary', ''))
                unique_news.append(item)

        return unique_news[:30]

    def get_political_impact(self, symbol: str) -> dict:
        """Siyasi gelişmelerin hisseye etkisini analiz eder"""
        sector = self._get_stock_sector(symbol)
        
        # Sektöre göre politik anahtar kelimeler
        political_terms = {
            "Bankacılık": ["TCMB faiz kararı", "bankacılık düzenleme", "BDDK", "kredi faiz"],
            "Enerji": ["enerji politikası", "EPDK", "doğalgaz fiyat", "elektrik fiyat"],
            "Havacılık": ["sivil havacılık", "turizm", "uçuş yasağı", "havalimanı"],
            "İnşaat & GYO": ["inşaat sektörü", "konut", "kentsel dönüşüm", "imar"],
            "Madencilik": ["maden kanunu", "altın fiyat", "maden ruhsat"],
            "Teknoloji": ["savunma sanayi", "teknoloji yatırım", "ar-ge teşvik"],
            "Perakende": ["enflasyon tüketici", "perakende satış", "alışveriş"],
            "Telekomünikasyon": ["BTK", "telekomünikasyon düzenleme", "5G"],
        }

        terms = political_terms.get(sector, ["Türkiye ekonomi politikası"])
        
        political_news = []
        for term in terms:
            try:
                news = self._search_google_news(term)
                for item in news:
                    item['sentiment'] = self._analyze_sentiment(item['title'] + " " + item.get('summary', ''))
                    political_news.append(item)
            except Exception as e:
                logger.error(f"Politik haber hatası ({term}): {e}")

        # Genel politik sentiment hesapla
        if political_news:
            avg_sentiment = sum(n['sentiment']['score'] for n in political_news) / len(political_news)
        else:
            avg_sentiment = 0

        return {
            "sector": sector,
            "political_news": political_news[:10],
            "political_sentiment": round(avg_sentiment, 3),
            "impact": self._classify_political_impact(avg_sentiment),
            "analyzed_at": datetime.now().isoformat()
        }

    def _search_google_news(self, query: str) -> list:
        """Google News RSS ile haber arar"""
        try:
            encoded_query = quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}+when:7d&hl=tr&gl=TR&ceid=TR:tr"
            
            feed = feedparser.parse(url)
            news_list = []

            for entry in feed.entries[:10]:
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat()

                news_list.append({
                    "title": entry.get('title', ''),
                    "link": entry.get('link', ''),
                    "source": entry.get('source', {}).get('title', 'Google News') if hasattr(entry, 'source') else 'Google News',
                    "published": pub_date,
                    "summary": self._clean_html(entry.get('summary', '')),
                    "query": query
                })

            return news_list

        except Exception as e:
            logger.error(f"Google News RSS hatası: {e}")
            return []

    def _analyze_sentiment(self, text: str) -> dict:
        """Metni analiz ederek duygu skoru hesaplar"""
        # Türkçe kelime bazlı analiz
        text_lower = text.lower()
        
        positive_count = 0
        negative_count = 0
        matched_positive = []
        matched_negative = []

        for word in POSITIVE_WORDS_TR:
            if word.lower() in text_lower:
                positive_count += 1
                matched_positive.append(word)

        for word in NEGATIVE_WORDS_TR:
            if word.lower() in text_lower:
                negative_count += 1
                matched_negative.append(word)

        # TextBlob analizi (İngilizce baz, Türkçe için kısıtlı ama yine de faydalı)
        try:
            blob = TextBlob(text)
            textblob_score = blob.sentiment.polarity  # -1 ile 1 arası
        except:
            textblob_score = 0

        # Türkçe ve TextBlob skorlarını birleştir
        total_words = positive_count + negative_count
        if total_words > 0:
            turkish_score = (positive_count - negative_count) / total_words
        else:
            turkish_score = 0

        # Ağırlıklı ortalama (Türkçe'ye daha fazla ağırlık)
        combined_score = turkish_score * 0.7 + textblob_score * 0.3

        if combined_score > 0.3:
            label = "Pozitif"
            emoji = "🟢"
        elif combined_score < -0.3:
            label = "Negatif"
            emoji = "🔴"
        else:
            label = "Nötr"
            emoji = "🟡"

        return {
            "score": round(combined_score, 3),
            "label": label,
            "emoji": emoji,
            "positive_words": matched_positive,
            "negative_words": matched_negative,
            "turkish_score": round(turkish_score, 3),
            "textblob_score": round(textblob_score, 3)
        }

    def calculate_news_score(self, symbol: str) -> dict:
        """Hisse için haber bazlı skor hesaplar"""
        news = self.get_stock_news(symbol)
        political = self.get_political_impact(symbol)

        if not news:
            return {
                "score": 50,
                "signal": "TUT",
                "news_count": 0,
                "description": "Yeterli haber bulunamadı"
            }

        # Haber sentiment ortalaması
        sentiments = [n['sentiment']['score'] for n in news if 'sentiment' in n]
        if sentiments:
            avg_sentiment = sum(sentiments) / len(sentiments)
        else:
            avg_sentiment = 0

        # Politik etki
        political_sentiment = political.get('political_sentiment', 0)

        # Birleşik skor (0-100 arası)
        combined = (avg_sentiment * 0.6 + political_sentiment * 0.4) * 50 + 50
        combined = max(0, min(100, combined))

        if combined >= 65:
            signal = "AL"
            desc = f"Haberler ve politik gelişmeler olumlu ({len(news)} haber analiz edildi)"
        elif combined <= 35:
            signal = "SAT"
            desc = f"Haberler ve politik gelişmeler olumsuz ({len(news)} haber analiz edildi)"
        else:
            signal = "TUT"
            desc = f"Haberler nötr ({len(news)} haber analiz edildi)"

        return {
            "score": round(combined, 2),
            "signal": signal,
            "news_count": len(news),
            "avg_sentiment": round(avg_sentiment, 3),
            "political_sentiment": round(political_sentiment, 3),
            "political_impact": political.get('impact', 'Nötr'),
            "description": desc,
            "latest_news": news[:5]
        }

    def _get_stock_sector(self, symbol: str) -> str:
        """Hissenin sektörünü döndürür"""
        for sector, tickers in SECTORS.items():
            if symbol in tickers:
                return sector
        return "Diğer"

    def _classify_political_impact(self, sentiment: float) -> str:
        """Politik etkiyi sınıflandırır"""
        if sentiment > 0.3:
            return "Pozitif - Sektöre olumlu politikalar"
        elif sentiment < -0.3:
            return "Negatif - Sektöre olumsuz politikalar"
        else:
            return "Nötr - Belirgin bir etki yok"

    def _clean_html(self, text: str) -> str:
        """HTML etiketlerini temizler"""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
