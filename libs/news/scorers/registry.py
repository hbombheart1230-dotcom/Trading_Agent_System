from libs.news.scorers.simple import SimpleNewsSentimentScorer
from libs.news.scorers.llm import LLMNewsSentimentScorer


def get_scorer(name: str):
    name = str(name).lower()

    if name == "simple":
        return SimpleNewsSentimentScorer()

    if name == "llm":
        return LLMNewsSentimentScorer()

    # fallback
    return SimpleNewsSentimentScorer()
