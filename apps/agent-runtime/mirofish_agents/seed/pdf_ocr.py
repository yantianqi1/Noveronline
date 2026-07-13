from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, Protocol


class PdfOcrError(Exception):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


class PdfOcrBackendUnconfiguredError(PdfOcrError):
    def __init__(self) -> None:
        super().__init__("OCR_BACKEND_UNCONFIGURED", "OCR backend is not configured for scanned PDF")


class PdfOcrConfigurationError(PdfOcrError):
    def __init__(self) -> None:
        super().__init__("OCR_BACKEND_MISCONFIGURED", "OCR backend is misconfigured")


class PdfOcrProviderError(PdfOcrError):
    def __init__(self) -> None:
        super().__init__("OCR_PROVIDER_FAILED", "OCR provider failed")


class PdfOcrBackend(Protocol):
    def extract_text(self, pdf_bytes: bytes) -> str:
        """Extract text from every rendered page of one scanned PDF."""


RenderPages = Callable[[bytes, float], Iterable[Any]]
OcrImage = Callable[[Any, str, int, float | None], str]


class TesseractPdfOcrBackend:
    def __init__(
        self,
        *,
        languages: str = "eng+chi_sim",
        render_scale: float = 2.0,
        page_segmentation_mode: int = 3,
        page_timeout_seconds: float | None = None,
        render_pages: RenderPages | None = None,
        ocr_image: OcrImage | None = None,
    ) -> None:
        if re.fullmatch(r"[A-Za-z0-9_+-]+", languages) is None:
            raise PdfOcrConfigurationError()
        if not math.isfinite(render_scale) or render_scale <= 0:
            raise PdfOcrConfigurationError()
        if page_segmentation_mode < 0 or page_segmentation_mode > 13:
            raise PdfOcrConfigurationError()
        if page_timeout_seconds is not None and (
            not math.isfinite(page_timeout_seconds) or page_timeout_seconds <= 0
        ):
            raise PdfOcrConfigurationError()
        self.languages = languages
        self.render_scale = render_scale
        self.page_segmentation_mode = page_segmentation_mode
        self.page_timeout_seconds = page_timeout_seconds
        self._render_pages = render_pages or _render_pdf_pages
        self._ocr_image = ocr_image or _tesseract_image_text

    def extract_text(self, pdf_bytes: bytes) -> str:
        page_texts: list[str] = []
        try:
            for image in self._render_pages(pdf_bytes, self.render_scale):
                try:
                    text = self._ocr_image(
                        image,
                        self.languages,
                        self.page_segmentation_mode,
                        self.page_timeout_seconds,
                    ).strip()
                finally:
                    _close_if_supported(image)
                if not text:
                    raise PdfOcrProviderError()
                page_texts.append(text)
        except PdfOcrError:
            raise
        except Exception as exc:
            raise PdfOcrProviderError() from exc
        extracted = "\n\n".join(page_texts).strip()
        if not extracted:
            raise PdfOcrProviderError()
        return extracted


def configured_pdf_ocr_backend(
    env: Mapping[str, str] | None = None,
) -> PdfOcrBackend | None:
    values = os.environ if env is None else env
    backend_name = values.get("MIROFISH_OCR_BACKEND", "").strip().lower()
    if not backend_name:
        return None
    if backend_name != "tesseract":
        raise PdfOcrConfigurationError()
    return TesseractPdfOcrBackend(
        languages=values.get("MIROFISH_OCR_LANGUAGES", "eng+chi_sim").strip(),
        render_scale=_positive_float(values, "MIROFISH_OCR_RENDER_SCALE", 2.0),
        page_segmentation_mode=_psm(values.get("MIROFISH_OCR_PAGE_SEGMENTATION_MODE", "3")),
        page_timeout_seconds=_optional_positive_float(
            values.get("MIROFISH_OCR_PAGE_TIMEOUT_SECONDS", "")
        ),
    )


def _render_pdf_pages(pdf_bytes: bytes, render_scale: float) -> Iterator[Any]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)
    try:
        for page_index in range(len(document)):
            page = document[page_index]
            bitmap = None
            try:
                bitmap = page.render(scale=render_scale)
                yield bitmap.to_pil()
            finally:
                _close_if_supported(bitmap)
                _close_if_supported(page)
    finally:
        _close_if_supported(document)


def _tesseract_image_text(
    image: Any,
    languages: str,
    page_segmentation_mode: int,
    timeout_seconds: float | None,
) -> str:
    import pytesseract

    kwargs: dict[str, Any] = {
        "lang": languages,
        "config": f"--psm {page_segmentation_mode}",
    }
    if timeout_seconds is not None:
        kwargs["timeout"] = timeout_seconds
    return str(pytesseract.image_to_string(image, **kwargs))


def _positive_float(values: Mapping[str, str], key: str, default: float) -> float:
    raw = values.get(key, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise PdfOcrConfigurationError() from exc
    if not math.isfinite(value) or value <= 0:
        raise PdfOcrConfigurationError()
    return value


def _optional_positive_float(raw: str) -> float | None:
    normalized = raw.strip()
    if not normalized:
        return None
    try:
        value = float(normalized)
    except ValueError as exc:
        raise PdfOcrConfigurationError() from exc
    if not math.isfinite(value) or value <= 0:
        raise PdfOcrConfigurationError()
    return value


def _psm(raw: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise PdfOcrConfigurationError() from exc
    if value < 0 or value > 13:
        raise PdfOcrConfigurationError()
    return value


def _close_if_supported(value: Any) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()
