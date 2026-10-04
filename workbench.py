"""Shared knowledge tools and account-private state."""
import base64
import io
import json
import re
import secrets
import zipfile

from backend import audit


def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS personal_items (
        user_id INTEGER NOT NULL,item_id INTEGER NOT NULL,favorite INTEGER NOT NULL DEFAULT 0,
        opened TEXT,PRIMARY KEY(user_id,item_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS guides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT NOT NULL,
        prerequisites TEXT NOT NULL,steps TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS guide_progress (
        user_id INTEGER NOT NULL,guide_id INTEGER NOT NULL,step_key TEXT NOT NULL,
        PRIMARY KEY(user_id,guide_id,step_key))""")
    if "related_ids" not in {row["name"] for row in db.execute("PRAGMA table_info(items)")}:
        db.execute("ALTER TABLE items ADD COLUMN related_ids TEXT NOT NULL DEFAULT '[]'")


def related_ids(db, payload, old=None, restoring=False):
    ids = payload.get("related_ids", json.loads(old["related_ids"]) if old else [])
    if not isinstance(ids, list) or len(ids) > 50 or any(type(i) is not int or i < 1 for i in ids):
        raise ValueError("Högst 50 giltiga relations-ID krävs.")
    if len(set(ids)) != len(ids) or (old and old["id"] in ids):
        raise ValueError("Relationer måste vara unika och får inte hänvisa till posten själv.")
    existing = {row["id"] for row in db.execute("SELECT id FROM items")}
    previous = set(json.loads(old["related_ids"])) if old else set()
    if not restoring and any(i not in existing and i not in previous for i in ids):
        raise ValueError("En relaterad post finns inte längre.")
    return json.dumps([i for i in ids if not restoring or i in existing])


def guide_payload(db, payload, old=None):
    from registry import server_ids
    if not isinstance(payload, dict):
        raise ValueError("Ogiltig guide.")
    result = {}
    for key, limit in (("title", 200), ("description", 5000), ("prerequisites", 5000)):
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > limit or (key == "title" and not value.strip()):
            raise ValueError("Guiden kräver en titel och giltiga textfält.")
        result[key] = value.strip() if key == "title" else value
    steps = payload.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise ValueError("En guide måste innehålla 1–100 steg.")
    old_keys = {step["key"] for step in json.loads(old["steps"])} if old else set()
    new_servers = server_ids(db, payload, old)
    changed_servers = old is not None and set(json.loads(new_servers)) != set(json.loads(old["server_ids"]))
    keys, normalized = set(), []
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("text"), str) or not 1 <= len(step["text"].strip()) <= 2000:
            raise ValueError("Varje steg kräver 1–2000 tecken.")
        key = step.get("key")
        if key is not None and (not isinstance(key, str) or key not in old_keys or key in keys):
            raise ValueError("Ogiltig eller upprepad stegnyckel.")
        key = key or secrets.token_hex(16)
        keys.add(key)
        item_id = step.get("item_id")
        if item_id is not None and (type(item_id) is not int or not db.execute(
                "SELECT 1 FROM items WHERE id=? AND deleted_at IS NULL", (item_id,)).fetchone()):
            # Existing steps may retain a link to a trashed/purged post, visibly marked in the UI.
            previous = next((s for s in json.loads(old["steps"]) if s["key"] == key), None) if old else None
            if not previous or previous.get("item_id") != item_id:
                raise ValueError("Stegets länkade post finns inte i biblioteket.")
        previous = next((s for s in json.loads(old["steps"]) if s["key"] == key), None) if old else None
        if previous and (changed_servers or previous["text"] != step["text"] or previous.get("item_id") != item_id):
            key = secrets.token_hex(16)
        normalized.append({"key": key, "text": step["text"], "item_id": item_id})
    result["steps"] = json.dumps(normalized, ensure_ascii=False)
    result["server_ids"] = new_servers
    return result


def export_zip(db, project_id):
    project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        raise FileNotFoundError("Projektsamlingen finns inte.")
    condition = "deleted_at IS NULL AND EXISTS (SELECT 1 FROM json_each(items.project_ids) WHERE value=?)"
    stats = db.execute("SELECT COUNT(*),COALESCE(SUM(COALESCE(length(filedata),0)+"
                       "length(CAST(content AS BLOB))+length(CAST(notes AS BLOB))),0) FROM items WHERE " + condition,
                       (project_id,)).fetchone()
    if stats[0] > 5000 or stats[1] > 50 * 1024 * 1024:
        raise ValueError("Projektet är för stort för ZIP-export (högst 5000 poster/50 MB rådata).")
    rows = [dict(row) for row in db.execute("SELECT * FROM items WHERE " + condition + " ORDER BY id", (project_id,))]
    index = [project["name"], project["description"], "",
             "Offline-export. Inget körs automatiskt. Granska risker och argument före användning.", ""]
    payload_items = []
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", row["download_name"] or row["title"]).strip(". ")[:100] or "text"
            text_path = f'posts/{row["id"]}-{safe}'
            if not row["download_name"]:
                text_path += ".txt"
            archive.writestr(text_path, row["content"])
            archive.writestr(f'notes/{row["id"]}.txt', row["notes"] + "\nRisk: " + row["risk"] +
                             "\nRelationer: " + row["related_ids"])
            index.append(f'{row["id"]}. {row["title"]} -> {text_path} (risk: {row["risk"]})')
            if row["filedata"] is not None:
                filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", row["filename"]).strip(". ")[:100] or "file"
                path = f'attachments/{row["id"]}-{filename}'
                archive.writestr(path, row["filedata"])
                index.append("   Bilaga: " + path)
            row["project_ids"] = [project_id]
            row["server_ids"] = json.loads(row["server_ids"])
            row["related_ids"] = json.loads(row["related_ids"])
            row["filedata"] = base64.b64encode(row["filedata"]).decode() if row["filedata"] is not None else None
            payload_items.append(row)
        archive.writestr("INDEX.txt", "\n".join(index))
        archive.writestr("library.json", json.dumps({"version": 1, "items": payload_items,
                                                    "projects": [dict(project)],
                                                    "servers": [dict(row) for row in db.execute("SELECT * FROM servers")
                                                                if any(row["id"] in item["server_ids"] for item in payload_items)]}, ensure_ascii=False))
    return data.getvalue()


def get(handler, db, path):
    uid = handler.user["id"]
    if path == "/api/personal":
        handler.reply(200, [dict(row) for row in db.execute(
            "SELECT p.item_id,p.favorite,p.opened FROM personal_items p JOIN items i ON i.id=p.item_id "
            "WHERE p.user_id=? AND i.deleted_at IS NULL ORDER BY p.opened DESC", (uid,))])
        return True
    if path == "/api/guides":
        guides = []
        for row in db.execute("SELECT * FROM guides ORDER BY title,id"):
            completed = [r["step_key"] for r in db.execute(
                "SELECT step_key FROM guide_progress WHERE user_id=? AND guide_id=?", (uid, row["id"]))]
            guides.append({**dict(row), "steps": json.loads(row["steps"]), "server_ids": json.loads(row["server_ids"]), "completed": completed})
        handler.reply(200, guides)
        return True
    match = re.fullmatch(r"/api/projects/(\d+)/export", path)
    if match:
        handler.reply(200, export_zip(db, int(match[1])), "application/zip",
                      {"Content-Disposition": f'attachment; filename="project-{match[1]}.zip"'})
        return True
    return False


def mutate(handler, db, method, path):
    personal = re.fullmatch(r"/api/personal/(\d+)", path)
    progress = re.fullmatch(r"/api/guides/(\d+)/progress", path)
    match = re.fullmatch(r"/api/guides/(\d+)", path)
    uid = handler.user["id"]
    if personal and method == "PUT":
        item_id = int(personal[1])
        if not db.execute("SELECT 1 FROM items WHERE id=? AND deleted_at IS NULL", (item_id,)).fetchone():
            raise FileNotFoundError("Posten finns inte i biblioteket.")
        payload = handler.read_json(2048)
        if not isinstance(payload, dict) or not payload or set(payload) - {"favorite", "opened"}:
            raise ValueError("Ogiltig personlig markering.")
        if any(type(value) is not bool for value in payload.values()) or ("opened" in payload and not payload["opened"]):
            raise ValueError("Markeringar måste vara booleska; opened måste vara true.")
        db.execute("INSERT OR IGNORE INTO personal_items(user_id,item_id) VALUES (?,?)", (uid, item_id))
        if "favorite" in payload:
            db.execute("UPDATE personal_items SET favorite=? WHERE user_id=? AND item_id=?",
                       (int(payload["favorite"]), uid, item_id))
        if payload.get("opened"):
            db.execute("UPDATE personal_items SET opened=strftime('%Y-%m-%d %H:%M:%f','now') WHERE user_id=? AND item_id=?",
                       (uid, item_id))
            db.execute("UPDATE personal_items SET opened=NULL WHERE user_id=? AND item_id NOT IN "
                       "(SELECT item_id FROM personal_items WHERE user_id=? ORDER BY opened DESC LIMIT 100)", (uid, uid))
        db.execute("DELETE FROM personal_items WHERE user_id=? AND favorite=0 AND opened IS NULL", (uid,))
        db.commit()
        handler.reply(200, {"ok": True})
        return True
    if progress and method == "PUT":
        row = db.execute("SELECT steps FROM guides WHERE id=?", (int(progress[1]),)).fetchone()
        if not row:
            raise FileNotFoundError("Guiden finns inte.")
        payload = handler.read_json(16384)
        completed = payload.get("completed") if isinstance(payload, dict) else None
        keys = {step["key"] for step in json.loads(row["steps"])}
        if not isinstance(completed, list) or len(completed) > 100 or any(not isinstance(k, str) or k not in keys for k in completed):
            raise ValueError("Ogiltiga avbockade steg.")
        db.execute("DELETE FROM guide_progress WHERE user_id=? AND guide_id=?", (uid, int(progress[1])))
        db.executemany("INSERT INTO guide_progress VALUES (?,?,?)",
                       [(uid, int(progress[1]), key) for key in set(completed)])
        db.commit()
        handler.reply(200, {"ok": True})
        return True
    if (path == "/api/guides" and method == "POST") or (match and method in ("PUT", "DELETE")):
        guide_id = int(match[1]) if match else None
        old = db.execute("SELECT * FROM guides WHERE id=?", (guide_id,)).fetchone() if match else None
        if match and not old:
            raise FileNotFoundError("Guiden finns inte.")
        if method == "DELETE":
            db.execute("DELETE FROM guides WHERE id=?", (guide_id,))
            db.execute("DELETE FROM guide_progress WHERE guide_id=?", (guide_id,))
        else:
            if not match and db.execute("SELECT COUNT(*) FROM guides").fetchone()[0] >= 200:
                raise ValueError("Högst 200 guider.")
            values = guide_payload(db, handler.read_json(300000), old)
            if old:
                db.execute("UPDATE guides SET title=?,description=?,prerequisites=?,steps=?,server_ids=? WHERE id=?",
                           (*values.values(), guide_id))
                keys = {step["key"] for step in json.loads(values["steps"])}
                for row in db.execute("SELECT DISTINCT step_key FROM guide_progress WHERE guide_id=?", (guide_id,)).fetchall():
                    if row["step_key"] not in keys:
                        db.execute("DELETE FROM guide_progress WHERE guide_id=? AND step_key=?", (guide_id, row["step_key"]))
            else:
                guide_id = db.execute("INSERT INTO guides(title,description,prerequisites,steps,server_ids) VALUES (?,?,?,?,?)",
                                      tuple(values.values())).lastrowid
        audit(db, handler.user["username"], "guide." + method.lower(), guide_id)
        db.commit()
        handler.reply(201 if method == "POST" else 200, {"id": guide_id})
        return True
    return False
