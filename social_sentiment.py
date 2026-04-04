"""
Sosyal Sentiment ve Haber Modülü — v2

Kaynaklar (hepsi ÜCRETSİZ):
1. ntscraper — Twitter/X scraping (API key gerektirmez)
2. Investing.com — BeautifulSoup ile yorum scraping
3. GoogleNews — Son 1 saatteki haber başlıkları
4. Google Trends — Hype / arama hacmi analizi
5. KAP — Kamuyu Aydınlatma Platformu haberleri
"""

import logging
import re
import os
import time
from datetime import datetime, timedelta
from urllib.parse import quote
import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ===== TÜRKÇE DUYGU KELİMELERİ =====
POSITIVE_WORDS = [
    "yükseliş", "boğa", "alım", "güçlü", "rekor", "artış", "kâr", "temettü",
    "büyüme", "olumlu", "fırsat", "kazanç", "pozitif", "destek", "hedef",
    "aşıyor", "rallye", "patlama", "talep", "güçleniyor", "yükseliyor",
    "sıçrama", "atılım", "rekor kırdı", "tavan", "beklentilerin üzerinde",
    "açığa al", "uçuş", "roket", "aya gidiyoruz", "al", "long", "bullish",
    "muhteşem", "harika", "müthiş", "iyi", "süper", "mükemmel", "başarılı",
]

NEGATIVE_WORDS = [
    "düşüş", "ayı", "satış", "zayıf", "çöküş", "kayıp", "zarar", "risk",
    "olumsuz", "tehlike", "kriz", "panik", "negatif", "baskı", "direnç",
    "kırılma", "çakılma", "fırtına", "gerileme", "düşüyor", "eriyor",
    "batıyor", "taban", "beklentilerin altında", "manipülasyon", "balon",
    "short", "bearish", "sat", "kaç", "tehdit", "ceza", "soruşturma",
    "kötü", "felaket", "endişe", "uyarı",
]


