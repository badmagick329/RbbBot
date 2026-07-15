from pathlib import Path

import pendulum

from rbb_bot.utils.scraper import Scraper

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "release_table.html"



def test_parser_parses_release_rows_and_inherits_the_previous_date():
    releases = Scraper.get_release_list(
        FIXTURE_PATH.read_text(encoding="utf-8"), month="march", year="2024"
    )

    assert len(releases) == 2

    first, second = releases
    assert first.release_date == pendulum.date(2024, 3, 2)
    assert first.release_time == pendulum.datetime(2024, 3, 2, 13, 30, tz="Asia/Seoul")
    assert first.artist.name == "Artist One"
    assert first.album_title == "Album One"
    assert first.release_type.name == "Single"
    assert first.title == "Track One"
    assert first.reddit_urls == ["/r/kpop/comments/example/track-one"]

    assert second.release_date == pendulum.date(2024, 3, 2)
    assert second.release_time is None
    assert second.artist.name == "Artist Two"
    assert second.reddit_urls == []
