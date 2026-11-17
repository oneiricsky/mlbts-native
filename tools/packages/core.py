"""Shared pieces of the stand-in server: the log and the message-handler registry (one copy for every module)."""
import threading
import time

LOCK = threading.Lock()
LOGF = None                 # the log file (server.main opens it); without one, lines go to stderr
HANDLERS = {}               # msg id -> fn(conn, body)


def log(msg):
    """One line for the log. Never standard output: the runtime reads the server's "ready" line there."""
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    with LOCK:
        if LOGF:
            LOGF.write(line + '\n')
            LOGF.flush()
        else:
            import sys
            print(line, file=sys.stderr, flush=True)


def handles(*ids):
    def deco(fn):
        for i in ids:
            HANDLERS[i] = fn
        return fn
    return deco
