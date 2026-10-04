import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHELL = (Path(r"C:\Program Files\Git\bin\bash.exe") if os.name == "nt"
         else shutil.which("sh"))


@unittest.skipUnless(SHELL and Path(SHELL).exists(), "POSIX-shell saknas")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        shutil.copyfile(ROOT / "install.sh", self.folder / "install.sh")
        self.bin = self.folder / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$*" >> calls.txt\n'
            'case "$*" in\n'
            '  info) exit "${FAIL_INFO:-0}" ;;\n'
            '  "compose version") exit "${FAIL_VERSION:-0}" ;;\n'
            '  "compose config --quiet") exit "${FAIL_CONFIG:-0}" ;;\n'
            '  "compose up -d --build --wait --wait-timeout 120") exit "${FAIL_START:-0}" ;;\n'
            '  *) echo "Unexpected Docker command" >&2; exit 99 ;;\n'
            'esac\n', encoding="utf-8", newline="\n")
        docker.chmod(0o700)

    def run_install(self, **env):
        if os.name == "nt":
            command = [str(SHELL), "-c",
                       'export PATH="$(cygpath -u "$1"):$PATH"; cd "$(cygpath -u "$2")"; sh install.sh',
                       "test-install", str(self.bin), str(self.folder)]
        else:
            command = [str(SHELL), str(self.folder / "install.sh")]
        return subprocess.run(command, cwd=self.folder,
                              env={**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"], **env},
                              capture_output=True, text=True, timeout=20)

    def test_first_install_generates_configuration_and_waits(self):
        result = self.run_install(APP_PASSWORD="must-not-be-used")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = (self.folder / ".env").read_text().splitlines()
        password = lines[0].split("=", 1)[1]
        self.assertRegex(password, r"^[a-f0-9]{48}$")
        self.assertEqual(lines[1:], ["BIND_ADDRESS=0.0.0.0", "APP_PORT=8080"])
        self.assertIn(password, result.stdout)
        self.assertIn("compose up -d --build --wait --wait-timeout 120",
                      (self.folder / "calls.txt").read_text())
        if os.name != "nt":
            self.assertEqual((self.folder / ".env").stat().st_mode & 0o777, 0o600)

    def test_repeat_install_preserves_configuration(self):
        original = "APP_PASSWORD=existing-secret-for-test\nBIND_ADDRESS=127.0.0.1\nAPP_PORT=8081\n"
        (self.folder / ".env").write_text(original)
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.folder / ".env").read_text(), original)
        self.assertNotIn("existing-secret-for-test", result.stdout)

    def test_docker_not_ready_does_not_create_configuration(self):
        result = self.run_install(FAIL_INFO="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.folder / ".env").exists())
        self.assertIn("Docker svarar inte", result.stderr)

    def test_invalid_configuration_does_not_start_container(self):
        result = self.run_install(FAIL_CONFIG="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("compose up", (self.folder / "calls.txt").read_text())
        self.assertIn("Konfigurationen ar ogiltig", result.stderr)

    def test_start_failure_does_not_report_success(self):
        result = self.run_install(FAIL_START="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.folder / ".env").exists())
        self.assertNotIn("halsokontrollen har godkants", result.stdout)
        self.assertIn("Installationen ar inte klar", result.stderr)


if __name__ == "__main__":
    unittest.main()
