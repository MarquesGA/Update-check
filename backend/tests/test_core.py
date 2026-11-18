import tempfile
import unittest
from datetime import date
from pathlib import Path
import sys
from unittest.mock import patch

from backend.analyzer.correlation import correlate
from backend.database.db import connect, initialize
from backend.package_manager.pacman import parse_checkupdates


class CoreTests(unittest.TestCase):
    def test_checkupdates_parser(self):
        parsed = parse_checkupdates("linux-cachyos 6.17-1 -> 6.18-1\nmesa 25.2 -> 25.3\n")
        self.assertEqual([p["name"] for p in parsed], ["linux-cachyos", "mesa"])
        self.assertEqual(parsed[0]["available_version"], "6.18-1")
        self.assertEqual(parse_checkupdates("sem saída válida"), [])

    def test_correlation_requires_exact_package_name(self):
        items = [{"id": 1, "title": "Issue: linux-cachyos freezes", "content": "Reported freeze",
                  "published_at": "2026-11-10", "url": "https://example.invalid/1"},
                 {"id": 2, "title": "linux-cachyos2 is fine", "content": "", "url": "https://example.invalid/2"}]
        result = correlate("linux-cachyos", items)
        self.assertEqual(result["report_count"], 1)
        self.assertEqual(result["risk"], "informative")

    def test_completed_github_report_is_shown_as_resolved(self):
        result = correlate("mesa", [{"id": 3, "title": "mesa regression", "content": "",
            "published_at": "2026-11-10", "url": "https://example.invalid/3", "resolution": "fixed"}])
        self.assertEqual(result["report_count"], 0)
        self.assertEqual(result["resolved_count"], 1)
        self.assertEqual(result["risk"], "normal")

    def test_critical_risk_requires_recent_corroboration_across_sources(self):
        reports = [{"id": i, "source_id": 1 if i < 4 else 2, "title": "mesa regression",
                    "content": "", "published_at": date.today().isoformat(),
                    "url": f"https://example.invalid/{i}", "resolution": "open"} for i in range(1, 6)]
        self.assertEqual(correlate("mesa", reports)["risk"], "critical")

    def test_database_deduplicates_publication_url(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "data.sqlite"
            initialize(dbpath)
            with connect(dbpath) as db:
                source_id = db.execute("SELECT id FROM sources LIMIT 1").fetchone()[0]
                for _ in range(2):
                    db.execute("INSERT OR IGNORE INTO publications(source_id,title,url) VALUES(?,?,?)",
                               (source_id, "Example", "https://example.invalid/post"))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 1)

    def test_sync_refreshes_existing_issue_resolution_and_content(self):
        from backend.collectors import sync
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "data.sqlite"
            initialize(dbpath)
            with connect(dbpath) as db:
                db.execute("UPDATE sources SET enabled=0")
                db.execute("UPDATE sources SET enabled=1 WHERE kind='github'")
            initial = {"external_id": "42", "title": "GPU regression", "content": "still affected",
                       "author": "dev", "published_at": "2026-11-01", "url": "https://example.invalid/issue/42",
                       "resolution": "open"}
            fixed = {**initial, "content": "fixed in 2.0", "resolution": "fixed"}
            with patch.object(sync, "collect", side_effect=[[initial], [fixed]]):
                sync.sync_all(dbpath)
                sync.sync_all(dbpath)
            with connect(dbpath) as db:
                rows = db.execute("SELECT content,resolution FROM publications").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["content"], rows[0]["resolution"]), ("fixed in 2.0", "fixed"))

    def test_none_database_path_uses_default_path(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "default.sqlite"
            with patch("backend.database.db.DB_PATH", dbpath):
                with connect(None) as db:
                    db.execute("SELECT 1")
            self.assertTrue(dbpath.exists())

    def test_successful_empty_package_refresh_clears_stale_updates(self):
        from backend.app import refresh_packages
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "data.sqlite"
            initialize(dbpath)
            with connect(dbpath) as db:
                db.execute("INSERT INTO packages(name,installed_version,available_version,repository) VALUES(?,?,?,?)",
                           ("stale-package", "1", "2", "official"))
            with patch("backend.app.get_updates", return_value=([], None)):
                result = refresh_packages(dbpath)
            with connect(dbpath) as db:
                count = db.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
            self.assertEqual(result["packages"], [])
            self.assertEqual(count, 0)

    def test_package_query_only_calls_checkupdates(self):
        from backend.package_manager import pacman
        with patch.object(pacman.shutil, "which", side_effect=lambda name: "/usr/bin/checkupdates" if name == "checkupdates" else None), \
             patch.object(pacman.subprocess, "run", return_value=type("P", (), {"returncode": 0, "stdout": "pkg 1 -> 2", "stderr": ""})()) as run:
            packages, error = pacman.get_updates()
        self.assertIsNone(error)
        self.assertEqual(packages[0]["available_version"], "2")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/checkupdates"])

    def test_aur_query_uses_read_only_paru_mode(self):
        from backend.package_manager import pacman
        outputs = [type("P", (), {"returncode": 0, "stdout": "official 1 -> 2", "stderr": ""})(),
                   type("P", (), {"returncode": 0, "stdout": "aur-tool 3 -> 4", "stderr": ""})()]
        which = lambda name: {"checkupdates": "/usr/bin/checkupdates", "paru": "/usr/bin/paru"}.get(name)
        with patch.object(pacman.shutil, "which", side_effect=which), \
             patch.object(pacman.subprocess, "run", side_effect=outputs) as run:
            packages, error = pacman.get_updates()
        self.assertIsNone(error)
        self.assertEqual([(p["name"], p["repository"]) for p in packages],
                         [("official", "official"), ("aur-tool", "AUR")])
        self.assertEqual(run.call_args_list[1].args[0], ["/usr/bin/paru", "-Qua"])

    def test_hardware_detection_returns_expected_fields(self):
        from backend.hardware import detect
        with patch.object(detect, "command", side_effect=lambda args: {
            "lscpu": "Model name: Test CPU\nCore(s) per socket: 4\nCPU(s): 8",
            "lspci": "01:00.0 VGA compatible controller [0300]: Test GPU [1234:abcd]\n\tKernel driver in use: amdgpu",
            "findmnt": "btrfs",
        }.get(args[0], "")):
            result = detect.detect()
        self.assertEqual(result["cpu"], "Test CPU")
        self.assertEqual(result["gpus"][0]["driver"], "amdgpu")
        self.assertEqual(result["filesystem"], "btrfs")

    def test_hardware_cpu_name_falls_back_to_proc_cpuinfo(self):
        from backend.hardware import detect
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if str(path) == "/proc/cpuinfo":
                return "processor : 0\nmodel name : Locale-proof CPU\nphysical id : 0\ncore id : 0\n\nprocessor : 1\nmodel name : Locale-proof CPU\nphysical id : 0\ncore id : 1\n"
            if str(path) == "/etc/os-release": return 'PRETTY_NAME="Test Linux"\n'
            if str(path) == "/proc/meminfo": return "MemTotal: 1024 kB\n"
            return original(path, *args, **kwargs)
        with patch.object(detect, "command", side_effect=lambda args: {
            "lscpu": "Nom du modèle: localized\nCPU(s): 2", "lspci": "", "findmnt": "btrfs"
        }.get(args[0], "")), patch.object(Path, "read_text", autospec=True, side_effect=read_text):
            result = detect.detect()
        self.assertEqual(result["cpu"], "Locale-proof CPU")
        self.assertEqual(result["cores"], "2")

    def test_package_download_size_parser(self):
        from backend.package_manager.pacman import parse_download_sizes
        parsed = parse_download_sizes("Name : mesa\nDownload Size : 1.50 MiB\n\nName : kernel\nDownload Size : 512.00 KiB\n\nName : mesa\nDownload Size : 2.00 MiB\n")
        self.assertEqual(parsed, {"mesa": int(1.5 * 1024**2), "kernel": 512 * 1024})

    def test_requested_sources_are_registered(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "data.sqlite"
            initialize(dbpath)
            with connect(dbpath) as db:
                names = {row["name"]: row["url"] for row in db.execute("SELECT name,url FROM sources")}
        self.assertEqual(names["CachyOS Distribution Issues"], "https://github.com/CachyOS/distribution/issues")
        self.assertEqual(names["Mesa Issues"], "https://gitlab.freedesktop.org/mesa/mesa/-/issues")
        self.assertEqual(names["AMD GPU Driver Issues"], "https://github.com/ROCm/amdgpu/issues")

    def test_system_commands_are_fixed_and_not_auto_confirmed(self):
        from backend import system_operations as ops
        paths = {"pkexec": "/usr/bin/pkexec", "pacman": "/usr/bin/pacman", "snapper": "/usr/bin/snapper"}
        with patch.object(ops.shutil, "which", side_effect=lambda name: paths.get(name)):
            update, _ = ops.command_for("update")
            snapshot, _ = ops.command_for("snapshot")
        self.assertEqual(update, ["/usr/bin/pkexec", "/usr/bin/pacman", "-Syu"])
        self.assertNotIn("--noconfirm", update)
        self.assertEqual(snapshot[1:5], ["/usr/bin/snapper", "--config", "root", "create"])

    def test_update_prefers_installed_aur_helper_without_shell(self):
        from backend import system_operations as ops
        paths = {"paru": "/usr/bin/paru", "pkexec": "/usr/bin/pkexec", "pacman": "/usr/bin/pacman"}
        with patch.object(ops.shutil, "which", side_effect=lambda name: paths.get(name)):
            argv, _ = ops.command_for("update")
        self.assertEqual(argv, ["/usr/bin/paru", "-Syu"])

    def test_update_requires_explicit_confirmation_before_start(self):
        from backend.system_operations import start
        with self.assertRaises(PermissionError):
            start("update")
        with self.assertRaises(PermissionError):
            start("snapshot")

    def test_operation_input_accepts_password_without_interpreting_shell_text(self):
        from backend import system_operations as ops
        job_id = "input-test"
        ops._jobs[job_id] = {"id": job_id, "kind": "update", "status": "running", "master": 123}
        try:
            with patch.object(ops.os, "write") as write:
                ops.send_input(job_id, "S3nh@; texto literal")
            self.assertEqual(write.call_args.args, (123, "S3nh@; texto literal\n".encode()))
            with self.assertRaises(ValueError):
                ops.send_input(job_id, "senha\ncom quebra")
        finally:
            ops._jobs.pop(job_id, None)

    def test_system_operations_are_in_combined_history(self):
        from backend.app import combine_history
        records = combine_history([], [{"kind": "update", "started_at": "2026-11-12T10:00:00Z", "status": "completed"}])
        self.assertEqual(records[0]["package_name"], "Atualização do sistema")
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["record_type"], "operation")

    def test_local_api_rejects_foreign_hosts_and_origins(self):
        from backend.app import local_request_allowed
        self.assertTrue(local_request_allowed("127.0.0.1:8765", "http://127.0.0.1:8765", 8765, "same-origin"))
        self.assertFalse(local_request_allowed("attacker.example:8765", "http://attacker.example:8765", 8765, "same-origin"))
        self.assertFalse(local_request_allowed("127.0.0.1:8765", "https://attacker.example", 8765, "cross-site"))

    def test_source_fetch_allowlist_blocks_local_or_unknown_hosts(self):
        from backend.collectors.sync import validate_source_url
        validate_source_url("https://api.github.com/repos/CachyOS/distribution/issues", github=True)
        with self.assertRaises(ValueError):
            validate_source_url("http://127.0.0.1:8765/api/status")
        with self.assertRaises(ValueError):
            validate_source_url("https://example.com/feed.xml")
        with self.assertRaises(ValueError):
            validate_source_url("https://github.com/CachyOS/distribution", github=True)

    def test_operation_runner_provides_controlling_terminal_and_captures_output(self):
        from backend import system_operations as ops
        from backend.database import db as persistence
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "data.sqlite"
            persistence.initialize(dbpath)
            job_id = "pty-test"
            job = {"id": job_id, "kind": "update", "status": "queued", "output": "",
                   "exit_code": None, "error": None, "master": None}
            ops._jobs[job_id] = job
            with persistence.connect(dbpath) as db:
                db.execute("INSERT INTO system_operations(id,kind,status,started_at) VALUES(?,?,?,?)",
                           (job_id, "update", "queued", "2026-11-12T00:00:00+00:00"))
            with patch.object(ops, "connect", side_effect=lambda *args, **kwargs: persistence.connect(dbpath)):
                ops._run(job_id, [sys.executable, "-c", "import os; assert os.isatty(0); open('/dev/tty').close(); print('pty-ready')"])
            self.assertEqual(job["status"], "completed")
            self.assertIn("pty-ready", job["output"])
            ops._jobs.pop(job_id, None)

    def test_cachyos_issue_source_uses_requested_repository(self):
        import json
        from backend.collectors import sync
        payload = json.dumps([{"id": 123, "title": "Issue title", "body": "mesa issue",
            "html_url": "https://github.com/CachyOS/distribution/issues/123", "state": "closed",
            "state_reason": "completed", "updated_at": "2026-11-12", "user": {"login": "dev"}}]).encode()
        with patch.object(sync, "fetch", return_value=payload) as fetch:
            result = sync.collect({"kind": "github_repo", "url": "https://github.com/CachyOS/distribution/issues"})
        self.assertIn("/repos/CachyOS/distribution/issues?", fetch.call_args.args[0])
        self.assertEqual(result[0]["resolution"], "fixed")

    def test_amd_gpu_source_handles_github_issue_without_body(self):
        import json
        from backend.collectors import sync
        payload = json.dumps([{"id": 244, "title": "Driver issue", "body": None,
            "html_url": "https://github.com/ROCm/amdgpu/issues/244", "state": "open",
            "user": None}]).encode()
        with patch.object(sync, "fetch", return_value=payload) as fetch:
            result = sync.collect({"kind": "github_repo", "url": "https://github.com/ROCm/amdgpu/issues"})
        self.assertIn("/repos/ROCm/amdgpu/issues?", fetch.call_args.args[0])
        self.assertEqual(result[0]["content"], "")
        self.assertEqual(result[0]["author"], "")

    def test_mesa_source_uses_gitlab_issues_api(self):
        import json
        from backend.collectors import sync
        payload = json.dumps([{"id": 5, "iid": 9, "title": "Renderer regression", "description": "", "state": "opened",
            "web_url": "https://gitlab.freedesktop.org/mesa/mesa/-/issues/9", "author": {"name": "user"}}]).encode()
        with patch.object(sync, "fetch", return_value=payload) as fetch:
            result = sync.collect({"kind": "gitlab", "url": "https://gitlab.freedesktop.org/mesa/mesa/-/issues"})
        self.assertIn("/api/v4/projects/mesa%2Fmesa/issues", fetch.call_args.args[0])
        self.assertEqual(result[0]["resolution"], "open")


if __name__ == "__main__":
    unittest.main()
