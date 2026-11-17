"""Local stand-in for the game's online servers, so Road to the Show's Packages work without a connection.

The runtime starts it when offline packages are on (runtime/mlb/packages.c) and stops it with the game. It listens
on 127.0.0.1 only and connects to nothing. The game's own online code talks to it: the olClient protocol (codec.py)
inside TLS, three connections on one port (auth, conductor, service) told apart by what they send. login.py logs the
game in as one local player, handlers.py and services.py answer the service connection's requests: the inventory,
the equipment packs Road to the Show awards, and opening them.

    python -I tools/packages/server.py --game <install folder> [--data <folder>] [--port N] [--log <file>]
    python -I tools/packages/server.py --child
    python -I tools/packages/server.py --check --game <install folder>

--data (default <install folder>/profile/offline-packages) keeps what belongs to this player and this PC: state.json
(packs owned, items they gave) and the server's certificate (cert.pem) and key, made on first start (cert.py). Once
it listens, the server prints one line, "ready <port> <certificate file>", or "failed <why>" and ends. Everything else
goes to the log (default <install folder>/logs/packages-server.log).

--check starts the server and ends at once: the setup runs it to see that the server works on this PC and to have the
certificate made before the first game. It fails when the game data has no equipment to give (tools/equipment).

--child is how the runtime starts it: the folders come as lines on standard input ("romfs <the game's romfs folder>",
"data <folder>", "log <file>", then "start"), and the server ends when its standard input closes, which it does when
the game ends, however it ends.

Standard library only.
"""
import argparse
import json
import os
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:                 # python -I leaves the script's folder out
    sys.path.insert(0, str(HERE))
import cert  # noqa: E402
import codec  # noqa: E402
import core  # noqa: E402
from core import HANDLERS, log  # noqa: E402

PING_EVERY = 8.0            # the client drops a link after 20 s with nothing received


class State:
    """What the player has: a JSON file, written whole on every change."""

    def __init__(self, path):
        self.path = Path(path)
        self.d = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.lock = threading.Lock()

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.d, indent=1), encoding='utf-8')
            tmp.replace(self.path)


class Conn:
    """One connection of the game. Handlers (core.HANDLERS) answer its messages by message id."""
    n = 0

    def __init__(self, sock, server):
        Conn.n += 1
        self.id = Conn.n
        self.sock, self.server = sock, server
        self.dec = codec.StreamDecoder()
        self.kind = 'new'           # 'auth', 'conductor' or 'service' once known
        self.alive = True
        self.wlock = threading.Lock()
        self.ctx = {}               # per-connection scratch for handlers

    def tag(self):
        return f'[c{self.id} {self.kind}]'

    def hang_up(self, why):
        """Close the connection. The game then reports a lost connection, goes back to its title screen and logs in
        again from there."""
        log(f'{self.tag()} hanging up: {why}')
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def send(self, msg_id, body=b'', note=''):
        if not self.alive:
            return
        data = codec.encode_frame(msg_id, body)
        with self.wlock:
            try:
                self.sock.sendall(data)
            except OSError as e:
                log(f'{self.tag()} send failed: {e}')
                self.alive = False
                return
        log(f'{self.tag()} -> {msg_id:#010x} {len(body)} B {note}')

    def send_msg(self, msg, note=''):
        """Send one ready message (u32 length | u32 id | body, as server_msgs.py builds them)."""
        self.send(int.from_bytes(msg[4:8], 'little'), msg[8:], note)

    def pinger(self):
        while self.alive:
            time.sleep(PING_EVERY)
            if self.alive:
                with self.wlock:
                    try:
                        self.sock.sendall(codec.encode_frame(codec.MSG_PING, codec.body_ping()))
                    except OSError:
                        self.alive = False

    def run(self):
        threading.Thread(target=self.pinger, daemon=True).start()
        try:
            while self.alive:
                data = self.sock.recv(65536)
                if not data:
                    break
                for mid, body in self.dec.feed(data):
                    self.dispatch(mid, body)
        except (OSError, ssl.SSLError, ValueError) as e:
            log(f'{self.tag()} connection error: {e}')
        finally:
            self.alive = False
            try:
                self.sock.close()
            except OSError:
                pass
            log(f'{self.tag()} closed')

    def dispatch(self, mid, body):
        if mid == codec.MSG_HEARTBEAT:
            return
        fn = HANDLERS.get(mid)
        if fn is None:
            log(f'{self.tag()} <- {mid:#010x} not handled, {len(body)} B')
            return
        self.ctx['_mid'] = mid
        try:
            fn(self, body)
        except Exception as e:      # keep the link up; the log says what broke
            log(f'{self.tag()} handler {fn.__name__} failed: {type(e).__name__}: {e}')


