"""Tests for tools/packages that need no game: a client here plays the game's side against the real server code.

    python -I -m unittest discover -s tools/packages/tests -v        (standard library only)
"""
import io
import re
import socket
import ssl
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
if str(TOOL) not in sys.path:
    sys.path.insert(0, str(TOOL))
import cert  # noqa: E402
import codec  # noqa: E402
import core  # noqa: E402
import rpc  # noqa: E402
import server  # noqa: E402
import server_msgs as sm  # noqa: E402
import services  # noqa: E402

core.LOGF = io.StringIO()    # the server's log lines are not part of a test run

CATALOG = '''<response>
\t<brands>\t<brand id="7" name="Acme^r^"/></brands>
\t<slot_types><slot_type id="0" name="Bat"/><slot_type id="3" name="Cleats"/></slot_types>
\t<items>
\t\t<item id="46885" name="Four-Seam Fastball" type_id="11" rarity_id="0"/>
\t\t<item id="800001" name="Silver Bat" type_id="2" rarity_id="2" brand_id="7" slot_type_id="0" texture_name="A"/>
\t\t<item id="800002" name="Gold Bat" type_id="2" rarity_id="3" brand_id="7" slot_type_id="0" texture_name="B"/>
\t\t<item id="800003" name="Diamond Cleats" type_id="2" rarity_id="4" brand_id="7" slot_type_id="3" texture_name="C"/>
\t</items>
</response>
'''
OWNED = '<response>\n\t<items>\n\t\t<item id="46885" quantity="1"/>\n\t</items>\n</response>\n'


def make_game(root):
    rtts = root / 'game' / 'romfs' / 'FRONTEND' / 'RTTS'
    rtts.mkdir(parents=True)
    (rtts / 'INVENTORYDATA.XML').write_text(CATALOG, encoding='utf-8')
    (rtts / 'INVQUANTITYDATA.XML').write_text(OWNED, encoding='utf-8')
    return root


class Certificate(unittest.TestCase):
    def test_made_once_and_trusted_by_a_tls_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, k = Path(tmp) / 'cert.pem', Path(tmp) / 'key.pem'
            self.assertTrue(cert.make(c, k))
            first = c.read_bytes()
            self.assertFalse(cert.make(c, k))                    # there already: kept
            self.assertEqual(c.read_bytes(), first)
            srv = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            srv.minimum_version = ssl.TLSVersion.TLSv1_2
            srv.load_cert_chain(c, k)
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)

            def serve():
                raw, _ = listener.accept()
                with srv.wrap_socket(raw, server_side=True) as t:
                    t.sendall(b'ok')

            threading.Thread(target=serve, daemon=True).start()
            client = ssl.create_default_context(cafile=str(c))   # checks the chain and the server name
            client.minimum_version = ssl.TLSVersion.TLSv1_2
            with socket.create_connection(('127.0.0.1', listener.getsockname()[1]), timeout=10) as raw:
                with client.wrap_socket(raw, server_hostname='production.mlb26.mlbtheshow.net') as t:
                    self.assertEqual(t.recv(2), b'ok')
            listener.close()

    def test_signature_is_checked_by_its_public_key(self):
        key = cert.rsa_key(1024)                                 # small: quick; make() uses 2048
        sig = cert.sign(key, b'message')
        opened = pow(int.from_bytes(sig, 'big'), key['e'], key['n']).to_bytes(128, 'big')
        self.assertTrue(opened.startswith(b'\x00\x01\xff'))
        import hashlib
        self.assertTrue(opened.endswith(hashlib.sha256(b'message').digest()))


class Wire(unittest.TestCase):
    def test_frames_split_and_joined(self):
        token = codec.encode_frame(codec.MSG_AUTH_TOKEN, codec.body_auth_token('some.id.token'))
        beat = codec.encode_frame(codec.MSG_HEARTBEAT, codec.body_heartbeat(0x4d))
        self.assertEqual(beat.hex(), 'a50209000000' + '09000000' + 'ade1d9d4' + '4d')
        dec, got = codec.StreamDecoder(), []
        data = token + beat
        for i in range(0, len(data), 7):                         # arrives in pieces
            got += dec.feed(data[i:i + 7])
        self.assertEqual([m for m, _ in got], [codec.MSG_AUTH_TOKEN, codec.MSG_HEARTBEAT])
        self.assertEqual(codec.Reader(got[0][1]).string(), 'some.id.token')

    def test_compressed_long_message(self):
        body = codec.body_auth_token('x' * 40000 + 'tail')
        wire = codec.encode_frame(codec.MSG_AUTH_TOKEN, body, compress=True)
        msgs, blocks = codec.decode_frames(wire)
        self.assertEqual(msgs, [(codec.MSG_AUTH_TOKEN, body)])
        self.assertTrue(all(flags & codec.FLAG_LZ4 for flags, _, _ in blocks))
        self.assertLess(len(wire), len(body))

    def test_fields(self):
        w = codec.Writer().string('').string('é' * 100).u16(0x1234).u64(1 << 40).vec_u8(b'\x01\x02').bytes()
        r = codec.Reader(w)
        self.assertEqual((r.string(), r.string(), r.u16(), r.u64(), r.vec_u8()),
                         ('', 'é' * 100, 0x1234, 1 << 40, b'\x01\x02'))
        self.assertTrue(r.done())

    def test_request_as_the_game_writes_it(self):
        self.assertEqual(rpc.params_to_json({'view_mode': 'RTTS', 'care_packages_only': True}),
                         '{"care_packages_only":true,"view_mode":"RTTS"}')
        body = rpc.encode_service_request(7, 'inventory.view_packs', {'view_mode': 'RTTS'})
        req = rpc.decode_service_request(body)
        self.assertEqual((req['request_id'], req['service']), (7, 'inventory.view_packs'))
        self.assertEqual(rpc.parse_params_json(req['params_json']), {'view_mode': 'RTTS'})
        xml = rpc.make_response_xml('<items/>')
        self.assertTrue(rpc.check_response_xml(xml)[0])
        self.assertFalse(rpc.check_response_xml('<result><response/></result>')[0])   # no status


