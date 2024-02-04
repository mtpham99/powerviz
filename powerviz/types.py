from datetime import datetime
from typing import Literal, TypeAlias

Dates: TypeAlias = list[datetime] | Literal["latest", "today"]


class DatesTypeError(TypeError):
    def __init__(
        self,
        message: str = (
            'Invalid "dates" input. "dates" must be a '
            'list of datetimes, "latest", or "today".'
        ),
    ) -> None:
        super().__init__(message)


class FileTypeError(TypeError):
    def __init__(
        self,
        message: str = "Unrecognized filetype.",
    ) -> None:
        super().__init__(message)
