"""A parser for tests that treats the bytes as the text itself."""

from public_atlas.integrations.parse.base import PAGE_SEPARATOR, ParsedDocument, ParseFailed


class MemoryParser:
    """The test double: the bytes are the text, form feeds separate the pages, and anything
    that is not UTF-8 fails to parse."""

    name = "memory"
    version = "0"

    def warm_up(self) -> None:
        return

    def parse(
        self,
        data: bytes,
        filename: str,
        *,
        page_batch: int | None = None,  # noqa: ARG002 - the text has no ranges to hold
    ) -> ParsedDocument:
        try:
            text = data.decode()
        except UnicodeDecodeError as exc:
            raise ParseFailed(f"{filename}: not text ({exc.reason})") from None
        pages = tuple(page.strip() for page in text.split(PAGE_SEPARATOR))
        return ParsedDocument(pages=pages, parser=self.name, version=self.version)
