import logging
from social_sentiment import SocialSentimentAnalyzer

logger = logging.getLogger(__name__)

class Brain:
    def __init__(self):
        self.sentiment_analyzer = SocialSentimentAnalyzer()

    def confirm_trade(self, symbol):
        """
        Duygu analizine bakar, %70'in altındaysa AL sinyalini engeller.
        """
        logger.info(f"{symbol} için duygu analizi yapılıyor...")
        try:
            # Sadece kritik kaynakları kontrol edeceğiz: Twitter ve Investing
            
            tw_data = self.sentiment_analyzer.scrape_twitter(symbol)
            inv_data = self.sentiment_analyzer.scrape_investing_comments(symbol)
            news_data = self.sentiment_analyzer.scrape_google_news(symbol)

            scores = []
            if tw_data.get("available"):
                scores.append(tw_data["score"])
            if inv_data.get("available"):
                scores.append(inv_data["score"])
            if news_data.get("available"):
                scores.append(news_data["score"])
                
            if not scores:
                logger.warning(f"{symbol} için sosyal veri bulunamadı, güvenli varsayılıyor.")
                return True, 50.0, "Veri Yok"

            avg_score = sum(scores) / len(scores)
            
            if avg_score < 70:
                logger.info(f"{symbol} duygu skoru yetersiz: %{avg_score:.2f} (Sınır: %70)")
                return False, avg_score, f"Duygu skoru yetersiz (Sınır: %70, Gerçekleşen: %{avg_score:.2f})"
                
            return True, avg_score, f"Duygu skoru süper (Gerçekleşen: %{avg_score:.2f})"
            
        except Exception as e:
            logger.error(f"Brain hatası: {e}")
            return False, 50.0, str(e)
