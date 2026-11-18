from __future__ import annotations

import fcntl
import os
import pty
import select
import shutil
import struct
import subprocess
import termios
import threading
import time
import uuid
from datetime import datetime, timezone

from backend.database.db import connect

_lock = threading.RLock()
_jobs: dict[str, dict] = {}
_active_job: str | None = None
_MAX_OUTPUT = 80_000


def command_for(kind: str) -> tuple[list[str], str]:
    if kind == "snapshot":
        pkexec = shutil.which("pkexec")
        snapper = shutil.which("snapper")
        if snapper and pkexec:
            label = "Criar snapshot manual com Snapper"
            description = "Update Watch - snapshot manual antes de atualizar"
            return [pkexec, snapper, "--config", "root", "create", "--description", description], label
        timeshift = shutil.which("timeshift")
        if timeshift and pkexec:
            return [pkexec, timeshift, "--create", "--comments", "Update Watch - snapshot manual antes de atualizar", "--tags", "D"], "Criar snapshot manual com Timeshift"
        raise RuntimeError("Não encontrei Snapper ou Timeshift com pkexec. Configure um gerenciador de snapshots antes de criar o snapshot.")
    if kind == "update":
        for helper in ("paru", "yay"):
            executable = shutil.which(helper)
            if executable:
                return [executable, "-Syu"], f"Atualizar sistema com {helper} -Syu"
        pacman = shutil.which("pacman")
        pkexec = shutil.which("pkexec")
        if not pacman or not pkexec:
            raise RuntimeError("Atualização direta requer pacman e pkexec.")
        return [pkexec, pacman, "-Syu"], "Atualizar sistema com pacman -Syu"
    raise ValueError("Operação não permitida")


def _append_output(job: dict, chunk: bytes) -> None:
    if not chunk:
        return
    text = chunk.decode("utf-8", errors="replace")
    with _lock:
        job["output"] = (job["output"] + text)[-_MAX_OUTPUT:]


def _attach_controlling_terminal() -> None:
    # Popen connects stdin/stdout to the PTY slave before running this hook.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


def _run(job_id: str, argv: list[str]) -> None:
    global _active_job
    job = _jobs[job_id]
    master = slave = None
    try:
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        with _lock:
            job["master"] = master
            job["status"] = "running"
        with connect() as db:
            db.execute("UPDATE system_operations SET status='running' WHERE id=?", (job_id,))
        env = {**os.environ, "TERM": "xterm-256color", "LC_ALL": "C.UTF-8"}
        process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, close_fds=True,
                                   env=env, start_new_session=True, preexec_fn=_attach_controlling_terminal)
        os.close(slave)
        slave = None
        job["pid"] = process.pid
        terminal_eof = False
        while process.poll() is None:
            if terminal_eof:
                time.sleep(0.2)
                continue
            readable, _, _ = select.select([master], [], [], 0.2)
            if readable:
                try:
                    _append_output(job, os.read(master, 8192))
                except OSError:
                    terminal_eof = True
        # Drain output already buffered by the terminal after the child exits.
        while not terminal_eof:
            readable, _, _ = select.select([master], [], [], 0)
            if not readable:
                break
            try:
                _append_output(job, os.read(master, 8192))
            except OSError:
                terminal_eof = True
        code = process.wait()
        with _lock:
            job["exit_code"] = code
            job["status"] = "completed" if code == 0 else "failed"
            if code != 0:
                job["error"] = f"O processo encerrou com código {code}."
    except Exception as exc:
        with _lock:
            job["status"] = "failed"
            job["error"] = str(exc)
    finally:
        if slave is not None:
            os.close(slave)
        if master is not None:
            with _lock:
                job["master"] = None
            try:
                os.close(master)
            except OSError:
                pass
        with _lock:
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            if _active_job == job_id:
                _active_job = None
        try:
            with connect() as db:
                db.execute("UPDATE system_operations SET status=?,exit_code=?,finished_at=?,detail=? WHERE id=?",
                           (job["status"], job.get("exit_code"), job["finished_at"],
                            job.get("error") or job["output"][-2000:], job_id))
        except Exception:
            pass


def start(kind: str, confirmation: str | None = None) -> dict:
    global _active_job
    if kind == "update" and confirmation != "UPDATE":
        raise PermissionError("Confirme explicitamente a atualização do sistema.")
    if kind == "snapshot" and confirmation != "SNAPSHOT":
        raise PermissionError("Confirme explicitamente a criação do snapshot.")
    argv, label = command_for(kind)
    with _lock:
        if _active_job:
            existing = _jobs.get(_active_job, {})
            if existing.get("status") in ("queued", "running"):
                raise RuntimeError("Já existe uma operação do sistema em andamento.")
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        job = {"id": job_id, "kind": kind, "label": label, "status": "queued", "output": "",
               "started_at": now, "finished_at": None, "exit_code": None, "error": None, "master": None}
        _jobs[job_id] = job
        _active_job = job_id
        with connect() as db:
            db.execute("INSERT INTO system_operations(id,kind,status,started_at) VALUES(?,?,?,?)",
                       (job_id, kind, "queued", now))
        threading.Thread(target=_run, args=(job_id, argv), daemon=True, name=f"update-watch-{kind}").start()
        return public_job(job)


def public_job(job: dict) -> dict:
    return {key: job.get(key) for key in
            ("id", "kind", "label", "status", "output", "started_at", "finished_at", "exit_code", "error")}


def get(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return public_job(job) if job else None


def send_input(job_id: str, value: str) -> None:
    # Input goes only to the controlling TTY of a fixed argv command; it is never
    # evaluated by a shell. Permit passwords and package-manager answers, while
    # rejecting terminal control characters and pasted multi-line commands.
    if (not isinstance(value, str) or not value or len(value) > 256 or
            not all(char.isprintable() for char in value)):
        raise ValueError("Informe uma resposta de até 256 caracteres, sem quebras de linha ou controles.")
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["status"] != "running" or job["kind"] not in ("update", "snapshot") or job.get("master") is None:
            raise RuntimeError("Não há uma operação ativa aguardando resposta.")
        os.write(job["master"], value.encode("utf-8") + b"\n")


def history() -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM system_operations ORDER BY started_at DESC LIMIT 20")]


def active() -> dict | None:
    with _lock:
        job = _jobs.get(_active_job) if _active_job else None
        if job and job.get("status") in ("queued", "running"):
            return public_job(job)
        return None


def recover_stale() -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute("""UPDATE system_operations SET status='interrupted',finished_at=?,
                    detail=CASE WHEN detail='' THEN 'O app foi reiniciado antes de registrar o término.' ELSE detail END
                    WHERE status IN ('queued','running')""", (now,))
