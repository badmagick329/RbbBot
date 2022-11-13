class NotOk(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class TimeoutError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
