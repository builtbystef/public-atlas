"""One page of a list, as every list route serves it: the rows asked for, how many there are in
all, and the window they came from. The console's tables page through `total`."""

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
