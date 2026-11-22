"""Login / session / conductor messages of the MLB The Show 26 olClient protocol: server-reply builders and
client-message parsers, checked against the game's own Serialize/Deserialize code (see NOTES at the bottom).

Every builder returns ONE message (u32 total_len | u32 msg_id | body), ready for block framing with codec.py
(encode_stream / encode_block). Every parser takes the message *body* (what codec.StreamDecoder yields as
(msg_id, body)).
"""
import calendar
import struct
import time

from codec import Reader, Writer, encode_message

# ----------------------------------------------------------------------------- message ids
# auth connection (CPluginAuth, f_70009e7fb4 handles S->C)
LOGIN_NSA            = 0x1397A1DF  # C->S  string id_token                                  (first msg on auth conn)
LOGIN_RESPONSE       = 0x26046C4C  # S->C  u8 ok, Token
LOGIN_RESPONSE_EX    = 0x7E7FDEE1  # S->C  same handler path as LOGIN_RESPONSE (+u32 code,+string,+u64); not needed
TOKEN_ECHO           = 0xDE3AC304  # C->S  Token, u8(=1)                                    (fresh profile)
TOKEN_ECHO_AUTHZ     = 0x0CA403F1  # C->S  Token, u8(=1), u64 flags(0|0x20|0x100)           (account re-authorization)
TOKEN_ECHO_LINK      = 0x66BAEA30  # C->S  Token, u8(=1), string, string                    (AttemptLinkDevice2Mlbts)
SESSION_RESPONSE     = 0x58AB8B20  # S->C  u8 err, AccountSession
SESSION_RESPONSE_LNK = 0x323F96A4  # S->C  u8 err, AccountSession, u8 link_status
AUTHZ_RESPONSE       = 0x4DC2CA3F  # S->C  u8 code  (0 or 0xee -> kStateAccountAuthorized, else ...Failed)
REGISTER_RESULT      = 0xDE4C73F9  # S->C  u32 code, string text (0 -> kStateRegistered, else kStateAuthFailed)
# any connection (olClient core)
KEEPALIVE            = 0xD4D9E1AD  # C->S  u8 (garbage)
PING                 = 0x9A77845F  # S->C  u8 ; client answers with KEEPALIVE
COMPAT_REJECT        = 0xB6D5B13E  # S->C  ONLY to reject: client logs "Server is not compatible" and disconnects(4)
# conductor connection (conductor plugin f_70009f100c sends, f_70009f1400 handles)
CONDUCTOR_QUERY      = 0x63174F11  # C->S  AccountSession   (CNetPlayer::ConnectConductorSession path)
CONDUCTOR_QUERY_PTY  = 0x78919356  # C->S  AccountSession   (CPartyManager::ConnectConductor path)
CONDUCTOR_ANSWER     = 0x07B7014F  # S->C  u8 keep_session, Endpoint, guid plugin_id, u64 (ignored by CNetPlayer)
CONDUCTOR_ANSWER_PTY = 0x1B26202C  # S->C  u8 success, Endpoint

NAMES = {v: k for k, v in globals().items() if k.isupper() and isinstance(v, int) and v > 0xFFFF}

AUTH_IDS = {LOGIN_NSA, TOKEN_ECHO, TOKEN_ECHO_AUTHZ, TOKEN_ECHO_LINK}
CONDUCTOR_IDS = {CONDUCTOR_QUERY, CONDUCTOR_QUERY_PTY}


def classify(first_msg_id):
    """Which logical connection a socket is, from the first non-keepalive message the client sent.
    No SNI is sent and the TLS layer never sees a host name, so this is the only discriminator."""
    if first_msg_id in AUTH_IDS: return 'auth'
    if first_msg_id in CONDUCTOR_IDS: return 'conductor'
    if first_msg_id == KEEPALIVE: return None            # not decisive yet
    return 'service'


# ----------------------------------------------------------------------------- field types
EXPIRES_FMT = '%Y-%m-%dT%H:%M:%S'   # parsed by f_70015310d0 with strtol + timegm (UTC); len >= 19 required


def expires_str(t=None, days=None):
    """'YYYY-MM-DDTHH:MM:SS' (UTC). Must be > now + 30 s on the client clock (f_7001531280(t, 30))."""
    if days is not None: t = time.time() + days * 86400
    if t is None: return '2037-12-31T00:00:00'        # far future, below 2^31 for safety
    return time.strftime(EXPIRES_FMT, time.gmtime(t))


