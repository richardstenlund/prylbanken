import base64
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import unittest
import zipfile

import test_server as integration


class WorkbenchTests(unittest.TestCase):
    setUpClass = integration.ServerTests.__dict__["setUpClass"]
    tearDownClass = integration.ServerTests.__dict__["tearDownClass"]
    start = integration.ServerTests.__dict__["start"]
    request = integration.ServerTests.__dict__["request"]
    setUp = integration.ServerTests.setUp
    create = integration.ServerTests.create

    def login_as(self, username, password="reader-test-password"):
        status, body, headers = self.request("POST", "/api/login",
            {"username": username, "password": password}, auth=False)
        if status == 200:
            type(self).cookie = headers["Set-Cookie"].split(";", 1)[0]
            type(self).csrf = self.request("GET", "/api/me")[1]["csrf"]
        return status, body, headers

    def test_personal_state_is_private_reader_writable_and_survives_restart(self):
        item = self.create()
        self.assertEqual(self.request("PUT", f"/api/personal/{item}", {"favorite": True, "opened": True})[0], 200)
        self.assertEqual(self.request("GET", "/api/items")[1][0]["favorite"], 0)
        admin_cookie, admin_csrf = type(self).cookie, type(self).csrf
        self.assertEqual(self.request("POST", "/api/users", {"username":"reader", "password":"reader-test-password",
                                                           "role":"reader"})[0], 201)
        self.assertEqual(self.login_as("reader")[0], 200)
        self.assertEqual(self.request("GET", "/api/personal")[1], [])
        self.assertEqual(self.request("PUT", f"/api/personal/{item}", {"favorite":True})[0], 200)
        self.assertEqual(self.request("POST", "/api/guides", {"title":"Forbidden"})[0], 403)
        self.assertEqual(self.request("PUT", f"/api/personal/{item}", {"favorite":"yes"})[0], 400)
        self.assertEqual(self.request("PUT", "/api/personal/999999", {"favorite":True})[0], 404)
        type(self).cookie, type(self).csrf = admin_cookie, admin_csrf
        before = self.request("GET", "/api/personal")[1]
        self.process.terminate(); self.process.wait(timeout=5); type(self).start()
        self.assertEqual(self.request("GET", "/api/personal")[1], before)
        self.request("DELETE", f"/api/items/{item}")
        self.assertEqual(self.request("GET", "/api/personal")[1], [])
        self.request("POST", f"/api/items/{item}/restore")
        self.assertEqual(self.request("GET", "/api/personal")[1], before)

    def test_guides_progress_is_private_and_changed_steps_reset_completion(self):
        item = self.create()
        payload = {"title":"Restore server", "description":"Guide", "prerequisites":"Backup first",
                   "steps":[{"text":"Check target","item_id":item},{"text":"Verify","item_id":None}]}
        status, body, _ = self.request("POST", "/api/guides", payload)
        self.assertEqual(status, 201)
        guide_id = body["id"]
        guide = self.request("GET", "/api/guides")[1][0]
        key = guide["steps"][0]["key"]
        self.assertEqual(self.request("PUT", f"/api/guides/{guide_id}/progress", {"completed":[key]})[0], 200)
        admin_cookie, admin_csrf = type(self).cookie, type(self).csrf
        self.request("POST", "/api/users", {"username":"reader", "password":"reader-test-password", "role":"reader"})
        self.login_as("reader")
        self.assertEqual(self.request("GET", "/api/guides")[1][0]["completed"], [])
        self.assertEqual(self.request("PUT", f"/api/guides/{guide_id}/progress", {"completed":[key]})[0], 200)
        self.assertEqual(self.request("PUT", f"/api/guides/{guide_id}", guide)[0], 403)
        self.assertEqual(self.request("PUT", f"/api/guides/{guide_id}/progress", {"completed":["bad"]})[0], 400)
        type(self).cookie, type(self).csrf = admin_cookie, admin_csrf
        self.assertEqual(self.request("PUT", f"/api/guides/{guide_id}", guide)[0], 200)
        self.assertEqual(self.request("GET", "/api/guides")[1][0]["completed"], [key])
        guide["steps"][0]["text"] = "Check a different target"
        self.assertEqual(self.request("PUT", f"/api/guides/{guide_id}", guide)[0], 200)
        changed = self.request("GET", "/api/guides")[1][0]
        self.assertNotEqual(changed["steps"][0]["key"], key)
        self.assertEqual(changed["completed"], [])
        self.assertEqual(self.request("POST", "/api/guides", {**payload,"steps":[]})[0], 400)
        self.assertEqual(self.request("POST", "/api/guides", {**payload,"steps":[{"text":"X","key":[]} ]})[0], 400)
        self.assertEqual(self.request("DELETE", f"/api/guides/{guide_id}")[0], 200)
        self.assertEqual(len(self.request("GET", "/api/items")[1]), 1)

    def test_relations_risk_reviews_history_export_and_no_id_reuse(self):
        first = self.create(title="Compose")
        second = self.create(title="Environment", related_ids=[first], risk="outage", review_months="2",
                             reviewed_at="2026-01-31")
        row = next(row for row in self.request("GET", "/api/items")[1] if row["id"] == second)
        self.assertEqual((row["risk"],row["review_months"],row["related_ids"]), ("outage","2",[first]))
        self.assertEqual(self.request("PUT", f"/api/items/{second}", {**row,"related_ids":[second]})[0], 400)
        for bad in ({"risk":"safe"},{"review_months":"0"},{"review_months":"121"},{"reviewed_at":"2026-02-30"},
                    {"related_ids":[999999]}, {"related_ids":[first,first]}):
            self.assertEqual(self.request("POST", "/api/items", {"title":"Bad","category":"kod",**bad})[0], 400)
        self.request("PUT", f"/api/items/{second}", {**row,"risk":"read","related_ids":[]})
        history = self.request("GET", f"/api/items/{second}/history")[1]
        self.assertIn("outage", {revision["risk"] for revision in history})
        original = next(revision for revision in history if revision["risk"] == "outage")
        self.request("POST", f'/api/items/{second}/history/{original["id"]}/restore')
        restored = next(row for row in self.request("GET", "/api/items")[1] if row["id"] == second)
        self.assertEqual(restored["related_ids"], [first])
        self.request("DELETE", f"/api/items/{first}")
        self.request("DELETE", f"/api/trash/{first}")
        self.request("DELETE", f"/api/items/{second}")
        self.request("DELETE", f"/api/trash/{second}")
        fresh = self.create(title="Unrelated")
        self.assertGreater(fresh, second)

    def test_project_zip_contains_exact_payload_and_roundtrip_relations_and_guides(self):
        project = self.request("POST", "/api/projects", {"name":"Host","description":"Offline tools"})[1]["id"]
        first = self.create(title="../../Compose", content="  services:\n  x: {}\n", download_name="compose.yaml",
                            project_ids=[project], filename="..\\bad.zip", filedata=base64.b64encode(b"\x00ZIP").decode())
        second = self.create(title="Env", content="KEY=value\n", related_ids=[first], project_ids=[project])
        self.create(title="Not in project")
        self.request("POST", "/api/guides", {"title":"Deploy","steps":[{"text":"Prepare","item_id":first}]})
        status, binary, _ = self.request("GET", f"/api/projects/{project}/export")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(binary)) as archive:
            names = archive.namelist()
            self.assertTrue(all(not name.startswith("/") and ".." not in name.split("/") and "\\" not in name for name in names))
            self.assertEqual(archive.read(f"posts/{first}-compose.yaml"), b"  services:\n  x: {}\n")
            self.assertEqual(archive.read(f"posts/{second}-Env.txt"), b"KEY=value\n")
            self.assertTrue(any(archive.read(name) == b"\x00ZIP" for name in names if name.startswith("attachments/")))
            self.assertIn("INDEX.txt", names)
            exported = json.loads(archive.read("library.json"))
            self.assertEqual(len(exported["items"]), 2)
        full = self.request("GET", "/api/backup")[1]
        self.assertEqual(len(full["guides"]), 1)
        self.assertNotIn("personal_items", full)
        status, result, _ = self.request("POST", "/api/restore", full)
        self.assertEqual(status, 201, result)
        copies = [item for item in self.request("GET", "/api/items")[1] if item["title"] == "Env"]
        self.assertEqual(len(copies), 2)
        new_env = next(item for item in copies if item["id"] != second)
        self.assertNotEqual(new_env["related_ids"], [first])
        self.assertTrue(new_env["related_ids"])
        self.assertEqual(len(self.request("GET", "/api/guides")[1]), 2)
        self.assertEqual(self.request("GET", "/api/projects/999999/export")[0], 404)

    def test_zip_limits_enforced_at_exact_boundaries_before_reading_blobs(self):
        project = self.request("POST", "/api/projects", {"name":"Limits"})[1]["id"]
        item = self.create(project_ids=[project])
        database = Path(self.directory.name) / "library.sqlite"
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE items SET content='',notes='',filename='large.bin',filedata=zeroblob(?) WHERE id=?",
                       (50 * 1024 * 1024, item))
        # Direct DB setup checks the aggregate export boundary; normal uploads remain capped at 20 MB.
        status, archive, _ = self.request("GET", f"/api/projects/{project}/export")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(zipped.getinfo(f"attachments/{item}-large.bin").file_size, 50 * 1024 * 1024)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE items SET content='x' WHERE id=?", (item,))
        self.assertEqual(self.request("GET", f"/api/projects/{project}/export")[0], 400)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE items SET filedata=NULL,filename=NULL,content='' WHERE id=?", (item,))
            db.executemany("INSERT INTO items(title,category,project_ids) VALUES ('Limit','kod',?)",
                           [(json.dumps([project]),)] * 4999)
        self.assertEqual(self.request("GET", f"/api/projects/{project}/export")[0], 200)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("INSERT INTO items(title,category,project_ids) VALUES ('Excess','kod',?)", (json.dumps([project]),))
        self.assertEqual(self.request("GET", f"/api/projects/{project}/export")[0], 400)

    def test_new_static_script_is_served_as_javascript_and_forms_never_use_get(self):
        status, body, headers = self.request("GET", "/workbench.js", auth=False)
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertIn(b"makeDialog", body)
        self.assertIn(b"boot();", self.request("GET", "/expansion.js", auth=False)[1])
        html = self.request("GET", "/login", auth=False)[1]
        self.assertIn(b'id="login-form" method="post"', html)
        self.assertIn(b'id="register-form" method="post"', html)
        self.assertIn("blob:", headers["Content-Security-Policy"])
        self.assertNotIn(b'name="code"', html)
        self.assertEqual(self.request("GET", "/api/2fa")[0], 404)
        self.assertEqual(self.request("POST", "/api/2fa/setup", {"password":"integration-test-password"})[0], 404)
        with closing(sqlite3.connect(Path(self.directory.name) / "library.sqlite")) as db:
            self.assertFalse(any(row[1].startswith("totp") for row in db.execute("PRAGMA table_info(users)")))

    def test_saved_search_preserves_private_and_review_filters(self):
        status, result, _ = self.request("POST", "/api/searches",
            {"name":"My old favorites","filters":{"personal":True,"review":True}})
        self.assertEqual(status, 201, result)
        self.assertTrue(result["filters"]["personal"])
        self.assertTrue(self.request("GET", "/api/searches")[1][0]["filters"]["review"])
        self.assertEqual(self.request("POST", "/api/searches",
            {"name":"Invalid","filters":{"personal":"true"}})[0], 400)

    def test_full_backup_restore_preserves_guides_and_personal_state(self):
        password = "integration-test-password"
        item = self.create(title="Backed up")
        self.request("PUT", f"/api/personal/{item}", {"favorite":True,"opened":True})
        self.request("POST", "/api/guides", {"title":"Backed up guide","steps":[{"text":"Check","item_id":item}]})
        guide = self.request("GET", "/api/guides")[1][0]
        self.request("PUT", f'/api/guides/{guide["id"]}/progress', {"completed":[guide["steps"][0]["key"]]})
        status, backup, _ = self.request("POST", "/api/backups", {})
        self.assertEqual(status, 201, backup)
        self.request("PUT", f"/api/personal/{item}", {"favorite":False})
        self.request("DELETE", f'/api/guides/{guide["id"]}')
        status, result, _ = self.request("POST", f'/api/backups/{backup["name"]}/restore', {"confirm":True})
        self.assertEqual(status, 200, result)
        self.assertEqual(self.request("GET", "/api/items")[0], 401)
        self.assertEqual(self.login_as("admin",password)[0], 200)
        self.assertTrue(self.request("GET", "/api/personal")[1][0]["favorite"])
        restored = self.request("GET", "/api/guides")[1][0]
        self.assertEqual(restored["completed"], [guide["steps"][0]["key"]])
