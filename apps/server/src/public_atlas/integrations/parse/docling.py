"""Docling, the parser behind the parse queue. Docling is imported inside the methods only:
the other images do not install the parse dependency group, and an import at module level
would break them at startup."""

import ctypes
import ctypes.util
import gc
import logging
from functools import cached_property
from importlib.metadata import version
from io import BytesIO
from typing import TYPE_CHECKING, Any

from public_atlas.integrations.parse.base import ParsedDocument, ParseFailed
from public_atlas.shared import diagnostics

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter
    from docling_core.types.doc import DoclingDocument

# What the parse image and CI download with `docling-tools models download`, into the
# directory `DOCLING_ARTIFACTS_PATH` names (unset, Docling uses its Hugging Face cache). Keep
# in step with `converter`: no table model, since the parse worker reads with table structure
# off. The list loader's `tables` parse uses the table model (`tableformer`), which Docling
# fetches into its Hugging Face cache on the machine that loads such a list.
MODELS = ("layout", "rapidocr")

logger = logging.getLogger(__name__)

PAGE_BREAK = "\n<!-- page -->\n"
# glibc's `mallopt` parameter for the number of malloc arenas.
M_ARENA_MAX = -8


class DoclingParser:
    """One per process, so the models load once. A PDF is converted in ranges of `page_batch`
    pages, one `convert` call each, because Docling holds every page of a call in memory until
    the call is done. `timeout` is per range, in seconds."""

    name = "docling"

    def __init__(self, *, timeout: float, page_batch: int, max_pages: int) -> None:
        self.timeout = timeout
        self.page_batch = page_batch
        self.max_pages = max_pages
        self._libc = _glibc()
        if self._libc is not None:
            # Two malloc arenas: each thread Docling and its runtimes start would otherwise
            # keep its own, and what one frees another cannot reuse.
            self._libc.mallopt(M_ARENA_MAX, 2)

    def release_memory(self) -> None:
        """Hands freed memory back to the kernel. glibc keeps what a range freed for the process,
        and the next range rarely fits the holes: without this, the process grew by hundreds
        of MB a range until the worker was killed."""
        gc.collect()
        if self._libc is not None:
            self._libc.malloc_trim(0)

    @cached_property
    def version(self) -> str:
        return version("docling")

    @cached_property
    def converter(self) -> DocumentConverter:
        """The reading-order converter the parse worker uses."""
        return self._build_converter(tables=False)

    @cached_property
    def table_converter(self) -> DocumentConverter:
        """The converter for a list PDF whose records are a table's rows: table structure on,
        so each row renders as a markdown table row, one line each."""
        return self._build_converter(tables=True)

    def _build_converter(self, *, tables: bool) -> DocumentConverter:
        """Other formats than PDF take Docling's defaults."""
        from docling.datamodel.accelerator_options import (  # noqa: PLC0415
            AcceleratorDevice,
            AcceleratorOptions,
        )
        from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
        from docling.datamodel.pipeline_options import (  # noqa: PLC0415
            HeadingHierarchyOptions,
            PdfPipelineOptions,
            RapidOcrOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: PLC0415

        pdf = PdfPipelineOptions(
            # OCR runs only where a page has no text layer.
            do_ocr=True,
            ocr_options=RapidOcrOptions(rapidocr_params=ocr_params()),
            # The agent reads a file to classify it and to quote a line; neither needs a
            # table's cells reconstructed, and the table model cost minutes per budget book.
            # A list whose records are a table's rows asks for them (`tables`).
            do_table_structure=tables,
            heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
            do_code_enrichment=False,
            do_formula_enrichment=False,
            do_picture_classification=False,
            do_picture_description=False,
            generate_page_images=False,
            generate_picture_images=False,
            enable_remote_services=False,
            # Past it Docling stops with the pages it has: a partial result, which `_convert`
            # treats as a failure.
            document_timeout=self.timeout,
            # The layout models go on the GPU when a CUDA build is installed; OCR stays on the
            # CPU regardless, see `ocr_params`.
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.AUTO),
        )
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf)}
        )

    def warm_up(self) -> None:
        from docling.datamodel.base_models import InputFormat  # noqa: PLC0415

        self.converter.initialize_pipeline(InputFormat.PDF)

    def parse(  # noqa: PLR0913 - the range and the rows asked for, all keyword
        self,
        data: bytes,
        filename: str,
        *,
        start: int = 1,
        limit: int | None = None,
        page_batch: int | None = None,
        tables: bool = False,
    ) -> ParsedDocument:
        """The pages from `start`, at most `limit` of them, in ranges of `page_batch` pages
        (the parser's own size unless given: the parse job passes 1 when an earlier attempt
        took the worker down, so the peak is one page's worth). `tables` reconstructs the
        tables, for a list read by rows."""
        batch = page_batch or self.page_batch

        def span(from_page: int) -> int:
            return batch if limit is None else max(1, min(batch, start + limit - from_page))

        pages, total = self._convert(data, filename, start=start, batch=span(start), tables=tables)
        if total > self.max_pages:
            raise ParseFailed(
                f"the file has {total} pages; files over {self.max_pages} pages are not parsed"
            )
        if total == 0:
            # A format without pages: the one call was the whole document.
            return ParsedDocument(pages=tuple(pages), parser=self.name, version=self.version)
        end = total if limit is None else min(total, start - 1 + limit)
        while start + len(pages) <= end:
            more, _ = self._convert(
                data,
                filename,
                start=start + len(pages),
                batch=span(start + len(pages)),
                tables=tables,
            )
            if not more:
                break
            pages.extend(more)
        return ParsedDocument(
            pages=tuple(pages), parser=self.name, version=self.version, first=start, total=total
        )

    def _convert(
        self, data: bytes, filename: str, *, start: int, batch: int, tables: bool = False
    ) -> tuple[list[str], int]:
        """The pages from `start` to the end of its range, and how many pages the document has:
        0 for a format without pages, whose one call is the whole document."""
        from docling.datamodel.base_models import ConversionStatus, DocumentStream  # noqa: PLC0415
        from docling.exceptions import ConversionError  # noqa: PLC0415

        stream = DocumentStream(name=filename, stream=BytesIO(data))
        page_range = (start, start + batch - 1)
        try:
            converter = self.table_converter if tables else self.converter
            result = converter.convert(
                stream, raises_on_error=False, max_num_pages=self.max_pages, page_range=page_range
            )
        except ConversionError as exc:
            raise ParseFailed(str(exc)) from exc
        total = result.input.page_count
        if total > self.max_pages:
            return [], total
        if result.status != ConversionStatus.SUCCESS:
            errors = "; ".join(error.error_message for error in result.errors)
            raise ParseFailed(f"{result.status.value}: {errors or 'no detail'}")
        pages = _pages(result.document, start=start, end=min(start + batch - 1, total))
        del result
        self.release_memory()
        logger.info(
            "Parsed pages %d-%d of %s (%d pages): process holds %s MB",
            start,
            start + len(pages) - 1,
            filename,
            total,
            diagnostics.rss_mb(),
        )
        return pages, total