def expires_epoch(s):
    """Mirror of f_70015310d0: returns the UTC epoch the client computes, or 0 if the client rejects the string."""
    b = s.encode() if isinstance(s, str) else s
    if len(b) < 19 or b[4:5] != b'-' or b[7:8] != b'-' or b[10:11] != b'T' or b[13:14] != b':' or b[16:17] != b':':
        return 0
    try:
        y, mo, d, h, mi, se = int(b[0:4]), int(b[5:7]), int(b[8:10]), int(b[11:13]), int(b[14:16]), int(b[17:19])
    except ValueError:
        return 0
    if y < 1900 or mo < 1: return 0
    return calendar.timegm((y, mo, d, h, mi, se, 0, 0, 0))


class Token:
    """Token (f_70014c2930 ser / f_70014c2b00 deser): string expires, guid16, vec<u8>, vec<u8>."""
    def __init__(self, expires=None, guid=b'\x11' * 16, blob_a=b'', blob_b=b''):
        self.expires = expires or expires_str(); self.guid = bytes(guid); self.blob_a = bytes(blob_a); self.blob_b = bytes(blob_b)
        assert len(self.guid) == 16
    def write(self, w): w.string(self.expires).raw(self.guid, 16).vec_u8(self.blob_a).vec_u8(self.blob_b); return w
    @classmethod
    def read(cls, r): return cls(r.string(), r.raw(16), r.vec_u8(), r.vec_u8())
    def __eq__(self, o): return isinstance(o, Token) and vars(self) == vars(o)
    def __repr__(self): return 'Token(%r, guid=%s, a=%s, b=%s)' % (self.expires, self.guid.hex(), self.blob_a.hex(), self.blob_b.hex())


class AccountSession:
    """AccountSession (f_70014bdc08 ser / f_70014bde34 deser):
    u64 account_id, u64 flags, string username, string expires, guid16, vec<u8>, vec<u8>."""
    def __init__(self, account_id=1, flags=0, username='OfflinePlayer', expires=None, guid=b'\x22' * 16,
                 blob_a=b'', blob_b=b''):
        self.account_id = account_id; self.flags = flags; self.username = username
        self.expires = expires or expires_str(); self.guid = bytes(guid); self.blob_a = bytes(blob_a); self.blob_b = bytes(blob_b)
        assert len(self.guid) == 16
    def write(self, w):
        return (w.u64(self.account_id).u64(self.flags).string(self.username).string(self.expires)
                 .raw(self.guid, 16).vec_u8(self.blob_a).vec_u8(self.blob_b))
    @classmethod
    def read(cls, r):
        return cls(r.u64(), r.u64(), r.string(), r.string(), r.raw(16), r.vec_u8(), r.vec_u8())
    def bytes(self): return self.write(Writer()).bytes()
    def __eq__(self, o): return isinstance(o, AccountSession) and vars(self) == vars(o)
    def __repr__(self):
        return 'AccountSession(id=%d, flags=%#x, user=%r, expires=%r, guid=%s, a=%s, b=%s)' % (
            self.account_id, self.flags, self.username, self.expires, self.guid.hex(), self.blob_a.hex(), self.blob_b.hex())


def endpoint(ip='127.0.0.1', port=10000):
    """Endpoint (f_70015395cc ser / f_7001539684 deser), 18 bytes:
      bytes 0..15  address as two LE u64 = the raw in-memory address object:
                   IPv4 -> in_addr in NETWORK order at bytes 0..3, ff ff at 4..5, zeros 6..15
                   (client types it IPv4 iff hi==0 and lo>>32 == 0xffff, f_70015391b4)
      bytes 16..17 port as stored in the object = htons(port), written LE  ->  BIG-endian port bytes on the wire
                   (client does ntohs() on it before connecting, f_7001538ed0 -> ntohs)
    The client turns it into inet_ntop(AF_INET) text ('127.0.0.1') and connects through GetHostEntByName."""
    a = bytes(int(x) for x in ip.split('.'))
    assert len(a) == 4
    return a + b'\xff\xff' + b'\x00' * 10 + struct.pack('>H', port)


