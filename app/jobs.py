from __future__ import annotations

import concurrent.futures
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from . import store


class Cancelled(RuntimeError):
    pass


class Context:
    def __init__(self, manager, jid):
        self.manager, self.jid = manager, jid

    def check(self):
        if self.manager.read(self.jid).get("cancel_requested"):
            raise Cancelled("Operazione annullata. I risultati completati sono conservati.")

    def progress(self, message: str, percent: int | None = None):
        self.check()
        updates = {"message": message}
        if percent is not None:
            updates["percent"] = max(0, min(100, percent))
        self.manager.update(self.jid, **updates)

    def run(self, args: list[str], cwd: Path | None = None, timeout: int = 7200):
        self.check()
        proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started = time.monotonic()
        try:
            while True:
                try:
                    stdout, stderr = proc.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    self.check()
                    if time.monotonic() - started > timeout:
                        raise TimeoutError("Tempo massimo del comando superato.")
            if proc.returncode:
                raise RuntimeError(f"{Path(args[0]).name} non riuscito:\n{stderr.decode(errors='replace')[-4500:]}")
            return stdout
        except BaseException:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.communicate()
            raise


class Jobs:
    """Single worker: bounded CPU/RAM and deterministic project mutations."""
    def __init__(self):
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
        self.lock = threading.RLock()
        self.runner = None

    @property
    def root(self):
        r = store.DATA_ROOT / "jobs"; r.mkdir(parents=True, exist_ok=True); return r

    def read(self, jid: str):
        if not __import__("re").fullmatch(r"j_[0-9a-f]{12}", jid):
            raise ValueError("ID operazione non valido.")
        with self.lock:
            return json.loads((self.root / (jid + ".json")).read_text("utf-8"))

    def update(self, jid, **fields):
        with self.lock:
            obj = self.read(jid); obj.update(fields, updated=time.time())
            store.atomic_json(self.root / (jid + ".json"), obj)
            return obj

    def list(self, pid=None):
        with self.lock:
            items = []
            for f in self.root.glob("j_*.json"):
                try:
                    j = json.loads(f.read_text("utf-8"))
                    if not pid or j["project_id"] == pid: items.append(j)
                except (OSError, ValueError): pass
            return sorted(items, key=lambda j: j["created"], reverse=True)

    def assert_idle(self, pid):
        if any(j["status"] in ("queued", "running") for j in self.list(pid)):
            raise ValueError("Progetto in lavorazione: attendi il termine o annulla prima di modificarlo.")

    def recover(self):
        for j in self.list():
            if j["status"] in ("queued", "running"):
                self.update(j["id"], status="interrupted", message="Container riavviato: ripeti l'azione per riprendere dai risultati salvati.")

    def submit(self, pid: str, request: dict):
        with self.lock:
            self.assert_idle(pid)
            jid = "j_" + uuid.uuid4().hex[:12]
            job = dict(id=jid, project_id=pid, request=request, status="queued", percent=0,
                       message="In coda", created=time.time(), updated=time.time(), cancel_requested=False)
            store.atomic_json(self.root / (jid + ".json"), job)
            self.pool.submit(self.execute, jid)
            return job

    def execute(self, jid):
        try:
            j = self.update(jid, status="running")
            ctx = Context(self, jid); ctx.check()
            self.runner(j["project_id"], j["request"], ctx)
            self.update(jid, status="completed", percent=100, message="Completato")
        except Cancelled as e:
            self.update(jid, status="cancelled", message=str(e))
        except Exception as e:
            self.update(jid, status="failed", message=str(e)[-6000:])


JOBS = Jobs()
