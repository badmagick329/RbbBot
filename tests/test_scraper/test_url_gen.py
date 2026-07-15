import pendulum

from rbb_bot.utils.scraper import Scraper


def test_urls_include_every_month_from_january_2018_to_the_current_month(monkeypatch):
    monkeypatch.setattr(
        "rbb_bot.utils.scraper.pendulum.now",
        lambda: pendulum.datetime(2024, 3, 15, tz="UTC"),
    )

    urls = Scraper.generate_urls(object.__new__(Scraper))

    assert urls[0] == Scraper.reddit_wiki_base.format(year=2018, month="january")
    assert urls[-1] == Scraper.reddit_wiki_base.format(year=2024, month="march")
    assert len(urls) == 75