class Game:
    """The game's side: TLS connections to the server under test and the messages the game sends."""

    def __init__(self, port, cert_file):
        self.port = port
        self.tls = ssl.create_default_context(cafile=str(cert_file))
        self.tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self.dec, self.open = {}, []

    def connect(self):
        raw = socket.create_connection(('127.0.0.1', self.port), timeout=10)
        self.open.append(self.tls.wrap_socket(raw, server_hostname='production.mlb26.mlbtheshow.net'))
        return self.open[-1]

    def close(self):
        for s in self.open:
            s.close()
        self.open = []

    def exchange(self, s, msg, want):
        if msg:
            s.sendall(codec.encode_stream(msg))
        dec = self.dec.setdefault(id(s), codec.StreamDecoder())
        while True:
            data = s.recv(65536)
            assert data, 'the server closed the connection'
            for mid, body in dec.feed(data):
                if mid == want:
                    return body

    def call(self, s, rid, name, params):
        body = self.exchange(s, codec.encode_message(rpc.MSG_SERVICE_REQUEST,
                                                     rpc.encode_service_request(rid, name, params)),
                             rpc.MSG_SERVICE_RESPONSE)
        r = rpc.decode_service_response(body)
        assert r['request_id'] == rid and r['service'] == name, r
        assert rpc.check_response_xml(r['xml'])[0], r['xml']
        return r['xml']

    def log_in(self):
        """Auth, conductor and service connections, as the game opens them. -> the service connection."""
        a = self.connect()
        b = self.exchange(a, codec.encode_message(sm.LOGIN_NSA, codec.body_auth_token('a.token')), sm.LOGIN_RESPONSE)
        r = codec.Reader(b)
        assert r.u8() == 1
        token = sm.Token.read(r)
        b = self.exchange(a, codec.encode_message(sm.TOKEN_ECHO, token.write(codec.Writer()).u8(1).bytes()),
                          sm.SESSION_RESPONSE)
        r = codec.Reader(b)
        assert r.u8() == 0
        self.account = sm.AccountSession.read(r)
        c = self.connect()
        b = self.exchange(c, codec.encode_message(sm.CONDUCTOR_QUERY, self.account.bytes()), sm.CONDUCTOR_ANSWER)
        r = codec.Reader(b)
        r.u8()
        self.endpoint = sm.parse_endpoint(r.raw(18))
        return self.service()

    def service(self):
        s = self.connect()
        s.sendall(codec.encode_stream(codec.encode_message(rpc.MSG_SERVICE_CONNECT,
                                                           self.account.bytes() + b'\x44' * 16)))
        return s


