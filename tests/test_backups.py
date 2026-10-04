from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend import Backups


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manager = Backups(self.root)
        self.manager.directory = self.root / "backups"
        self.manager.enabled = True
        with closing(sqlite3.connect(self.root / "library.sqlite")) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE sample(value TEXT)")
            db.execute("INSERT INTO sample VALUES ('committed content')")

    def test_online_backup_and_daily_retention_exactly_fourteen(self):
        self.manager.directory.mkdir()
        for day in range(1, 21):
            (self.manager.directory / f"daily-2000-01-{day:02d}.sqlite").touch()
        entry = self.manager.create("daily")
        files = self.manager.files()
        self.assertEqual(len(files), 14)
        self.assertIn(entry["name"], {file["name"] for file in files})
        self.assertFalse((self.manager.directory / "daily-2000-01-07.sqlite").exists())
        self.assertTrue((self.manager.directory / "daily-2000-01-08.sqlite").exists())
        with closing(sqlite3.connect(self.manager.path(entry["name"]))) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT value FROM sample").fetchone()[0], "committed content")
        self.assertEqual(list(self.manager.directory.glob("*.pending")), [])

    def test_manual_and_safety_retention_are_independently_bounded(self):
        for kind in ("manual", "safety"):
            for _ in range(16):
                self.manager.create(kind)
        files = self.manager.files()
        self.assertEqual(len([file for file in files if file["name"].startswith("manual-")]), 14)
        self.assertEqual(len([file for file in files if file["name"].startswith("safety-")]), 14)

    def test_online_backup_includes_committed_wal_data(self):
        with closing(sqlite3.connect(self.root / "library.sqlite")) as source:
            source.execute("INSERT INTO sample VALUES ('still in WAL')")
            source.commit()
            self.assertTrue((self.root / "library.sqlite-wal").exists())
            entry = self.manager.create()
            with closing(sqlite3.connect(self.manager.path(entry["name"]))) as destination:
                values = [row[0] for row in destination.execute("SELECT value FROM sample")]
                self.assertEqual(values, ["committed content", "still in WAL"])

    def test_backup_failure_is_logged_and_status_reports_error(self):
        blocked = self.root / "not-a-directory"
        blocked.write_text("blocked", encoding="ascii")
        self.manager.directory = blocked
        with self.assertLogs(level="ERROR"):
            with self.assertRaises(OSError):
                self.manager.create()
        self.assertTrue(self.manager.last_error)
        self.manager.directory = self.root / "backups"
        self.manager.create()
        self.assertIsNone(self.manager.status()["last_error"])

    def test_daily_scheduler_creates_missing_day_and_waits_one_hour(self):
        self.manager.stop = Mock()
        self.manager.stop.is_set.side_effect = [False, True]
        with patch.object(self.manager, "create") as create:
            self.manager.run()
        create.assert_called_once_with("daily")
        self.manager.stop.wait.assert_called_once_with(3600)

    def test_daily_scheduler_does_not_overwrite_existing_day(self):
        self.manager.create("daily")
        self.manager.stop = Mock()
        self.manager.stop.is_set.side_effect = [False, True]
        with patch.object(self.manager, "create") as create:
            self.manager.run()
        create.assert_not_called()

    def test_backup_names_reject_traversal_and_disabled_creation(self):
        for name in ("../library.sqlite", r"..\library.sqlite", "library.sqlite", "manual-bad.sqlite"):
            with self.assertRaises(ValueError):
                self.manager.path(name)
        self.manager.enabled = False
        with self.assertRaises(ValueError):
            self.manager.create()
        self.assertFalse(self.manager.status()["enabled"])

    def enable_external(self):
        self.external = self.root / "nas"
        self.external.mkdir()
        (self.external / ".prylbanken-backup-target").touch()
        self.manager.external_directory = self.external

    def test_external_copy_is_byte_verified_and_corruption_repaired(self):
        self.enable_external()
        entry = self.manager.create()
        original = self.manager.path(entry["name"])
        copy = self.external / entry["name"]
        self.assertEqual(original.read_bytes(), copy.read_bytes())
        self.assertTrue(self.manager.status()["external"]["last_success"])
        copy.write_bytes(b"corrupt copy")
        self.manager.sync_external()
        self.assertEqual(original.read_bytes(), copy.read_bytes())
        self.assertEqual(list(self.external.glob("*.pending")), [])

    def test_external_missing_mount_reports_error_keeps_local_and_retries(self):
        self.enable_external()
        marker = self.external / ".prylbanken-backup-target"
        marker.unlink()
        with self.assertLogs(level="ERROR"), self.assertRaises(OSError):
            self.manager.create()
        self.assertEqual(len(self.manager.files()), 1)
        self.assertTrue(self.manager.status()["external"]["last_error"])
        self.assertEqual(list(self.external.glob("*.sqlite")), [])
        marker.touch()
        self.manager.sync_external()
        self.assertIsNone(self.manager.status()["external"]["last_error"])
        self.assertEqual(len(list(self.external.glob("*.sqlite"))), 1)

    def test_external_retention_exactly_fourteen_and_unrelated_files_kept(self):
        self.enable_external()
        for day in range(1, 21):
            (self.external / f"daily-2000-01-{day:02d}.sqlite").touch()
        unrelated = self.external / "personal.sqlite"
        unrelated.write_bytes(b"untouched")
        self.manager.create("daily")
        self.assertEqual(len(list(self.external.glob("daily-*.sqlite"))), 14)
        self.assertEqual(unrelated.read_bytes(), b"untouched")

    def test_external_same_directory_is_rejected(self):
        self.manager.external_directory = self.manager.directory
        with self.assertLogs(level="ERROR"), self.assertRaises(ValueError):
            self.manager.create()