def _pages(document: DoclingDocument, *, start: int, end: int) -> list[str]:
    """One entry per page, numbered by the document's own page items, so a page with nothing on
    it is an empty entry and the pages after it keep their numbers: the evidence locator is a
    page number, and Docling's page-break export would leave such a page out."""
    if not document.pages:
        markdown = document.export_to_markdown(page_break_placeholder=PAGE_BREAK)
        return [page.strip() for page in markdown.split(PAGE_BREAK)]
    return [document.export_to_markdown(page_no=number).strip() for number in range(start, end + 1)]


def _glibc() -> ctypes.CDLL | None:
    """The C library when it is glibc, which has `malloc_trim` and `mallopt`; None elsewhere."""
    name = ctypes.util.find_library("c")
    if name is None:
        return None
    try:
        libc = ctypes.CDLL(name)
        libc.malloc_trim.argtypes = (ctypes.c_size_t,)
        libc.malloc_trim.restype = ctypes.c_int
        libc.mallopt.argtypes = (ctypes.c_int, ctypes.c_int)
        libc.mallopt.restype = ctypes.c_int
    except OSError, AttributeError:
        return None
    return libc


# Every switch Docling would turn on from the accelerator device, pinned off.
_OCR_ON_CPU: dict[str, Any] = {
    "EngineConfig.onnxruntime.use_cuda": False,
    "EngineConfig.paddle.use_cuda": False,
    "EngineConfig.torch.use_cuda": False,
    **{f"{model}.use_cuda": False for model in ("Det", "Cls", "Rec")},
    **{f"{model}.use_dml": False for model in ("Det", "Cls", "Rec")},
}


def ocr_params() -> dict[str, Any]:
    """RapidOCR on the CPU, whatever device the layout models run on. Docling puts OCR on the
    GPU whenever a CUDA build is installed, and on a 6 GB card the OCR runtime could not get
    its working memory next to the layout and table models: seven of the first crawl's parses
    failed inside cuDNN. OCR's text crops are small and cheap on the otherwise idle CPU."""
    return dict(_OCR_ON_CPU)
