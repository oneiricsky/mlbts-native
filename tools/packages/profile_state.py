"""The RTTS Standard Package counter ("Next Standard Package in N games") lives on the server, not in the save
(UniversalProfileState): after each counted game the client sends 0x0AD404ED {u32, u64 flags,
u8 counter} and only the server message 0xAFE1519A {u32, u64, u8} (handler f_7000946e20) sets it back after a login.
Without this the counter restarts at 0 on every boot and the 10-game pack never comes."""
import struct

from core import handles, log

MSG_STATE_UP = 0x0AD404ED      # client -> server
MSG_STATE_DOWN = 0xAFE1519A    # server -> client


@handles(MSG_STATE_UP)
def state_up(conn, body):
    if len(body) < 13:
        log(f'{conn.tag()} profile state: short body {body.hex()}')
        return
    a, flags, counter = struct.unpack_from('<IQB', body, 0)
    st = conn.server.state
    st.d['profile_state'] = body[:13].hex()
    st.save()
    log(f'{conn.tag()} profile state saved: standard-package counter {counter} ({a:#x}, flags {flags:#x})')


def on_service_connect(conn):
    """Give the client its saved counter back once the service connection is up."""
    saved = conn.server.state.d.get('profile_state')
    if saved:
        body = bytes.fromhex(saved)
        conn.send(MSG_STATE_DOWN, body, note=f'standard-package counter {body[12]}')
