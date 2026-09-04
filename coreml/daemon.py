#!/usr/bin/env python3
"""
LocalForge warm-model daemon.

Started best-effort and non-blockingly by ane_bridge.rs / advisory_engine.rs
when the Unix socket at ~/.localforge/daemon.sock doesn't respond. Keeps the
CoreML model and the Qwen/MLX model resident across commits instead of
paying Python-interpreter + model-load cost on every single one.

If the daemon is unreachable or fails for any reason, callers fall back to
the existing per-invocation shim (infer.py / advisory.py) — this process is
a pure optimization, never a dependency.

Protocol: one JSON object per connection, newline-terminated request, one
JSON response written back before the connection is closed.
  {"cmd": "ping"}                                  -> {"ok": true}
  {"cmd": "infer", "diff": "..."}                  -> infer.py's output shape
  {"cmd": "advise", "diff": "...", "log_dir": "...", "report_file": "..."}
                                                    -> advisory.py's output shape
  {"cmd": "shutdown"}                              -> {"ok": true}, then exits

Exits on its own after IDLE_TIMEOUT seconds with no requests, so a forgotten
daemon never lingers holding a multi-GB model in memory indefinitely.
"""

import json
import os
import socket
import socketserver
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

HOME = os.path.expanduser("~")
SOCKET_PATH = os.path.join(HOME, ".localforge", "daemon.sock")
IDLE_TIMEOUT = 30 * 60  # seconds

_last_activity = time.time()
_activity_lock = threading.Lock()

_ane_lock = threading.Lock()
_ane_state: dict = {}       # {"model":..., "tfidf":...} once loaded

_advisory_lock = threading.Lock()
_advisory_state: dict = {}  # {"model":..., "tokenizer":..., "model_dir":...} once loaded


def _touch():
    global _last_activity
    with _activity_lock:
        _last_activity = time.time()


def _idle_seconds() -> float:
    with _activity_lock:
        return time.time() - _last_activity


def _handle_infer(diff_text: str) -> dict:
    import infer as infer_mod

    with _ane_lock:
        if "model" not in _ane_state:
            model, tfidf = infer_mod.load_ane()
            _ane_state["model"] = model
            _ane_state["tfidf"] = tfidf
        model = _ane_state["model"]
        tfidf = _ane_state["tfidf"]

    output, _label = infer_mod.run_infer(diff_text, model, tfidf)
    return output


def _handle_advise(diff_text: str, log_dir: str, report_file: str | None) -> dict:
    import advisory as advisory_mod

    model_dir = advisory_mod._find_model_dir()

    model = tokenizer = None
    if os.path.isdir(model_dir):
        with _advisory_lock:
            if _advisory_state.get("model_dir") != model_dir:
                m, t = advisory_mod.load_model(model_dir)
                _advisory_state["model"] = m
                _advisory_state["tokenizer"] = t
                _advisory_state["model_dir"] = model_dir
            model = _advisory_state.get("model")
            tokenizer = _advisory_state.get("tokenizer")

    return advisory_mod.run(
        diff_text, model_dir, log_dir, report_file, model=model, tokenizer=tokenizer
    )


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        _touch()
        try:
            raw = self.rfile.readline()
            if not raw:
                return
            req = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            self._respond({"error": f"bad request: {e}"})
            return

        cmd = req.get("cmd")
        try:
            if cmd == "ping":
                self._respond({"ok": True})
            elif cmd == "infer":
                self._respond(_handle_infer(req.get("diff", "")))
            elif cmd == "advise":
                self._respond(
                    _handle_advise(
                        req.get("diff", ""), req.get("log_dir", ""), req.get("report_file")
                    )
                )
            elif cmd == "shutdown":
                self._respond({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                # Safety net: force-exit if serve_forever doesn't unblock
                # promptly (e.g. scheduler contention under heavy load) — a
                # daemon meant to be killable should never need a manual kill.
                threading.Thread(target=_force_exit_after, args=(5.0,), daemon=True).start()
            else:
                self._respond({"error": f"unknown cmd: {cmd}"})
        except Exception as e:
            self._respond({"error": f"daemon error: {e}"})
        finally:
            _touch()

    def _respond(self, obj: dict):
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False


def _force_exit_after(seconds: float):
    time.sleep(seconds)
    os._exit(0)


def _idle_watchdog(server: Server):
    while True:
        time.sleep(30)
        if _idle_seconds() > IDLE_TIMEOUT:
            threading.Thread(target=_force_exit_after, args=(5.0,), daemon=True).start()
            server.shutdown()
            return


def main():
    os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)

    # Single-instance guard: if another daemon already owns the socket,
    # connecting to it succeeds and we exit quietly instead of racing to bind.
    try:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1)
        probe.connect(SOCKET_PATH)
        probe.close()
        return  # already running
    except OSError:
        pass  # nothing listening — safe to bind

    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    try:
        server = Server(SOCKET_PATH, Handler)
    except OSError:
        return  # lost the race to another daemon starting concurrently

    watchdog = threading.Thread(target=_idle_watchdog, args=(server,), daemon=True)
    watchdog.start()

    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            os.remove(SOCKET_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main()
