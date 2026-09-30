"""Testing call: the wire contract is shared by the board, the Harness (central_logic.py) and the
Web App (webapp/logic.js); tools/webtest/fixtures/wire_lines.json holds rows both sides must
agree on. This file runs every row through central_logic.py; tools/webtest/logic.test.js runs the
same rows through webapp/logic.js in headless Chrome. Editing a row breaks whichever side
disagrees. Expected values are literals in the JSON (from the spec's Wire contract), not computed here.
Seam: central_logic.LineReassembler and classify_line.
Glue, proven on the board: central.py.

    .venv/bin/python -m unittest discover -s tools/verify
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import central_logic as cl  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webtest", "fixtures", "wire_lines.json")
with open(FIXTURES, encoding="utf-8") as f:
    DATA = json.load(f)


def chunk_bytes(chunk):
    return chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)


class SharedWireFixtures(unittest.TestCase):
    def test_fixture_file_has_rows(self):
        self.assertGreater(len(DATA["reassemble"]), 5)
        self.assertGreater(len(DATA["classify"]), 20)

    def test_reassembly_rows(self):
        for row in DATA["reassemble"]:
            with self.subTest(row["name"]):
                r = cl.LineReassembler()
                got = [r.feed(chunk_bytes(c)) for c in row["chunks"]]
                self.assertEqual(got, row["lines"])
                self.assertEqual(r.pending, row["pending"])

    def test_classification_rows(self):
        for row in DATA["classify"]:
            with self.subTest(row["line"]):
                got = cl.classify_line(row["line"])
                self.assertEqual(got.kind, row["kind"])
                self.assertEqual(got.raw, row["line"])
                self.assertEqual(got.seq, row.get("seq"))
                self.assertEqual(got.uptime_ms, row.get("uptime_ms"))
                self.assertEqual(got.brightness, row.get("brightness"))
                self.assertEqual(got.message, row.get("message"))

    def test_deeply_nested_line_is_noise_not_an_exception(self):
        self.assertEqual(cl.classify_line('{"a":' + "[" * 100000).kind, cl.OTHER)
        self.assertEqual(cl.classify_line('{"a":' + "[" * 100000 + "]" * 100000 + "}").kind, cl.OTHER)


if __name__ == "__main__":
    unittest.main()
