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
from urllib.parse import urlsplit
from catalog import PACKS, EXAMPLES

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
PASSWORD = os.environ.get("APP_PASSWORD", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_SECONDS = 12 * 60 * 60
HASH_ITERATIONS = 600000
MAX_FILE = 20 * 1024 * 1024
MAX_BODY = 29 * 1024 * 1024


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
                         "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
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
                "SELECT sessions.token_hash,sessions.csrf,users.id,users.username "
                "FROM sessions JOIN users ON users.id=sessions.user_id "
                "WHERE token_hash=? AND expires>?", (digest, int(time.time()))).fetchone()
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
        return {"id": self.user["id"], "username": self.user["username"], "role": "admin",
                "csrf": self.user["csrf"]}

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
        try:
            self.get()
        except sqlite3.Error:
            import traceback
            self.log_error("Databasfel: %s", traceback.format_exc())
            self.reply(500, {"error": "Databasen kunde inte läsas. Kontrollera serverloggen."})

    def get(self):
        path = urlsplit(self.path).path
        if path in ("/", "/login", "/app.js", "/login.js", "/style.css"):
            if path == "/" and not self.session():
                self.reply(303, "", headers={"Location": "/login"})
                return
            filename, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                              "/login": ("login.html", "text/html; charset=utf-8"),
                              "/login.js": ("login.js", "text/javascript; charset=utf-8"),
                              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                              "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
            self.reply(200, (ROOT / "public" / filename).read_bytes(), mime)
            return
        if path == "/api/health":
            with connect() as db:
                db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            self.reply(200, {"ok": True})
            return
        if not self.authenticated():
            return
        with connect() as db:
            if path == "/api/me":
                self.reply(200, self.public_user())
                return
            if path == "/api/users":
                rows = db.execute("SELECT id,username,created FROM users ORDER BY username").fetchall()
                self.reply(200, [{**dict(row), "role": "admin"} for row in rows])
                return
            if path == "/api/examples":
                self.reply(200, {"packs": [{**pack, "count": sum(item["pack"] == pack["id"] for item in EXAMPLES)}
                                          for pack in PACKS], "items": EXAMPLES})
                return
            if path == "/api/items":
                rows = db.execute(
                    "SELECT id,title,category,content,notes,tags,favorite,filename,"
                    "length(filedata) AS filesize,created,updated FROM items "
                    "ORDER BY favorite DESC,updated DESC,id DESC").fetchall()
                self.reply(200, [dict(row) for row in rows])
                return
            if path == "/api/backup":
                rows = []
                for row in db.execute("SELECT * FROM items ORDER BY id"):
                    item = dict(row)
                    item["filedata"] = base64.b64encode(item["filedata"]).decode() if item["filedata"] is not None else None
                    rows.append(item)
                self.reply(200, {"version": 1, "items": rows},
                           headers={"Content-Disposition": 'attachment; filename="prylbanken-backup.json"'})
                return
            if path.startswith("/api/files/") and path.removeprefix("/api/files/").isdigit():
                row = db.execute("SELECT filename,filedata FROM items WHERE id=?",
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
        path = urlsplit(self.path).path
        try:
            origin = self.headers.get("Origin")
            if (origin and urlsplit(origin).netloc != self.headers.get("Host")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.reply(403, {"error": "Begäran från en annan webbplats nekades."})
                return
            if method == "POST" and path == "/api/login":
                self.login()
                return
            if not self.authenticated():
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode(), self.user["csrf"].encode()):
                self.reply(403, {"error": "Säkerhetstoken saknas eller har gått ut. Ladda om sidan."})
                return
            with connect() as db:
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
                        added += 1
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
                    username, password = credentials(self.read_json(8192))
                    valid_password(password)
                    try:
                        cursor = db.execute("INSERT INTO users(username,password_hash) VALUES (?,?)",
                                            (username, password_hash(password)))
                    except sqlite3.IntegrityError:
                        self.reply(409, {"error": "Användarnamnet finns redan."})
                        return
                    db.commit()
                    self.reply(201, {"id": cursor.lastrowid, "username": username, "role": "admin"})
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
                    db.commit()
                    self.reply(200, {"ok": True}, headers={"Set-Cookie": self.session_cookie("", 0)})
                    return
                if method == "POST" and path == "/api/restore":
                    payload = self.read_json()
                    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("items"), list):
                        raise ValueError("Ogiltig säkerhetskopia.")
                    if len(payload["items"]) > 5000:
                        raise ValueError("Högst 5000 poster per import.")
                    for item in payload["items"]:
                        self.save(db, item)
                    db.commit()
                    self.reply(201, {"message": f'{len(payload["items"])} poster importerade.'})
                    return
                if method == "POST" and path == "/api/items":
                    item_id = self.save(db, self.read_json())
                    db.commit()
                    self.reply(201, {"id": item_id})
                    return
                if path.startswith("/api/items/") and path.removeprefix("/api/items/").isdigit():
                    item_id = int(path.rsplit("/", 1)[1])
                    if not db.execute("SELECT id FROM items WHERE id=?", (item_id,)).fetchone():
                        self.reply(404, {"error": "Posten finns inte längre."})
                        return
                    if method == "DELETE":
                        db.execute("DELETE FROM items WHERE id=?", (item_id,))
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
        except sqlite3.Error:
            import traceback
            self.log_error("Databasfel: %s", traceback.format_exc())
            self.reply(500, {"error": "Databasen kunde inte uppdateras. Kontrollera serverloggen och diskutrymmet."})

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
            row = db.execute("SELECT id,password_hash FROM users WHERE username=?", (username,)).fetchone()
            db.commit()
            matches = password_matches(password, row["password_hash"] if row else DUMMY_HASH)
            if not row or not matches:
                self.reply(401, {"error": "Fel användarnamn eller lösenord."})
                return
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT password_hash FROM users WHERE id=?", (row["id"],)).fetchone()
            if not current or current["password_hash"] != row["password_hash"]:
                self.reply(401, {"error": "Fel användarnamn eller lösenord."})
                return
            db.execute("DELETE FROM login_attempts WHERE address=?", (address,))
            token, csrf = secrets.token_hex(32), secrets.token_hex(32)
            db.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires) VALUES (?,?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, now + SESSION_SECONDS))
            db.commit()
        self.reply(200, {"ok": True}, headers={"Set-Cookie": self.session_cookie(token)})

    def save(self, db, payload, item_id=None):
        values = validate(payload)
        favorite = payload.get("favorite", False)
        if not isinstance(favorite, (bool, int)) or favorite not in (0, 1):
            raise ValueError("Ogiltig favoritmarkering.")
        values["favorite"] = int(favorite)
        if "filedata" in payload and payload["filedata"] is not None:
            filename = payload.get("filename", "")
            if not isinstance(filename, str) or not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
                raise ValueError("Ogiltigt filnamn.")
            encoded = payload["filedata"]
            if not isinstance(encoded, str) or len(encoded) > (MAX_FILE + 2) // 3 * 4:
                raise ValueError("Filen får vara högst 20 MB.")
            blob = base64.b64decode(encoded, validate=True)
            if len(blob) > MAX_FILE:
                raise ValueError("Filen får vara högst 20 MB.")
            values.update(filename=filename.replace("\\", "/").rsplit("/", 1)[-1], filedata=blob)
        elif item_id is None:
            values.update(filename=None, filedata=None)
        columns = list(values)
        if item_id is None:
            cursor = db.execute(f"INSERT INTO items ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                list(values.values()))
            return cursor.lastrowid
        db.execute(f"UPDATE items SET {','.join(c + '=?' for c in columns)},updated=CURRENT_TIMESTAMP WHERE id=?",
                   [*values.values(), item_id])
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
        if "example_key" not in {row["name"] for row in db.execute("PRAGMA table_info(items)")}:
            db.execute("ALTER TABLE items ADD COLUMN example_key TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS items_example_key ON items(example_key)")
        if not db.execute("SELECT id FROM users LIMIT 1").fetchone():
            try:
                valid_password(PASSWORD)
            except ValueError as error:
                raise SystemExit(f"APP_PASSWORD krävs för att skapa första admin-kontot: {error}")
            db.execute("INSERT INTO users(username,password_hash) VALUES ('admin',?)", (password_hash(PASSWORD),))
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    print("Prylbanken lyssnar på port", server.server_port, flush=True)
    server.serve_forever()
