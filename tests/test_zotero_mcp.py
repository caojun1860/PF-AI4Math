import os
import unittest
from unittest.mock import patch

from ai4math_mcp.zotero_server import (
    ZoteroReadError,
    _base_url,
    _bounded_int,
    _validate_item_key,
    compact_item,
    zotero_get_citation_metadata,
)


class ZoteroMCPTests(unittest.TestCase):
    def test_item_key_is_normalized_and_validated(self):
        self.assertEqual(_validate_item_key("up6aq5up"), "UP6AQ5UP")
        with self.assertRaises(ValueError):
            _validate_item_key("../secret")

    def test_limits_are_hard_bounded(self):
        self.assertEqual(_bounded_int(5, minimum=1, maximum=10, name="limit"), 5)
        with self.assertRaises(ValueError):
            _bounded_int(11, minimum=1, maximum=10, name="limit")

    def test_compact_item_omits_local_attachment_paths(self):
        item = {
            "data": {
                "key": "UP6AQ5UP",
                "itemType": "journalArticle",
                "title": "A result",
                "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                "path": "/private/paper.pdf",
            }
        }
        self.assertEqual(compact_item(item)["creators"], ["Ada Lovelace"])
        self.assertNotIn("path", compact_item(item))

    def test_endpoint_must_be_zotero_loopback(self):
        with patch.dict(os.environ, {"ZOTERO_LOCAL_API": "https://example.com/api"}):
            with self.assertRaises(ZoteroReadError):
                _base_url()

    @patch("ai4math_mcp.zotero_server._client")
    def test_citation_metadata_has_an_explicit_allowlist(self, client_factory):
        client_factory.return_value.get.return_value = {
            "data": {
                "key": "UP6AQ5UP",
                "title": "H^1 and dyadic H^1",
                "creators": [{"firstName": "Sergei", "lastName": "Treil"}],
                "date": "2008",
                "DOI": "10.example/demo",
                "url": "https://example.test/paper",
                "publicationTitle": "Private collection name",
                "tags": [{"tag": "private-tag"}],
            }
        }
        result = zotero_get_citation_metadata("UP6AQ5UP")
        self.assertEqual(
            set(result), {"key", "title", "creators", "date", "doi", "url"}
        )


if __name__ == "__main__":
    unittest.main()