class Server:
    def __init__(self, state, cert_file, key_file, port=0):
        self.state = state
        self.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.tls.minimum_version = ssl.TLSVersion.TLSv1_2     # said outright; the game itself comes with TLS 1.3
        self.tls.load_cert_chain(cert_file, key_file)
        self.sock = socket.socket()
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.sock.bind(('127.0.0.1', port))     # this PC only; port 0: any free one
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]

    def serve(self):
        while True:
            try:
                raw, _ = self.sock.accept()
            except OSError:
                return                          # closed
            threading.Thread(target=self.accept, args=(raw,), daemon=True).start()

    def accept(self, raw):
        try:
            sock = self.tls.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError) as e:
            log(f'TLS handshake failed: {e}')
            raw.close()
            return
        Conn(sock, self).run()

    def close(self):
        self.sock.close()


def start(romfs, data, port=0):
    """A listening Server for the game files in `romfs`, keeping its state and certificate in `data`."""
    import handlers  # noqa: F401  (registers the message handlers)
    import services
    data.mkdir(parents=True, exist_ok=True)
    cert_file, key_file = data / 'cert.pem', data / 'key.pem'
    if cert.make(cert_file, key_file):
        log(f'made a certificate for this PC: {cert_file}')
    state = State(data / 'state.json')
    services.init(romfs, state)
    return Server(state, cert_file, key_file, port), cert_file


def child_settings(stdin):
    """The runtime's lines on standard input, up to "start": -> {'romfs': Path, 'data': Path, 'log': Path}."""
    got = {}
    for raw in iter(stdin.readline, b''):
        key, _, value = raw.decode('utf-8').strip().partition(' ')
        if key == 'start':
            break
        if key in ('romfs', 'data', 'log') and value:
            got[key] = Path(value)
    missing = [k for k in ('romfs', 'data', 'log') if k not in got]
    if missing:
        raise SystemExit(f'failed the runtime did not say: {", ".join(missing)}')
    return got


def end_with_the_game(stdin):
    """Ends the server once standard input closes: the game holds its other end and never writes to it again."""
    def watch():
        while stdin.read(1):
            pass
        log('the game ended; so does the server')
        os._exit(0)
    threading.Thread(target=watch, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', type=Path, help='the install folder (the one with mlb.exe)')
    ap.add_argument('--data', type=Path, help='state and certificate folder (default: profile/offline-packages)')
    ap.add_argument('--port', type=int, default=0, help='port on 127.0.0.1 (default: any free one)')
    ap.add_argument('--log', type=Path, help='log file (default: logs/packages-server.log in --game)')
    ap.add_argument('--child', action='store_true', help='started by the runtime: see above')
    ap.add_argument('--check', action='store_true', help='start, say whether it works, and end')
    a = ap.parse_args()
    if a.child:
        got = child_settings(sys.stdin.buffer)
        romfs, data, log_file = got['romfs'], got['data'], got['log']
    elif a.game:
        romfs = a.game / 'game' / 'romfs'
        data = a.data or a.game / 'profile' / 'offline-packages'
        log_file = a.log or a.game / 'logs' / 'packages-server.log'
    else:
        ap.error('--game <install folder> is needed')
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        core.LOGF = open(log_file, 'w', encoding='utf-8')
        server, cert_file = start(romfs, data, a.port)
        if a.check:
            import services
            items = sum(map(len, services.BY_RARITY.values()))
            if not items:
                raise RuntimeError('the game data has no Road to the Show equipment for the packs to give '
                                   '(tools/equipment adds it)')
            server.close()
            print(f'the server works: {items} equipment items for the packs, certificate {cert_file}', flush=True)
            return
    except Exception as e:
        why = f'{type(e).__name__}: {e}'
        log(f'could not start: {why}')
        print('failed ' + ' '.join(why.split()), flush=True)
        raise SystemExit(1)
    log(f'listening on 127.0.0.1:{server.port}')
    print(f'ready {server.port} {cert_file}', flush=True)
    if a.child:
        end_with_the_game(sys.stdin.buffer)
    server.serve()


if __name__ == '__main__':
    main()
