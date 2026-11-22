"""
RPC ("service") transport of MLB The Show 26 (Switch port) on the olClient *service* connection.

Everything here was read from the game's code (addresses in the 1.0.20 main module).

Client side, one RPC (e.g. inventory.view_packs):
  f_7000a12970  Transaction::Run      "STARTING SERVICE [%s]" ... "SENDING SERVICE END"
    f_70009f85a0  request_id = global counter @0x7003abf068 (returns current, stores +1; skips 0xFFFFFFFF)
    f_7000a15440  params map -> JSON text (types 1..8); type-9 params (binary) go to the blob map instead
    f_70009f85c0  ServicePlugin::SendRequest: registers a pending entry keyed by
                  pending_key(request_id, service) then f_7001530fb0 -> f_700151c884 (olClient send)
  message 0x801FB56C ServiceRequest   (Serialize f_7001503bd0, Deserialize f_7001503f50)

Server -> client:
  message 0x30D39658 ServiceResponse  (Serialize f_70015041b0, Deserialize f_700150422c)
    f_70009f9070  ServicePlugin::OnMessage: id == 0x30D39658 -> look up pending_key(msg.request_id,
                  msg.service) -> callback = bind(f_7000a13298, txn)
    f_7000a13298  requires msg.request_id == txn.request_id AND msg.service == txn.service (strcmp),
                  msg.xml != "timedout"; parses msg.xml (f_7000a62db4: TinyXML2 doc -> root element);
                  root.status.{message,id} required; id text atoi'd; id == 0 -> root.response required.
  Timeout: f_70009f8cf0 synthesises a ServiceResponse with xml "timedout" when a request is pending
  >= 20001 ms (0x4E21).

Wire (bodies use codec.py primitives, no tags, little endian):

  ServiceRequest 0x801FB56C  (client -> server)
     u32     request_id
     string  service            e.g. "inventory.view_packs"
     string  params_json        e.g. {"care_packages_only":true,"view_mode":"RTTS"}  ("{}" when no params)
     u32     n_blob_keys, then n_blob_keys x string key      (type-9/binary params; normally 0)
     u32     n_blobs,     then n_blobs x (u32 len + len bytes) value of blob_keys[i], in key order
  ServiceResponse 0x30D39658 (server -> client)
     u32     request_id         echo
     string  service            echo (exact bytes)
     string  xml                full XML document text

params_json format (f_700151a26c begin '{', f_700151aa40 key '"%s":', separator ',' from table
0x7002206578 ["", ","], f_700151a4d4 end '}'), values by param type:
  1 bool   -> true / false          (f_700151bb48, table @0x7001da9f88)
  2 int    -> %d                    (f_700151ab30)
  3 uint   -> %u                    (f_700151aed0)
  4 int64  -> %ld                   (f_700151ad00)
  5 uint64 -> %lu                   (f_700151b0a0)
  6 float, 7 double -> %f           (f_700151bd28)
  8 string -> "raw text"            (f_700151b7b0 called with escape=0: NOT escaped)
  Order = iteration order of the transaction's std::map<std::string,...> (ascending key). No spaces.

Other messages registered by the Service plugin (f_70015043a0 group, plugin name "Service", type 9):
  0x7C335915 ServiceConnect C->S, sent once when the plugin attaches (f_70009f8c4c):
             AccountSession + 16-byte guid.  No reply is awaited (state 6 is set right after attach).
  0x94E26BC1 C->S? body: AccountSession            (Serialize f_7001503b2c)    - sender not traced
  0xC031F812 C->S? body: u64                        (Serialize f_7001503a1c)    - sender not traced
  0xDF31986F ?     body: u32, string                (Serialize f_70015042d4)    - not handled in OnMessage
  0x9FD30956 S->C  body: string, string (OnMessage branch: clears online-manager strings, f_70016527d8)
  0xE54920EB S->C  (no vtable found; factory f_70014dd530) OnMessage stores fields into online mgr +0x628..
  0xF63439D4 / 0x23BF9620 (group f_7001505770) S->C: OnMessage looks up a 2nd map keyed by u32 @+8
"""
import json
import struct
import xml.etree.ElementTree as ET

