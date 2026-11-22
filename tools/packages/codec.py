"""
Codec for the MLB The Show 26 (Switch) "olClient" binary protocol, as it runs inside TLS between the game and
the stand-in server (server.py). Function names are addresses in the 1.0.20 main module.

Two layers, everything little-endian:

1. Stream blocks (olClient transport, f_700151cd40 send / f_700151d2a0 recv)
     u8   magic  = 0xA5                       (f_7001502d14 writes, f_7001502db4 checks)
     u8   flags  : 0x02 always set by sender; 0x04 = payload is an LZ4 *block* (raw LZ4, no frame)
     u32  length : bytes of payload that follow (compressed size if 0x04); max 0x8000
     payload
   A block is a slice of a continuous message byte-stream: the sender cuts its send
   buffer into chunks of <= 0x7FC0 bytes, so messages can span blocks and a block can
   hold several messages. Receiver max decompressed size per block is 0x8000.

2. Messages (f_700151d520 parse, f_7001502b4c/f_7001502bd4 header ser/deser)
     u32  length : whole message incl. this 8-byte header
     u32  msgId  : per-class constant (not a checksum; e.g. 0x1397A1DF lives at 0x70022DDE38)
     body        : the class's hand-written Serialize() output, fixed field order, NO type tags

Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_70014bdc08 u64, f_70014e2b00 u16,
f_70015351a4 raw bytes, f_700092ce50/f_700092ae20 string, f_70014c2930 vector<u8>):
     u8/bool  1 byte;  u16 2;  u32/i32/f32 4;  u64/i64/f64 8   (all LE)
     string   u32 len, then (only if len > 0) LEB128(len), then len bytes
     bytes[N] N raw bytes (fixed-size arrays, e.g. 16 or 64)
     vector   u32 count, then count elements
"""
import struct

MAGIC = 0xA5
FLAG_BASE = 0x02
FLAG_LZ4 = 0x04
MAX_BLOCK = 0x8000
SEND_CHUNK = 0x7FC0

# Known message ids (verified getters / registrations)
MSG_AUTH_TOKEN = 0x1397A1DF   # client->server, body: string (NSA id token).  getter f_70014c8a18
MSG_HEARTBEAT = 0xD4D9E1AD    # client->server every 15 s idle, body: u8 (unused).  getter f_700150330c
MSG_PING = 0x9A77845F         # server->client: makes the client send a heartbeat now.  getter f_70015032d8

NAMES = {MSG_AUTH_TOKEN: 'AuthToken', MSG_HEARTBEAT: 'Heartbeat', MSG_PING: 'Ping'}


# ----------------------------------------------------------------------------- LZ4 block
def lz4_block_decompress(src, max_out=MAX_BLOCK):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255: break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        if off == 0 or off > len(out):
            raise ValueError('lz4: bad offset')
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255: break
        ml += 4
        start = len(out) - off
        for k in range(ml):
            out.append(out[start + k])
        if len(out) > max_out:
            raise ValueError('lz4: output exceeds %d' % max_out)
    return bytes(out)


def _lz4_len(v):
    out = bytearray()
    while v >= 255:
        out.append(255); v -= 255
    out.append(v)
    return out


def lz4_block_compress(src):
    """Greedy LZ4 block compressor (valid for LZ4_decompress_safe)."""
    n = len(src)
    out = bytearray()
    table = {}
    anchor = i = 0
    limit = n - 12  # LZ4 rules: last match must start >= 12 bytes before end, last 5 bytes literal
    while i < limit:
        key = src[i:i + 4]
        cand = table.get(key)
        table[key] = i
        if cand is not None and i - cand <= 0xFFFF:
            ml = 4
            while i + ml < n - 5 and src[cand + ml] == src[i + ml]:
                ml += 1
            lit = i - anchor
            tok = (min(lit, 15) << 4) | min(ml - 4, 15)
            out.append(tok)
            if lit >= 15: out += _lz4_len(lit - 15)
            out += src[anchor:i]
            out += struct.pack('<H', i - cand)
            if ml - 4 >= 15: out += _lz4_len(ml - 4 - 15)
            i += ml
            anchor = i
        else:
            i += 1
    lit = n - anchor
    out.append(min(lit, 15) << 4)
    if lit >= 15: out += _lz4_len(lit - 15)
    out += src[anchor:]
    return bytes(out)


# ----------------------------------------------------------------------------- blocks
def encode_block(payload, compress=False):
    """One stream block. Mirrors f_700151cd40: compress only if it actually shrinks."""
    if len(payload) > SEND_CHUNK:
        raise ValueError('block payload > 0x7FC0; use encode_stream')
    flags, body = FLAG_BASE, payload
    if compress:
        c = lz4_block_compress(payload)
        if 0 < len(c) < len(payload):
            flags, body = FLAG_BASE | FLAG_LZ4, c
    return struct.pack('<BBI', MAGIC, flags, len(body)) + body


def encode_stream(msg_bytes, compress=False):
    """Cut a byte stream of messages into blocks the way the game does (0x7FC0 chunks)."""
    return b''.join(encode_block(msg_bytes[o:o + SEND_CHUNK], compress)
                    for o in range(0, len(msg_bytes), SEND_CHUNK))


