"""A self-signed TLS certificate for the local stand-in server, made on the player's PC with the standard library.

The game checks the server it logs in to against a list of trusted certificates. With offline packages on, the
runtime puts this one certificate in that list (runtime/mlb/packages.c) and the stand-in server presents it, so the
game's own check passes without being weakened. Every PC makes its own key the first time, so no private key is ever
shipped or shared; the certificate is only good for a server on this PC, and only this game is told to trust it.

    make(cert_path, key_path)    writes both as PEM (RSA 2048, SHA-256); returns False when they were already there

Making the key takes a few seconds, once.
"""
import base64
import calendar
import hashlib
import math
import secrets
import time

# what the game calls its servers; the certificate is valid for these names only
NAMES = ['production.mlb.mlbtheshow.net', 'production.mlb26.mlbtheshow.net', 'prodaccount.mlb.mlbtheshow.net',
         '*.mlb.mlbtheshow.net', '*.mlb26.mlbtheshow.net', '*.mlbtheshow.net']
SUBJECT = 'MLB The Show 26 offline packages (this PC only)'
SMALL_PRIMES = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]


# ---- RSA ------------------------------------------------------------------------------------------------------------

def _probably_prime(n, rounds=40):
    """Miller-Rabin with random bases: a composite passes with probability below 4 ** -rounds."""
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        x = pow(secrets.randbelow(n - 3) + 2, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        n = secrets.randbits(bits) | (3 << (bits - 2)) | 1      # top two bits set: the product has 2 * bits bits
        if all(n % p for p in SMALL_PRIMES) and _probably_prime(n):
            return n


def rsa_key(bits=2048):
    e = 65537
    while True:
        p, q = _prime(bits // 2), _prime(bits // 2)
        if p != q and math.gcd(e, (p - 1) * (q - 1)) == 1:
            d = pow(e, -1, (p - 1) * (q - 1))
            return dict(n=p * q, e=e, d=d, p=p, q=q, dp=d % (p - 1), dq=d % (q - 1), qi=pow(q, -1, p))


def sign(key, data):
    """RSASSA-PKCS1-v1_5 with SHA-256."""
    k = (key['n'].bit_length() + 7) // 8
    digest_info = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(data).digest()
    padded = b'\x00\x01' + b'\xff' * (k - len(digest_info) - 3) + b'\x00' + digest_info
    return pow(int.from_bytes(padded, 'big'), key['d'], key['n']).to_bytes(k, 'big')


# ---- DER ------------------------------------------------------------------------------------------------------------

def _tlv(tag, body):
    n, k = len(body), (len(body).bit_length() + 7) // 8
    length = bytes([n]) if n < 0x80 else bytes([0x80 | k]) + n.to_bytes(k, 'big')
    return bytes([tag]) + length + body


def _seq(*parts):
    return _tlv(0x30, b''.join(parts))


def _int(v):
    return _tlv(0x02, v.to_bytes(v.bit_length() // 8 + 1, 'big'))      # one more byte than needed: never negative


def _oid(dotted):
    a = [int(x) for x in dotted.split('.')]
    body = bytes([a[0] * 40 + a[1]])
    for v in a[2:]:
        chunk = [v & 0x7f]
        while v > 0x7f:
            v >>= 7
            chunk.append(0x80 | (v & 0x7f))
        body += bytes(reversed(chunk))
    return _tlv(0x06, body)


def _utc(t):
    return _tlv(0x17, time.strftime('%y%m%d%H%M%SZ', time.gmtime(t)).encode())


SHA256_RSA = _seq(_oid('1.2.840.113549.1.1.11'), _tlv(0x05, b''))


def certificate(key, names=NAMES, subject=SUBJECT, now=None):
    """A self-signed X.509 v3 certificate (DER) for `names`, from a day ago until the end of 2049."""
    now = time.time() if now is None else now
    name = _seq(_tlv(0x31, _seq(_oid('2.5.4.3'), _tlv(0x0c, subject.encode()))))
    public = _seq(_seq(_oid('1.2.840.113549.1.1.1'), _tlv(0x05, b'')),
                  _tlv(0x03, b'\x00' + _seq(_int(key['n']), _int(key['e']))))
    extensions = _seq(
        _seq(_oid('2.5.29.19'), _tlv(0x01, b'\xff'), _tlv(0x04, _seq(_tlv(0x01, b'\xff')))),      # CA: its own issuer
        _seq(_oid('2.5.29.17'), _tlv(0x04, _seq(*[_tlv(0x82, n.encode()) for n in names]))))      # the server names
    tbs = _seq(_tlv(0xa0, _int(2)), _int(secrets.randbits(63) | 1), SHA256_RSA, name,
               _seq(_utc(now - 86400), _utc(calendar.timegm((2049, 12, 30, 0, 0, 0)))), name, public,
               _tlv(0xa3, extensions))
    return _seq(tbs, SHA256_RSA, _tlv(0x03, b'\x00' + sign(key, tbs)))


def private_key(key):
    """The key as PKCS #1 RSAPrivateKey (DER)."""
    return _seq(_int(0), *[_int(key[f]) for f in ('n', 'e', 'd', 'p', 'q', 'dp', 'dq', 'qi')])


def pem(label, der):
    b64 = base64.b64encode(der).decode()
    return f'-----BEGIN {label}-----\n' + '\n'.join(b64[i:i + 64] for i in range(0, len(b64), 64)) + \
        f'\n-----END {label}-----\n'


def make(cert_path, key_path):
    """Write a new certificate and key unless both files are there. -> whether they were made now."""
    if cert_path.exists() and key_path.exists():
        return False
    key = rsa_key()
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(pem('RSA PRIVATE KEY', private_key(key)), encoding='ascii')
    cert_path.write_text(pem('CERTIFICATE', certificate(key)), encoding='ascii')
    return True
