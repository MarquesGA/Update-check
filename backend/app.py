from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlsplit

from backend.analyzer.correlation import correlate
from backend.collectors.sync import sync_all
from backend.database.db import DB_PATH, connect, initialize, rows
from backend.hardware.detect import detect as detect_hardware
from backend.package_manager.pacman import get_updates
from backend.system_operations import active as active_operation
from backend.system_operations import get as get_operation
from backend.system_operations import history as operation_history
from backend.system_operations import send_input as send_operation_input
from backend.system_operations import start as start_operation
from backend.system_operations import recover_stale as recover_stale_operations

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "frontend"


def refresh_packages(path=None) -> dict:
    packages, error = get_updates()
    with connect(path) as db:
        if not error:
            db.execute("DELETE FROM packages")
        for package in packages:
            db.execute("""INSERT INTO packages(name,installed_version,available_version,repository,download_size,updated_at)
              VALUES(?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(name) DO UPDATE SET
              installed_version=excluded.installed_version,available_version=excluded.available_version,
              repository=excluded.repository,download_size=excluded.download_size,updated_at=CURRENT_TIMESTAMP""",
              (package["name"], package["installed_version"], package["available_version"], package["repository"], package.get("download_size")))
            db.execute("INSERT INTO update_history(package_name,installed_version,available_version) VALUES(?,?,?)",
                       (package["name"], package["installed_version"], package["available_version"]))
    return {"packages": packages, "error": error}


def combine_history(package_history: list[dict], operations: list[dict]) -> list[dict]:
    operation_rows = [{"package_name": "Atualização do sistema" if op["kind"] == "update" else "Snapshot do sistema",
                       "installed_version": "—", "available_version": "—",
                       "detected_at": op["started_at"], "status": op["status"],
                       "record_type": "operation"} for op in operations]
    return sorted(package_history + operation_rows, key=lambda item: item["detected_at"], reverse=True)


