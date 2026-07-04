from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app


class WebUiTest(unittest.TestCase):
    def test_root_serves_html_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            response = app.test_client().get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.content_type)
            self.assertIn(b"ModNews Console", response.data)

    def test_api_health_serves_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            response = app.test_client().get("/api/health")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["service"], "modnews api")

    def test_report_route_requires_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            response = app.test_client().post("/api/report/generate", json={})

            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
