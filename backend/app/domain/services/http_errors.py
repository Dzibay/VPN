"""Ошибки доменного слоя с HTTP-семантикой; эндпоинты переводят их в ``HTTPException``."""


class HttpServiceError(Exception):
    __slots__ = ("status_code", "detail")

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = int(status_code)
        self.detail = detail
        super().__init__(detail)
