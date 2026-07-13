from __future__ import annotations

import pytest

from mirofish_agents.seed.pdf_ocr import (
    PdfOcrConfigurationError,
    PdfOcrProviderError,
    TesseractPdfOcrBackend,
    configured_pdf_ocr_backend,
)


def test_tesseract_backend_preserves_page_order_without_page_limit() -> None:
    rendered: list[tuple[bytes, float]] = []
    calls: list[tuple[str, str, int, float | None]] = []

    def render_pages(pdf_bytes: bytes, scale: float) -> list[str]:
        rendered.append((pdf_bytes, scale))
        return ["page-1", "page-2", "page-3"]

    def ocr_image(
        image: str,
        languages: str,
        psm: int,
        timeout: float | None,
    ) -> str:
        calls.append((image, languages, psm, timeout))
        return {"page-1": "第一章", "page-2": "第二章", "page-3": "Chapter Three"}[image]

    backend = TesseractPdfOcrBackend(
        languages="eng+chi_sim",
        render_scale=2.5,
        page_segmentation_mode=6,
        page_timeout_seconds=12.0,
        render_pages=render_pages,
        ocr_image=ocr_image,
    )

    assert backend.extract_text(b"%PDF-scanned") == "第一章\n\n第二章\n\nChapter Three"
    assert rendered == [(b"%PDF-scanned", 2.5)]
    assert calls == [
        ("page-1", "eng+chi_sim", 6, 12.0),
        ("page-2", "eng+chi_sim", 6, 12.0),
        ("page-3", "eng+chi_sim", 6, 12.0),
    ]


def test_tesseract_backend_fails_when_all_pages_are_blank() -> None:
    backend = TesseractPdfOcrBackend(
        render_pages=lambda _pdf, _scale: ["page"],
        ocr_image=lambda _image, _languages, _psm, _timeout: "   ",
    )

    with pytest.raises(PdfOcrProviderError) as exc_info:
        backend.extract_text(b"%PDF-scanned")

    assert exc_info.value.code == "OCR_PROVIDER_FAILED"
    assert exc_info.value.public_message == "OCR provider failed"


def test_tesseract_backend_fails_instead_of_silently_skipping_one_blank_page() -> None:
    closed: list[str] = []

    class PageImage:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    backend = TesseractPdfOcrBackend(
        render_pages=lambda _pdf, _scale: [PageImage("page-1"), PageImage("page-2")],
        ocr_image=lambda image, _languages, _psm, _timeout: (
            "recognized" if image.name == "page-1" else ""
        ),
    )

    with pytest.raises(PdfOcrProviderError) as exc_info:
        backend.extract_text(b"%PDF-scanned")

    assert exc_info.value.code == "OCR_PROVIDER_FAILED"
    assert closed == ["page-1", "page-2"]


def test_tesseract_backend_maps_missing_runtime_dependency_to_stable_failure() -> None:
    backend = TesseractPdfOcrBackend(
        render_pages=lambda _pdf, _scale: (_ for _ in ()).throw(
            ModuleNotFoundError("private dependency path")
        ),
    )

    with pytest.raises(PdfOcrProviderError) as exc_info:
        backend.extract_text(b"%PDF-scanned")

    assert exc_info.value.code == "OCR_PROVIDER_FAILED"
    assert exc_info.value.public_message == "OCR provider failed"
    assert "private dependency path" not in str(exc_info.value)


def test_configured_pdf_ocr_backend_requires_explicit_supported_backend() -> None:
    assert configured_pdf_ocr_backend({}) is None
    with pytest.raises(PdfOcrConfigurationError):
        configured_pdf_ocr_backend({"MIROFISH_OCR_BACKEND": "unknown"})


def test_configured_pdf_ocr_backend_reads_explicit_tesseract_options() -> None:
    backend = configured_pdf_ocr_backend(
        {
            "MIROFISH_OCR_BACKEND": "tesseract",
            "MIROFISH_OCR_LANGUAGES": "eng",
            "MIROFISH_OCR_RENDER_SCALE": "3",
            "MIROFISH_OCR_PAGE_SEGMENTATION_MODE": "6",
            "MIROFISH_OCR_PAGE_TIMEOUT_SECONDS": "15",
        }
    )

    assert isinstance(backend, TesseractPdfOcrBackend)
    assert backend.languages == "eng"
    assert backend.render_scale == 3
    assert backend.page_segmentation_mode == 6
    assert backend.page_timeout_seconds == 15


@pytest.mark.parametrize(
    "env",
    [
        {"MIROFISH_OCR_BACKEND": "tesseract", "MIROFISH_OCR_LANGUAGES": "eng;rm"},
        {"MIROFISH_OCR_BACKEND": "tesseract", "MIROFISH_OCR_RENDER_SCALE": "0"},
        {
            "MIROFISH_OCR_BACKEND": "tesseract",
            "MIROFISH_OCR_PAGE_SEGMENTATION_MODE": "99",
        },
        {
            "MIROFISH_OCR_BACKEND": "tesseract",
            "MIROFISH_OCR_PAGE_TIMEOUT_SECONDS": "-1",
        },
    ],
)
def test_configured_pdf_ocr_backend_rejects_unsafe_or_invalid_options(
    env: dict[str, str],
) -> None:
    with pytest.raises(PdfOcrConfigurationError):
        configured_pdf_ocr_backend(env)
