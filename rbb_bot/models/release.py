from tortoise import Model, fields
import pendulum


class Artist(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=510)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return self.name


class Release(Model):
    id = fields.IntField(pk=True)
    artist = fields.ForeignKeyField("models.Artist", related_name="releases")
    album_title = fields.CharField(max_length=510)
    title = fields.CharField(max_length=510)
    release_date = fields.DateField()
    release_time = fields.DatetimeField(null=True)
    release_type = fields.ForeignKeyField("models.ReleaseType", related_name="releases")
    urls = fields.JSONField(null=True)
    reddit_urls = fields.JSONField(null=True)
    timezone = fields.CharField(max_length=30, default="Asia/Seoul")

    def __repr__(self):
        return self.__str__()

    @property
    def release_time_in_tz(self):
        if not self.release_time:
            return None
        return pendulum.instance(self.release_time).in_timezone(self.timezone)

    @property
    def time_string(self):
        if not self.release_time:
            return ""
        return f"{self.release_time_in_tz.to_datetime_string()} {self.release_time_in_tz.timezone_name}"

    @property
    def date_string(self):
        return self.release_date.strftime("%Y-%m-%d")

    def __str__(self):
        time_string = self.time_string
        return (
            f"Artist: {self.artist} - Release: {self.album_title} | {self.title} "
            f"({time_string if time_string else self.date_string}) "
            f'[{self.release_type}] {self.urls if self.urls else ""}'
        )


class ReleaseType(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return self.name
