"""Message handlers of the service connection: the game's RPCs (login.py has the auth and conductor ones).

RPC transport (rpc.py, checked against the game's code):
  client -> ServiceRequest 0x801FB56C {u32 request_id; string service; string params_json; blob keys; blobs}
  server -> ServiceResponse 0x30D39658 {u32 request_id; string service; string xml}   (must echo id and service)
  xml: <result><status><id>0</id><message>OK</message></status><response>...</response></result>
The client fails a request after 20 s without an answer, so every request gets one, even unknown services.
"""
import rpc
from core import handles, log

SERVICES = {}               # service name -> fn(conn, params) -> inner xml of <response>,
                            # or (inner, status_id, msg[, attributes of the <response> tag])


def service(*names):
    def deco(fn):
        for n in names:
            SERVICES[n] = fn
        return fn
    return deco


@handles(rpc.MSG_SERVICE_CONNECT)
def service_connect(conn, body):
    conn.kind = 'service'
    try:
        log(f'{conn.tag()} service connect: {rpc.decode_service_connect(body)}')
    except Exception as e:
        log(f'{conn.tag()} service connect (undecoded: {e})')
    profile_state.on_service_connect(conn)


@handles(rpc.MSG_SERVICE_REQUEST)
def service_request(conn, body):
    conn.kind = 'service'
    req = rpc.decode_service_request(body)
    rid, name, params = req['request_id'], req['service'], rpc.parse_params_json(req['params_json'])
    fn = SERVICES.get(name)
    if fn is None:
        log(f'{conn.tag()} request {name} {params}: not one this server knows, answered empty')
        out = ''
    else:
        out = fn(conn, params)
    status, msg, rattrs = 0, 'OK', ''
    if isinstance(out, tuple):
        out, status, msg, *rest = out
        rattrs = rest[0] if rest else ''
    xml = rpc.make_response_xml(out, status_id=status, message=msg, response_attrs=rattrs)
    conn.send(rpc.MSG_SERVICE_RESPONSE, rpc.encode_service_response(rid, name, xml),
              note=f'{name} ({len(xml)} B xml)')
    if fn is not None:
        log(f'{conn.tag()} request {name} {params} answered')


import services  # noqa: E402,F401       (registers the RPC implementations)
import profile_state  # noqa: E402       (the RTTS standard-package counter)
import login  # noqa: E402,F401          (registers the auth and conductor handlers)