import codec
from codec import Reader, Writer

MSG_SERVICE_REQUEST = 0x801FB56C
MSG_SERVICE_RESPONSE = 0x30D39658
MSG_SERVICE_CONNECT = 0x7C335915
MSG_SVC_ACCOUNT = 0x94E26BC1
MSG_SVC_U64 = 0xC031F812
MSG_SVC_U32_STR = 0xDF31986F
MSG_SVC_STR_STR = 0x9FD30956
MSG_SVC_E549 = 0xE54920EB

NAMES = {
    MSG_SERVICE_REQUEST: 'ServiceRequest', MSG_SERVICE_RESPONSE: 'ServiceResponse',
    MSG_SERVICE_CONNECT: 'ServiceConnect', MSG_SVC_ACCOUNT: 'Svc_94E26BC1', MSG_SVC_U64: 'Svc_C031F812',
    MSG_SVC_U32_STR: 'Svc_DF31986F', MSG_SVC_STR_STR: 'Svc_9FD30956', MSG_SVC_E549: 'Svc_E54920EB',
}

TIMEOUT_MS = 20001          # f_70009f8cf0: pending request is failed with xml "timedout" after this
TIMEDOUT_XML = 'timedout'   # f_7000a13298 treats this exact xml string as an error


# ----------------------------------------------------------------------------- params JSON
def params_to_json(params):
    """Reproduce the client's JSON text for a params dict (bool/int/float/str values)."""
    parts = []
    for k in sorted(params, key=lambda s: s.encode('utf-8')):
        v = params[k]
        if isinstance(v, bool):
            t = 'true' if v else 'false'
        elif isinstance(v, int):
            t = '%d' % v
        elif isinstance(v, float):
            t = '%f' % v
        elif isinstance(v, str):
            t = '"%s"' % v           # the game does not escape string params
        else:
            raise TypeError('unsupported param type for %r: %r' % (k, type(v)))
        parts.append('"%s":%s' % (k, t))
    return '{' + ','.join(parts) + '}'


def parse_params_json(text):
    """Lenient parse of params_json (strings are unescaped by the client, so json may fail)."""
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {'__raw__': text}


# ----------------------------------------------------------------------------- ServiceRequest
def encode_service_request(request_id, service, params=None, blobs=None):
    """Body of ServiceRequest. params: dict (encoded like the game) or a ready JSON str."""
    pj = params if isinstance(params, str) else params_to_json(params or {})
    blobs = blobs or {}
    keys = sorted(blobs, key=lambda s: s.encode('utf-8'))
    w = Writer().u32(request_id).string(service).string(pj)
    w.vector(keys, lambda w_, k: w_.string(k))
    w.u32(len(keys))
    for k in keys:
        w.vec_u8(blobs[k])
    return w.bytes()


def decode_service_request(body):
    r = Reader(body)
    req = {'request_id': r.u32(), 'service': r.string(), 'params_json': r.string()}
    keys = r.vector(lambda r_: r_.string())
    n = r.u32()
    vals = [r.vec_u8() for _ in range(n)]
    req['blobs'] = dict(zip(keys, vals))
    req['params'] = parse_params_json(req['params_json'])
    if not r.done():
        raise ValueError('ServiceRequest: %d trailing bytes' % (len(body) - r.p))
    return req


# ----------------------------------------------------------------------------- ServiceResponse
def encode_service_response(request_id, service, xml):
    return Writer().u32(request_id).string(service).string(xml).bytes()


def decode_service_response(body):
    r = Reader(body)
    resp = {'request_id': r.u32(), 'service': r.string(), 'xml': r.string()}
    if not r.done():
        raise ValueError('ServiceResponse: %d trailing bytes' % (len(body) - r.p))
    return resp


