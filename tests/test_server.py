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
        cls.backup_directory = tempfile.TemporaryDirectory()
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
               "DATA_DIR": cls.directory.name, "BACKUP_DIR": cls.backup_directory.name,
               "PORT": str(cls.port), **overrides}
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
        cls.backup_directory.cleanup()

    def setUp(self):
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            db.execute("DELETE FROM items")
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM login_attempts")
            db.execute("DELETE FROM registration_attempts")
            db.execute("DELETE FROM users WHERE username != 'admin'")
            for table in ("history", "activity", "projects", "saved_searches"):
                db.execute(f"DELETE FROM {table}")
        status, body, headers = self.request("POST", "/api/login",
                                            {"username": "admin", "password": "integration-test-password"}, auth=False)
        self.assertEqual(status, 200, body)
        type(self).cookie = headers["Set-Cookie"].split(";", 1)[0]
        type(self).csrf = self.request("GET", "/api/me")[1]["csrf"]
        self.request("PUT", "/api/settings", {"registration_open": True})

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

    def test_metadata_roundtrip_and_partial_edit(self):
        metadata = {"language": "python", "download_name": "backup.py", "os": "Linux",
                    "program_version": "3.13", "ports": "8080/tcp", "dependencies": "Python",
                    "tested_at": "2026-10-04", "status": "tested"}
        item_id = self.create(**metadata)
        row = next(item for item in self.request("GET", "/api/items")[1] if item["id"] == item_id)
        for key, value in metadata.items():
            self.assertEqual(row[key], value)
        self.assertEqual(self.request("PUT", f"/api/items/{item_id}",
                                      {"title": "Changed", "category": "kod", "content": "new"})[0], 200)
        row = self.request("GET", "/api/items")[1][0]
        for key, value in metadata.items():
            self.assertEqual(row[key], value)
        for bad in ({"language": "bad-language"}, {"status": "invented"},
                    {"tested_at": "2026-02-31"}, {"download_name": "../secret.txt"}):
            self.assertEqual(self.request("POST", "/api/items",
                                          {"title": "Bad", "category": "kod", **bad})[0], 400)

    def test_history_restores_content_metadata_and_file(self):
        item_id = self.create(content="original\n", language="bash", download_name="original.sh",
                              filename="original.txt", filedata="aGVq")
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(self.request("PUT", f"/api/items/{item_id}", {
            **row, "content": "changed\n", "language": "python", "download_name": "new.py",
            "filename": "new.txt", "filedata": "bmV3"})[0], 200)
        history = self.request("GET", f"/api/items/{item_id}/history")[1]
        original = next(version for version in history if version["content"] == "original\n")
        self.assertNotIn("filedata", original)
        self.assertEqual(original["actor"], "admin")
        self.assertEqual(self.request("POST", f'/api/items/{item_id}/history/{original["id"]}/restore')[0], 200)
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(row["content"], "original\n")
        self.assertEqual(row["language"], "bash")
        self.assertEqual(row["download_name"], "original.sh")
        _, file_content, headers = self.request("GET", f"/api/files/{item_id}")
        self.assertEqual(file_content, b"hej")
        self.assertIn("original.txt", headers["Content-Disposition"])
        self.assertGreaterEqual(len(self.request("GET", f"/api/items/{item_id}/history")[1]), 3)

    def test_trash_restore_and_permanent_delete(self):
        item_id = self.create(filename="saved.txt", filedata="aGVq")
        self.assertEqual(self.request("DELETE", f"/api/items/{item_id}")[0], 200)
        self.assertEqual(self.request("GET", "/api/items")[1], [])
        self.assertEqual(self.request("GET", f"/api/files/{item_id}")[0], 404)
        trash = self.request("GET", "/api/trash")[1]
        self.assertTrue(any(item["id"] == item_id for item in trash))
        self.assertEqual(self.request("POST", f"/api/items/{item_id}/restore")[0], 200)
        self.assertEqual(self.request("GET", f"/api/files/{item_id}")[1], b"hej")
        self.assertNotEqual(self.request("DELETE", f"/api/trash/{item_id}")[0], 200)
        self.request("DELETE", f"/api/items/{item_id}")
        self.assertEqual(self.request("DELETE", f"/api/trash/{item_id}")[0], 200)
        self.assertFalse(any(item["id"] == item_id for item in self.request("GET", "/api/trash")[1]))
        self.assertEqual(self.request("GET", f"/api/files/{item_id}")[0], 404)

    def test_category_hierarchy_rename_move_and_cycles(self):
        status, parent, _ = self.request("POST", "/api/categories", {"name": "My Games", "parent": None})
        self.assertEqual(status, 201, parent)
        status, child, _ = self.request("POST", "/api/categories", {"name": "My Linux", "parent": parent["key"]})
        self.assertEqual(status, 201, child)
        item_id = self.create(category=child["key"])
        self.assertEqual(self.request("PUT", f'/api/categories/{child["key"]}',
                                      {"name": "Renamed Linux", "parent": parent["key"]})[0], 200)
        self.assertEqual(self.request("PUT", f'/api/categories/{parent["key"]}',
                                      {"name": "My Games", "parent": child["key"]})[0], 400)
        self.assertEqual(self.request("DELETE", f'/api/categories/{child["key"]}', {"move_to": "kod"})[0], 200)
        row = next(item for item in self.request("GET", "/api/items")[1] if item["id"] == item_id)
        self.assertEqual(row["category"], "kod")

    def test_registration_switch_persists(self):
        self.assertEqual(self.request("PUT", "/api/settings", {"registration_open": False})[0], 200)
        self.assertFalse(self.request("GET", "/api/registration", auth=False)[1]["registration_open"])
        self.assertEqual(self.request("POST", "/api/register",
                                      {"username": "notallowed", "password": "valid-long-password"}, auth=False)[0], 403)
        self.process.terminate()
        self.process.wait(timeout=5)
        type(self).start()
        self.assertFalse(self.request("GET", "/api/registration", auth=False)[1]["registration_open"])
        self.assertEqual(self.request("PUT", "/api/settings", {"registration_open": True})[0], 200)

    def test_builtin_category_rename_parent_and_delete_guard(self):
        self.assertEqual(self.request("PUT", "/api/categories/linux",
                                      {"name": "Linux servers", "parent": "kod"})[0], 200)
        categories = self.request("GET", "/api/categories")[1]
        linux = next(category for category in categories if category["key"] == "linux")
        self.assertEqual((linux["name"], linux["parent"]), ("Linux servers", "kod"))
        self.assertEqual(self.request("DELETE", "/api/categories/linux", {"move_to": "kod"})[0], 400)
        self.request("PUT", "/api/categories/linux", {"name": "Linux", "parent": None})

    def test_category_move_includes_trash_and_preserves_link_validation(self):
        category = self.request("POST", "/api/categories", {"name": "Temporary"})[1]
        item_id = self.create(category=category["key"], content="not a URL")
        self.request("DELETE", f"/api/items/{item_id}")
        self.assertEqual(self.request("DELETE", f'/api/categories/{category["key"]}',
                                      {"move_to": "lankar"})[0], 400)
        self.assertEqual(self.request("DELETE", f'/api/categories/{category["key"]}',
                                      {"move_to": "linux"})[0], 200)
        row = next(item for item in self.request("GET", "/api/trash")[1] if item["id"] == item_id)
        self.assertEqual(row["category"], "linux")
        self.assertEqual(self.request("POST", f"/api/items/{item_id}/restore")[0], 200)

    def test_reset_revokes_existing_session_and_does_not_log_password(self):
        password = "specific-secret-reset-value"
        user = self.request("POST", "/api/users", {"username": "resetme", "password": "original-long-password"})[1]
        headers = self.request("POST", "/api/login",
                               {"username": "resetme", "password": "original-long-password"}, auth=False)[2]
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("POST", f'/api/users/{user["id"]}/reset-password', {"password": password})[0], 200)
        self.assertEqual(self.request("GET", "/api/me", extra={"Cookie": cookie})[0], 401)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "resetme", "password": "original-long-password"}, auth=False)[0], 401)
        self.assertNotIn(password, json.dumps(self.request("GET", "/api/activity")[1]))

    def test_admin_disable_reset_and_session_revocation(self):
        user = self.request("POST", "/api/users", {"username": "managed", "password": "managed-user-password"})[1]
        cookie = self.request("POST", "/api/login",
                              {"username": "managed", "password": "managed-user-password"}, auth=False)[2]["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("PUT", f'/api/users/{user["id"]}', {"active": False})[0], 200)
        self.assertEqual(self.request("GET", "/api/me", extra={"Cookie": cookie})[0], 401)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "managed", "password": "managed-user-password"}, auth=False)[0], 401)
        self.assertEqual(self.request("PUT", f'/api/users/{user["id"]}', {"active": True})[0], 200)
        self.assertEqual(self.request("POST", f'/api/users/{user["id"]}/reset-password',
                                      {"password": "managed-reset-password"})[0], 200)
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "managed", "password": "managed-reset-password"}, auth=False)[0], 200)
        me = self.request("GET", "/api/me")[1]
        self.assertEqual(self.request("PUT", f'/api/users/{me["id"]}', {"active": False})[0], 400)

    def test_activity_log_and_management_authentication(self):
        item_id = self.create(title="Activity test")
        self.request("DELETE", f"/api/items/{item_id}")
        rows = self.request("GET", "/api/activity")[1]
        self.assertTrue(any(row["actor"] == "admin" and str(item_id) in str(row["target"]) for row in rows))
        self.assertLessEqual(len(rows), 200)
        for path in ("/api/trash", "/api/categories", "/api/activity", "/api/backups", "/api/settings"):
            self.assertEqual(self.request("GET", path, auth=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/backups", extra={"X-CSRF-Token": ""})[0], 403)

    def test_backup_download_integrity_and_full_restore(self):
        project = self.request("POST", "/api/projects", {"name": "Backed up project"})[1]
        self.request("POST", "/api/users", {"username": "backupreader", "password": "backup-reader-password", "role": "reader"})
        self.request("POST", "/api/searches", {"name": "Backed up search", "filters": {"project": str(project["id"])}})
        item_id = self.create(title="Backed up", filename="file.txt", filedata="aGVq", project_ids=[project["id"]])
        status, body, _ = self.request("POST", "/api/backups")
        self.assertIn(status, (200, 201), body)
        files = self.request("GET", "/api/backups")[1]["files"]
        self.assertTrue(files)
        name = body.get("name") or max(files, key=lambda file: file["created"])["name"]
        status, raw, headers = self.request("GET", f"/api/backups/{name}")
        self.assertEqual(status, 200)
        self.assertTrue(raw.startswith(b"SQLite format 3"))
        self.assertIn("attachment", headers["Content-Disposition"])
        destination = Path(self.backup_directory.name) / "verify-download.sqlite"
        destination.write_bytes(raw)
        try:
            with closing(sqlite3.connect(destination)) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            destination.unlink()
        self.create(title="After backup")
        self.request("DELETE", f'/api/projects/{project["id"]}')
        self.assertEqual(self.request("POST", f"/api/backups/{name}/restore", {"confirm": False})[0], 400)
        self.assertEqual(self.request("POST", f"/api/backups/{name}/restore", {"confirm": True})[0], 200)
        self.assertEqual(self.request("GET", "/api/me")[0], 401)
        status, _, headers = self.request("POST", "/api/login",
                                         {"username": "admin", "password": "integration-test-password"}, auth=False)
        self.assertEqual(status, 200)
        type(self).cookie = headers["Set-Cookie"].split(";", 1)[0]
        type(self).csrf = self.request("GET", "/api/me")[1]["csrf"]
        rows = self.request("GET", "/api/items")[1]
        self.assertEqual([item["title"] for item in rows], ["Backed up"])
        self.assertEqual(self.request("GET", f"/api/files/{item_id}")[1], b"hej")
        self.assertEqual(rows[0]["project_ids"], [project["id"]])
        self.assertEqual(self.request("GET", "/api/projects")[1][0]["name"], "Backed up project")
        self.assertEqual(self.request("GET", "/api/searches")[1][0]["name"], "Backed up search")
        users = self.request("GET", "/api/users")[1]
        self.assertEqual(next(user for user in users if user["username"] == "backupreader")["role"], "reader")

    def test_corrupt_full_backup_does_not_replace_data(self):
        self.create(title="Survives failed restore")
        entry = self.request("POST", "/api/backups")[1]
        path = Path(self.backup_directory.name) / entry["name"]
        path.write_bytes(b"not SQLite")
        try:
            self.assertEqual(self.request("POST", f'/api/backups/{entry["name"]}/restore',
                                          {"confirm": True})[0], 500)
            self.assertTrue(self.request("GET", "/api/backups")[1]["last_error"])
            self.assertEqual(self.request("GET", "/api/items")[1][0]["title"], "Survives failed restore")
            self.assertEqual(self.request("GET", "/api/me")[0], 200)
        finally:
            path.unlink()

    def test_static_assets(self):
        for path in ("/", "/login", "/login.js", "/app.js", "/features.js", "/library-tools.js", "/style.css"):
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
        self.assertEqual(set(users[0]), {"id", "username", "created", "role", "active"})
        self.assertTrue(users[0]["active"])
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db:
            stored = db.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        self.assertNotIn("integration-test-password", stored)
        self.assertRegex(stored, r"^[a-f0-9]{32}:[a-f0-9]{64}$")

    def test_public_registration_unique_names_and_reader_access(self):
        payload = {"username": "PublicUser", "password": "public-user-password", "role": "admin"}
        status, user, _ = self.request("POST", "/api/register", payload, auth=False)
        self.assertEqual(status, 201)
        self.assertEqual(user["username"], "publicuser")
        self.assertEqual(user["role"], "reader")
        for username in ("PublicUser", "PUBLICUSER", "publicuser", "ADMIN"):
            self.assertEqual(self.request("POST", "/api/register",
                                          {**payload, "username": username}, auth=False)[0], 409)
        status, _, headers = self.request("POST", "/api/login", payload, auth=False)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        me = self.request("GET", "/api/me", extra={"Cookie": cookie})[1]
        self.assertEqual(me["role"], "reader")
        extra = {"Cookie": cookie, "X-CSRF-Token": me["csrf"]}
        item_id = self.create(title="Shared data")
        self.assertEqual(self.request("GET", "/api/items", extra=extra)[0], 200)
        self.assertEqual(self.request("DELETE", f"/api/items/{item_id}", extra=extra)[0], 403)
        self.assertEqual(self.request("POST", "/api/users",
                                      {"username": "createdbypublic", "password": "another-user-password"},
                                      extra=extra)[0], 403)

    def role_session(self, username, role):
        user = self.request("POST", "/api/users", {"username": username, "password": "test-role-password", "role": role})[1]
        headers = self.request("POST", "/api/login", {"username": username, "password": "test-role-password"}, auth=False)[2]
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        me = self.request("GET", "/api/me", extra={"Cookie": cookie})[1]
        return user, {"Cookie": cookie, "X-CSRF-Token": me["csrf"]}

    def test_readers_blocked_from_all_shared_mutations_and_admin_data(self):
        _, extra = self.role_session("reader", "reader")
        item_id = self.create(filename="file.txt", filedata="aGVq")
        history_id = self.request("GET", f"/api/items/{item_id}/history")[1][0]["id"]
        for method, path, payload in (
            ("POST", "/api/items", {"title": "Bad", "category": "kod"}),
            ("PUT", f"/api/items/{item_id}", {"title": "Bad", "category": "kod"}),
            ("DELETE", f"/api/items/{item_id}", None),
            ("POST", f"/api/items/{item_id}/restore", {}),
            ("POST", f"/api/items/{item_id}/history/{history_id}/restore", {}),
            ("DELETE", f"/api/trash/{item_id}", None),
            ("POST", "/api/projects", {"name": "No"}),
            ("POST", "/api/categories", {"name": "No"}),
            ("POST", "/api/examples", {"packs": ["docker"]}),
            ("POST", "/api/restore", {"version": 1, "items": []}),
            ("POST", "/api/batch/import", {"items": []}),
            ("POST", "/api/backups", {}),
        ):
            self.assertEqual(self.request(method, path, payload, extra=extra)[0], 403, path)
        for path in ("/api/users", "/api/settings", "/api/activity", "/api/backups"):
            self.assertEqual(self.request("GET", path, extra=extra)[0], 403, path)
        for path in ("/api/items", "/api/categories", "/api/projects", "/api/trash",
                     "/api/backup", f"/api/files/{item_id}", f"/api/items/{item_id}/history"):
            self.assertEqual(self.request("GET", path, extra=extra)[0], 200, path)
        search = self.request("POST", "/api/searches", {"name": "My view", "filters": {"tags": "linux"}}, extra=extra)
        self.assertEqual(search[0], 201)
        self.assertEqual(self.request("GET", "/api/searches", extra=extra)[1][0]["name"], "My view")

    def test_editor_can_change_library_but_not_administer_or_purge(self):
        _, extra = self.role_session("editor", "editor")
        status, item, _ = self.request("POST", "/api/items", {"title": "Editor", "category": "kod"}, extra=extra)
        self.assertEqual(status, 201)
        self.assertEqual(self.request("DELETE", f'/api/items/{item["id"]}', extra=extra)[0], 200)
        self.assertEqual(self.request("DELETE", f'/api/trash/{item["id"]}', extra=extra)[0], 403)
        self.assertEqual(self.request("POST", f'/api/items/{item["id"]}/restore', {}, extra=extra)[0], 200)
        self.assertEqual(self.request("POST", "/api/projects", {"name": "Editor project"}, extra=extra)[0], 201)
        for path in ("/api/users", "/api/settings", "/api/backups"):
            self.assertEqual(self.request("GET", path, extra=extra)[0], 403)
        self.assertEqual(self.request("PUT", "/api/users/1", {"role": "admin"}, extra=extra)[0], 403)

    def test_role_changes_revoke_sessions_and_protect_own_admin(self):
        user, extra = self.role_session("changer", "admin")
        self.assertEqual(self.request("PUT", f'/api/users/{user["id"]}', {"role": "reader"})[0], 200)
        self.assertEqual(self.request("GET", "/api/me", extra=extra)[0], 401)
        admin_id = self.request("GET", "/api/me")[1]["id"]
        self.assertEqual(self.request("PUT", f"/api/users/{admin_id}", {"role": "editor"})[0], 400)
        self.assertEqual(self.request("PUT", f'/api/users/{user["id"]}', {"role": "bad"})[0], 400)

    def test_projects_memberships_history_delete_and_json_roundtrip(self):
        project = self.request("POST", "/api/projects", {"name": "Home server", "description": "Shared project"})[1]
        item_id = self.create(project_ids=[project["id"]])
        self.assertEqual(self.request("GET", "/api/items")[1][0]["project_ids"], [project["id"]])
        self.request("PUT", f"/api/items/{item_id}", {"title": "Changed", "category": "kod", "content": "new"})
        self.assertEqual(self.request("GET", "/api/items")[1][0]["project_ids"], [project["id"]])
        export = self.request("GET", "/api/backup")[1]
        self.assertEqual(export["projects"][0]["name"], "Home server")
        self.assertEqual(self.request("POST", "/api/restore", export)[0], 201)
        rows = self.request("GET", "/api/items")[1]
        imported = next(item for item in rows if item["id"] != item_id)
        self.assertNotEqual(imported["project_ids"], [project["id"]])
        self.assertEqual(len(self.request("GET", "/api/projects")[1]), 2)
        history = self.request("GET", f"/api/items/{item_id}/history")[1]
        self.assertEqual(self.request("DELETE", f'/api/projects/{project["id"]}')[0], 200)
        self.assertTrue(any(item["id"] == item_id for item in self.request("GET", "/api/items")[1]))
        self.assertEqual(self.request("POST", f'/api/items/{item_id}/history/{history[-1]["id"]}/restore')[0], 200)
        restored = next(item for item in self.request("GET", "/api/items")[1] if item["id"] == item_id)
        self.assertEqual(restored["project_ids"], [])
        self.assertEqual(self.request("POST", "/api/items",
                                      {"title": "Bad", "category": "kod", "project_ids": [project["id"]]})[0], 400)

    def test_saved_searches_are_private_and_persist(self):
        _, extra = self.role_session("searchreader", "reader")
        filters = {"query": "docker linux", "tags": "docker,linux", "descendants": True, "attachments": True,
                   "category": "linux", "project": "", "sort": "title", "os": "Ubuntu"}
        saved = self.request("POST", "/api/searches", {"name": "My Linux", "filters": filters}, extra=extra)[1]
        self.assertEqual(self.request("GET", "/api/searches")[1], [])
        self.assertEqual(self.request("DELETE", f'/api/searches/{saved["id"]}')[0], 404)
        self.process.terminate(); self.process.wait(timeout=5); type(self).start()
        rows = self.request("GET", "/api/searches", extra=extra)[1]
        self.assertEqual(rows[0]["filters"]["tags"], "docker,linux")
        self.assertTrue(rows[0]["filters"]["descendants"])
        self.assertEqual(self.request("DELETE", f'/api/searches/{saved["id"]}', extra=extra)[0], 200)
        for bad in ({"attachments": "yes"}, {"project": []}, {"sort": "invalid"}, None):
            self.assertEqual(self.request("POST", "/api/searches", {"name": "Bad", "filters": bad}, extra=extra)[0], 400)

    def test_batch_preview_duplicates_atomicity_and_recheck(self):
        candidate = {"title": "script.sh", "category": "linux", "content": "  echo hello\n", "language": "bash"}
        duplicate = {**candidate, "title": "renamed.sh"}
        payload = {"items": [candidate, duplicate]}
        preview = self.request("POST", "/api/batch/preview", payload)
        self.assertEqual(preview[0], 200)
        self.assertEqual(preview[1]["items"][1]["duplicate"], {"index": 0})
        self.assertEqual(self.request("GET", "/api/items")[1], [])
        self.assertEqual(self.request("POST", "/api/batch/import", payload)[1], {"added": 1, "skipped": 1})
        preview = self.request("POST", "/api/batch/preview", {"items": [candidate]})[1]
        self.assertIn("id", preview["items"][0]["duplicate"])
        self.assertEqual(self.request("POST", "/api/batch/import", {"items": [candidate]})[1], {"added": 0, "skipped": 1})
        self.assertEqual(self.request("POST", "/api/batch/import",
                                      {"items": [candidate], "allow_duplicates": True})[1]["added"], 1)
        before = len(self.request("GET", "/api/items")[1])
        self.assertEqual(self.request("POST", "/api/batch/import",
                                      {"items": [{**candidate, "content": "different"}, {**candidate, "title": ""}]})[0], 400)
        self.assertEqual(len(self.request("GET", "/api/items")[1]), before)
        for invalid in ({"items": []}, {"items": [candidate] * 51}, {"items": [candidate], "allow_duplicates": "yes"},
                        {"items": [{**candidate, "favorite": "bad"}]}):
            self.assertEqual(self.request("POST", "/api/batch/preview", invalid)[0], 400)

    def test_batch_binary_and_utf8_byte_threshold(self):
        file = {"title": "archive.zip", "category": "filer", "filename": "archive.zip", "filedata": "AAEC"}
        result = self.request("POST", "/api/batch/import", {"items": [file]})
        self.assertEqual(result[0], 201)
        row = self.request("GET", "/api/items")[1][0]
        self.assertEqual(self.request("GET", f'/api/files/{row["id"]}')[1], b"\x00\x01\x02")
        for text, expected in (("å" * 100000, 200), ("å" * 100001, 400)):
            self.assertEqual(self.request("POST", "/api/batch/preview",
                                          {"items": [{"title": "test.txt", "category": "kod", "content": text}]})[0], expected)
        empty = {"title": "empty.txt", "category": "kod", "content": "", "download_name": "empty.txt"}
        result = self.request("POST", "/api/batch/import", {"items": [empty, {**empty, "title": "empty2.txt"}]})
        self.assertEqual(result[1], {"added": 1, "skipped": 1})
        self.assertIsNotNone(self.request("POST", "/api/batch/preview", {"items": [empty]})[1]["items"][0]["duplicate"])

    def test_batch_total_attachment_limit_exact_threshold(self):
        encoded = base64.b64encode(b"x" * (20 * 1024 * 1024)).decode()
        candidate = {"title": "limit.bin", "category": "filer", "filename": "limit.bin", "filedata": encoded}
        self.assertEqual(self.request("POST", "/api/batch/preview", {"items": [candidate]})[0], 200)
        extra = {"title": "extra.bin", "category": "filer", "filename": "extra.bin", "filedata": "eA=="}
        self.assertEqual(self.request("POST", "/api/batch/preview", {"items": [candidate, extra]})[0], 400)

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
        self.create(filename="file.txt", filedata="aGVq", language="python",
                    download_name="helper.py", status="tested", tested_at="2026-10-04")
        backup = self.request("GET", "/api/backup")[1]
        self.assertEqual(backup["version"], 1)
        self.assertEqual(backup["items"][0]["filedata"], "aGVq")
        self.assertEqual(backup["items"][0]["download_name"], "helper.py")
        self.assertNotIn("users", backup)
        self.assertNotIn("sessions", backup)
        self.assertEqual(self.request("POST", "/api/restore", backup)[0], 201)
        rows = self.request("GET", "/api/items")[1]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["language"] == "python" and row["status"] == "tested" for row in rows))

    def test_import_is_atomic(self):
        payload = {"version": 1, "items": [{"title": "Valid", "category": "linux"},
                                          {"title": "", "category": "kod"}]}
        self.assertEqual(self.request("POST", "/api/restore", payload)[0], 400)
        self.assertEqual(self.request("GET", "/api/items")[1], [])

    def test_catalog_output_and_import_all(self):
        catalog = self.request("GET", "/api/examples")[1]
        self.assertEqual(len(catalog["packs"]), 10)
        self.assertEqual(len(catalog["items"]), 190)
        self.assertEqual(len({item["key"] for item in catalog["items"]}), 190)
        self.assertEqual(sum(pack["count"] for pack in catalog["packs"]), 190)
        for item in catalog["items"]:
            self.assertTrue(item["content"])
            self.assertIn("Referens: https://", item["notes"])
        packs = [pack["id"] for pack in catalog["packs"]]
        status, result, _ = self.request("POST", "/api/examples", {"packs": packs})
        self.assertEqual(status, 201)
        self.assertEqual(result, {"added": 190, "skipped": 0})
        rows = self.request("GET", "/api/items")[1]
        self.assertEqual(len(rows), 190)
        self.assertTrue(any("Valheim" in row["title"] for row in rows))
        self.assertTrue(any("Counter-Strike 2" in row["title"] for row in rows))

    def test_catalog_idempotency_preserves_edits_and_allows_deleted_templates(self):
        result = self.request("POST", "/api/examples", {"packs": ["docker"]})[1]
        self.assertEqual(result["added"], 15)
        rows = self.request("GET", "/api/items")[1]
        edited = {**rows[0], "content": "MY CUSTOM COMMAND"}
        self.request("PUT", f'/api/items/{edited["id"]}', edited)
        result = self.request("POST", "/api/examples", {"packs": ["docker", "docker"]})[1]
        self.assertEqual(result, {"added": 0, "skipped": 15})
        self.assertTrue(any(row["content"] == "MY CUSTOM COMMAND" for row in self.request("GET", "/api/items")[1]))
        self.request("DELETE", f'/api/items/{rows[1]["id"]}')
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["docker"]})[1],
                         {"added": 1, "skipped": 14})
        latest = max(self.request("GET", "/api/items")[1], key=lambda row: row["id"])
        self.request("DELETE", f'/api/items/{latest["id"]}')
        self.create(title="Manual item reusing a deleted ID")
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["docker"]})[1],
                         {"added": 1, "skipped": 14})

    def test_expanded_catalog_pack_shapes_and_safety(self):
        catalog = self.request("GET", "/api/examples")[1]
        packs = {pack["id"]: pack["count"] for pack in catalog["packs"]}
        self.assertEqual(packs["containers"], 12)
        self.assertEqual(packs["program"], 16)
        self.assertEqual(packs["skript"], 12)
        for item in catalog["items"]:
            self.assertIn(item["pack"], packs)
            self.assertLessEqual(len(item["title"]), 200)
            self.assertLessEqual(len(item["content"]), 200000)
            self.assertLessEqual(len(item["notes"]), 10000)
            if item["pack"] == "containers":
                self.assertTrue(item["content"].startswith("services:\n"))
                self.assertIn("restart: unless-stopped", item["content"])
                self.assertIn("localhost", item["notes"])
                ports = [line.strip() for line in item["content"].splitlines()
                         if line.strip().startswith('- "')]
                self.assertTrue(all(line.startswith('- "127.0.0.1:') for line in ports))
                self.assertNotIn("privileged:", item["content"])
                self.assertNotIn("/var/run/docker.sock", item["content"])
        status, result, _ = self.request("POST", "/api/examples",
                                         {"packs": ["containers", "program", "skript"]})
        self.assertEqual(status, 201)
        self.assertEqual(result, {"added": 40, "skipped": 0})

    def test_expanded_catalog_preserves_original_sixty_templates(self):
        catalog = self.request("GET", "/api/examples")[1]
        original = catalog["items"][:60]
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            for item in original:
                db.execute("INSERT INTO items(title,category,content,notes,tags,example_key) VALUES (?,?,?,?,?,?)",
                           (item["title"], item["category"], item["content"], item["notes"], item["tags"], item["key"]))
        row = self.request("GET", "/api/items")[1][0]
        self.request("PUT", f'/api/items/{row["id"]}', {**row, "content": "MY EDITED ORIGINAL"})
        packs = [pack["id"] for pack in catalog["packs"]]
        result = self.request("POST", "/api/examples", {"packs": packs})[1]
        self.assertEqual(result, {"added": 130, "skipped": 60})
        rows = self.request("GET", "/api/items")[1]
        self.assertEqual(len(rows), 190)
        self.assertTrue(any(item["content"] == "MY EDITED ORIGINAL" for item in rows))

    def test_proxmox_pack_sources_metadata_import_and_edit_preservation(self):
        catalog = self.request("GET", "/api/examples")[1]
        pack = next(pack for pack in catalog["packs"] if pack["id"] == "proxmox")
        self.assertEqual(pack["count"], 30)
        templates = [item for item in catalog["items"] if item["pack"] == "proxmox"]
        commands = [item for item in templates if item["category"] == "proxmox"]
        links = [item for item in templates if item["category"] == "lankar"]
        self.assertEqual((len(commands), len(links)), (26, 4))
        for item in commands:
            self.assertEqual(item["language"], "bash")
            self.assertEqual(item["status"], "template")
            self.assertIn("inte körtestad", item["notes"])
            self.assertIn("Referens: https://pve.proxmox.com/pve-docs/", item["notes"])
            self.assertNotIn("--force", item["content"])
            self.assertNotIn("curl", item["content"])
            self.assertNotIn("wget", item["content"])
        by_key = {item["key"]: item for item in templates}
        self.assertTrue(by_key["proxmox-vm-restore"]["content"].startswith('qmrestore "{{backup_archive}}" "{{new_vmid}}"'))
        self.assertTrue(by_key["proxmox-ct-restore"]["content"].startswith('pct restore "{{new_ctid}}" "{{backup_archive}}"'))
        self.assertEqual(by_key["proxmox-report-script"]["download_name"], "pve-inventory.sh")
        self.assertEqual(by_key["proxmox-backup-script"]["download_name"], "pve-backup.sh")
        self.assertIn("https://github.com/community-scripts/ProxmoxVE", [item["content"] for item in links])
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["proxmox"]})[1],
                         {"added": 30, "skipped": 0})
        rows = self.request("GET", "/api/items")[1]
        edited = next(row for row in rows if row["title"] == by_key["proxmox-report-script"]["title"])
        self.assertEqual(edited["content"], by_key["proxmox-report-script"]["content"])
        self.assertEqual(edited["language"], "bash")
        self.assertEqual(edited["download_name"], "pve-inventory.sh")
        self.assertEqual(edited["status"], "template")
        self.assertEqual(edited["tested_at"], "")
        vm_restore = next(row for row in rows if row["title"] == by_key["proxmox-vm-restore"]["title"])
        self.assertEqual(vm_restore["content"], by_key["proxmox-vm-restore"]["content"])
        self.request("PUT", f'/api/items/{edited["id"]}', {**edited, "content": "# MY EDITED SCRIPT\n"})
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["proxmox"]})[1],
                         {"added": 0, "skipped": 30})
        self.assertEqual(next(row["content"] for row in self.request("GET", "/api/items")[1]
                              if row["id"] == edited["id"]), "# MY EDITED SCRIPT\n")
        self.assertTrue(any(category["key"] == "proxmox" and category["name"] == "Proxmox VE"
                            for category in self.request("GET", "/api/categories")[1]))

    def test_game_expansion_platforms_and_install_ids(self):
        catalog = self.request("GET", "/api/examples")[1]
        self.assertEqual(next(pack["count"] for pack in catalog["packs"] if pack["id"] == "spel"), 68)
        by_key = {item["key"]: item for item in catalog["items"]}
        ids = {"zomboid": 380870, "unturned": 1110390, "gmod": 4020,
               "l4d2": 222860, "svencoop": 276060, "dst": 343050, "vrising": 1829350}
        for key, app_id in ids.items():
            self.assertIn(f"+app_update {app_id} validate", by_key[f"{key}-install"]["content"])
            self.assertIn("anonymous", by_key[f"{key}-install"]["content"])
            self.assertIn(f"{key}-windows", by_key)
            if key != "vrising":
                self.assertIn(f"{key}-linux", by_key)
        self.assertNotIn("vrising-linux", by_key)
        for key in ("openttd", "mindustry", "teeworlds"):
            self.assertIn(f"{key}-linux", by_key)
            self.assertIn(f"{key}-windows", by_key)
            self.assertNotIn(f"{key}-install", by_key)
        self.assertIn("ServerHelper.sh", by_key["unturned-linux"]["content"])
        self.assertIn("Steam Guard", by_key["game-tools-steamcmd-login"]["notes"])
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["spel"]})[1],
                         {"added": 68, "skipped": 0})
        self.assertEqual(self.request("POST", "/api/examples", {"packs": ["spel"]})[1],
                         {"added": 0, "skipped": 68})

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
            db.execute("PRAGMA foreign_keys=OFF")
            tables = [row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                db.execute('DROP TABLE "' + table.replace('"', '""') + '"')
            db.execute("""CREATE TABLE items (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '', favorite INTEGER NOT NULL DEFAULT 0,
                filename TEXT, filedata BLOB, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("INSERT INTO items(id,title,category,filename,filedata) VALUES (?,?,?,?,?)",
                       (item_id, "Legacy library", "custom-legacy", "legacy.txt", b"hej"))
        type(self).start()
        status, _, headers = self.request("POST", "/api/login",
                                         {"username": "admin", "password": "integration-test-password"}, auth=False)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        rows = self.request("GET", "/api/items", extra={"Cookie": cookie})[1]
        self.assertEqual(rows[0]["title"], "Legacy library")
        self.assertEqual(self.request("GET", f"/api/files/{item_id}", extra={"Cookie": cookie})[1], b"hej")
        self.assertEqual(rows[0]["language"], "plain")
        categories = self.request("GET", "/api/categories", extra={"Cookie": cookie})[1]
        self.assertTrue(any(category["key"] == "custom-legacy" for category in categories))

    def test_upgrade_preserves_existing_admin_accounts(self):
        self.request("POST", "/api/users", {"username": "legacyadmin", "password": "legacy-admin-password"})
        self.process.terminate()
        self.process.wait(timeout=5)
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db, db:
            db.execute("ALTER TABLE users DROP COLUMN role")
        type(self).start()
        users = self.request("GET", "/api/users")[1]
        self.assertEqual({user["username"] for user in users}, {"admin", "legacyadmin"})
        self.assertTrue(all(user["role"] == "admin" for user in users))
        self.assertEqual(self.request("POST", "/api/login",
                                      {"username": "legacyadmin", "password": "legacy-admin-password"}, auth=False)[0], 200)


if __name__ == "__main__":
    unittest.main()
