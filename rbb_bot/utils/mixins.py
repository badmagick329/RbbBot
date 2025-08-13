from discord import Client


class ClientMixin:
    client: Client | None = None

    @classmethod
    def inject_client(cls, client):
        cls.client = client
