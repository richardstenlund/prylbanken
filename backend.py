"""Schema migrations, revision storage and coordinated SQLite backups."""
import base64
import datetime as dt
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from library import fingerprint

DB_LOCK = threading.RLock()
LANGUAGES = {"plain", "bash", "powershell", "bat", "yaml", "json", "python", "javascript", "sql"}
METADATA = {
    "language": ("plain", 20), "download_name": ("", 255), "os": ("", 200),
    "program_version": ("", 200), "ports": ("", 1000), "dependencies": ("", 5000),
    "tested_at": ("", 10), "status": ("template", 20),
}
BUILTINS = {
    "lankar": "Länkar", "kod": "Kodsnuttar", "docker": "Docker",
    "spelserver": "Spelservrar", "steamcmd": "SteamCMD", "bat": "BAT & skript",
    "linux": "Linux", "windows": "Windows", "natverk": "Nätverk",
    "databaser": "Databaser & SQL", "utveckling": "Utveckling", "automation": "Automation",
    "sakerhet": "IT-säkerhet", "dokumentation": "Guider & anteckningar", "filer": "Filer",
}
ITEM_FIELDS = ("title", "category", "content", "notes", "tags", "favorite", "filename",
               "filedata", "example_key", "project_ids", *METADATA)


def audit(db, actor, action, target):
    db.execute("INSERT INTO activity(actor,action,target) VALUES (?,?,?)",
               (actor, action, str(target)))


def snapshot(db, item_id, actor):
    row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    data = {field: row[field] for field in ITEM_FIELDS}
    data["project_ids"] = json.loads(data["project_ids"])
    if data["filedata"] is not None:
        data["filedata"] = base64.b64encode(data["filedata"]).decode("ascii")
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
    last = db.execute("SELECT snapshot FROM history WHERE item_id=? ORDER BY id DESC LIMIT 1",
                      (item_id,)).fetchone()
    if not last or last["snapshot"] != encoded:
        db.execute("INSERT INTO history(item_id,actor,title,content,language,snapshot) VALUES (?,?,?,?,?,?)",
                   (item_id, actor, data["title"], data["content"], data["language"], encoded))


