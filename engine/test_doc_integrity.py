from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


import unittest

from doc_integrity import SOURCE_DOC_PAIRS, summarize_integrity


class DocIntegrityTest(unittest.TestCase):
    def test_all_source_pairs_are_registered(self) -> None:
        self.assertGreaterEqual(len(SOURCE_DOC_PAIRS), 1)

    def test_module_doc_integrity(self) -> None:
        integrity = summarize_integrity()
        self.assertTrue(integrity["ok"], integrity["failures"])


if __name__ == "__main__":
    unittest.main()
