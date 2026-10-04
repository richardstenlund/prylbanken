import base64
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{cls.port}"
        cls.auth = "Basic " + base64.b64encode(b"admin:integration-test-password").decode()
        cls.start()

    @classmethod
    def start(cls):
        env = {**os.environ, "APP_PASSWORD": "integration-test-password",
               "DATA_DIR": cls.directory.name, "PORT": str(cls.port)}
        cls.process = subprocess.Popen([sys.executable, str(ROOT / "server.py")],
                                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError("Testservern kunde inte startas.")
            try:
                cls.request("GET", "/api/items")
                return
            except urllib.error.URLError:
                time.sleep(.05)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        raise RuntimeError("Testservern svarar inte.")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.directory.cleanup()

    def setUp(self):
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            db.execute("DELETE FROM items")

    @classmethod
    def request(cls, method, path, payload=None, auth=True, extra=None):
        headers = {"Content-Type": "application/json", **(extra or {})}
        if auth:
            headers["Authorization"] = cls.auth
        req = urllib.request.Request(cls.url + path,
                                     data=None if payload is None else json.dumps(payload).encode(),
                                     method=method, headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
            return response.status, body, response.headers

    def create(self, **overrides):
        payload = {"title": "Test", "category": "kod", "content": "  print('hej')\n",
                   "notes": "Anteckning", "tags": "python, test", **overrides}
        status, body, _ = self.request("POST", "/api/items", payload)
        self.assertEqual(status, 201, body)
        return body["id"]

    def test_authentication(self):
        self.assertEqual(self.request("GET", "/api/items", auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/items", {}, auth=False)[0], 401)

    def test_static_assets(self):
        for path in ("/", "/app.js", "/style.css"):
            status, body, headers = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/server.py")[0], 404)

    def test_create_update_delete(self):
        item_id = self.create()
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(row["content"], "  print('hej')\n")
        self.assertEqual(self.request("PUT", f"/api/items/{item_id}",
                                     {**row, "title": "Uppdaterad", "favorite": True})[0], 200)
        self.assertEqual(self.request("GET", "/api/items")[1][0]["title"], "Uppdaterad")
        self.assertEqual(self.request("DELETE", f"/api/items/{item_id}")[0], 200)
        self.assertEqual(self.request("GET", "/api/items")[1], [])

    def test_custom_category(self):
        self.create(category="Proxmox & VM")
        self.assertEqual(self.request("GET", "/api/items")[1][0]["category"], "Proxmox & VM")

    def test_invalid_inputs(self):
        for payload in (None, [], {"title": "", "category": "kod"},
                        {"title": "Test", "category": "all"},
                        {"title": "Test", "category": "A" * 61},
                        {"title": "Test", "category": "kod", "favorite": 2},
                        {"title": "Test", "category": "kod", "content": 42}):
            self.assertEqual(self.request("POST", "/api/items", payload)[0], 400)

    def test_links(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "not-a-link"):
            self.assertEqual(self.request("POST", "/api/items",
                                         {"title": "Test", "category": "lankar", "content": url})[0], 400)
        self.create(category="lankar", content="https://docs.docker.com/")

    def test_file_roundtrip_and_edit_preserves_file(self):
        original = b"@echo off\r\necho hello\r\n"
        item_id = self.create(filename="start.bat", filedata=base64.b64encode(original).decode())
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(row["filesize"], len(original))
        self.assertNotIn("filedata", row)
        self.request("PUT", f"/api/items/{item_id}", {**row, "content": "changed"})
        status, body, headers = self.request("GET", f"/api/files/{item_id}")
        self.assertEqual((status, body), (200, original))
        self.assertIn("attachment;", headers["Content-Disposition"])

    def test_empty_file_and_unicode_filename(self):
        item_id = self.create(filename="räksmörgås.txt", filedata="")
        status, body, headers = self.request("GET", f"/api/files/{item_id}")
        self.assertEqual((status, body), (200, b""))
        self.assertIn("%C3%A4", headers["Content-Disposition"])

    def test_file_limit_exact_threshold(self):
        blob = b"x" * (20 * 1024 * 1024)
        self.create(filename="large.bin", filedata=base64.b64encode(blob).decode())
        status = self.request("POST", "/api/items", {"title": "Too large", "category": "filer",
                                                   "filename": "large.bin",
                                                   "filedata": base64.b64encode(blob + b"x").decode()})[0]
        self.assertEqual(status, 400)

    def test_invalid_file(self):
        for data in ("@@@", 42):
            self.assertEqual(self.request("POST", "/api/items",
                                         {"title": "Test", "category": "filer",
                                          "filename": "test.txt", "filedata": data})[0], 400)

    def test_backup_restore(self):
        self.create(filename="file.txt", filedata="aGVq")
        backup = self.request("GET", "/api/backup")[1]
        self.assertEqual(backup["version"], 1)
        self.assertEqual(backup["items"][0]["filedata"], "aGVq")
        self.assertEqual(self.request("POST", "/api/restore", backup)[0], 201)
        self.assertEqual(len(self.request("GET", "/api/items")[1]), 2)

    def test_import_is_atomic(self):
        payload = {"version": 1, "items": [{"title": "Valid", "category": "linux"},
                                          {"title": "", "category": "kod"}]}
        self.assertEqual(self.request("POST", "/api/restore", payload)[0], 400)
        self.assertEqual(self.request("GET", "/api/items")[1], [])

    def test_origin_protection(self):
        status = self.request("POST", "/api/items", {"title": "Test", "category": "kod"},
                              extra={"Origin": "https://untrusted.invalid"})[0]
        self.assertEqual(status, 403)
        status = self.request("POST", "/api/items", {"title": "Test", "category": "kod"},
                              extra={"Origin": self.url})[0]
        self.assertEqual(status, 201)

    def test_missing_item(self):
        for method in ("PUT", "DELETE", "GET"):
            path = "/api/files/99999" if method == "GET" else "/api/items/99999"
            self.assertEqual(self.request(method, path, {"title": "Test", "category": "kod"} if method == "PUT" else None)[0], 404)

    def test_persistence_after_restart(self):
        item_id = self.create(filename="saved.txt", filedata="aGVq")
        self.process.terminate()
        self.process.wait(timeout=5)
        type(self).start()
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(row["id"], item_id)
        self.assertEqual(self.request("GET", f"/api/files/{item_id}")[1], b"hej")


if __name__ == "__main__":
    unittest.main()