class StreamDecoder:
    """Feed raw TLS plaintext; get back (msgId, body) tuples. Handles split/merged blocks."""
    def __init__(self, allow_lz4=True):
        self.raw = bytearray()
        self.msgbuf = bytearray()
        self.allow_lz4 = allow_lz4
        self.blocks = []  # (flags, wire_len, payload_len) for inspection

    def feed(self, data):
        self.raw += data
        while len(self.raw) >= 6:
            magic, flags, ln = struct.unpack_from('<BBI', self.raw, 0)
            if magic != MAGIC:
                raise ValueError('stream: bad magic 0x%02x' % magic)
            if ln > MAX_BLOCK:
                raise ValueError('stream: block length %d > 0x8000' % ln)
            if len(self.raw) < 6 + ln:
                break
            body = bytes(self.raw[6:6 + ln]); del self.raw[:6 + ln]
            if flags & FLAG_LZ4:
                if not self.allow_lz4:
                    raise ValueError('stream is compressed but compression is not enabled')
                body = lz4_block_decompress(body)
            self.blocks.append((flags, ln, len(body)))
            self.msgbuf += body
        msgs = []
        while len(self.msgbuf) >= 8:
            mlen, mid = struct.unpack_from('<II', self.msgbuf, 0)
            if mlen < 8:
                raise ValueError('message length %d < 8' % mlen)
            if len(self.msgbuf) < mlen:
                break
            msgs.append((mid, bytes(self.msgbuf[8:mlen])))
            del self.msgbuf[:mlen]
        return msgs


def encode_message(msg_id, body):
    return struct.pack('<II', 8 + len(body), msg_id) + body


def encode_frame(msg_id, body, compress=False):
    """One message in its own block(s): what the game sent for frames 1 and 2."""
    return encode_stream(encode_message(msg_id, body), compress)


def decode_frames(data, allow_lz4=True):
    d = StreamDecoder(allow_lz4)
    msgs = d.feed(data)
    if d.raw or d.msgbuf:
        raise ValueError('trailing partial data: %d raw, %d msg bytes' % (len(d.raw), len(d.msgbuf)))
    return msgs, d.blocks


# ----------------------------------------------------------------------------- body fields
class Writer:
    def __init__(self): self.b = bytearray()
    def u8(self, v): self.b += struct.pack('<B', v & 0xFF); return self
    def bool(self, v): return self.u8(1 if v else 0)
    def u16(self, v): self.b += struct.pack('<H', v & 0xFFFF); return self
    def u32(self, v): self.b += struct.pack('<I', v & 0xFFFFFFFF); return self
    def i32(self, v): self.b += struct.pack('<i', v); return self
    def u64(self, v): self.b += struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF); return self
    def i64(self, v): self.b += struct.pack('<q', v); return self
    def f32(self, v): self.b += struct.pack('<f', v); return self
    def f64(self, v): self.b += struct.pack('<d', v); return self
    def raw(self, data, n=None):
        if n is not None and len(data) != n: raise ValueError('raw: want %d bytes' % n)
        self.b += data; return self
    def leb(self, v):
        while v >= 0x80:
            self.b.append((v & 0x7F) | 0x80); v >>= 7
        self.b.append(v); return self
    def string(self, s):
        data = s.encode('utf-8') if isinstance(s, str) else bytes(s)
        self.u32(len(data))
        if data:
            self.leb(len(data)); self.b += data
        return self
    def vec_u8(self, data): self.u32(len(data)); self.b += bytes(data); return self
    def vector(self, items, fn):
        self.u32(len(items))
        for it in items: fn(self, it)
        return self
    def bytes(self): return bytes(self.b)


class Reader:
    def __init__(self, b): self.b, self.p = b, 0
    def _take(self, n):
        if self.p + n > len(self.b): raise ValueError('read past end')
        v = self.b[self.p:self.p + n]; self.p += n; return v
    def u8(self): return self._take(1)[0]
    def bool(self): return self.u8() != 0
    def u16(self): return struct.unpack('<H', self._take(2))[0]
    def u32(self): return struct.unpack('<I', self._take(4))[0]
    def i32(self): return struct.unpack('<i', self._take(4))[0]
    def u64(self): return struct.unpack('<Q', self._take(8))[0]
    def i64(self): return struct.unpack('<q', self._take(8))[0]
    def f32(self): return struct.unpack('<f', self._take(4))[0]
    def f64(self): return struct.unpack('<d', self._take(8))[0]
    def raw(self, n): return bytes(self._take(n))
    def leb(self):
        v = sh = 0
        while True:
            c = self.u8(); v |= (c & 0x7F) << sh; sh += 7
            if not c & 0x80: return v
    def string_bytes(self):
        n = self.u32()
        if n == 0: return b''
        m = self.leb()          # game: resize to n, then copy m bytes (m <= remaining)
        return self.raw(m)
    def string(self): return self.string_bytes().decode('utf-8', 'replace')
    def vec_u8(self): return self.raw(self.u32())
    def vector(self, fn): return [fn(self) for _ in range(self.u32())]
    def done(self): return self.p == len(self.b)


# ----------------------------------------------------------------------------- known bodies
def body_auth_token(token): return Writer().string(token).bytes()
def body_heartbeat(b=0): return Writer().u8(b).bytes()
def body_ping(b=0): return Writer().u8(b).bytes()

def describe(mid, body):
    r = Reader(body)
    if mid == MSG_AUTH_TOKEN:
        return 'AuthToken(token=%r)' % r.string()
    if mid in (MSG_HEARTBEAT, MSG_PING):
        return '%s(byte=0x%02x)' % (NAMES[mid], r.u8())
    return 'msg 0x%08x (%d bytes): %s' % (mid, len(body), body.hex())