def parse_endpoint(b):
    lo, hi = struct.unpack_from('<QQ', b, 0)
    port = struct.unpack_from('>H', b, 16)[0]
    if hi == 0 and (lo >> 32) == 0xFFFF:
        return 'ipv4', '.'.join(str(x) for x in b[0:4]), port
    if lo == 0 and hi == 0:
        return 'none', None, port
    return 'ipv6', b[0:16].hex(), port


# ----------------------------------------------------------------------------- server -> client builders
def login_response(token=None, ok=True):
    """0x26046c4c: u8 ok, Token. ok!=0 and Token.expires > now+30s -> client echoes the Token (0xde3ac304)."""
    return encode_message(LOGIN_RESPONSE, (token or Token()).write(Writer().u8(1 if ok else 0)).bytes())


def session_response(acct=None, err=0):
    """0x58ab8b20: u8 err (0 = ok), AccountSession. Reply to 0xde3ac304 (and acceptable for any token echo).
    err==0 and AccountSession.expires > now+30s -> kStateAuthenticated ('CPluginAuth: Authentication succeeded')."""
    return encode_message(SESSION_RESPONSE, (acct or AccountSession()).write(Writer().u8(err)).bytes())


def session_response_link(acct=None, err=0, link_status=0):
    """0x323f96a4: u8 err, AccountSession, u8 link_status. Reply to 0x66baea30 (device<->mlbts link).
    link_status 0 = 'Linking ... succeeded', 0xef = 'already linked'; any value still ends in kStateAuthenticated."""
    w = (acct or AccountSession()).write(Writer().u8(err))
    return encode_message(SESSION_RESPONSE_LNK, w.u8(link_status).bytes())


def authz_response(code=0):
    """0x4dc2ca3f: u8 code. Reply to 0x0ca403f1. 0 or 0xee -> kStateAccountAuthorized, else ...AuthorizationFailed."""
    return encode_message(AUTHZ_RESPONSE, Writer().u8(code).bytes())


def register_result(code=0, text=''):
    """0xde4c73f9: u32 code, string text. code 0 -> kStateRegistered, else kStateAuthFailed (text kept)."""
    return encode_message(REGISTER_RESULT, Writer().u32(code).string(text).bytes())


def conductor_answer(ip='127.0.0.1', port=10000, plugin_id=b'\x33' * 16, value=0, keep_session=True):
    """0x07b7014f: u8 keep_session, Endpoint(18), guid16 plugin_id, u64 value. Reply to 0x63174f11.
    keep_session=0 makes CNetPlayer wipe its cached AccountSession (f_70009b29b0) -> send 1.
    Endpoint must not be null (addr==0 and port==0) and plugin_id must not be all-zero, else
    'CNetPlayer::OnConductorAnswer : A null endpoint or plugin id was specified.'  value is not read by CNetPlayer."""
    assert any(plugin_id), 'plugin_id must be non-zero'
    w = Writer().u8(1 if keep_session else 0).raw(endpoint(ip, port), 18).raw(bytes(plugin_id), 16).u64(value)
    return encode_message(CONDUCTOR_ANSWER, w.bytes())


def conductor_answer_party(ip='127.0.0.1', port=10000, success=True):
    """0x1b26202c: u8 success, Endpoint. Reply to 0x78919356 (CPartyManager::OnConductorAnswer)."""
    return encode_message(CONDUCTOR_ANSWER_PTY, Writer().u8(1 if success else 0).raw(endpoint(ip, port), 18).bytes())


def ping(b=0):
    """0x9a77845f: u8. Makes the client send a keepalive (0xd4d9e1ad) at once."""
    return encode_message(PING, Writer().u8(b).bytes())


# ----------------------------------------------------------------------------- client -> server parsers
def _done(r, what):
    if not r.done(): raise ValueError('%s: %d trailing bytes' % (what, len(r.b) - r.p))


def parse_login_nsa(body):
    r = Reader(body); tok = r.string(); _done(r, 'LoginNSA'); return {'id_token': tok}


