"""Auth and conductor handlers: log the game in as one local player and point it at the service connection.

Flow (server_msgs.py, checked against the game's code):
  auth:      LoginNSA -> LoginResponse(Token); token echo (0xde3ac304 / 0x66baea30 / 0x0ca403f1) -> SessionResponse
  conductor: ConductorQuery(AccountSession) -> ConductorAnswer(endpoint 127.0.0.1:<port>, plugin id)
  service:   the client then opens a third TLS connection to that endpoint (handled in handlers.py)
"""
import server_msgs as sm
from core import handles, log

ACCOUNT = sm.AccountSession(account_id=0x0123456789ABCDEF, username='OfflinePlayer',
                            expires='2037-12-31T00:00:00', guid=b'\x22' * 16)
TOKEN = sm.Token(expires='2037-12-31T00:00:00', guid=b'\x11' * 16)
PLUGIN_ID = b'\x33' * 16


@handles(*sm.AUTH_IDS)
def auth(conn, body):
    conn.kind = 'auth'
    mid = conn.ctx.get('_mid')
    replies = sm.replies_for(mid, body, acct=ACCOUNT, token=TOKEN)
    if mid == sm.TOKEN_ECHO_AUTHZ:
        # Seen in game: a profile that already has device data echoes with the re-authorization variant. The
        # authorization answer alone leaves the client waiting; it then still needs the account session.
        replies = replies + [sm.session_response(ACCOUNT)]
    for r in replies:
        conn.send_msg(r, note=sm.NAMES.get(int.from_bytes(r[4:8], 'little'), ''))
    if mid != sm.LOGIN_NSA:
        log(f'{conn.tag()} login complete for {ACCOUNT.username}')


@handles(*sm.CONDUCTOR_IDS)
def conductor(conn, body):
    conn.kind = 'conductor'
    mid = conn.ctx.get('_mid')
    port = conn.server.port
    for r in sm.replies_for(mid, body, acct=ACCOUNT, service=('127.0.0.1', port), plugin_id=PLUGIN_ID):
        conn.send_msg(r, note=f'service endpoint 127.0.0.1:{port}')
