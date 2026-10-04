"""Shared server inventory, non-secret template profiles and bookmark import."""
from html.parser import HTMLParser
import base64
import json
import re
from urllib.parse import urlsplit

from backend import audit


def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,address TEXT NOT NULL,
        os TEXT NOT NULL,role TEXT NOT NULL,url TEXT NOT NULL,notes TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT NOT NULL,
        variables TEXT NOT NULL)""")
    for table in ("items", "guides"):
        if "server_ids" not in {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}:
            db.execute(f"ALTER TABLE {table} ADD COLUMN server_ids TEXT NOT NULL DEFAULT '[]'")
    db.execute("""CREATE TABLE IF NOT EXISTS link_checks (
        item_id INTEGER PRIMARY KEY,url TEXT NOT NULL,status TEXT NOT NULL,
        detail TEXT NOT NULL,checked TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS link_attempts (
        user_id INTEGER PRIMARY KEY,started INTEGER NOT NULL,attempts INTEGER NOT NULL)""")


def text(payload, field, limit, required=False):
    value = payload.get(field, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"Ogiltigt fält: {field} (högst {limit} tecken).")
    return value.strip() if field in ("name", "address", "url") else value


def server_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltig server.")
    values = {key: text(payload, key, limit, key == "name") for key, limit in
              (("name", 80), ("address", 255), ("os", 200), ("role", 200), ("url", 2000), ("notes", 5000))}
    if any(ord(c) < 32 for c in values["address"]):
        raise ValueError("Serveradressen får inte innehålla kontrolltecken.")
    if values["url"] and not safe_url(values["url"]):
        raise ValueError("Administrationslänken måste vara en HTTP/HTTPS-adress utan inloggningsuppgifter.")
    return values


def safe_url(value):
    try:
        if any(ord(c) < 33 for c in value) or "\\" in value:
            return False
        parsed = urlsplit(value)
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return False
        return parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


SECRET_NAME = re.compile(r"(password|passwd|pwd|secret|token|api_?key|credential|private_?key)", re.I)


def profile_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltig profil.")
    name, description = text(payload, "name", 80, True), text(payload, "description", 2000)
    variables = payload.get("variables")
    if not isinstance(variables, dict) or not 1 <= len(variables) <= 50:
        raise ValueError("En profil måste innehålla 1–50 variabler.")
    for key, value in variables.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,39}", key) or SECRET_NAME.search(key):
            raise ValueError("Variabelnamn måste vara giltiga mallnamn och får inte avse lösenord, nycklar eller token.")
        if not isinstance(value, str) or not value.strip() or len(value) > 2000 or "\0" in value:
            raise ValueError("Profilvärden kräver 1–2000 tecken utan NUL.")
    return {"name": name, "description": description, "variables": json.dumps(variables, ensure_ascii=False)}


def server_ids(db, payload, old=None, restoring=False):
    ids = payload.get("server_ids", json.loads(old["server_ids"]) if old else [])
    if not isinstance(ids, list) or len(ids) > 100 or any(type(i) is not int or i < 1 for i in ids):
        raise ValueError("Ogiltiga serverkopplingar.")
    if len(set(ids)) != len(ids):
        raise ValueError("Serverkopplingar måste vara unika.")
    existing = {row["id"] for row in db.execute("SELECT id FROM servers")}
    if not restoring and any(i not in existing for i in ids):
        raise ValueError("En kopplad server finns inte längre.")
    return json.dumps(sorted(set(ids) & existing))


class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items, self.url, self.title, self.skipped = [], None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.finish()
            self.url = dict(attrs).get("href", "")
            self.title = []

    def handle_data(self, data):
        if self.url is not None:
            self.title.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a":
            self.finish()

    def finish(self):
        if self.url is None:
            return
        if len(self.items) >= 5000:
            raise ValueError("Högst 5000 bokmärken per förhandsvisning.")
        if safe_url(self.url) and len(self.url) <= 200000:
            self.items.append({"title": ("".join(self.title).strip() or self.url)[:200],
                               "category": "lankar", "content": self.url, "notes": "Importerad från bokmärkesfil.",
                               "tags": "bokmarke", "risk": "read"})
        else:
            self.skipped += 1
        self.url = None


def get(handler, db, path, data_dir, backups):
    if path in ("/api/servers", "/api/profiles"):
        table = "servers" if path == "/api/servers" else "profiles"
        rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY name,id")]
        if table == "profiles":
            for row in rows:
                row["variables"] = json.loads(row["variables"])
        handler.reply(200, rows)
        return True
    if path == "/api/link-checks":
        handler.reply(200, [dict(row) for row in db.execute(
            "SELECT c.* FROM link_checks c JOIN items i ON i.id=c.item_id "
            "WHERE i.deleted_at IS NULL AND i.category='lankar' AND i.content=c.url")])
        return True
    if path == "/api/storage":
        if handler.user["role"] != "admin":
            handler.reply(403, {"error": "Administratörsbehörighet krävs."})
            return True
        database = data_dir / "library.sqlite"
        files = {suffix or "database": (database.with_name(database.name + suffix).stat().st_size
                                        if database.with_name(database.name + suffix).exists() else 0)
                 for suffix in ("", "-wal", "-shm")}
        total = db.execute("SELECT COALESCE(SUM(length(filedata)),0),COUNT(filedata) FROM items").fetchone()
        largest = [dict(row) for row in db.execute(
            "SELECT id,title,filename,length(filedata) AS bytes,deleted_at FROM items "
            "WHERE filedata IS NOT NULL ORDER BY bytes DESC,id LIMIT 20")]
        status = backups.status()
        handler.reply(200, {"database_bytes": files["database"], "wal_bytes": files["-wal"], "shm_bytes": files["-shm"],
                            "attachment_bytes": total[0], "attachment_count": total[1], "largest": largest,
                            "backups": status})
        return True
    return False


def mutate(handler, db, method, path, save, snapshot):
    if path == "/api/bookmarks/preview" and method == "POST":
        payload = handler.read_json(3 * 1024 * 1024)
        content = payload.get("html") if isinstance(payload, dict) else None
        if not isinstance(content, str) or len(content.encode()) > 2 * 1024 * 1024:
            raise ValueError("Bokmärkesfilen måste vara UTF-8 HTML och högst 2 MB.")
        parser = BookmarkParser(); parser.feed(content); parser.close(); parser.finish()
        handler.reply(200, {"items": parser.items, "skipped": parser.skipped})
        return True
    duplicate = re.fullmatch(r"/api/items/(\d+)/duplicate", path)
    if duplicate and method == "POST":
        row = db.execute("SELECT * FROM items WHERE id=? AND deleted_at IS NULL", (int(duplicate[1]),)).fetchone()
        if not row:
            raise FileNotFoundError("Posten finns inte i biblioteket.")
        payload = dict(row)
        payload.update(title=(row["title"][:190] + " (kopia)"), favorite=False, pinned="0",
                       project_ids=json.loads(row["project_ids"]), related_ids=json.loads(row["related_ids"]),
                       server_ids=json.loads(row["server_ids"]),
                       filedata=base64.b64encode(row["filedata"]).decode() if row["filedata"] is not None else None)
        item_id = save(db, payload)
        audit(db, handler.user["username"], "item.duplicate", f"{row['id']} -> {item_id}")
        db.commit(); handler.reply(201, {"id": item_id})
        return True
    match = re.fullmatch(r"/api/(servers|profiles)(?:/(\d+))?", path)
    if not match or method not in ("POST", "PUT", "DELETE"):
        return False
    table, identifier = match[1], int(match[2]) if match[2] else None
    if (method == "POST" and identifier) or (method != "POST" and identifier is None):
        raise ValueError("Ogiltig registeroperation.")
    if identifier and not db.execute(f"SELECT 1 FROM {table} WHERE id=?", (identifier,)).fetchone():
        raise FileNotFoundError("Registerposten finns inte.")
    if method == "DELETE":
        if table == "servers":
            for row in db.execute("SELECT * FROM items").fetchall():
                ids = json.loads(row["server_ids"])
                if identifier in ids:
                    snapshot(db, row["id"], handler.user["username"])
                    ids.remove(identifier)
                    db.execute("UPDATE items SET server_ids=?,updated=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(ids), row["id"]))
                    snapshot(db, row["id"], handler.user["username"])
            for row in db.execute("SELECT id,server_ids FROM guides").fetchall():
                ids = json.loads(row["server_ids"])
                if identifier in ids:
                    ids.remove(identifier)
                    db.execute("UPDATE guides SET server_ids=? WHERE id=?", (json.dumps(ids), row["id"]))
                    db.execute("DELETE FROM guide_progress WHERE guide_id=?", (row["id"],))
        db.execute(f"DELETE FROM {table} WHERE id=?", (identifier,))
    else:
        if not identifier and db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] >= 200:
            raise ValueError("Högst 200 poster per register.")
        values = (server_payload if table == "servers" else profile_payload)(handler.read_json(150000))
        columns = list(values)
        if identifier:
            db.execute(f"UPDATE {table} SET {','.join(key+'=?' for key in columns)} WHERE id=?",
                       [*values.values(), identifier])
        else:
            identifier = db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                    list(values.values())).lastrowid
    audit(db, handler.user["username"], table + "." + method.lower(), identifier)
    db.commit(); handler.reply(201 if method == "POST" else 200, {"id": identifier})
    return True
