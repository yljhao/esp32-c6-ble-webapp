"""Testing call: run.py's exit code is what makes a broken assertion fail `./build.sh test-web`, so its
report() gets a host test. Seam: run.report(results, errors) -> exit code. Glue, proven by the red
path in the ticket evidence: launching Chrome through Playwright.

    .venv/bin/python -m unittest discover -s tools/webtest
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # noqa: E402

OK = {"name": "a", "ok": True}
BAD = {"name": "b", "ok": False, "detail": "expected 1, got 2"}


def report(results, errors=()):
    out = io.StringIO()
    code = run.report(results, list(errors), out)
    return code, out.getvalue()


class Report(unittest.TestCase):
    def test_all_passing_exits_zero_with_a_pass_result_line(self):
        code, text = report([OK, OK])
        self.assertEqual(code, 0)
        self.assertIn("RESULT: PASS (2/2 tests, 0 page error(s))", text)

    def test_one_failing_test_exits_nonzero_and_names_it(self):
        code, text = report([OK, BAD])
        self.assertEqual(code, 1)
        self.assertIn("FAIL  b: expected 1, got 2", text)
        self.assertIn("RESULT: FAIL (1/2 tests", text)

    def test_a_page_error_fails_even_when_every_test_passed(self):
        code, text = report([OK], ["page error: boom"])
        self.assertEqual(code, 1)
        self.assertIn("RESULT: FAIL", text)

    def test_a_page_that_reports_no_tests_fails(self):
        code, text = report([])
        self.assertEqual(code, 1)
        self.assertIn("no tests", text)


if __name__ == "__main__":
    unittest.main()
