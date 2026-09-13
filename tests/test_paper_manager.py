from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.paper_manager import build_and_bundle, create_project, safe_slug, write_text


class PaperManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_is_question_scoped_and_idempotent(self) -> None:
        first = create_project("证明一个 UAP 定理", "对称空间 UAP", "对称空间 UAP", root=self.root)
        second = create_project("证明一个 UAP 定理", "对称空间 UAP", "对称空间 UAP", root=self.root)
        self.assertEqual(first["path"], second["path"])
        self.assertTrue((self.root / "papers" / "对称空间-UAP" / "main.tex").is_file())
        with self.assertRaises(ValueError):
            create_project("另一个问题", "标题", "对称空间 UAP", root=self.root)

    def test_scoped_writer_rejects_path_traversal(self) -> None:
        create_project("问题", "标题", "demo", root=self.root)
        result = write_text("demo", "sections/02-results.tex", "\\section{结果}\n", root=self.root)
        self.assertTrue(Path(result["path"]).is_file())
        with self.assertRaises(ValueError):
            write_text("demo", "../../secret.txt", "no", root=self.root)

    def test_bundle_contains_sources_and_manifest(self) -> None:
        create_project("问题", "标题", "demo", root=self.root)
        result = build_and_bundle("demo", root=self.root, run_latex=False)
        deliverables = self.root / "papers" / "demo" / "deliverables"
        bundle = deliverables / "demo-source.zip"
        self.assertIn(str(bundle), result["deliverables"])
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
        self.assertIn("main.tex", names)
        self.assertIn("sections/01-introduction.tex", names)
        manifest = json.loads((deliverables / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("demo-source.zip", manifest["deliverables"])

    def test_slug_keeps_readable_chinese_and_blocks_empty(self) -> None:
        self.assertEqual(safe_slug(" 对称空间 UAP "), "对称空间-UAP")
        with self.assertRaises(ValueError):
            safe_slug("...")


if __name__ == "__main__":
    unittest.main()