def migrate(db):
    columns = {r["name"] for r in db.execute("PRAGMA table_info(items)")}
    for field, (default, _) in METADATA.items():
        if field not in columns:
            db.execute(f"ALTER TABLE items ADD COLUMN {field} TEXT NOT NULL DEFAULT '{default}'")
    if "deleted_at" not in columns:
        db.execute("ALTER TABLE items ADD COLUMN deleted_at TEXT")
    if "active" not in {r["name"] for r in db.execute("PRAGMA table_info(users)")}:
        db.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "role" not in {r["name"] for r in db.execute("PRAGMA table_info(users)")}:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
    if "project_ids" not in columns:
        db.execute("ALTER TABLE items ADD COLUMN project_ids TEXT NOT NULL DEFAULT '[]'")
    if "fingerprint" not in columns:
        db.execute("ALTER TABLE items ADD COLUMN fingerprint TEXT")
        for row in db.execute("SELECT id,content,filedata,download_name FROM items").fetchall():
            db.execute("UPDATE items SET fingerprint=? WHERE id=?",
                       (fingerprint(row["content"], row["filedata"], bool(row["download_name"])), row["id"]))
    db.execute("CREATE INDEX IF NOT EXISTS items_fingerprint ON items(fingerprint)")
    db.execute("""CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS saved_searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,
        name TEXT NOT NULL,filters TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS categories (
        key TEXT PRIMARY KEY,name TEXT NOT NULL,parent TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actor TEXT NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,language TEXT NOT NULL,
        snapshot TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS history_item ON history(item_id,id)")
    db.execute("""CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL)""")
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO settings VALUES ('registration_open','true')")
    seeded = db.execute("SELECT value FROM settings WHERE key='categories_seeded'").fetchone()
    if not seeded:
        for key, name in BUILTINS.items():
            db.execute("INSERT OR IGNORE INTO categories(key,name) VALUES (?,?)", (key, name))
        db.execute("INSERT INTO settings VALUES ('categories_seeded','true')")
    for row in db.execute("SELECT DISTINCT category FROM items").fetchall():
        db.execute("INSERT OR IGNORE INTO categories(key,name) VALUES (?,?)",
                   (row["category"], row["category"]))
    for row in db.execute("SELECT id FROM items WHERE id NOT IN (SELECT item_id FROM history)").fetchall():
        snapshot(db, row["id"], "system")
    for row in db.execute("SELECT id FROM items WHERE deleted_at IS NOT NULL AND example_key IS NOT NULL").fetchall():
        snapshot(db, row["id"], "system")
        db.execute("UPDATE items SET example_key=NULL WHERE id=?", (row["id"],))


def restore_example_key(db, item_id, key):
    row = db.execute("SELECT deleted_at FROM items WHERE id=?", (item_id,)).fetchone()
    if row["deleted_at"] is not None or (key and db.execute(
            "SELECT 1 FROM items WHERE example_key=? AND id<>?", (key, item_id)).fetchone()):
        key = None
    db.execute("UPDATE items SET example_key=? WHERE id=?", (key, item_id))


def metadata(payload, old=None):
    result = {}
    for field, (default, limit) in METADATA.items():
        value = payload.get(field, old[field] if old is not None else default)
        if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value if field == "download_name"):
            raise ValueError(f"Ogiltigt metadatafält: {field}.")
        result[field] = value.strip()
    if result["language"] not in LANGUAGES:
        raise ValueError("Ogiltigt skriptspråk.")
    if result["status"] not in {"template", "tested", "needs-update"}:
        raise ValueError("Ogiltig teststatus.")
    date = result["tested_at"]
    if date:
        try:
            if dt.date.fromisoformat(date).isoformat() != date:
                raise ValueError()
        except ValueError:
            raise ValueError("Testdatum måste vara ett ISO-datum (ÅÅÅÅ-MM-DD).")
    name = result["download_name"]
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("Nedladdningsnamnet får inte innehålla en sökväg.")
    return result


def category_payload(db, payload, key=None):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltigt innehåll.")
    current = db.execute("SELECT * FROM categories WHERE key=?", (key,)).fetchone() if key else None
    name = payload.get("name", current["name"] if current else "")
    parent = payload.get("parent", current["parent"] if current else None)
    if not isinstance(name, str) or not name.strip() or len(name) > 60 or any(ord(c) < 32 for c in name):
        raise ValueError("Kategorinamn måste innehålla 1–60 tecken.")
    if parent == "":
        parent = None
    if parent is not None:
        if not isinstance(parent, str) or not db.execute("SELECT 1 FROM categories WHERE key=?", (parent,)).fetchone():
            raise ValueError("Överordnad kategori finns inte.")
        ancestor = parent
        seen = set()
        while ancestor:
            if ancestor == key or ancestor in seen:
                raise ValueError("Kategorier får inte bilda en cykel.")
            seen.add(ancestor)
            row = db.execute("SELECT parent FROM categories WHERE key=?", (ancestor,)).fetchone()
            ancestor = row["parent"] if row else None
    return name.strip(), parent


class Backups:
    def __init__(self, data):
        self.database = data / "library.sqlite"
        self.directory = Path(os.environ.get("BACKUP_DIR", str(data / "backups")))
        self.enabled = os.environ.get("BACKUPS_ENABLED", "true").lower() == "true"
        self.last_error = None
        self.external_directory = Path(os.environ["EXTERNAL_BACKUP_DIR"]) if os.environ.get("EXTERNAL_BACKUP_DIR") else None
        self.external_error = None
        self.external_last_success = None
        self.stop = threading.Event()

    def files(self):
        if not self.directory.exists():
            return []
        result = []
        for path in sorted(self.directory.glob("*.sqlite"), reverse=True):
            if self.valid_name(path.name) and path.is_file() and not path.is_symlink():
                stat = path.stat()
                result.append({"name": path.name, "created": dt.datetime.fromtimestamp(
                    stat.st_mtime, dt.timezone.utc).isoformat(), "size": stat.st_size})
        return result

    @staticmethod
    def valid_name(name):
        return bool(re.fullmatch(r"(?:daily-\d{4}-\d{2}-\d{2}|(?:manual|safety)-\d{8}T\d{12}-[a-f0-9]{8})\.sqlite", name))

    def path(self, name):
        if not self.valid_name(name):
            raise ValueError("Ogiltigt namn på säkerhetskopia.")
        path = self.directory / name
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError("Säkerhetskopian finns inte.")
        return path

    def status(self):
        return {"files": self.files(), "last_error": self.last_error, "enabled": self.enabled,
                "external": {"enabled": self.external_directory is not None,
                             "directory": str(self.external_directory) if self.external_directory else "",
                             "last_error": self.external_error, "last_success": self.external_last_success}}

    @staticmethod
    def checksum(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()

    def sync_external(self):
        if self.external_directory is None:
            return
        pending = None
        try:
            directory = self.external_directory
            if directory.resolve() == self.directory.resolve():
                raise ValueError("Extern backup måste använda en annan katalog än de lokala kopiorna.")
            if not directory.is_dir() or not (directory / ".prylbanken-backup-target").is_file():
                raise OSError("NAS-målet saknas eller markörfilen .prylbanken-backup-target saknas. Kontrollera monteringen.")
            with DB_LOCK:
                for entry in self.files():
                    source = self.path(entry["name"])
                    target = directory / entry["name"]
                    if target.is_symlink():
                        raise OSError("En extern säkerhetskopia får inte vara en symbolisk länk.")
                    digest = self.checksum(source)
                    if target.is_file() and self.checksum(target) == digest:
                        continue
                    pending = directory / (entry["name"] + "." + secrets.token_hex(8) + ".pending")
                    with pending.open("xb") as destination, source.open("rb") as original:
                        shutil.copyfileobj(original, destination)
                        destination.flush()
                        os.fsync(destination.fileno())
                    pending.chmod(0o600)
                    if self.checksum(pending) != digest:
                        raise OSError("Den externa kopian klarade inte kontrollsumman.")
                    pending.replace(target)
                    pending = None
                for prefix in ("daily-", "manual-", "safety-"):
                    files = sorted((p for p in directory.glob(prefix + "*.sqlite")
                                    if self.valid_name(p.name) and p.is_file() and not p.is_symlink()), reverse=True)
                    for expired in files[14:]:
                        expired.unlink()
            self.external_error = None
            self.external_last_success = dt.datetime.now(dt.timezone.utc).isoformat()
        except (OSError, ValueError) as error:
            self.external_error = str(error)
            logging.exception("External NAS backup failed")
            raise
        finally:
            if pending is not None and pending.exists():
                pending.unlink()

    def create(self, kind="manual", protect=None):
        if not self.enabled:
            raise ValueError("Automatiska och manuella SQLite-säkerhetskopior är avstängda.")
        with DB_LOCK:
            now = dt.datetime.now(dt.timezone.utc)
            name = ("daily-" + now.date().isoformat() if kind == "daily" else
                    kind + "-" + now.strftime("%Y%m%dT%H%M%S%f") + "-" + secrets.token_hex(4)) + ".sqlite"
            target = self.directory / name
            pending = target.with_suffix(".pending")
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(self.database)) as source:
                    destination = sqlite3.connect(pending)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                pending.replace(target)
                target.chmod(0o600)
                # Daily, manual and pre-restore safety backups each have a bounded retention.
                for prefix in ("daily-", "manual-", "safety-"):
                    old = sorted((p for p in self.directory.glob(prefix + "*.sqlite")
                                  if self.valid_name(p.name) and not p.is_symlink()), reverse=True)
                    kept = old[:14]
                    protected = next((p for p in old if p.name == protect), None)
                    if protected is not None and protected not in kept:
                        kept = old[:13] + [protected]
                    for path in old:
                        if path not in kept:
                            path.unlink()
                self.sync_external()
                self.last_error = None
                return next(entry for entry in self.files() if entry["name"] == name)
            except (OSError, sqlite3.Error) as error:
                self.last_error = str(error)
                logging.exception("SQLite backup failed")
                raise
            finally:
                if pending.exists():
                    pending.unlink()

    def restore(self, name, actor):
        with DB_LOCK:
            path = self.path(name)
            source = sqlite3.connect(path)
            source.row_factory = sqlite3.Row
            try:
                if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Säkerhetskopian är skadad.")
                for table, required in {
                    "items": {"id", "title", "category", "content", "filedata", "example_key"},
                    "users": {"id", "username", "password_hash"},
                    "sessions": {"token_hash", "user_id", "csrf", "expires"},
                    "login_attempts": {"address", "started", "attempts"},
                    "registration_attempts": {"address", "started", "attempts"},
                }.items():
                    if not required <= {r["name"] for r in source.execute(f"PRAGMA table_info({table})")}:
                        raise ValueError("Filen är inte en giltig Prylbanken-databas.")
                user_columns = {r["name"] for r in source.execute("PRAGMA table_info(users)")}
                conditions = []
                if "active" in user_columns:
                    conditions.append("active=1")
                if "role" in user_columns:
                    conditions.append("role='admin'")
                active = "WHERE " + " AND ".join(conditions) if conditions else ""
                if not source.execute("SELECT 1 FROM users " + active + " LIMIT 1").fetchone():
                    raise ValueError("Säkerhetskopian saknar ett aktivt administratörskonto.")
                safety = self.create("safety", protect=name)
                destination = sqlite3.connect(self.database)
                destination.row_factory = sqlite3.Row
                try:
                    source.backup(destination)
                    with destination:
                        migrate(destination)
                        destination.execute("DELETE FROM sessions")
                        audit(destination, actor, "database.restore", name)
                except Exception:
                    # Roll back the entire replacement if post-restore migration fails.
                    recovery = sqlite3.connect(self.path(safety["name"]))
                    try:
                        recovery.backup(destination)
                    finally:
                        recovery.close()
                    raise
                finally:
                    destination.close()
                self.last_error = None
                return safety
            except (OSError, sqlite3.Error, ValueError) as error:
                self.last_error = str(error)
                logging.exception("SQLite restore failed")
                raise
            finally:
                source.close()

    def run(self):
        while not self.stop.is_set():
            try:
                if self.enabled:
                    with DB_LOCK:
                        name = "daily-" + dt.datetime.now(dt.timezone.utc).date().isoformat() + ".sqlite"
                        if not (self.directory / name).is_file():
                            self.create("daily")
                        else:
                            self.sync_external()
            except (OSError, sqlite3.Error, ValueError) as error:
                self.last_error = str(error)
                logging.exception("Daily SQLite backup failed; retrying in one hour")
            self.stop.wait(3600)

    def start(self):
        threading.Thread(target=self.run, name="sqlite-backups", daemon=True).start()
