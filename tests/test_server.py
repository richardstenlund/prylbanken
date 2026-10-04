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
        cls.cookie = ""
        cls.csrf = ""
        cls.start()

    @classmethod
    def start(cls, **overrides):
        env = {**os.environ, "APP_PASSWORD": "integration-test-password",
               "DATA_DIR": cls.directory.name, "PORT": str(cls.port), **overrides}
        cls.process = subprocess.Popen([sys.executable, str(ROOT / "server.py")],
                                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError("Testservern kunde inte startas.")
            try:
                cls.request("GET", "/api/health", auth=False)
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
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM login_attempts")
            db.execute("DELETE FROM registration_attempts")
            db.execute("DELETE FROM users WHERE username != 'admin'")
        status, body, headers = self.request("POST", "/api/login",
                                            {"username": "admin", "password": "integration-test-password"}, auth=False)
        self.assertEqual(status, 200, body)
        type(self).cookie = headers["Set-Cookie"].split(";", 1)[0]
        type(self).csrf = self.request("GET", "/api/me")[1]["csrf"]

    @classmethod
    def request(cls, method, path, payload=None, auth=True, extra=None):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Cookie"] = cls.cookie
            headers["X-CSRF-Token"] = cls.csrf
        headers.update(extra or {})
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
        for path in ("/api/me", "/api/users", "/api/backup", "/api/files/1"):
            self.assertEqual(self.request("GET", path, auth=False)[0], 401)
        basic = "Basic " + base64.b64encode(b"admin:integration-test-password").decode()
        self.assertEqual(self.request("GET", "/api/items", auth=False,
                                      extra={"Authorization": basic})[0], 401)

    def test_static_assets(self):
        for path in ("/", "/login", "/login.js", "/app.js", "/style.css"):
            status, body, headers = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/server.py")[0], 404)

    def test_public_login_and_health(self):
        self.assertEqual(self.request("GET", "/login", auth=False)[0], 200)
        self.assertEqual(self.request("GET", "/api/health", auth=False)[1], {"ok": True})
        self.assertIn(b'id="login-form"', self.request("GET", "/", auth=False)[1])

    def test_login_cookie_and_invalid_credentials(self):
        status, _, headers = self.request("POST", "/api/login",
                                         {"username": "ADMIN", "password": "integration-test-password"}, auth=False)
        self.assertEqual(status, 200)
        for flag in ("HttpOnly", "SameSite=Strict", "Max-Age=43200", "Path=/"):
            self.assertIn(flag, headers["Set-Cookie"])
        for username in ("admin", "missing"):
            status, body, headers = self.request("POST", "/api/login",
                                                {"username": username, "password": "wrong"}, auth=False)
            self.assertEqual(status, 401)
            self.assertEqual(body["error"], "Fel användarnamn eller lösenord.")
            self.assertNotIn("WWW-Authenticate", headers)

    def test_create_admin_and_shared_library(self):
        item_id = self.create()
        payload = {"username": "Richard", "password": "new-user-test-password"}
        status, user, _ = self.request("POST", "/api/users", payload)
        self.assertEqual(status, 201)
        self.assertEqual(user["role"], "admin")
        self.assertEqual(user["username"], "richard")
        self.assertEqual(self.request("POST", "/api/users", payload)[0], 409)
        status, _, headers = self.request("POST", "/api/login", payload, auth=False)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        me = self.request("GET", "/api/me", extra={"Cookie": cookie})[1]
        self.assertEqual(me["username"], "richard")
        self.assertEqual(self.request("GET", "/api/items", extra={"Cookie": cookie})[1][0]["id"], item_id)
        status = self.request("POST", "/api/users",
                              {"username": "another", "password": "another-user-password"},
                              extra={"Cookie": cookie, "X-CSRF-Token": me["csrf"]})[0]
        self.assertEqual(status, 201)

    def test_user_validation_and_admin_user_creation_requires_login(self):
        payload = {"username": "newuser", "password": "new-user-test-password"}
        self.assertEqual(self.request("POST", "/api/users", payload, auth=False)[0], 401)
        for username, password in (("ab", "long-enough-password"), ("bad user", "long-enough-password"),
                                   ("valid", "short"), ("valid", "x" * 257)):
            self.assertEqual(self.request("POST", "/api/users",
                                          {"username": username, "password": password})[0], 400)
        users = self.request("GET", "/api/users")[1]
        self.assertEqual(set(users[0]), {"id", "username", "created", "role"})
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db:
            stored = db.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        self.assertNotIn("integration-test-password", stored)
        self.assertRegex(stored, r"^[a-f0-9]{32}:[a-f0-9]{64}$")

    def test_public_registration_unique_names_and_admin_access(self):
        payload = {"username": "PublicUser", "password": "public-user-password"}
        status, user, _ = self.request("POST", "/api/register", payload, auth=False)
        self.assertEqual(status, 201)
        self.assertEqual(user["username"], "publicuser")
        self.assertEqual(user["role"], "admin")
        for username in ("PublicUser", "PUBLICUSER", "publicuser", "ADMIN"):
            self.assertEqual(self.request("POST", "/api/register",
                                          {**payload, "username": username}, auth=False)[0], 409)
        status, _, headers = self.request("POST", "/api/login", payload, auth=False)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        me = self.request("GET", "/api/me", extra={"Cookie": cookie})[1]
        self.assertEqual(me["role"], "admin")
        extra = {"Cookie": cookie, "X-CSRF-Token": me["csrf"]}
        item_id = self.create(title="Shared data")
        self.assertEqual(self.request("DELETE", f"/api/items/{item_id}", extra=extra)[0], 200)
        self.assertEqual(self.request("POST", "/api/users",
                                      {"username": "createdbypublic", "password": "another-user-password"},
                                      extra=extra)[0], 201)

    def test_registration_validation_origin_and_rate_limit(self):
        for payload in ([], {}, {"username": "ab", "password": "long-test-password"},
                        {"username": "newuser", "password": "short"},
                        {"username": "bad name", "password": "long-test-password"},
                        {"username": "newuser", "password": "x" * 257}):
            self.assertEqual(self.request("POST", "/api/register", payload, auth=False)[0], 400)
        payload = {"username": "newuser", "password": "long-test-password"}
        self.assertEqual(self.request("POST", "/api/register", payload, auth=False,
                                      extra={"Origin": "https://untrusted.invalid"})[0], 403)
        self.assertEqual(self.request("POST", "/api/register", payload, auth=False,
                                      extra={"Sec-Fetch-Site": "cross-site"})[0], 403)
        for index in range(5):
            self.assertEqual(self.request("POST", "/api/register",
                                          {**payload, "username": f"user{index}"}, auth=False)[0], 201)
        status, _, headers = self.request("POST", "/api/register", payload, auth=False)
        self.assertEqual(status, 429)
        self.assertEqual(headers["Retry-After"], "300")
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            db.execute("UPDATE registration_attempts SET started=0")
        self.assertEqual(self.request("POST", "/api/register", payload, auth=False)[0], 201)

    def test_csrf_required_for_mutations(self):
        for token in ("", "wrong"):
            self.assertEqual(self.request("POST", "/api/items", {"title": "Test", "category": "kod"},
                                          extra={"X-CSRF-Token": token})[0], 403)
            self.assertEqual(self.request("POST", "/api/logout", extra={"X-CSRF-Token": token})[0], 403)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "admin", "password": "integration-test-password"}, auth=False,
                                      extra={"Origin": "https://untrusted.invalid"})[0], 403)

    def test_logout_revokes_session(self):
        status, _, headers = self.request("POST", "/api/logout")
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/me")[0], 401)

    def test_expired_and_forged_sessions(self):
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            db.execute("UPDATE sessions SET expires=0")
        self.assertEqual(self.request("GET", "/api/me")[0], 401)
        for cookie in ("prylbanken_session=garbage", "prylbanken_session=" + "a" * 64):
            self.assertEqual(self.request("GET", "/api/me", extra={"Cookie": cookie})[0], 401)

    def test_login_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.request("POST", "/api/login",
                                          {"username": "admin", "password": "wrong"}, auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "admin", "password": "integration-test-password"}, auth=False)[0], 429)
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            db.execute("UPDATE login_attempts SET started=0")
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "admin", "password": "integration-test-password"}, auth=False)[0], 200)

    def test_change_password_revokes_all_sessions(self):
        self.request("POST", "/api/users", {"username": "tester", "password": "old-user-test-password"})
        cookies = []
        for _ in range(2):
            headers = self.request("POST", "/api/login", {"username": "tester", "password": "old-user-test-password"}, auth=False)[2]
            cookies.append(headers["Set-Cookie"].split(";", 1)[0])
        csrf = self.request("GET", "/api/me", extra={"Cookie": cookies[0]})[1]["csrf"]
        extra = {"Cookie": cookies[0], "X-CSRF-Token": csrf}
        self.assertEqual(self.request("PUT", "/api/password",
                                      {"current_password": "wrong", "new_password": "new-user-test-password"}, extra=extra)[0], 400)
        self.assertEqual(self.request("PUT", "/api/password",
                                      {"current_password": "old-user-test-password", "new_password": "new-user-test-password"}, extra=extra)[0], 200)
        for cookie in cookies:
            self.assertEqual(self.request("GET", "/api/me", extra={"Cookie": cookie})[0], 401)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "tester", "password": "old-user-test-password"}, auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "tester", "password": "new-user-test-password"}, auth=False)[0], 200)

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

    def test_catalog_output_and_import_all(self):
        catalog = self.request("GET", "/api/examples")[1]
        self.assertEqual(len(catalog["packs"]), 6)
        self.assertEqual(len(catalog["items"]), 60)
        self.assertEqual(len({item["key"] for item in catalog["items"]}), 60)
        self.assertEqual(sum(pack["count"] for pack in catalog["packs"]), 60)
        for item in catalog["items"]:
            self.assertTrue(item["content"])
            self.assertIn("Referens: https://", item["notes"])
        packs = [pack["id"] for pack in catalog["packs"]]
        status, result, _ = self.request("POST", "/api/examples", {"packs": packs})
        self.assertEqual(status, 201)
        self.assertEqual(result, {"added": 60, "skipped": 0})
        rows = self.request("GET", "/api/items")[1]
        self.assertEqual(len(rows), 60)
        self.assertTrue(any("Valheim" in row["title"] for row in rows))
        self.assertTrue(any("Counter-Strike 2" in row["title"] for row in rows))

    def test_catalog_idempotency_preserves_edits_and_allows_deleted_templates(self):
        result = self.request("POST", "/api/examples", {"packs": ["docker"]})[1]
        self.assertEqual(result["added"], 8)
        rows = self.request("GET", "/api/items")[1]
        edited = {**rows[0], "content": "MY CUSTOM COMMAND"}
        self.request("PUT", f'/api/items/{edited["id"]}', edited)
        result = self.request("POST", "/api/examples", {"packs": ["docker", "docker"]})[1]
        self.assertEqual(result, {"added": 0, "skipped": 8})
        self.assertTrue(any(row["content"] == "MY CUSTOM COMMAND" for row in self.request("GET", "/api/items")[1]))
        self.request("DELETE", f'/api/items/{rows[1]["id"]}')
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["docker"]})[1],
                         {"added": 1, "skipped": 7})
        latest = max(self.request("GET", "/api/items")[1], key=lambda row: row["id"])
        self.request("DELETE", f'/api/items/{latest["id"]}')
        self.create(title="Manual item reusing a deleted ID")
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["docker"]})[1],
                         {"added": 1, "skipped": 7})

    def test_catalog_requires_auth_and_valid_selection(self):
        self.assertEqual(self.request("GET", "/api/examples", auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["docker"]}, auth=False)[0], 401)
        for payload in ({}, {"packs": []}, {"packs": ["missing"]}, {"packs": [42]}, {"packs": "docker"}):
            self.assertEqual(self.request("POST", "/api/examples", payload)[0], 400)

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
        self.request("POST", "/api/users", {"username": "persisted", "password": "persisted-user-password"})
        self.process.terminate()
        self.process.wait(timeout=5)
        type(self).start(APP_PASSWORD="changed-bootstrap-password")
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(row["id"], item_id)
        self.assertEqual(self.request("GET", f"/api/files/{item_id}")[1], b"hej")
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "persisted", "password": "persisted-user-password"}, auth=False)[0], 200)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "admin", "password": "integration-test-password"}, auth=False)[0], 200)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "admin", "password": "changed-bootstrap-password"}, auth=False)[0], 401)

    def test_secure_cookie_configuration(self):
        self.process.terminate()
        self.process.wait(timeout=5)
        try:
            type(self).start(COOKIE_SECURE="true")
            headers = self.request("POST", "/api/login",
                                   {"username": "admin", "password": "integration-test-password"}, auth=False)[2]
            self.assertIn("; Secure", headers["Set-Cookie"])
        finally:
            self.process.terminate()
            self.process.wait(timeout=5)
            type(self).start(COOKIE_SECURE="false")

    def test_upgrade_from_original_database_preserves_library(self):
        item_id = self.create(title="Legacy library", filename="legacy.txt", filedata="aGVq")
        self.process.terminate()
        self.process.wait(timeout=5)
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            for table in ("sessions", "users", "login_attempts"):
                db.execute(f"DROP TABLE {table}")
            db.execute("DROP INDEX items_example_key")
            db.execute("ALTER TABLE items DROP COLUMN example_key")
        type(self).start()
        status, _, headers = self.request("POST", "/api/login",
                                         {"username": "admin", "password": "integration-test-password"}, auth=False)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        rows = self.request("GET", "/api/items", extra={"Cookie": cookie})[1]
        self.assertEqual(rows[0]["title"], "Legacy library")
        self.assertEqual(self.request("GET", f"/api/files/{item_id}", extra={"Cookie": cookie})[1], b"hej")


if __name__ == "__main__":
    unittest.main()
