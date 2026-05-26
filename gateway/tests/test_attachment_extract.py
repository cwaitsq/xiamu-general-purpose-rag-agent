from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.attachment_extract import extract_attachment_text
from app.config import Settings


def make_settings(*, media_preprocess_enabled: bool = False, media_output_dir: str = ".") -> Settings:
    return Settings(
        gateway_mode="qmd",
        gateway_api_key="",
        qmd_command="",
        qmd_node_bin="node",
        qmd_cli_path="",
        qmd_collection="foreign_trade_kb",
        qmd_search_mode="search",
        qmd_timeout_seconds=60,
        qdrant_url="",
        qdrant_api_key="",
        qdrant_collection="",
        qdrant_distance="Cosine",
        qdrant_timeout_seconds=30,
        retrieval_score_threshold=0.35,
        embedding_base_url="",
        embedding_api_key="",
        embedding_model="Qwen3-Embedding-0.6B",
        embedding_dimensions=None,
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        llm_temperature=0.2,
        llm_enabled=False,
        app_log_dir=".",
        media_preprocess_enabled=media_preprocess_enabled,
        multimodal_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        multimodal_api_key="test-key",
        multimodal_timeout_seconds=180,
        image_ocr_model="qwen-vl-ocr",
        audio_asr_model="qwen3-asr-flash",
        video_understand_model="qwen3.5-omni-plus",
        media_max_file_bytes=20 * 1024 * 1024,
        media_output_dir=media_output_dir,
    )


class AttachmentExtractTests(unittest.TestCase):
    def test_extract_attachment_reads_plain_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_path = Path(tmp_dir) / "brief.txt"
            sample_path.write_text("hello\n\nworld", encoding="utf-8")

            result = extract_attachment_text(
                str(sample_path),
                mime_type="text/plain",
                settings=make_settings(),
            )

            self.assertEqual(result.media_type, "text")
            self.assertEqual(result.text, "hello\n\nworld")
            self.assertEqual(result.warnings, [])

    def test_extract_attachment_falls_back_to_pdf_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_path = Path(tmp_dir) / "scan.pdf"
            sample_path.write_bytes(b"%PDF-1.4 fake")

            with patch("app.attachment_extract.read_raw_text", side_effect=ValueError("scan pdf")), patch(
                "app.attachment_extract.try_read_with_media_preprocess",
                return_value="scanned pdf text",
            ):
                result = extract_attachment_text(
                    str(sample_path),
                    mime_type="application/pdf",
                    settings=make_settings(media_preprocess_enabled=True),
                )

            self.assertEqual(result.media_type, "pdf_scan")
            self.assertEqual(result.text, "scanned pdf text")

    def test_extract_attachment_uses_media_preprocess_for_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_path = Path(tmp_dir) / "catalog.png"
            sample_path.write_bytes(b"fake-image")

            with patch(
                "app.attachment_extract.try_preprocess_unsupported_path",
                return_value="image ocr text",
            ) as mock_preprocess:
                result = extract_attachment_text(
                    str(sample_path),
                    mime_type="image/png",
                    settings=make_settings(media_preprocess_enabled=True),
                )

            self.assertEqual(result.media_type, "image")
            self.assertEqual(result.text, "image ocr text")
            self.assertTrue(mock_preprocess.called)


if __name__ == "__main__":
    unittest.main()
