import pendulum
from pydantic import BaseModel


class PyArtist(BaseModel):
    id: int | None
    name: str

    class Config:
        orm_mode = True


class PyReleaseType(BaseModel):
    id: int | None
    name: str

    class Config:
        orm_mode = True


class PyRelease(BaseModel):
    """
    Datetimes are saved in KST
    """

    id: int | None
    release_date: pendulum.Date
    release_time: pendulum.DateTime | None
    artist: PyArtist
    title: str
    album_title: str
    release_type: PyReleaseType
    reddit_urls: list[str]
    urls: list[str] | None

    class Config:
        orm_mode = True

    def __init__(self, **data):
        super().__init__(**data)
        self.format_dates()

    def format_dates(self) -> "PyRelease":
        self.release_date = pendulum.parse(str(self.release_date)).date()
        if self.release_time:
            self.release_time = pendulum.instance(self.release_time).in_timezone(
                "Asia/Seoul"
            )
        return self

    def to_dict(self) -> dict:
        d = self.dict()
        d["id"] = int(d["id"]) if d["id"] else None
        d["artist_id"] = d["artist"]["id"]
        d["artist"] = d["artist"]["name"]
        d["release_type_id"] = d["release_type"]["id"]
        d["release_type"] = d["release_type"]["name"]
        d["release_date"] = str(d["release_date"])
        if d["release_time"]:
            d["release_time"] = str(d["release_time"])
        return d

    @staticmethod
    def from_dict(d: dict) -> "PyRelease":
        d = dict(d)
        d["artist"] = PyArtist(
            id=d["artist_id"] if "artist_id" in d else None, name=d["artist"]
        )
        d["release_type"] = PyReleaseType(
            id=d["release_type_id"] if "release_type_id" in d else None,
            name=d["release_type"],
        )
        d["release_date"] = pendulum.parse(d["release_date"]).date()
        if d["release_time"]:
            d["release_time"] = pendulum.parse(d["release_time"])
        return PyRelease(**d)