def parse_token_echo(msg_id, body):
    """0xde3ac304 / 0x0ca403f1 / 0x66baea30 (ser f_70014be240 / f_70014be374 / f_70014be5a4)."""
    r = Reader(body)
    out = {'variant': NAMES.get(msg_id, hex(msg_id)), 'token': Token.read(r), 'u8': r.u8()}
    if msg_id == TOKEN_ECHO_AUTHZ:
        out['flags'] = r.u64()
    elif msg_id == TOKEN_ECHO_LINK:
        out['device_login'] = r.string(); out['device_id'] = r.string()
    elif msg_id != TOKEN_ECHO:
        raise ValueError('not a token echo: %#x' % msg_id)
    _done(r, out['variant']); return out


def parse_conductor_query(body):
    """0x63174f11 / 0x78919356 (ser f_7001505f6c / f_70015061bc -> AccountSession at +8)."""
    r = Reader(body); a = AccountSession.read(r); _done(r, 'ConductorQuery'); return a


def parse_keepalive(body):
    r = Reader(body); b = r.u8(); _done(r, 'Keepalive'); return b


def parse(msg_id, body):
    if msg_id == LOGIN_NSA: return parse_login_nsa(body)
    if msg_id in (TOKEN_ECHO, TOKEN_ECHO_AUTHZ, TOKEN_ECHO_LINK): return parse_token_echo(msg_id, body)
    if msg_id in CONDUCTOR_IDS: return parse_conductor_query(body)
    if msg_id == KEEPALIVE: return parse_keepalive(body)
    return None


def replies_for(msg_id, body, acct=None, token=None, service=('127.0.0.1', 10000), plugin_id=b'\x33' * 16):
    """Default stand-in behaviour: list of reply messages for one client message (empty if none)."""
    if msg_id == LOGIN_NSA:
        parse_login_nsa(body); return [login_response(token)]
    if msg_id == TOKEN_ECHO:
        parse_token_echo(msg_id, body); return [session_response(acct)]
    if msg_id == TOKEN_ECHO_LINK:
        parse_token_echo(msg_id, body); return [session_response_link(acct)]
    if msg_id == TOKEN_ECHO_AUTHZ:
        parse_token_echo(msg_id, body); return [authz_response(0)]
    if msg_id == CONDUCTOR_QUERY:
        parse_conductor_query(body); return [conductor_answer(service[0], service[1], plugin_id)]
    if msg_id == CONDUCTOR_QUERY_PTY:
        parse_conductor_query(body); return [conductor_answer_party(service[0], service[1])]
    return []


# ----------------------------------------------------------------------------- self-test
def _client_echo(msg_id, token, extra=b''):
    """What the client would send (built the way its serializers do): for tests that play the game's side."""
    return encode_message(msg_id, token.write(Writer()).u8(1).bytes() + extra)


# NOTES (evidence; addresses are in the 1.0.20 main module)
# - Strings: u32 n, LEB128 n, n bytes (f_700092ae20 resizes to n then copies the LEB length) -> keep both equal.
# - LoginResponse deser f_70014c3c40: u8 ok @+8, Token @+0x10 (string +0x18, guid +0x38, vec +0x48, vec +0x60).
# - Handler f_70009e7fb4: ok && !f_7001531280(timegm(expires),30) -> echo; ok && expired -> error 0xdead000a.
#   echo choice: CPluginAuth+0x54 (= CNetSession+0x59, set only by f_70009b2a54 <- f_70009a6e58 re-authorize)
#   -> 0x0ca403f1; else f_70009e8e10 'AttemptLinkDevice2Mlbts' true -> 0x66baea30; else 0xde3ac304.
# - SessionResponse deser f_70014be6f8 / f_70014be818 (u8, AccountSession, [u8]); handler: err==0 and
#   AccountSession.expires > now+30 s -> copies session, SetState(kStateAuthenticated=4).
# - Conductor: f_70009f100c sends 0x63174f11 (callback +0xd8) or 0x78919356 (+0xe8); f_70009f1400 maps
#   0x07b7014f -> OnConductorAnswer(endpoint, plugin guid, u64, keep==0) = f_70009a7800,
#   0x1b26202c -> CPartyManager::OnConductorAnswer(endpoint, success) = f_700093b09c.
# - Service connect f_70009a7454: inet_ntop(Endpoint addr) + ntohs(port) -> f_7001535e00 -> f_700151c1dc ->
#   GetHostEntByName(text) ('[olClient] Failed to resolve %s to an IP address.' on failure).