class Packages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game_dir = make_game(Path(self.tmp.name) / 'install')
        self.data = self.game_dir / 'profile' / 'offline-packages'
        self.start()

    def start(self):
        self.server, self.cert_file = server.start(self.game_dir / 'game' / 'romfs', self.data)
        threading.Thread(target=self.server.serve, daemon=True).start()
        self.game = Game(self.server.port, self.cert_file)

    def tearDown(self):
        self.game.close()
        self.server.close()
        self.tmp.cleanup()

    def test_listens_on_this_pc_only(self):
        self.assertEqual(self.server.sock.getsockname()[0], '127.0.0.1')

    def test_login_points_the_game_back_at_this_server(self):
        self.game.log_in()
        self.assertEqual(self.game.account.username, 'OfflinePlayer')
        self.assertEqual(self.game.endpoint[1:], ('127.0.0.1', self.server.port))

    def test_a_new_player_has_three_packs_and_owns_no_equipment(self):
        s = self.game.log_in()
        packs = self.game.call(s, 1, 'inventory.view_packs', {'care_packages_only': True, 'view_mode': 'RTTS'})
        self.assertEqual(packs.count('<item '), 3)
        owned = self.game.call(s, 2, 'inventory.view2', {})
        self.assertEqual(re.findall(r'<item id="(\d+)"', owned), ['46885'])    # only what the install lists

    def test_opening_a_pack_gives_an_item_of_the_pack_rarity_or_better(self):
        s = self.game.log_in()
        packs = self.game.call(s, 1, 'inventory.view_packs', {'view_mode': 'RTTS'})
        gold = re.search(r'<item id="(\d+)"[^>]*name="Gold Equipment Pack"', packs).group(1)
        reward = self.game.call(s, 2, 'inventory.open_pack', {'item_id': int(gold)})
        item = int(re.search(r'<item [^>]*\bid="(\d+)"', reward).group(1))
        self.assertIn(item, (800002, 800003))                                  # Gold or Diamond, never Silver
        self.assertIn('brand_name="Acme^r^"', reward)                          # what the reveal screen shows
        self.assertIn('is_new="1"', reward)
        owned = self.game.call(s, 3, 'inventory.view2', {})
        self.assertIn(f'<item id="{item}" quantity="1" is_new="1"', owned)
        self.assertEqual(self.game.call(s, 4, 'inventory.view_packs', {'view_mode': 'RTTS'}).count('<item '), 2)

    def test_what_the_player_has_survives_a_restart(self):
        s = self.game.log_in()
        self.game.call(s, 1, 'inventory.open_pack', {'item_id': 0})
        before = self.game.call(s, 2, 'inventory.view2', {})
        cert_before = self.cert_file.read_bytes()
        self.game.close()
        self.server.close()
        self.start()                                                           # the game is started again
        s = self.game.log_in()
        self.assertEqual(self.game.call(s, 1, 'inventory.view2', {}), before)
        self.assertEqual(self.game.call(s, 2, 'inventory.view_packs', {'view_mode': 'RTTS'}).count('<item '), 2)
        self.assertEqual(self.cert_file.read_bytes(), cert_before)             # the same certificate

    def test_road_to_the_show_awards_become_packs(self):
        s = self.game.log_in()
        self.game.call(s, 1, 'inventory.check_for_rewards', {'client_mission_ids': '15545,17085,17084'})
        packs = self.game.call(s, 2, 'inventory.view_packs', {'view_mode': 'RTTS'})
        self.assertEqual(packs.count('<item '), 6)                             # three starters and three awards
        info = self.game.call(s, 3, 'mission.reward_info', {'mission_ids': '15545,17085'})
        self.assertEqual(re.findall(r'texture_name="(\w+)"', info), ['box_equipment_silver', 'box_equipment_gold'])
        done = self.game.call(s, 4, 'mission.is_complete', {'mission_ids': '17084,17083'})
        self.assertEqual(re.findall(r'is_complete="(\w+)"', done), ['true', 'false'])    # a college's offer: once

    def test_hangs_up_when_the_game_is_back_on_the_main_menu_after_packages(self):
        # services.content_latest: the only place a lost connection is something the game recovers from by itself
        services.BACK_ON_THE_MENU = 0.05
        s = self.game.log_in()
        ask = {'content_update_type': 'RTTS'}
        self.game.call(s, 1, 'content_update.latest', ask)                     # the login asks once
        self.game.call(s, 2, 'content_update.latest', ask)                     # in and out of the mode, no Packages:
        self.game.call(s, 3, 'inventory.view_packs', {'view_mode': 'RTTS'})    # the connection stays
        self.game.call(s, 4, 'inventory.view_packs', {'care_packages_only': True, 'view_mode': 'RTTS'})   # Packages
        self.game.call(s, 5, 'content_update.latest', ask)                     # back on the main menu
        with self.assertRaisesRegex(AssertionError, 'closed the connection'):
            self.game.exchange(s, None, rpc.MSG_SERVICE_RESPONSE)
        self.game.close()
        s = self.game.log_in()                                                 # the game logs in again from its title
        self.assertEqual(self.game.call(s, 1, 'inventory.view_packs', {'view_mode': 'RTTS'}).count('<item '), 3)

    def test_the_package_counter_is_given_back_after_a_login(self):
        s = self.game.log_in()
        s.sendall(codec.encode_stream(codec.encode_message(0x0AD404ED, struct.pack('<IQB', 7, 0, 4))))
        self.game.call(s, 1, 'inventory.view2', {})                            # the server has read the counter
        back = self.game.exchange(self.game.service(), None, 0xAFE1519A)
        self.assertEqual(struct.unpack('<IQB', back[:13]), (7, 0, 4))

    def test_a_request_the_server_does_not_know_still_gets_an_answer(self):
        s = self.game.log_in()
        self.assertIn('<response', self.game.call(s, 1, 'something.new', {}))

    def test_starts_without_owning_when_the_install_owns_nothing(self):
        self.assertEqual(sorted(services.BASE_QTY), [46885])
        self.assertEqual({r: len(v) for r, v in services.BY_RARITY.items()}, {2: 1, 3: 1, 4: 1})


if __name__ == '__main__':
    unittest.main()