def local_request_allowed(host: str, origin: str | None, expected_port: int,
                         fetch_site: str | None = None) -> bool:
    try:
        authority = urlsplit("//" + host)
        if authority.hostname != "127.0.0.1" or authority.port != expected_port:
            return False
        if origin:
            parsed_origin = urlsplit(origin)
            if (parsed_origin.scheme != "http" or parsed_origin.hostname != "127.0.0.1" or
                    parsed_origin.port != expected_port):
                return False
        if fetch_site and fetch_site not in ("same-origin", "none"):
            return False
        return True
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "UpdateWatch/0.1"

    def log_message(self, fmt, *args):
        if self.path in ("/api/console", "/api/logs") or self.path.startswith("/api/operations/"):
            return
        log_dir = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "update-watch"
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (log_dir / "app.log").open("a", encoding="utf-8") as log:
            log.write((fmt % args) + "\n")

    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def local_request(self) -> bool:
        if local_request_allowed(self.headers.get("Host", ""), self.headers.get("Origin"),
                                 self.server.server_port, self.headers.get("Sec-Fetch-Site")):
            return True
        self.send_error(403, "Use o Update Watch em 127.0.0.1")
        return False

    def do_GET(self):
        if not self.local_request(): return
        path = urlparse(self.path).path
        try:
            if path == "/api/status":
                data = {"db": str(DB_PATH), "sources": rows("SELECT name,kind,enabled,last_sync,last_error FROM sources"),
                        "package_count": len(rows("SELECT name FROM packages")),
                        "publication_count": len(rows("SELECT id FROM publications"))}
            elif path == "/api/packages":
                packages = rows("SELECT * FROM packages ORDER BY name")
                pubs = rows("SELECT id,title,content,published_at,url,source_id,resolution FROM publications")
                for item in packages:
                    analysis = correlate(item["name"], pubs)
                    item.update({k: v for k, v in analysis.items() if k != "publications"})
                data = packages
            elif path == "/api/publications":
                query = parse_qs(urlparse(self.path).query)
                limit = min(max(int(query.get("limit", ["200"])[0]), 1), 500)
                data = rows("""SELECT p.*,s.name AS source_name FROM publications p LEFT JOIN sources s ON s.id=p.source_id
                              ORDER BY COALESCE(p.published_at,p.created_at) DESC LIMIT ?""", (limit,))
            elif path == "/api/analysis":
                packages = rows("SELECT * FROM packages ORDER BY name")
                pubs = rows("""SELECT p.id,p.title,p.content,p.published_at,p.url,p.source_id,p.resolution,
                                    s.name AS source_name FROM publications p
                                    LEFT JOIN sources s ON s.id=p.source_id""")
                data = [{"package": p["name"], **correlate(p["name"], pubs)} for p in packages]
            elif path == "/api/history":
                package_history = rows("SELECT * FROM update_history ORDER BY detected_at DESC LIMIT 500")
                data = combine_history(package_history, operation_history())
            elif path == "/api/operations":
                data = operation_history()
            elif path == "/api/logs":
                log_path = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "update-watch" / "app.log"
                try:
                    with log_path.open("rb") as log_file:
                        log_file.seek(0, os.SEEK_END)
                        length = log_file.tell()
                        log_file.seek(max(0, length - 32_000))
                        log_lines = log_file.read().decode("utf-8", errors="replace").splitlines()[-100:]
                except OSError:
                    log_lines = []
                data = {"logs": log_lines, "operations": operation_history()}
            elif path == "/api/console":
                active = active_operation()
                latest = None if active else next(iter(operation_history()), None)
                data = {"active_operation": active, "latest_operation": latest}
            elif path.startswith("/api/operations/"):
                data = get_operation(path.rsplit("/", 1)[1])
                if data is None:
                    self.send_json({"error": "Operação não encontrada"}, 404); return
            elif path == "/api/sources":
                data = rows("SELECT * FROM sources ORDER BY id")
            elif path == "/api/hardware":
                self.send_json(detect_hardware()); return
            elif path == "/" or path.startswith("/assets/"):
                target = WEB / ("index.html" if path == "/" else path.removeprefix("/assets/"))
                if not target.resolve().is_relative_to(WEB.resolve()) or not target.is_file():
                    self.send_error(404); return
                payload = target.read_bytes()
                mime = "text/html; charset=utf-8" if target.suffix == ".html" else "text/" + ("css" if target.suffix == ".css" else "javascript") + "; charset=utf-8"
                self.send_response(200); self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers(); self.wfile.write(payload); return
            else:
                self.send_error(404); return
            self.send_json(data)
        except (ValueError, OSError) as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self):
        if not self.local_request(): return
        path = urlparse(self.path).path
        try:
            if path == "/api/refresh":
                data = refresh_packages()
                self.send_json(data)
            elif path == "/api/sync":
                self.send_json(sync_all())
            elif path == "/api/snapshot":
                length = min(int(self.headers.get("Content-Length", "0")), 2048)
                body = json.loads(self.rfile.read(length) or b"{}")
                self.send_json(start_operation("snapshot", body.get("confirmation")), 202)
            elif path == "/api/update":
                length = min(int(self.headers.get("Content-Length", "0")), 2048)
                body = json.loads(self.rfile.read(length) or b"{}")
                self.send_json(start_operation("update", body.get("confirmation")), 202)
            elif path.startswith("/api/operations/") and path.endswith("/input"):
                operation_id = path.split("/")[3]
                length = min(int(self.headers.get("Content-Length", "0")), 1024)
                body = json.loads(self.rfile.read(length) or b"{}")
                send_operation_input(operation_id, body.get("text", ""))
                self.send_json({"ok": True})
            elif path == "/api/hardware/detect":
                self.send_json(detect_hardware())
            elif path == "/api/reanalyze":
                packages = rows("SELECT * FROM packages")
                pubs = rows("SELECT id,title,content,published_at,url,source_id FROM publications")
                with connect() as db:
                    for package in packages:
                        result = correlate(package["name"], pubs)
                        db.execute("INSERT INTO analyses(package_name,risk,report_count,summary,publication_ids) VALUES(?,?,?,?,?)",
                          (package["name"], result["risk"], result["report_count"], result["summary"],
                           json.dumps([p["id"] for p in result["publications"]])))
                self.send_json({"analyzed": len(packages)})
            elif path.startswith("/api/publications/") and path.endswith("/read"):
                pub_id = int(path.split("/")[3])
                with connect() as db: db.execute("UPDATE publications SET read=1 WHERE id=?", (pub_id,))
                self.send_json({"ok": True})
            elif path.startswith("/api/publications/") and path.endswith("/favorite"):
                pub_id = int(path.split("/")[3])
                with connect() as db: db.execute("UPDATE publications SET favorite=1-favorite WHERE id=?", (pub_id,))
                self.send_json({"ok": True})
            else:
                self.send_error(404)
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, 409)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_PATCH(self):
        if not self.local_request(): return
        if not self.path.startswith("/api/sources/"):
            self.send_error(404); return
        try:
            source_id = int(self.path.rsplit("/", 1)[1])
            length = min(int(self.headers.get("Content-Length", "0")), 4096)
            data = json.loads(self.rfile.read(length) or b"{}")
            with connect() as db:
                db.execute("UPDATE sources SET enabled=? WHERE id=?", (int(bool(data.get("enabled"))), source_id))
            self.send_json({"ok": True})
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)


def main():
    initialize()
    recover_stale_operations()
    host, port = "127.0.0.1", int(os.environ.get("UPDATE_WATCH_PORT", "8765"))
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        print(f"Não foi possível abrir {host}:{port}: {exc}", file=sys.stderr); raise SystemExit(1)
    server.daemon_threads = True
    print(f"Update Watch ativo em http://{host}:{port} (SQLite: {DB_PATH})")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__": main()
