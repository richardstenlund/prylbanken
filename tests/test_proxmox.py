from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import unittest

from backend import migrate
from proxmox_catalog import EXAMPLES


GIT_BASH = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
BASH = str(GIT_BASH) if GIT_BASH.is_file() else shutil.which("bash")
SCRIPTS = {item["key"]: item["content"] for item in EXAMPLES if item.get("download_name")}


class ProxmoxMigrationTests(unittest.TestCase):
    def test_seeded_install_gets_category_without_overwriting_custom_names(self):
        with closing(sqlite3.connect(":memory:")) as db, db:
            db.row_factory = sqlite3.Row
            db.executescript("""
                CREATE TABLE items(id INTEGER PRIMARY KEY,category TEXT,content TEXT,
                                   filedata BLOB,example_key TEXT);
                CREATE TABLE users(id INTEGER PRIMARY KEY);
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                INSERT INTO settings VALUES ('categories_seeded','true');
                CREATE TABLE categories(key TEXT PRIMARY KEY,name TEXT NOT NULL,parent TEXT);
                INSERT INTO categories VALUES ('docker','Mina containrar',NULL);
            """)
            migrate(db)
            self.assertEqual(db.execute("SELECT name FROM categories WHERE key='proxmox'").fetchone()[0],
                             "Proxmox VE")
            self.assertEqual(db.execute("SELECT name FROM categories WHERE key='docker'").fetchone()[0],
                             "Mina containrar")
            db.execute("UPDATE categories SET name='Min virtualisering',parent='docker' WHERE key='proxmox'")
            migrate(db)
            self.assertEqual(tuple(db.execute("SELECT name,parent FROM categories WHERE key='proxmox'").fetchone()),
                             ("Min virtualisering", "docker"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM categories WHERE key='proxmox'").fetchone()[0], 1)


@unittest.skipUnless(BASH, "Bash krävs för skripttester")
class ProxmoxScriptTests(unittest.TestCase):
    def run_script(self, source, arguments=(), confirmation="", mock=""):
        result = subprocess.run([BASH, "-c", mock + "\n" + source, "pve-test", *arguments],
                                input=confirmation.encode("utf-8"), capture_output=True, timeout=5)
        return subprocess.CompletedProcess(result.args, result.returncode,
                                           result.stdout.decode("utf-8"), result.stderr.decode("utf-8"))

    def test_all_bash_templates_have_valid_syntax(self):
        for item in EXAMPLES:
            if item["language"] == "bash":
                with self.subTest(key=item["key"]):
                    result = subprocess.run([BASH, "-n"], input=item["content"], text=True,
                                            capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_backup_requires_valid_arguments_and_confirmation(self):
        source = SCRIPTS["proxmox-backup-script"]
        mock = 'vzdump() { printf "MOCK_BACKUP"; printf " <%s>" "$@"; }\n'
        for arguments, confirmation in [
            ((), "BACKUP\n"), (("100",), "BACKUP\n"),
            (("invalid", "backup"), "BACKUP\n"), (("99", "backup"), "BACKUP\n"),
            (("100", "--all"), "BACKUP\n"), (("100", "backup;bad"), "BACKUP\n"),
            (("100", "backup"), "no\n"), (("100", "backup"), ""),
        ]:
            with self.subTest(arguments=arguments, confirmation=confirmation):
                result = self.run_script(source, arguments, confirmation, mock)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("MOCK_BACKUP", result.stdout)
        result = self.run_script(source, ("100", "backup-store"), "BACKUP\n", mock)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MOCK_BACKUP <100> <--storage> <backup-store> <--mode> <snapshot>", result.stdout)

    def test_backup_propagates_failure(self):
        result = self.run_script(SCRIPTS["proxmox-backup-script"], ("100", "backup"), "BACKUP\n",
                                 'vzdump() { printf "Mock backup failed\\n" >&2; return 7; }\n')
        self.assertEqual(result.returncode, 7)
        self.assertIn("Mock backup failed", result.stderr)

    def test_inventory_stops_on_failure(self):
        mock = ('pveversion() { printf "Mock version\\n"; }\n'
                'qm() { printf "Mock inventory failed\\n" >&2; return 8; }\n'
                'pct() { printf "SHOULD_NOT_RUN\\n"; }\n'
                'pvesm() { printf "SHOULD_NOT_RUN\\n"; }\n')
        result = self.run_script(SCRIPTS["proxmox-report-script"], mock=mock)
        self.assertEqual(result.returncode, 8)
        self.assertIn("Mock inventory failed", result.stderr)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout)
