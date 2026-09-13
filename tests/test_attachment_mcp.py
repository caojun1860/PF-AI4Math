"""Tests for attachment-reading MCP tools (url_fetch, image_describe)."""

import unittest
from pathlib import Path
from unittest import mock

from ai4math_mcp import research_workspace_server as rws


class TestToolRegistration(unittest.TestCase):
    def test_new_tools_registered(self):
        names = {tool.name for tool in rws.mcp._tool_manager.list_tools()}
        self.assertIn("url_fetch", names)
        self.assertIn("image_describe", names)
        self.assertIn("pdf_extract", names)

    def test_image_path_rejects_non_image(self):
        with mock.patch.object(rws.Path, "resolve", return_value=Path("/tmp/note.txt")):
            with mock.patch.object(Path, "is_file", return_value=True):
                with mock.patch.object(Path, "stat") as stat:
                    stat.return_value.st_size = 100
                    with self.assertRaises(ValueError):
                        rws._image_path("/tmp/note.txt")

    def test_image_path_rejects_oversize(self):
        with mock.patch.object(rws.Path, "resolve", return_value=Path("/tmp/big.png")):
            with mock.patch.object(Path, "is_file", return_value=True):
                with mock.patch.object(Path, "stat") as stat:
                    stat.return_value.st_size = 11 * 1024 * 1024
                    with self.assertRaises(ValueError):
                        rws._image_path("/tmp/big.png")

    def test_url_fetch_rejects_bad_scheme(self):
        with self.assertRaises(ValueError):
            rws.url_fetch("ftp://example.com", "test")

    def test_url_fetch_rejects_missing_netloc(self):
        with self.assertRaises(ValueError):
            rws.url_fetch("not-a-url", "test")

    def test_url_fetch_validates_max_characters(self):
        with self.assertRaises(ValueError):
            rws.url_fetch("https://example.com", "test", max_characters=100)


if __name__ == "__main__":
    unittest.main()
