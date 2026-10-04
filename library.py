"""Shared validation for collections, saved searches and batch import."""
import base64
import binascii
import hashlib
import json

ROLES = {"reader", "editor", "admin"}


def named(payload, limit=80):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltigt innehåll.")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > limit or any(ord(c) < 32 for c in name):
        raise ValueError(f"Namn måste innehålla 1–{limit} tecken.")
    return name.strip()


def attachments(payload, creating=False):
    if "filedata" in payload and payload["filedata"] is not None:
        filename, encoded = payload.get("filename", ""), payload["filedata"]
        maximum = 20 * 1024 * 1024
        if not isinstance(filename, str) or not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
            raise ValueError("Ogiltigt filnamn.")
        if not isinstance(encoded, str) or len(encoded) > (maximum + 2) // 3 * 4:
            raise ValueError("Filen får vara högst 20 MB.")
        try:
            blob = base64.b64decode(encoded, validate=True)
        except binascii.Error:
            raise ValueError("Ogiltig filkodning.")
        if len(blob) > maximum:
            raise ValueError("Filen får vara högst 20 MB.")
        return {"filename": filename.replace("\\", "/").rsplit("/", 1)[-1], "filedata": blob}
    return {"filename": None, "filedata": None} if "filedata" in payload or creating else {}


def fingerprint(content, blob, text_file=False):
    if not content and blob is None and not text_file:
        return None
    digest = hashlib.sha256()
    digest.update(content.encode("utf-8"))
    digest.update(b"\x00attachment\x00" if blob is not None else b"\x00text\x00")
    if blob is not None:
        digest.update(blob)
    return digest.hexdigest()


def project_ids(db, payload, old=None, restoring=False):
    values = payload.get("project_ids", json.loads(old["project_ids"]) if old is not None else [])
    if not isinstance(values, list) or len(values) > 100 or any(type(value) is not int or value < 1 for value in values):
        raise ValueError("Ogiltig projektsamling.")
    existing = {row[0] for row in db.execute("SELECT id FROM projects")}
    if not restoring and any(value not in existing for value in values):
        raise ValueError("Projektsamlingen finns inte längre.")
    return json.dumps(sorted(set(values) & existing))


def search_filters(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ogiltiga sökfilter.")
    result = {}
    for key, maximum in {"query": 500, "category": 60, "tags": 500, "os": 200,
                         "language": 20, "status": 20, "sort": 20}.items():
        value = payload.get(key, "new" if key == "sort" else "all" if key == "category" else "")
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError(f"Ogiltigt sökfilter: {key}.")
        result[key] = value
    for key in ("descendants", "attachments", "personal", "review", "troubleshooting"):
        value = payload.get(key, False)
        if not isinstance(value, bool):
            raise ValueError(f"Ogiltigt sökfilter: {key}.")
        result[key] = value
    project = payload.get("project", "")
    if not isinstance(project, str) or len(project) > 20 or (project and not project.isdigit()):
        raise ValueError("Ogiltig projektfiltrering.")
    result["project"] = project
    server = payload.get("server", "")
    if not isinstance(server, str) or len(server) > 20 or (server and not server.isdigit()):
        raise ValueError("Ogiltig serverfiltrering.")
    result["server"] = server
    if result["sort"] not in {"new", "old", "title"}:
        raise ValueError("Ogiltig sortering.")
    if result["status"] not in {"", "template", "tested", "needs-update"}:
        raise ValueError("Ogiltig statusfiltrering.")
    if result["language"] not in {"", "plain", "bash", "powershell", "bat", "yaml", "json", "python", "javascript", "sql", "markdown"}:
        raise ValueError("Ogiltig språkfiltrering.")
    return result
