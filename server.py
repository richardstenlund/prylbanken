import base64
import binascii
import hmac
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from catalog import PACKS, EXAMPLES
from backend import (DB_LOCK, METADATA, BUILTINS, Backups, audit, snapshot, migrate, metadata,
                     category_payload, restore_example_key)
from library import ROLES, named, attachments, fingerprint, project_ids, search_filters
import workbench

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
PASSWORD = os.environ.get("APP_PASSWORD", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_SECONDS = 12 * 60 * 60
HASH_ITERATIONS = 600000
MAX_FILE = 20 * 1024 * 1024
MAX_BODY = 29 * 1024 * 1024
BACKUPS = Backups(DATA)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), HASH_ITERATIONS).hex()
    return f"{salt}:{digest}"


def password_matches(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored)


def valid_password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 256:
        raise ValueError("Lösenord måste innehålla 12–256 tecken.")
    return value


def credentials(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltigt innehåll.")
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,40}", username):
        raise ValueError("Användarnamn: 3–40 tecken, bokstäver a–z, siffror, punkt, bindestreck eller understreck.")
    if not isinstance(password, str) or not 1 <= len(password) <= 256:
        raise ValueError("Ange ett lösenord (max 256 tecken).")
    return username.lower(), password


DUMMY_HASH = password_hash(secrets.token_hex(24))