def make_response_xml(response_inner='', status_id=0, message='OK', root='result', response_attrs=''):
    """Minimal document f_7000a13298 accepts. Root name is not checked; status/message/id must be
    child ELEMENTS of the root; when id == 0 a <response> child of the root is required."""
    # Scalar fields are read from XML ATTRIBUTES only (child elements are a separate map), and bools only count as
    # "true": a hook's top-level scalars are attributes on the <response> tag.
    ra = (' ' + response_attrs) if response_attrs else ''
    return ('<%s><status><id>%d</id><message>%s</message></status><response%s>%s</response></%s>'
            % (root, status_id, message, ra, response_inner, root))


def check_response_xml(xml):
    """Apply the checks f_7000a13298 makes; returns (ok, why)."""
    if xml == TIMEDOUT_XML:
        return False, 'timedout'
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return False, 'xml parse error: %s' % e
    st = root.find('status')
    if st is None or st.find('message') is None or st.find('id') is None:
        return False, 'missing status/message/id (client error code 2)'
    try:
        sid = int((st.find('id').text or '0').strip() or 0)
    except ValueError:
        sid = 0   # atoi semantics: non-numeric -> 0
    if sid != 0:
        return False, 'status id %d != 0 (server error path)' % sid
    if root.find('response') is None:
        return False, 'missing response (client error code 1)'
    return True, 'ok'


# ----------------------------------------------------------------------------- matching key
def pending_key(request_id, service):
    """Key of the client's pending-request map (f_70009f85c0 / f_70009f9070): BKDR*131 seeded with
    request_id over the service name bytes (signed chars). Informational: the server just echoes."""
    h = request_id & 0xFFFFFFFF
    for b in service.encode('utf-8'):
        h = (h * 131 + (b - 256 if b > 127 else b)) & 0xFFFFFFFF
    return h


# ----------------------------------------------------------------------------- ServiceConnect
def decode_account_session(r):
    """AccountSession as serialized by f_70014bdc08 (same layout as login-handshake/olproto.py)."""
    return {'account_id': r.u64(), 'flags': r.u64(), 'name': r.string(), 'expires': r.string(),
            'guid': r.raw(16).hex(), 'a': r.vec_u8(), 'b': r.vec_u8()}


def decode_service_connect(body):
    r = Reader(body)
    out = {'session': decode_account_session(r), 'plugin_guid': r.raw(16).hex()}
    if not r.done():
        out['trailing'] = body[r.p:].hex()
    return out


# ----------------------------------------------------------------------------- framing helpers
def request_frame(request_id, service, params=None, compress=False):
    return codec.encode_frame(MSG_SERVICE_REQUEST, encode_service_request(request_id, service, params), compress)


def response_frame(request_id, service, xml, compress=False):
    return codec.encode_frame(MSG_SERVICE_RESPONSE, encode_service_response(request_id, service, xml), compress)


def answer_request(req_body, xml):
    """Server helper: given a ServiceRequest body, build the ServiceResponse message bytes (no block)."""
    req = decode_service_request(req_body)
    return codec.encode_message(MSG_SERVICE_RESPONSE,
                                encode_service_response(req['request_id'], req['service'], xml))


def describe(mid, body):
    try:
        if mid == MSG_SERVICE_REQUEST:
            d = decode_service_request(body)
            return 'ServiceRequest(id=%d, service=%r, params=%s, blobs=%d)' % (
                d['request_id'], d['service'], d['params_json'], len(d['blobs']))
        if mid == MSG_SERVICE_RESPONSE:
            d = decode_service_response(body)
            return 'ServiceResponse(id=%d, service=%r, xml=%d bytes)' % (d['request_id'], d['service'], len(d['xml']))
        if mid == MSG_SERVICE_CONNECT:
            return 'ServiceConnect(%r)' % decode_service_connect(body)
    except Exception as e:  # noqa: BLE001
        return '%s (decode failed: %s) %s' % (NAMES.get(mid, hex(mid)), e, body.hex())
    return codec.describe(mid, body)
