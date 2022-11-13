class ClientMixin:
    client = None

    @classmethod
    def inject_client(cls, client):
        cls.client = client
