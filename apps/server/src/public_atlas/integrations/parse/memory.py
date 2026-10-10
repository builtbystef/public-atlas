"""A parser for tests that treats the bytes as the text itself."""

from public_atlas.integrations.parse.base import PAGE_SEPARATOR, ParsedDocument, ParseFailed


class MemoryParser:
    """The test double: the bytes are the text, form feeds separate the pages, and anything
    that is not UTF-8 fails to parse."""

    name = "memory"
    version = "0"

    def warm_up(self) -> None:
        return

    def parse(  # noqa: PLR0913 - the range and the rows asked for, all keyword
        self,
        data: bytes,
        filename: str,
        *,
        start: int = 1,
        limit: int | None = None,
        page_batch: int | None = None,  # noqa: ARG002 - the text has no ranges to hold
        tables: bool = False,  # noqa: ARG002 - the text has no tables to reconstruct
    ) -> ParsedDocument:
        try:
            text = data.decode()
        except UnicodeDecodeError as exc:
            raise ParseFailed(f"{filename}: not text ({exc.reason})") from None
        pages = [page.strip() for page in text.split(PAGE_SEPARATOR)]
        end = len(pages) if limit is None else min(len(pages), start - 1 + limit)
        return ParsedDocument(
            pages=tuple(pages[start - 1 : end]),
            parser=self.name,
            version=self.version,
            first=start,
            total=len(pages),
        )