@contextmanager
def connect():
    with DB_LOCK:
        db = sqlite3.connect(DATA / "library.sqlite", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltigt innehåll.")
    result = {}
    for name, limit in (("title", 200), ("category", 60), ("content", 200000),
                        ("notes", 10000), ("tags", 500)):
        value = payload.get(name, "")
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Ogiltigt eller för långt fält: {name}.")
        result[name] = value if name in ("content", "notes") else value.strip()
    if (not result["title"] or not result["category"] or
            result["category"] in ("all", "favorites", "__custom") or
            any(ord(c) < 32 for c in result["category"])):
        raise ValueError("Titel och en giltig kategori krävs.")
    if result["category"] == "lankar":
        url = urlsplit(result["content"])
        if url.scheme not in ("https", "http") or not url.netloc:
            raise ValueError("Länken måste börja med http:// eller https://.")
    favorite = payload.get("favorite", False)
    if not isinstance(favorite, (bool, int)) or favorite not in (0, 1):
        raise ValueError("Ogiltig favoritmarkering.")
    result["favorite"] = int(favorite)
    return result


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def reply(self, status, body, kind="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data: blob:; object-src 'none'; base-uri 'none'; "
                         "frame-ancestors 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        token = cookie.get("prylbanken_session")
        if not token or not re.fullmatch(r"[a-f0-9]{64}", token.value):
            return None
        digest = hashlib.sha256(token.value.encode()).hexdigest()
        with connect() as db:
            row = db.execute(
                "SELECT sessions.token_hash,sessions.csrf,users.id,users.username,users.role "
                "FROM sessions JOIN users ON users.id=sessions.user_id "
                "WHERE token_hash=? AND expires>? AND users.active=1", (digest, int(time.time()))).fetchone()
            return dict(row) if row else None

    def authenticated(self):
        self.user = self.session()
        if self.user:
            return True
        self.reply(401, {"error": "Logga in för att fortsätta."})
        return False

    def session_cookie(self, token, max_age=SESSION_SECONDS):
        return (f"prylbanken_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
                + ("; Secure" if COOKIE_SECURE else ""))

    def public_user(self):
        return {"id": self.user["id"], "username": self.user["username"], "role": self.user["role"],
                "csrf": self.user["csrf"]}

    def allowed(self, method, path):
        role = self.user["role"]
        admin = path.startswith(("/api/users", "/api/settings", "/api/backups")) or path == "/api/activity"
        if role != "admin" and admin:
            self.reply(403, {"error": "Administratörsbehörighet krävs."})
            return False
        personal = (path.startswith(("/api/searches", "/api/personal/")) or
                    bool(re.fullmatch(r"/api/guides/\d+/progress", path)) or
                    path in ("/api/password", "/api/logout"))
        if method != "GET" and role == "reader" and not personal:
            self.reply(403, {"error": "Läsare kan inte ändra det gemensamma biblioteket."})
            return False
        if method == "DELETE" and path.startswith("/api/trash/") and role != "admin":
            self.reply(403, {"error": "Permanent radering kräver administratörsbehörighet."})
            return False
        return True

    def read_json(self, limit=MAX_BODY):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Ogiltig storlek.")
        if not 0 < length <= limit:
            raise ValueError("För stor begäran. Filer får vara högst 20 MB.")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("JSON krävs.")
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Ogiltig JSON.")

    def do_GET(self):
        with DB_LOCK:
            self.handle_get()

    def handle_get(self):
        try:
            self.get()
        except ValueError as error:
            self.reply(400, {"error": str(error)})
        except FileNotFoundError as error:
            self.reply(404, {"error": str(error)})
        except OSError as error:
            self.log_error("Filfel: %s", error)
            self.reply(500, {"error": "Filen kunde inte läsas. Kontrollera serverloggen och volymens behörigheter."})
        except sqlite3.Error:
            import traceback
            self.log_error("Databasfel: %s", traceback.format_exc())
            self.reply(500, {"error": "Databasen kunde inte läsas. Kontrollera serverloggen."})

    def get(self):
        path = urlsplit(self.path).path
        if path in ("/", "/login", "/app.js", "/features.js", "/workbench.js", "/library-tools.js", "/login.js", "/style.css"):
            if path == "/" and not self.session():
                self.reply(303, "", headers={"Location": "/login"})
                return
            filename, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                              "/login": ("login.html", "text/html; charset=utf-8"),
                              "/login.js": ("login.js", "text/javascript; charset=utf-8"),
                              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                              "/features.js": ("features.js", "text/javascript; charset=utf-8"),
                              "/workbench.js": ("workbench.js", "text/javascript; charset=utf-8"),
                              "/library-tools.js": ("library-tools.js", "text/javascript; charset=utf-8"),
                              "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
            self.reply(200, (ROOT / "public" / filename).read_bytes(), mime)
            return
        if path == "/api/health":
            with connect() as db:
                db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            self.reply(200, {"ok": True})
            return
        if path == "/api/registration":
            with connect() as db:
                self.reply(200, self.settings(db))
            return
        if not self.authenticated():
            return
        if not self.allowed("GET", path):
            return
        if path == "/api/backups":
            self.reply(200, BACKUPS.status())
            return
        if path.startswith("/api/backups/"):
            name = path.removeprefix("/api/backups/")
            content = BACKUPS.path(name).read_bytes()
            self.reply(200, content, "application/vnd.sqlite3",
                       {"Content-Disposition": f'attachment; filename="{name}"'})
            return
        with connect() as db:
            if path == "/api/me":
                self.reply(200, self.public_user())
                return
            if workbench.get(self, db, path):
                return
            if path == "/api/users":
                rows = db.execute("SELECT id,username,created,active,role FROM users ORDER BY username").fetchall()
                self.reply(200, [{**dict(row), "active": bool(row["active"])} for row in rows])
                return
            if path == "/api/projects":
                self.reply(200, [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY name,id")])
                return
            if path == "/api/searches":
                self.reply(200, [{**dict(row), "filters": json.loads(row["filters"])} for row in db.execute(
                    "SELECT id,name,filters FROM saved_searches WHERE user_id=? ORDER BY name,id", (self.user["id"],))])
                return
            if path == "/api/settings":
                self.reply(200, self.settings(db))
                return
            if path == "/api/categories":
                self.reply(200, [dict(row) for row in db.execute("SELECT key,name,parent FROM categories ORDER BY name,key")])
                return
            if path == "/api/activity":
                self.reply(200, [dict(row) for row in db.execute(
                    "SELECT id,created,actor,action,target FROM activity ORDER BY id DESC LIMIT 200")])
                return
            history_match = re.fullmatch(r"/api/items/(\d+)/history", path)
            if history_match:
                item_id = int(history_match[1])
                if not db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
                    self.reply(404, {"error": "Posten finns inte längre."})
                    return
                self.reply(200, [{**{key: row[key] for key in ("id", "created", "actor", "title", "content", "language")},
                                 "risk": json.loads(row["snapshot"]).get("risk", "unclassified")} for row in db.execute(
                    "SELECT id,created,actor,title,content,language,snapshot FROM history WHERE item_id=? ORDER BY id DESC", (item_id,))])
                return
            if path == "/api/examples":
                self.reply(200, {"packs": [{**pack, "count": sum(item["pack"] == pack["id"] for item in EXAMPLES)}
                                          for pack in PACKS], "items": EXAMPLES})
                return
            if path in ("/api/items", "/api/trash"):
                condition = "deleted_at IS NULL" if path == "/api/items" else "deleted_at IS NOT NULL"
                rows = db.execute(
                    "SELECT id,title,category,content,notes,tags,favorite,filename,"
                    "length(filedata) AS filesize,created,updated,deleted_at,project_ids,related_ids," + ",".join(METADATA) + " FROM items WHERE " + condition + " "
                    "ORDER BY favorite DESC,updated DESC,id DESC").fetchall()
                self.reply(200, [{**dict(row), "project_ids": json.loads(row["project_ids"]),
                                 "related_ids": json.loads(row["related_ids"])} for row in rows])
                return
            if path == "/api/backup":
                rows = []
                for row in db.execute("SELECT * FROM items WHERE deleted_at IS NULL ORDER BY id"):
                    item = dict(row)
                    item["project_ids"] = json.loads(item["project_ids"])
                    item["related_ids"] = json.loads(item["related_ids"])
                    item["filedata"] = base64.b64encode(item["filedata"]).decode() if item["filedata"] is not None else None
                    rows.append(item)
                self.reply(200, {"version": 1, "items": rows,
                                "projects": [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY id")],
                                "guides": [{**dict(row), "steps": json.loads(row["steps"])}
                                           for row in db.execute("SELECT * FROM guides ORDER BY id")]},
                           headers={"Content-Disposition": 'attachment; filename="prylbanken-backup.json"'})
                return
            if path.startswith("/api/files/") and path.removeprefix("/api/files/").isdigit():
                row = db.execute("SELECT filename,filedata FROM items WHERE id=? AND deleted_at IS NULL",
                                 (int(path.rsplit("/", 1)[1]),)).fetchone()
                if row and row["filedata"] is not None:
                    from urllib.parse import quote
                    self.reply(200, row["filedata"], "application/octet-stream",
                               {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(row["filename"])})
                    return
        self.reply(404, {"error": "Hittades inte."})

    def do_POST(self):
        self.mutate("POST")

    def do_PUT(self):
        self.mutate("PUT")

    def do_DELETE(self):
        self.mutate("DELETE")

    def mutate(self, method):
        with DB_LOCK:
            self.handle_mutation(method)

    @staticmethod
    def settings(db):
        row = db.execute("SELECT value FROM settings WHERE key='registration_open'").fetchone()
        return {"registration_open": bool(row and row["value"] == "true")}

    def handle_mutation(self, method):
        path = urlsplit(self.path).path
        try:
            origin = self.headers.get("Origin")
            if (origin and urlsplit(origin).netloc != self.headers.get("Host")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.reply(403, {"error": "Begäran från en annan webbplats nekades."})
                return
            if method == "POST" and path == "/api/login":
                self.login()
                return
            if method == "POST" and path == "/api/register":
                username, password = credentials(self.read_json(8192))
                valid_password(password)
                now = int(time.time())
                with connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if not self.settings(db)["registration_open"]:
                        self.reply(403, {"error": "Registrering är stängd."})
                        return
                    db.execute("DELETE FROM registration_attempts WHERE started<=?", (now - 300,))
                    address = self.client_address[0]
                    attempt = db.execute("SELECT attempts FROM registration_attempts WHERE address=?", (address,)).fetchone()
                    if attempt and attempt["attempts"] >= 5:
                        db.commit()
                        self.reply(429, {"error": "För många registreringsförsök. Vänta fem minuter."},
                                   headers={"Retry-After": "300"})
                        return
                    db.execute("INSERT INTO registration_attempts(address,started,attempts) VALUES (?,?,1) "
                               "ON CONFLICT(address) DO UPDATE SET attempts=attempts+1", (address, now))
                    self.create_user(db, username, password)
                return
            if not self.authenticated():
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode(), self.user["csrf"].encode()):
                self.reply(403, {"error": "Säkerhetstoken saknas eller har gått ut. Ladda om sidan."})
                return
            if not self.allowed(method, path):
                return
            if method == "POST" and path == "/api/backups":
                entry = BACKUPS.create()
                with connect() as db:
                    audit(db, self.user["username"], "backup.create", entry["name"])
                self.reply(201, entry)
                return
            backup_restore = re.fullmatch(r"/api/backups/([^/]+)/restore", path)
            if method == "POST" and backup_restore:
                payload = self.read_json(8192)
                if not isinstance(payload, dict) or payload.get("confirm") is not True:
                    raise ValueError("Bekräfta återställningen med confirm: true.")
                safety = BACKUPS.restore(backup_restore[1], self.user["username"])
                self.reply(200, {"ok": True, "safety_backup": safety},
                           headers={"Set-Cookie": self.session_cookie("", 0)})
                return
            with connect() as db:
                if workbench.mutate(self, db, method, path):
                    return
                if self.manage(db, method, path):
                    return
                if self.library_management(db, method, path):
                    return
                if method == "POST" and path == "/api/examples":
                    payload = self.read_json(8192)
                    selected = payload.get("packs") if isinstance(payload, dict) else None
                    if (not isinstance(selected, list) or not selected or
                            any(not isinstance(key, str) or key not in {p["id"] for p in PACKS} for key in selected)):
                        raise ValueError("Välj minst ett giltigt startpaket.")
                    db.execute("BEGIN IMMEDIATE")
                    added = skipped = 0
                    for example in EXAMPLES:
                        if example["pack"] not in selected:
                            continue
                        existing = db.execute("SELECT id FROM items WHERE example_key=?",
                                              (example["key"],)).fetchone()
                        if existing:
                            skipped += 1
                            continue
                        item_id = self.save(db, example)
                        db.execute("UPDATE items SET example_key=? WHERE id=?", (example["key"], item_id))
                        snapshot(db, item_id, self.user["username"])
                        added += 1
                    audit(db, self.user["username"], "examples.import", f"{added} added, {skipped} skipped")
                    db.commit()
                    self.reply(201, {"added": added, "skipped": skipped})
                    return
                if method == "POST" and path == "/api/logout":
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (self.user["token_hash"],))
                    db.commit()
                    self.reply(200, {"ok": True},
                               headers={"Set-Cookie": self.session_cookie("", 0)})
                    return
                if method == "POST" and path == "/api/users":
                    payload = self.read_json(8192)
                    username, password = credentials(payload)
                    valid_password(password)
                    self.create_user(db, username, password, payload.get("role", "admin"))
                    return
                if method == "PUT" and path == "/api/password":
                    payload = self.read_json(8192)
                    if not isinstance(payload, dict):
                        raise ValueError("Ogiltigt innehåll.")
                    old = payload.get("current_password")
                    new = valid_password(payload.get("new_password"))
                    if not isinstance(old, str) or not 1 <= len(old) <= 256:
                        raise ValueError("Ange ditt nuvarande lösenord.")
                    row = db.execute("SELECT password_hash FROM users WHERE id=?", (self.user["id"],)).fetchone()
                    if not password_matches(old, row["password_hash"]):
                        self.reply(400, {"error": "Nuvarande lösenord är felaktigt."})
                        return
                    db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(new), self.user["id"]))
                    db.execute("DELETE FROM sessions WHERE user_id=?", (self.user["id"],))
                    audit(db, self.user["username"], "user.password", self.user["id"])
                    db.commit()
                    self.reply(200, {"ok": True}, headers={"Set-Cookie": self.session_cookie("", 0)})
                    return
                if method == "POST" and path == "/api/restore":
                    payload = self.read_json()
                    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("items"), list):
                        raise ValueError("Ogiltig säkerhetskopia.")
                    if len(payload["items"]) > 5000:
                        raise ValueError("Högst 5000 poster per import.")
                    projects = payload.get("projects", [])
                    if not isinstance(projects, list) or len(projects) > 100:
                        raise ValueError("Högst 100 projektsamlingar per import.")
                    if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] + len(projects) > 100:
                        raise ValueError("Högst 100 projektsamlingar i biblioteket.")
                    project_map = {}
                    for project in projects:
                        name = named(project)
                        old_id = project.get("id")
                        if type(old_id) is not int or old_id < 1 or old_id in project_map:
                            raise ValueError("Ogiltigt projekt-ID i importen.")
                        description = self.project_description(project)
                        cursor = db.execute("INSERT INTO projects(name,description) VALUES (?,?)", (name, description))
                        project_map[old_id] = cursor.lastrowid
                    added = skipped = 0
                    item_map, pending_relations, seen_ids, missing_links = {}, [], set(), 0
                    example_keys = {example["key"] for example in EXAMPLES}
                    for item in payload["items"]:
                        if not isinstance(item, dict):
                            raise ValueError("Ogiltig post i säkerhetskopian.")
                        ids = item.get("project_ids", [])
                        if not isinstance(ids, list) or any(type(value) is not int or value not in project_map for value in ids):
                            raise ValueError("Postens projektsamling saknas i importen.")
                        item = {**item, "project_ids": [project_map[value] for value in ids]}
                        key = item.get("example_key")
                        if key is not None and (not isinstance(key, str) or key not in example_keys):
                            raise ValueError("Ogiltig exempelnyckel i säkerhetskopian.")
                        old_id = item.get("id")
                        if old_id is not None:
                            if type(old_id) is not int or old_id < 1 or old_id in seen_ids:
                                raise ValueError("Ogiltiga eller upprepade post-ID i importen.")
                            seen_ids.add(old_id)
                        if key and db.execute("SELECT 1 FROM items WHERE example_key=?", (key,)).fetchone():
                            if type(item.get("id")) is int:
                                item_map[item["id"]] = db.execute("SELECT id FROM items WHERE example_key=?", (key,)).fetchone()["id"]
                            skipped += 1
                            continue
                        relations = item.get("related_ids", [])
                        if (not isinstance(relations, list) or len(relations) > 50 or
                                any(type(i) is not int or i < 1 for i in relations) or len(set(relations)) != len(relations)):
                            raise ValueError("Ogiltiga relationer i importen.")
                        item_id = self.save(db, {**item, "related_ids": []})
                        if old_id is not None:
                            item_map[old_id] = item_id
                        pending_relations.append((item_id, relations))
                        if key:
                            db.execute("UPDATE items SET example_key=? WHERE id=?", (key, item_id))
                            snapshot(db, item_id, self.user["username"])
                        added += 1
                    for item_id, relations in pending_relations:
                        missing_links += sum(i not in item_map for i in relations)
                        mapped = list(dict.fromkeys(item_map[i] for i in relations if i in item_map and item_map[i] != item_id))
                        db.execute("UPDATE items SET related_ids=? WHERE id=?", (json.dumps(mapped), item_id))
                        snapshot(db, item_id, self.user["username"])
                    guides = payload.get("guides", [])
                    if not isinstance(guides, list) or len(guides) + db.execute("SELECT COUNT(*) FROM guides").fetchone()[0] > 200:
                        raise ValueError("Högst 200 guider.")
                    for guide in guides:
                        if not isinstance(guide, dict) or not isinstance(guide.get("steps"), list):
                            raise ValueError("Ogiltig guide i importen.")
                        steps = []
                        for step in guide["steps"]:
                            if not isinstance(step, dict):
                                raise ValueError("Ogiltigt guidesteg.")
                            source_id = step.get("item_id")
                            if source_id is not None and type(source_id) is not int:
                                raise ValueError("Ogiltig postlänk i guidesteg.")
                            if source_id is not None and source_id not in item_map:
                                missing_links += 1
                            steps.append({"text": step.get("text"), "item_id": item_map.get(source_id)})
                        values = workbench.guide_payload(db, {**guide, "steps": steps})
                        db.execute("INSERT INTO guides(title,description,prerequisites,steps) VALUES (?,?,?,?)",
                                   tuple(values.values()))
                    audit(db, self.user["username"], "items.import", f"{added} added, {skipped} skipped")
                    db.commit()
                    warning = f" {missing_links} länkar saknade mål i importfilen och kunde inte kopplas." if missing_links else ""
                    self.reply(201, {"message": f'{added} poster importerade.' + warning, "added": added, "skipped": skipped})
                    return
                if method == "POST" and path == "/api/items":
                    item_id = self.save(db, self.read_json())
                    db.commit()
                    self.reply(201, {"id": item_id})
                    return
                if path.startswith("/api/items/") and path.removeprefix("/api/items/").isdigit():
                    item_id = int(path.rsplit("/", 1)[1])
                    if not db.execute("SELECT id FROM items WHERE id=? AND deleted_at IS NULL", (item_id,)).fetchone():
                        self.reply(404, {"error": "Posten finns inte längre."})
                        return
                    if method == "DELETE":
                        snapshot(db, item_id, self.user["username"])
                        db.execute("UPDATE items SET deleted_at=CURRENT_TIMESTAMP,example_key=NULL,updated=CURRENT_TIMESTAMP WHERE id=?", (item_id,))
                        audit(db, self.user["username"], "item.trash", item_id)
                    elif method == "PUT":
                        self.save(db, self.read_json(), item_id)
                    else:
                        self.reply(405, {"error": "Metoden stöds inte."})
                        return
                    db.commit()
                    self.reply(200, {"ok": True})
                    return
            self.reply(404, {"error": "Hittades inte."})
        except (ValueError, binascii.Error) as error:
            self.reply(400, {"error": str(error)})
        except FileNotFoundError as error:
            self.reply(404, {"error": str(error)})
        except OSError as error:
            self.log_error("Filfel: %s", error)
            self.reply(500, {"error": "Säkerhetskopian kunde inte sparas eller återställas. Kontrollera serverloggen och volymens behörigheter."})
        except sqlite3.Error:
            import traceback
            self.log_error("Databasfel: %s", traceback.format_exc())
            self.reply(500, {"error": "Databasen kunde inte uppdateras. Kontrollera serverloggen och diskutrymmet."})

    def manage(self, db, method, path):
        actor = self.user["username"]
        if method == "PUT" and path == "/api/settings":
            payload = self.read_json(8192)
            if not isinstance(payload, dict) or not isinstance(payload.get("registration_open"), bool):
                raise ValueError("registration_open måste vara true eller false.")
            value = payload["registration_open"]
            db.execute("UPDATE settings SET value=? WHERE key='registration_open'", (json.dumps(value),))
            audit(db, actor, "settings.registration", "open" if value else "closed")
            db.commit()
            self.reply(200, self.settings(db))
            return True
        user_match = re.fullmatch(r"/api/users/(\d+)(/reset-password)?", path)
        if user_match and ((method == "POST" and user_match[2]) or (method == "PUT" and not user_match[2])):
            user_id = int(user_match[1])
            payload = self.read_json(8192)
            if not isinstance(payload, dict):
                raise ValueError("Ogiltigt innehåll.")
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT id,active,role FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                self.reply(404, {"error": "Användaren finns inte."})
                return True
            if user_match[2]:
                password = valid_password(payload.get("password"))
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), user_id))
                action = "user.reset-password"
            else:
                active = payload.get("active", bool(user["active"]))
                role = payload.get("role", user["role"])
                if not isinstance(active, bool) or not isinstance(role, str) or role not in ROLES:
                    raise ValueError("Ange giltig roll och active: true eller false.")
                if user_id == self.user["id"] and (not active or role != user["role"]):
                    raise ValueError("Du kan inte inaktivera eller ändra rollen för ditt eget konto.")
                if user["active"] and user["role"] == "admin" and (not active or role != "admin") and db.execute(
                        "SELECT COUNT(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0] <= 1:
                    raise ValueError("Det sista aktiva administratörskontot får inte inaktiveras.")
                db.execute("UPDATE users SET active=?,role=? WHERE id=?", (int(active), role, user_id))
                action = "user.role" if role != user["role"] else "user.enable" if active else "user.disable"
            if user_match[2] or not active or role != user["role"]:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(db, actor, action, user_id)
            db.commit()
            headers = {"Set-Cookie": self.session_cookie("", 0)} if user_match[2] and user_id == self.user["id"] else None
            self.reply(200, {"ok": True}, headers=headers)
            return True
        category_match = re.fullmatch(r"/api/categories/([^/]+)", path)
        if (method == "POST" and path == "/api/categories") or (category_match and method in ("PUT", "DELETE")):
            payload = self.read_json(8192)
            db.execute("BEGIN IMMEDIATE")
            key = unquote(category_match[1]) if category_match else None
            if key and not db.execute("SELECT 1 FROM categories WHERE key=?", (key,)).fetchone():
                self.reply(404, {"error": "Kategorin finns inte."})
                return True
            if method == "DELETE":
                if not isinstance(payload, dict):
                    raise ValueError("Ogiltigt innehåll.")
                if key in BUILTINS:
                    raise ValueError("Inbyggda kategorier kan byta namn och flyttas, men inte tas bort.")
                if db.execute("SELECT 1 FROM categories WHERE parent=?", (key,)).fetchone():
                    raise ValueError("Flytta underkategorierna innan kategorin tas bort.")
                move_to = payload.get("move_to")
                count = db.execute("SELECT COUNT(*) FROM items WHERE category=?", (key,)).fetchone()[0]
                if move_to is not None and (not isinstance(move_to, str) or move_to == key or
                        not db.execute("SELECT 1 FROM categories WHERE key=?", (move_to,)).fetchone()):
                    raise ValueError("Välj en annan giltig målkategori.")
                if count and not move_to:
                    raise ValueError("Kategorin innehåller poster. Ange move_to.")
                rows = db.execute("SELECT * FROM items WHERE category=?", (key,)).fetchall()
                for row in rows:
                    validate({**dict(row), "category": move_to})
                for row in rows:
                    snapshot(db, row["id"], actor)
                    db.execute("UPDATE items SET category=?,updated=CURRENT_TIMESTAMP WHERE id=?", (move_to, row["id"]))
                    snapshot(db, row["id"], actor)
                    audit(db, actor, "item.move-category", row["id"])
                db.execute("DELETE FROM categories WHERE key=?", (key,))
                audit(db, actor, "category.delete", key)
                db.commit()
                self.reply(200, {"ok": True})
            else:
                name, parent = category_payload(db, payload, key)
                if key:
                    db.execute("UPDATE categories SET name=?,parent=? WHERE key=?", (name, parent, key))
                else:
                    key = "custom-" + secrets.token_hex(8)
                    db.execute("INSERT INTO categories(key,name,parent) VALUES (?,?,?)", (key, name, parent))
                audit(db, actor, "category.create" if method == "POST" else "category.update", key)
                db.commit()
                self.reply(201 if method == "POST" else 200, {"key": key, "name": name, "parent": parent})
            return True
        trash_match = re.fullmatch(r"/api/trash/(\d+)", path)
        restore_match = re.fullmatch(r"/api/items/(\d+)/restore", path)
        history_match = re.fullmatch(r"/api/items/(\d+)/history/(\d+)/restore", path)
        if ((method == "DELETE" and trash_match) or (method == "POST" and (restore_match or history_match))):
            match = trash_match or restore_match or history_match
            item_id = int(match[1])
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not row or ((trash_match or restore_match) and row["deleted_at"] is None):
                self.reply(404, {"error": "Posten finns inte i papperskorgen." if not history_match else "Posten finns inte."})
                return True
            if trash_match:
                db.execute("DELETE FROM personal_items WHERE item_id=?", (item_id,))
                db.execute("DELETE FROM history WHERE item_id=?", (item_id,))
                db.execute("DELETE FROM items WHERE id=?", (item_id,))
                action = "item.delete-permanently"
            elif history_match:
                revision = db.execute("SELECT snapshot FROM history WHERE id=? AND item_id=?",
                                      (int(history_match[2]), item_id)).fetchone()
                if not revision:
                    self.reply(404, {"error": "Versionen finns inte."})
                    return True
                payload = json.loads(revision["snapshot"])
                # Historical categories may have been deleted; revive their stable key.
                if not db.execute("SELECT 1 FROM categories WHERE key=?", (payload["category"],)).fetchone():
                    db.execute("INSERT INTO categories(key,name) VALUES (?,?)", (payload["category"], payload["category"]))
                    audit(db, actor, "category.restore", payload["category"])
                self.save(db, payload, item_id, restoring=True)
                restore_example_key(db, item_id, payload.get("example_key", row["example_key"]))
                snapshot(db, item_id, actor)
                action = "item.restore-version"
            else:
                revision = db.execute("SELECT snapshot FROM history WHERE item_id=? ORDER BY id DESC LIMIT 1",
                                      (item_id,)).fetchone()
                db.execute("UPDATE items SET deleted_at=NULL,updated=CURRENT_TIMESTAMP WHERE id=?", (item_id,))
                key = json.loads(revision["snapshot"]).get("example_key") if revision else None
                restore_example_key(db, item_id, key)
                snapshot(db, item_id, actor)
                action = "item.restore"
            audit(db, actor, action, item_id)
            db.commit()
            self.reply(200, {"ok": True})
            return True
        return False

    @staticmethod
    def project_description(payload):
        description = payload.get("description", "")
        if not isinstance(description, str) or len(description) > 2000:
            raise ValueError("Projektbeskrivningen får vara högst 2000 tecken.")
        return description

    def library_management(self, db, method, path):
        project_match = re.fullmatch(r"/api/projects/(\d+)", path)
        if (method == "POST" and path == "/api/projects") or (project_match and method in ("PUT", "DELETE")):
            db.execute("BEGIN IMMEDIATE")
            project_id = int(project_match[1]) if project_match else None
            if project_id and not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
                self.reply(404, {"error": "Projektsamlingen finns inte."})
                return True
            if method == "DELETE":
                for row in db.execute("SELECT id,project_ids FROM items").fetchall():
                    ids = json.loads(row["project_ids"])
                    if project_id in ids:
                        snapshot(db, row["id"], self.user["username"])
                        ids.remove(project_id)
                        db.execute("UPDATE items SET project_ids=?,updated=CURRENT_TIMESTAMP WHERE id=?",
                                   (json.dumps(ids), row["id"]))
                        snapshot(db, row["id"], self.user["username"])
                db.execute("DELETE FROM projects WHERE id=?", (project_id,))
                result = {"ok": True}
            else:
                payload = self.read_json(8192)
                name, description = named(payload), self.project_description(payload)
                if project_id:
                    db.execute("UPDATE projects SET name=?,description=? WHERE id=?", (name, description, project_id))
                else:
                    if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] >= 100:
                        raise ValueError("Högst 100 projektsamlingar.")
                    project_id = db.execute("INSERT INTO projects(name,description) VALUES (?,?)",
                                            (name, description)).lastrowid
                result = {"id": project_id, "name": name, "description": description}
            audit(db, self.user["username"], "project." + {"POST": "create", "PUT": "update", "DELETE": "delete"}[method],
                  project_id)
            db.commit()
            self.reply(201 if method == "POST" else 200, result)
            return True
        search_match = re.fullmatch(r"/api/searches/(\d+)", path)
        if (method == "POST" and path == "/api/searches") or (method == "DELETE" and search_match):
            db.execute("BEGIN IMMEDIATE")
            if method == "DELETE":
                count = db.execute("DELETE FROM saved_searches WHERE id=? AND user_id=?",
                                   (int(search_match[1]), self.user["id"])).rowcount
                if not count:
                    self.reply(404, {"error": "Den sparade sökningen finns inte för ditt konto."})
                    return True
                result = {"ok": True}
            else:
                payload = self.read_json(8192)
                name = named(payload)
                filters = search_filters(payload.get("filters"))
                if db.execute("SELECT COUNT(*) FROM saved_searches WHERE user_id=?", (self.user["id"],)).fetchone()[0] >= 100:
                    raise ValueError("Högst 100 sparade sökningar per konto.")
                search_id = db.execute("INSERT INTO saved_searches(user_id,name,filters) VALUES (?,?,?)",
                                       (self.user["id"], name, json.dumps(filters))).lastrowid
                result = {"id": search_id, "name": name, "filters": filters}
            db.commit()
            self.reply(201 if method == "POST" else 200, result)
            return True
        if method == "POST" and path in ("/api/batch/preview", "/api/batch/import"):
            payload = self.read_json()
            candidates = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(candidates, list) or not 1 <= len(candidates) <= 50:
                raise ValueError("Välj 1–50 filer per import.")
            allow_duplicates = payload.get("allow_duplicates", False)
            if not isinstance(allow_duplicates, bool):
                raise ValueError("Ogiltig dubblettinställning.")
            db.execute("BEGIN IMMEDIATE")
            seen, prepared, total = {}, [], 0
            for index, candidate in enumerate(candidates):
                values = validate(candidate)
                values.update(metadata(candidate))
                values.update(attachments(candidate, True))
                text_size = len(values["content"].encode("utf-8"))
                if values["filedata"] is None and text_size > 200000:
                    raise ValueError("Kodfiler får vara högst 200 kB. Importera större filer som bilagor.")
                total += text_size + len(values["filedata"] or b"")
                if total > 20 * 1024 * 1024:
                    raise ValueError("Filerna får tillsammans vara högst 20 MB.")
                project_ids(db, candidate)
                mark = fingerprint(values["content"], values["filedata"], bool(values["download_name"]))
                existing = db.execute("SELECT id,title FROM items WHERE fingerprint=? AND deleted_at IS NULL LIMIT 1",
                                      (mark,)).fetchone() if mark else None
                duplicate = dict(existing) if existing else ({"index": seen[mark]} if mark and mark in seen else None)
                if mark and mark not in seen:
                    seen[mark] = index
                prepared.append({"index": index, "title": values["title"], "duplicate": duplicate})
            if path.endswith("/preview"):
                self.reply(200, {"items": prepared})
                return True
            added = skipped = 0
            for candidate, result in zip(candidates, prepared):
                if result["duplicate"] and not allow_duplicates:
                    skipped += 1
                else:
                    self.save(db, candidate)
                    added += 1
            audit(db, self.user["username"], "items.import", f"{added} added, {skipped} skipped")
            db.commit()
            self.reply(201, {"added": added, "skipped": skipped})
            return True
        return False

    def create_user(self, db, username, password, role="reader"):
        if not isinstance(role, str) or role not in ROLES:
            raise ValueError("Ogiltig användarroll.")
        try:
            cursor = db.execute("INSERT INTO users(username,password_hash,role) VALUES (?,?,?)",
                                (username, password_hash(password), role))
        except sqlite3.IntegrityError as error:
            if error.sqlite_errorname != "SQLITE_CONSTRAINT_UNIQUE":
                raise
            self.reply(409, {"error": "Användarnamnet finns redan. Välj ett annat."})
            return
        audit(db, self.user["username"] if getattr(self, "user", None) else username, "user.create", cursor.lastrowid)
        db.commit()
        self.reply(201, {"id": cursor.lastrowid, "username": username, "role": role})

    def login(self):
        username, password = credentials(self.read_json(8192))
        now = int(time.time())
        with connect() as db:
            # Reserve an attempt atomically before the expensive password check.
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE started<=?", (now - 300,))
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            address = self.client_address[0]
            attempt = db.execute("SELECT attempts FROM login_attempts WHERE address=?", (address,)).fetchone()
            if attempt and attempt["attempts"] >= 10:
                db.commit()
                self.reply(429, {"error": "För många inloggningsförsök. Vänta fem minuter."},
                           headers={"Retry-After": "300"})
                return
            db.execute("INSERT INTO login_attempts(address,started,attempts) VALUES (?,?,1) "
                       "ON CONFLICT(address) DO UPDATE SET attempts=attempts+1", (address, now))
            row = db.execute("SELECT id,password_hash FROM users WHERE username=? AND active=1", (username,)).fetchone()
            db.commit()
            matches = password_matches(password, row["password_hash"] if row else DUMMY_HASH)
            if not row or not matches:
                self.reply(401, {"error": "Fel användarnamn eller lösenord."})
                return
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT password_hash FROM users WHERE id=? AND active=1", (row["id"],)).fetchone()
            if not current or current["password_hash"] != row["password_hash"]:
                self.reply(401, {"error": "Fel användarnamn eller lösenord."})
                return
            db.execute("DELETE FROM login_attempts WHERE address=?", (address,))
            token, csrf = secrets.token_hex(32), secrets.token_hex(32)
            db.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires) VALUES (?,?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, now + SESSION_SECONDS))
            audit(db, username, "user.login", row["id"])
            db.commit()
        self.reply(200, {"ok": True}, headers={"Set-Cookie": self.session_cookie(token)})

    def save(self, db, payload, item_id=None, restoring=False):
        old = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone() if item_id is not None else None
        values = validate(payload)
        values.update(metadata(payload, old))
        values["project_ids"] = project_ids(db, payload, old, restoring)
        values["related_ids"] = workbench.related_ids(db, payload, old, restoring)
        if not db.execute("SELECT 1 FROM categories WHERE key=?", (values["category"],)).fetchone():
            # Preserve compatibility with old exports and the legacy custom-category editor.
            db.execute("INSERT INTO categories(key,name) VALUES (?,?)", (values["category"], values["category"]))
            audit(db, self.user["username"], "category.create", values["category"])
        values.update(attachments(payload, item_id is None))
        values["fingerprint"] = fingerprint(values["content"], values.get("filedata", old["filedata"] if old else None),
                                            bool(values["download_name"]))
        actor = self.user["username"]
        columns = list(values)
        if item_id is None:
            sequence = db.execute("SELECT value FROM settings WHERE key='item_sequence'").fetchone()
            maximum = db.execute("SELECT COALESCE(MAX(id),0) FROM items").fetchone()[0]
            new_id = max(maximum, int(sequence["value"]) if sequence else 0) + 1
            db.execute("INSERT INTO settings(key,value) VALUES ('item_sequence',?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(new_id),))
            cursor = db.execute(f"INSERT INTO items (id,{','.join(columns)}) VALUES (?,{','.join('?' for _ in columns)})",
                                [new_id, *values.values()])
            snapshot(db, cursor.lastrowid, actor)
            audit(db, actor, "item.create", cursor.lastrowid)
            return cursor.lastrowid
        snapshot(db, item_id, actor)
        db.execute(f"UPDATE items SET {','.join(c + '=?' for c in columns)},updated=CURRENT_TIMESTAMP WHERE id=?",
                   [*values.values(), item_id])
        snapshot(db, item_id, actor)
        audit(db, actor, "item.update", item_id)
        return item_id


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '', favorite INTEGER NOT NULL DEFAULT 0,
            filename TEXT, filedata BLOB, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,
            csrf TEXT NOT NULL,expires INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
            address TEXT PRIMARY KEY,started INTEGER NOT NULL,attempts INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS registration_attempts (
            address TEXT PRIMARY KEY,started INTEGER NOT NULL,attempts INTEGER NOT NULL)""")
        if "example_key" not in {row["name"] for row in db.execute("PRAGMA table_info(items)")}:
            db.execute("ALTER TABLE items ADD COLUMN example_key TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS items_example_key ON items(example_key)")
        migrate(db)
        if not db.execute("SELECT id FROM users LIMIT 1").fetchone():
            try:
                valid_password(PASSWORD)
            except ValueError as error:
                raise SystemExit(f"APP_PASSWORD krävs för att skapa första admin-kontot: {error}")
            db.execute("INSERT INTO users(username,password_hash) VALUES ('admin',?)", (password_hash(PASSWORD),))
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    BACKUPS.start()
    print("Prylbanken lyssnar på port", server.server_port, flush=True)
    server.serve_forever()
