import src.models as models


def test_models_lazy_exports_include_crawl_action():
    assert "CrawlAction" in dir(models)
