import base64
import binascii
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
PASSWORD = os.environ.get("APP_PASSWORD", "")
MAX_FILE = 20 * 1024 * 1024
MAX_BODY = 29 * 1024 * 1024


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

    def authenticated(self):
        expected = "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()
        if hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            return True
        self.reply(401, {"error": "Logga in med användarnamn admin."},
                   headers={"WWW-Authenticate": 'Basic realm="Prylbanken", charset="UTF-8"'})
        return False

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Ogiltig storlek.")
        if not 0 < length <= MAX_BODY:
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
        if not self.authenticated():
            return
        path = urlsplit(self.path).path
        if path in ("/", "/app.js", "/style.css"):
            filename, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                              "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                              "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
            self.reply(200, (ROOT / "public" / filename).read_bytes(), mime)
            return
        with connect() as db:
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
        if not self.authenticated():
            return
        origin = self.headers.get("Origin")
        if (origin and urlsplit(origin).netloc != self.headers.get("Host")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.reply(403, {"error": "Begäran från en annan webbplats nekades."})
            return
        path = urlsplit(self.path).path
        try:
            with connect() as db:
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
    if len(PASSWORD) < 12 or ":" in PASSWORD:
        raise SystemExit("APP_PASSWORD måste innehålla minst 12 tecken och får inte innehålla kolon.")
    DATA.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '', favorite INTEGER NOT NULL DEFAULT 0,
            filename TEXT, filedata BLOB, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("PRAGMA journal_mode=WAL")
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    print("Prylbanken lyssnar på port", server.server_port, flush=True)
    server.serve_forever()
