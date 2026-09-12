import pendulum
from tortoise.transactions import atomic
from rbb_bot.models import Artist, Release, ReleaseType
from rbb_bot.infrastructure.releases.records import PyRelease


class ReleaseRepository:
    @staticmethod
    async def read(recent: bool = True):
        """
        Get the cbs from the database

        Parameters
        ----------
        recent: bool
            If True, only get the cbs from the last 2 months
        """
        if recent:
            start_date = pendulum.now().subtract(months=2).date()
            releases = await Release.filter(
                release_date__gte=start_date
            ).prefetch_related("release_type", "artist")
        else:
            releases = await Release.all().prefetch_related("release_type", "artist")
        return [
            PyRelease.from_orm(release).format_dates().to_dict() for release in releases
        ]

    @atomic()
    async def save(self, cbs: list[dict]):
        """
        Save the cbs to the database
        """
        update_releases = list()
        create_releases = list()
        BATCH = 500

        remove_dates = [cb["release_date"] for cb in cbs if cb["id"] is None]
        remove_dates = list(set(remove_dates))
        await Release.filter(release_date__in=remove_dates).delete()

        artist_names = list(set([cb["artist"] for cb in cbs]))
        release_types_names = list(set([cb["release_type"] for cb in cbs]))
        saved_artists = await Artist.filter(name__in=artist_names)
        saved_release_types = await ReleaseType.filter(name__in=release_types_names)
        artist_names_map = {artist.name: artist for artist in saved_artists}
        release_types_names_map = {
            release_type.name: release_type for release_type in saved_release_types
        }

        for i, cb in enumerate(cbs):
            if cb["id"] is None:
                if cb["artist"] not in artist_names_map:
                    artist = Artist(name=cb["artist"])
                    artist_names_map[cb["artist"]] = artist
                    await artist.save()
                else:
                    artist = artist_names_map[cb["artist"]]
                if cb["release_type"] not in release_types_names_map:
                    release_type = ReleaseType(name=cb["release_type"])
                    release_types_names_map[cb["release_type"]] = release_type
                    await release_type.save()
                else:
                    release_type = release_types_names_map[cb["release_type"]]
                release = Release(
                    artist=artist,
                    album_title=cb["album_title"],
                    title=cb["title"],
                    release_date=cb["release_date"],
                    release_time=pendulum.parse(cb["release_time"])
                    if cb["release_time"]
                    else None,
                    release_type=release_type,
                    urls=cb["urls"],
                    reddit_urls=cb["reddit_urls"],
                )
                create_releases.append(release)
                if len(create_releases) == BATCH:
                    await Release.bulk_create(create_releases)
                    create_releases = list()
            else:
                release = await Release.get(id=cb["id"])
                release.release_time = (
                    pendulum.parse(cb["release_time"]) if cb["release_time"] else None
                )
                release.reddit_urls = cb["reddit_urls"]
                release.urls = cb["urls"] if cb["urls"] else release.urls
                update_releases.append(release)
                if len(update_releases) == BATCH:
                    await Release.bulk_update(
                        update_releases,
                        fields=["release_time", "reddit_urls", "urls"],
                    )
                    update_releases = list()

        if len(create_releases) > 0:
            await Release.bulk_create(create_releases)

        if len(update_releases) > 0:
            await Release.bulk_update(
                update_releases, fields=["release_time", "reddit_urls", "urls"]
            )
