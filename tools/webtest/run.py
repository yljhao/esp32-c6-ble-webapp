#!/usr/bin/env python3
"""Runs the Web App logic tests in headless Google Chrome (spec: Testing Decisions).

Serves the repository root on 127.0.0.1 (an ephemeral port), opens tools/webtest/index.html in the
installed Chrome (`channel="chrome"`, no browser download) and prints one PASS/FAIL line per test
and a final `RESULT:` line. Exits 0 only when every test passed and the page raised no error.
No Web Bluetooth, no board, no serial port, no PC Bluetooth adapter is touched.

    .venv/bin/python tools/webtest/run.py        (or ./build.sh test-web)
"""
import functools
import http.server
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE = "/tools/webtest/index.html"
TIMEOUT_MS = 20000


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(_Quiet, directory=ROOT)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run_page(url):
    """Open the test page in headless Chrome; return (results, page_errors)."""
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(f"page error: {e}"))
            page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
            page.on("requestfailed", lambda r: errors.append(f"request failed: {r.url}"))
            page.goto(url)
            page.wait_for_function("window.__results !== undefined", timeout=TIMEOUT_MS)
            results = page.evaluate("window.__results")
        finally:
            browser.close()
    return results, errors


def report(results, errors, out=sys.stdout):
    """Print the per-test lines and the RESULT line; return the process exit code."""
    failed = 0
    for r in results:
        if r["ok"]:
            print(f"PASS  {r['name']}", file=out)
        else:
            failed += 1
            print(f"FAIL  {r['name']}: {r.get('detail', '')}", file=out)
    for e in errors:
        print(f"FAIL  {e}", file=out)
    bad = failed + len(errors)
    if not results:
        bad += 1
        print("FAIL  the page reported no tests", file=out)
    total = len(results)
    print(f"RESULT: {'FAIL' if bad else 'PASS'} ({total - failed}/{total} tests, {len(errors)} page error(s))", file=out)
    return 1 if bad else 0


def main():
    httpd = serve()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}{PAGE}"
        try:
            results, errors = run_page(url)
        except Exception as e:  # Chrome missing, page never finished, ...
            print(f"FAIL  could not run the page: {type(e).__name__}: {e}")
            print("RESULT: FAIL (0/0 tests, page did not run)")
            return 1
        return report(results, errors)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(main())