class SocialSentimentAnalyzer:
    """Çok kaynaklı ücretsiz sosyal medya ve haber sentiment analizi"""

    def __init__(self):
        self.cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    # ==================== 1. TWITTER/X (ntscraper) ====================

    def scrape_twitter(self, symbol: str, max_tweets: int = 50) -> dict:
        """
        ntscraper ile Twitter/X'ten ücretsiz tweet çeker.
        API key gerektirmez.
        """
        try:
            from ntscraper import Nitter

            scraper = Nitter(log_level=0)

            # Hashtag aramaları
            hashtags = [f"#{symbol}", f"${symbol}", f"#BIST100 {symbol}"]
            all_tweets = []

            for tag in hashtags:
                try:
                    results = scraper.get_tweets(tag, mode='hashtag', number=max_tweets // len(hashtags))
                    tweets = results.get('tweets', [])
                    for t in tweets:
                        text = t.get('text', '')
                        if text:
                            all_tweets.append(text)
                except Exception as e:
                    logger.debug(f"ntscraper hashtag hatası ({tag}): {e}")
                    continue

            if not all_tweets:
                return {
                    "symbol": symbol,
                    "source": "twitter_ntscraper",
                    "available": False,
                    "tweet_count": 0,
                    "score": 50,
                    "mood": "NÖTR",
                    "description": "Tweet bulunamadı veya erişim engeli"
                }

            # Duygu analizi
            bullish = 0
            bearish = 0
            neutral = 0

            for text in all_tweets:
                sentiment = self._analyze_turkish_sentiment(text)
                if sentiment > 0:
                    bullish += 1
                elif sentiment < 0:
                    bearish += 1
                else:
                    neutral += 1

            total = bullish + bearish
            if total > 0:
                score = (bullish / total) * 100
            else:
                score = 50

            mood = "POZİTİF" if score > 60 else ("NEGATİF" if score < 40 else "NÖTR")

            return {
                "symbol": symbol,
                "source": "twitter_ntscraper",
                "available": True,
                "tweet_count": len(all_tweets),
                "bullish": bullish,
                "bearish": bearish,
                "neutral": neutral,
                "score": round(score, 2),
                "mood": mood,
                "description": f"Twitter: {bullish} olumlu, {bearish} olumsuz, {neutral} nötr ({len(all_tweets)} tweet)"
            }

        except ImportError:
            logger.warning("ntscraper yüklü değil: pip install ntscraper")
            return {"symbol": symbol, "source": "twitter_ntscraper", "available": False,
                    "score": 50, "mood": "NÖTR", "description": "ntscraper yüklü değil"}
        except Exception as e:
            logger.error(f"Twitter scraping hatası ({symbol}): {e}")
            return {"symbol": symbol, "source": "twitter_ntscraper", "available": False,
                    "score": 50, "mood": "NÖTR", "description": str(e)}

    # ==================== 2. INVESTING.COM YORUMLARI ====================

    def scrape_investing_comments(self, symbol: str, max_comments: int = 50) -> dict:
        """
        Investing.com'dan BeautifulSoup ile ilgili hisse yorumlarını çeker.
        """
        try:
            # Investing.com Türkiye hisse sayfası arama
            search_url = f"https://tr.investing.com/search/?q={symbol}&tab=quotes"
            resp = self.session.get(search_url, timeout=10)

            if resp.status_code != 200:
                return self._empty_result(symbol, "investing.com", "Sayfa erişim hatası")

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Arama sonuçlarından ilk hisseyi bul
            links = soup.select('a[href*="/equities/"]')
            stock_url = None
            for link in links[:5]:
                href = link.get('href', '')
                text = link.get_text('', strip=True).upper()
                if symbol.upper() in text:
                    stock_url = f"https://tr.investing.com{href}" if href.startswith('/') else href
                    break

            if not stock_url:
                # Fallback: doğrudan yorum sayfasını dene
                return self._empty_result(symbol, "investing.com", "Hisse bulunamadı")

            # Yorum sayfasını çek
            comment_url = f"{stock_url}-commentary" if not stock_url.endswith('-commentary') else stock_url
            resp2 = self.session.get(comment_url, timeout=10)

            if resp2.status_code != 200:
                return self._empty_result(symbol, "investing.com", "Yorum sayfası erişilemedi")

            soup2 = BeautifulSoup(resp2.text, 'html.parser')

            # Yorumları bul
            comments = []
            comment_elements = soup2.select('.comment-text, .js-comment-text, [data-test="comment-text"]')

            if not comment_elements:
                # Alternatif selektörler
                comment_elements = soup2.select('.commentText, .comment_text_div, .comment-body')

            for elem in comment_elements[:max_comments]:
                text = elem.get_text('', strip=True)
                if len(text) > 10:
                    comments.append(text)

            if not comments:
                return self._empty_result(symbol, "investing.com", "Yorum bulunamadı")

            # Duygu analizi
            bullish = 0
            bearish = 0
            for text in comments:
                sentiment = self._analyze_turkish_sentiment(text)
                if sentiment > 0:
                    bullish += 1
                elif sentiment < 0:
                    bearish += 1

            total = bullish + bearish
            score = (bullish / total * 100) if total > 0 else 50
            mood = "POZİTİF" if score > 60 else ("NEGATİF" if score < 40 else "NÖTR")

            return {
                "symbol": symbol,
                "source": "investing.com",
                "available": True,
                "comment_count": len(comments),
                "bullish": bullish,
                "bearish": bearish,
                "score": round(score, 2),
                "mood": mood,
                "sample_comments": comments[:3],
                "description": f"Investing.com: {bullish} olumlu, {bearish} olumsuz ({len(comments)} yorum)"
            }

        except Exception as e:
            logger.error(f"Investing.com scraping hatası ({symbol}): {e}")
            return self._empty_result(symbol, "investing.com", str(e))

    # ==================== 3. GOOGLE NEWS (ÜCRETSİZ) ====================

    def scrape_google_news(self, symbol: str, company_name: str = None) -> dict:
        """
        GoogleNews kütüphanesi ile son 1 saatteki haber başlıklarını çeker.
        Politik ve ekonomik haberleri filtreler.
        """
        try:
            from GoogleNews import GoogleNews

            gn = GoogleNews(lang='tr', region='TR', period='1d')
            gn.clear()

            # Hisse adı + sembol ile ara
            search_terms = [f"{symbol} hisse"]
            if company_name:
                search_terms.append(company_name)

            all_news = []

            for term in search_terms:
                try:
                    gn.get_news(term)
                    results = gn.results(sort=True)
                    for r in results:
                        title = r.get('title', '')
                        desc = r.get('desc', '')
                        source = r.get('media', '')
                        date = r.get('date', '')
                        link = r.get('link', '')

                        if title and len(title) > 10:
                            all_news.append({
                                "title": title,
                                "description": desc,
                                "source": source,
                                "date": date,
                                "link": link,
                            })
                    gn.clear()
                except Exception as e:
                    logger.debug(f"GoogleNews arama hatası ({term}): {e}")

            # Duplicate temizle
            seen_titles = set()
            unique_news = []
            for n in all_news:
                if n["title"] not in seen_titles:
                    seen_titles.add(n["title"])
                    unique_news.append(n)

            if not unique_news:
                return {
                    "symbol": symbol,
                    "source": "google_news",
                    "available": False,
                    "news_count": 0,
                    "score": 50,
                    "news_clean": True,
                    "description": "Haber bulunamadı"
                }

            # Her haber için duygu analizi
            positive = 0
            negative = 0
            critical_negative = False

            for news in unique_news:
                full_text = f"{news['title']} {news['description']}".lower()
                sentiment = self._analyze_turkish_sentiment(full_text)

                if sentiment > 0:
                    positive += 1
                    news["sentiment"] = "POZİTİF"
                elif sentiment < 0:
                    negative += 1
                    news["sentiment"] = "NEGATİF"

                    # Kritik negatif haber kontrolü
                    critical_words = ["soruşturma", "iflas", "ceza", "dolandırıcılık",
                                      "gözaltı", "tutuklama", "konkordato", "haciz"]
                    if any(w in full_text for w in critical_words):
                        critical_negative = True
                        news["critical"] = True
                else:
                    news["sentiment"] = "NÖTR"

            total = positive + negative
            score = (positive / total * 100) if total > 0 else 50
            news_clean = negative == 0

            return {
                "symbol": symbol,
                "source": "google_news",
                "available": True,
                "news_count": len(unique_news),
                "positive": positive,
                "negative": negative,
                "score": round(score, 2),
                "news_clean": news_clean,
                "critical_negative": critical_negative,
                "mood": "POZİTİF" if score > 60 else ("NEGATİF" if score < 40 else "NÖTR"),
                "top_news": unique_news[:5],
                "description": (
                    f"Haberler: {positive} olumlu, {negative} olumsuz ({len(unique_news)} haber). "
                    f"{'🚨 KRİTİK NEGATİF HABER!' if critical_negative else '✅ Haber temiz' if news_clean else '⚠️ Olumsuz haber var'}"
                )
            }

        except ImportError:
            logger.warning("GoogleNews yüklü değil: pip install GoogleNews")
            # Fallback: feedparser ile Google News RSS
            return self._scrape_google_news_rss(symbol)
        except Exception as e:
            logger.error(f"GoogleNews hatası ({symbol}): {e}")
            return self._scrape_google_news_rss(symbol)

    def _scrape_google_news_rss(self, symbol: str) -> dict:
        """Fallback: Google News RSS ile haber çekme"""
        try:
            query = f"{symbol} hisse borsa"
            url = f"https://news.google.com/rss/search?q={quote(query)}&hl=tr&gl=TR&ceid=TR:tr"
            feed = feedparser.parse(url)

            if not feed.entries:
                return self._empty_result(symbol, "google_news_rss", "Haber yok")

            positive = 0
            negative = 0
            news_list = []

            for entry in feed.entries[:20]:
                title = entry.get('title', '')
                summary = self._clean_html(entry.get('summary', ''))
                full_text = f"{title} {summary}".lower()

                sentiment = self._analyze_turkish_sentiment(full_text)
                s_label = "POZİTİF" if sentiment > 0 else ("NEGATİF" if sentiment < 0 else "NÖTR")

                if sentiment > 0:
                    positive += 1
                elif sentiment < 0:
                    negative += 1

                news_list.append({
                    "title": title,
                    "sentiment": s_label,
                    "source": entry.get('source', {}).get('title', ''),
                })

            total = positive + negative
            score = (positive / total * 100) if total > 0 else 50

            return {
                "symbol": symbol,
                "source": "google_news_rss",
                "available": True,
                "news_count": len(news_list),
                "positive": positive,
                "negative": negative,
                "score": round(score, 2),
                "news_clean": negative == 0,
                "mood": "POZİTİF" if score > 60 else ("NEGATİF" if score < 40 else "NÖTR"),
                "top_news": news_list[:5],
                "description": f"RSS: {positive} olumlu, {negative} olumsuz ({len(news_list)} haber)"
            }

        except Exception as e:
            return self._empty_result(symbol, "google_news_rss", str(e))

    # ==================== 4. GOOGLE TRENDS ====================

    def get_google_trends(self, symbol: str, company_name: str = None) -> dict:
        """Google Trends ile arama hacmi ani artış tespiti (Hype kontrolü)"""
        try:
            from pytrends.request import TrendReq
            pytrends = TrendReq(hl='tr', tz=180)

            keywords = [symbol]
            if company_name:
                keywords.append(company_name)

            pytrends.build_payload(keywords[:1], cat=0, timeframe='now 7-d', geo='TR')
            interest = pytrends.interest_over_time()

            if interest.empty:
                return {"symbol": symbol, "trend_available": False, "score": 50,
                        "hype_level": "BİLİNMEYEN", "description": "Veri yok"}

            col = keywords[0]
            recent = interest[col].iloc[-24:].mean() if len(interest) >= 24 else interest[col].mean()
            older = interest[col].iloc[:-24].mean() if len(interest) > 24 else interest[col].mean()

            change_ratio = (recent / older) if older > 0 else 1.0

            if change_ratio > 3.0:
                hype = "ÇOK YÜKSEK"
                score = 40
                desc = f"⚠️ HYPE TEHLİKESİ! Aramalar {change_ratio:.1f}x arttı"
            elif change_ratio > 2.0:
                hype = "YÜKSEK"
                score = 45
                desc = f"Aramalar {change_ratio:.1f}x arttı"
            elif change_ratio > 1.5:
                hype = "ORTA"
                score = 55
                desc = f"Aramalarda artış ({change_ratio:.1f}x)"
            else:
                hype = "NORMAL"
                score = 50
                desc = "Aramalar normal"

            return {
                "symbol": symbol, "trend_available": True,
                "change_ratio": round(change_ratio, 2),
                "hype_level": hype, "score": score, "description": desc
            }

        except Exception as e:
            logger.debug(f"Google Trends hatası ({symbol}): {e}")
            return {"symbol": symbol, "trend_available": False, "score": 50,
                    "hype_level": "BİLİNMEYEN", "description": str(e)}

    # ==================== 5. KAP İZLEYİCİ ====================

    def check_kap_news(self, symbol: str) -> dict:
        """KAP haberlerini kontrol eder — fiyatı etkileyecek haberleri filtreler"""
        try:
            query = f"site:kap.org.tr {symbol}"
            url = f"https://news.google.com/rss/search?q={quote(query)}&hl=tr&gl=TR&ceid=TR:tr"
            feed = feedparser.parse(url)

            positive_kw = [
                "bedelsiz", "temettü", "kâr payı", "ihale kazandı", "sözleşme",
                "yeni iş", "sipariş", "gelir artışı", "kâr açıkladı", "rekor",
                "ortaklık", "birleşme", "stratejik", "yatırım", "kapasite"
            ]
            negative_kw = [
                "zarar", "ceza", "soruşturma", "dava", "haciz", "iflas",
                "spk uyarı", "bddk", "sermaye azaltımı", "borca batık",
                "konkordato", "grev", "üretim durdu", "erteleme"
            ]

            positive_count = 0
            negative_count = 0
            kap_news = []

            for entry in feed.entries[:10]:
                title = entry.get('title', '').lower()
                summary = self._clean_html(entry.get('summary', '')).lower()
                full_text = f"{title} {summary}"

                is_pos = any(kw in full_text for kw in positive_kw)
                is_neg = any(kw in full_text for kw in negative_kw)

                if is_pos:
                    positive_count += 1
                if is_neg:
                    negative_count += 1

                kap_news.append({
                    "title": entry.get('title', ''),
                    "sentiment": "POZİTİF" if is_pos else ("NEGATİF" if is_neg else "NÖTR"),
                    "is_price_impacting": is_pos or is_neg
                })

            total = positive_count + negative_count
            kap_score = (positive_count / total * 100) if total > 0 else 50
            news_clean = negative_count == 0

            return {
                "symbol": symbol,
                "kap_news": kap_news[:5],
                "positive_count": positive_count,
                "negative_count": negative_count,
                "kap_score": round(kap_score, 2),
                "news_clean": news_clean,
                "description": (
                    f"KAP: {positive_count} olumlu, {negative_count} olumsuz. "
                    f"{'✅ Temiz' if news_clean else '❌ Olumsuz haber var!'}"
                )
            }
        except Exception as e:
            logger.error(f"KAP kontrol hatası ({symbol}): {e}")
            return {"symbol": symbol, "kap_news": [], "kap_score": 50,
                    "news_clean": True, "description": f"KAP hatası: {e}"}

    # ==================== BİRLEŞİK SKOR ====================

    def get_combined_social_score(self, symbol: str, company_name: str = None) -> dict:
        """Tüm kaynakları birleştirerek final sosyal skor üretir"""
        results = {}
        scores = []
        weights = []

        # 1. Twitter (ntscraper)
        twitter = self.scrape_twitter(symbol)
        results["twitter"] = twitter
        if twitter.get("available"):
            scores.append(twitter["score"])
            weights.append(0.20)

        # 2. Investing.com yorumları
        investing = self.scrape_investing_comments(symbol)
        results["investing"] = investing
        if investing.get("available"):
            scores.append(investing["score"])
            weights.append(0.15)

        # 3. GoogleNews haberleri  
        news = self.scrape_google_news(symbol, company_name)
        results["google_news"] = news
        if news.get("available"):
            scores.append(news["score"])
            weights.append(0.25)

        # 4. KAP haberleri (en güvenilir)
        kap = self.check_kap_news(symbol)
        results["kap"] = kap
        scores.append(kap["kap_score"])
        weights.append(0.30)

        # 5. Google Trends
        trends = self.get_google_trends(symbol, company_name)
        results["google_trends"] = trends
        if trends.get("trend_available"):
            scores.append(trends["score"])
            weights.append(0.10)

        # Ağırlıklı ortalama
        total_weight = sum(weights)
        if total_weight > 0:
            combined_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
        else:
            combined_score = 50

        mood = "POZİTİF" if combined_score > 60 else ("NEGATİF" if combined_score < 40 else "NÖTR")

        # Kritik negatif haber varsa direkt NEGATİF
        if news.get("critical_negative"):
            mood = "NEGATİF"
            combined_score = min(combined_score, 25)

        return {
            "symbol": symbol,
            "combined_score": round(combined_score, 2),
            "mood": mood,
            "news_clean": kap.get("news_clean", True) and news.get("news_clean", True),
            "hype_warning": trends.get("hype_level") in ["YÜKSEK", "ÇOK YÜKSEK"],
            "critical_alert": news.get("critical_negative", False),
            "sources_used": len([s for s in scores]),
            "details": results,
            "analyzed_at": datetime.now().isoformat()
        }

    # ==================== DUYGU ANALİZİ ====================

    def _analyze_turkish_sentiment(self, text: str) -> int:
        """
        Türkçe metin duygu analizi.
        Dönüş: +1 (pozitif), -1 (negatif), 0 (nötr)
        """
        text_lower = text.lower()

        pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)

        # Emoji analizi
        positive_emojis = ['🚀', '📈', '💰', '🔥', '💎', '✅', '👍', '🟢', '⬆️', '🎯']
        negative_emojis = ['📉', '💀', '🔴', '❌', '⬇️', '😱', '🩸', '☠️']

        pos_count += sum(1 for e in positive_emojis if e in text)
        neg_count += sum(1 for e in negative_emojis if e in text)

        if pos_count > neg_count:
            return 1
        elif neg_count > pos_count:
            return -1
        return 0

    # ==================== YARDIMCI ====================

    def _clean_html(self, text: str) -> str:
        clean = re.sub(r'<[^>]+>', '', text)
        return re.sub(r'\s+', ' ', clean).strip()

    def _empty_result(self, symbol, source, reason):
        return {
            "symbol": symbol, "source": source, "available": False,
            "score": 50, "mood": "NÖTR", "description": reason
        }
