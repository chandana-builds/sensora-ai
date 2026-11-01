class StoreUnavailable(Exception):
    """The database cannot be reached or rejected our credentials."""


class StoreError(Exception):
    pass


class QuotaExceeded(Exception):
    pass
