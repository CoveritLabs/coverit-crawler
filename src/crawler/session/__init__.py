from src.crawler.session.base import CrawlSessionBase
from src.crawler.session.explore import CrawlSessionExploreMixin
from src.crawler.session.sequence import CrawlSessionSequenceMixin


class CrawlSession(CrawlSessionBase, CrawlSessionExploreMixin, CrawlSessionSequenceMixin):
    pass


__all__ = ["CrawlSession"]
