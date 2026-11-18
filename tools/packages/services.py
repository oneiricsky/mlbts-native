"""What the game asks the service connection for, and the answers: going online, the inventory, and the equipment
packs of Road to the Show.

What each request must answer was read from the game's scripts and code. The item catalog is the install's own
FRONTEND/RTTS/INVENTORYDATA.XML with the equipment tools/equipment added to it; what the player owns starts from
INVQUANTITYDATA.XML (nothing of the equipment when it was added with --no-own) and packs add to that. The player's
state (packs owned, items they gave, which are new) is in state.json (server.State).
"""
import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

from core import log
from handlers import service

PACK_TYPE = 4                       # inventory.view_packs item type_id the RTTS open path checks for
PACK_ID_BASE = 900000
BOXES = {                           # box -> (rarity_id for the open animation, box art in LIVE.TEX, item rarity odds)
    'silver': (2, 'box_equipment_silver', {2: 70, 3: 25, 4: 5}),
    'gold': (3, 'box_equipment_gold', {3: 80, 4: 20}),
    'diamond': (4, 'box_equipment_diamond', {4: 100}),
}
STARTER = ['silver', 'gold', 'diamond']
SLOT_NAMES = {0: 'Bat', 1: 'Batting Gloves', 2: 'Fielding Glove', 3: 'Cleats', 4: 'Catcher Mask', 5: 'Chest Protector',
              6: 'Leg Guards', 7: 'Elbow Guard', 8: 'Shin Guard', 9: 'Wrist Guard', 10: 'Compression Sleeve',
              11: 'Bat Grip', 12: 'Eyewear', 13: 'Ritual', 14: 'Socks', 15: 'Sliding Mitt'}
# RTTS mission ids that award an equipment package (FRONTEND/RTTS/MILESTONEREWARDS.XML, GAMEQUESTS.XML,
# AMATEURREWARDS.XML college offers; gold-tier colleges have equipmentType=1).
MISSION_BOX = {15545: 'silver', 17085: 'gold'}
for _m in (17084, 17713, 17083, 17712, 17689, 17716, 17692, 17711, 17690, 17715, 17691, 17714, 17082, 17706, 17081,
           17705, 17080, 17704, 17693, 17710, 17694, 17709, 17695, 17708, 17696, 17707):
    MISSION_BOX[_m] = 'silver'
for _m in (17078, 17701, 17079, 17700, 17072, 17699, 17697, 17703, 17698, 17702, 17688, 17717):
    MISSION_BOX[_m] = 'gold'


# ---- catalog and state -----------------------------------------------------------------------------------------------

def _catalog(romfs):
    rtts = romfs / 'FRONTEND' / 'RTTS'
    root = ET.parse(rtts / 'INVENTORYDATA.XML').getroot()
    eq = [i for i in root.iter('item') if i.get('type_id') == '2']
    by_rarity = {}
    for i in eq:
        by_rarity.setdefault(int(i.get('rarity_id', 0)), []).append(int(i.get('id')))
    base = {}
    q = ET.parse(rtts / 'INVQUANTITYDATA.XML').getroot()
    for i in q.iter('item'):
        base[int(i.get('id'))] = int(i.get('quantity', 1))
    names = {int(i.get('id')): i.get('name') for i in eq}
    items = {int(i.get('id')): dict(i.attrib) for i in eq}
    brands = {int(b.get('id')): b.get('name', '') for b in root.iter('brand')}
    slots = {int(s.get('id')): s.get('name', '') for s in root.iter('slot_type')}
    return by_rarity, base, names, items, brands, slots


BY_RARITY, BASE_QTY, NAMES, ITEMS, BRANDS, SLOTS = {}, {}, {}, {}, {}, {}   # the install's catalog, set by init()
STATE = None                        # server.State, set by init()


def init(romfs, state):
    """Called by server.start: reads the install's item catalog; a new player gets the starter packs."""
    global STATE, BY_RARITY, BASE_QTY, NAMES, ITEMS, BRANDS, SLOTS
    BY_RARITY, BASE_QTY, NAMES, ITEMS, BRANDS, SLOTS = _catalog(romfs)
    log(f'catalog: {sum(map(len, BY_RARITY.values()))} equipment items, {len(BASE_QTY)} owned at the start')
    STATE = state
    d = state.d
    d.setdefault('packs', [])       # [{id, box}]
    d.setdefault('gained', {})      # item id (str) -> extra quantity from packs
    d.setdefault('new', [])         # item ids flagged new until the game clears them
    d.setdefault('next_pack', PACK_ID_BASE + 1)
    d.setdefault('missions_granted', [])
    if not d.get('starter_given'):
        for box in STARTER:
            give(box, why='starter')
        d['starter_given'] = True
    state.save()


def give(box, why=''):
    d = STATE.d
    pid = d['next_pack']
    d['next_pack'] += 1
    d['packs'].append({'id': pid, 'box': box})
    STATE.save()
    log(f'pack {pid} ({box}) granted {why}')
    return pid


def attrs(**kv):
    return ' '.join(f'{k}={quoteattr(str(v))}' for k, v in kv.items())


# ---- going online --------------------------------------------------------------------------------------------------

# Scalars are XML attributes and bools must read "true". EULA accepted and no GDPR prompt send
# the login straight on (ol_OnlineEntry -> ol_RewardPopup) instead of the Code of Conduct.
@service('mlb_login.post_update')
def post_update(conn, p):
    return ('<player_profile player_id="1" player_name="OfflinePlayer"/>', 0, 'OK',
            'is_eula_accepted="true" is_gdpr="false" gdpr_response="1"')


@service('announcement.list')
def announcements(conn, p):
    return '<announcements/>'


@service('policy.view')
def policy_view(conn, p):
    return '<policy id="1" is_accepted="true"/>'


@service('policy.accept')
def policy_accept(conn, p):
    return ''


@service('telemetry.get_params')
def telemetry(conn, p):
    return '<param>{"enabled":false}</param>'


@service('player.get_link_status')
def link_status(conn, p):
    return '<AccountLink is_linked="false"/>'


@service('universal_profile.update_currency')
def currency(conn, p):
    return '<wallet currency="0"/>'


@service('inventory.client')
def item_templates(conn, p):
    # "Not modified": a response without an <info> child saves nothing (SaveItemTemplates returns early), so the game
    # keeps the install's INVENTORYDATA.XML. A full catalog would be saved as INV_DATA.DAT and win over that file
    # from then on; an error status shows a popup.
    return ''


# ---- inventory -------------------------------------------------------------------------------------------------------

def owned_items_xml():
    d = STATE.d
    qty = dict(BASE_QTY)
    for k, v in d['gained'].items():
        qty[int(k)] = qty.get(int(k), 0) + v
    new = set(d['new'])
    rows = [f'<item {attrs(id=i, quantity=q, is_new=1 if i in new else 0, gid=i)}/>' for i, q in sorted(qty.items())]
    return '<items>' + ''.join(rows) + '</items>'


@service('inventory.view', 'inventory.view2')
def view(conn, p):
    return owned_items_xml()


@service('inventory.clear_viewed_new')
def clear_new(conn, p):
    ids = {int(x) for x in re.findall(r'\d+', str(p.get('item_ids', '')))}
    STATE.d['new'] = [i for i in STATE.d['new'] if ids and i not in ids]
    STATE.save()
    return ''


@service('inventory.view_packs')
def view_packs(conn, p):
    rows = []
    for pk in STATE.d['packs']:
        rarity, art, _ = BOXES[pk['box']]
        row = attrs(id=pk['id'], type_id=PACK_TYPE, rarity_id=rarity, anim_index=0, quantity=1, is_care_package=1,
                    name=pk['box'].title() + ' Equipment Pack', texture_name=art)
        rows.append(f'<item {row}/>')
    conn.ctx['listed'] = [pk['id'] for pk in STATE.d['packs']]
    if p.get('care_packages_only'):         # the Packages screen itself asks this way (see content_latest)
        conn.ctx['packages_opened'] = True
    return '<items>' + ''.join(rows) + '</items>'


@service('inventory.open_pack')
def open_pack(conn, p):
    d = STATE.d
    want = int(p.get('item_id') or 0)
    pk = next((x for x in d['packs'] if x['id'] == want), None) or (d['packs'][0] if d['packs'] else None)
    if pk is None:
        return '', 1, 'no packs'
    if pk['id'] != want:
        log(f'open_pack asked for {want}; opening pack {pk["id"]} instead')
    _, _, odds = BOXES[pk['box']]
    pool_r = [r for r in odds if BY_RARITY.get(r)]
    rarity = random.choices(pool_r, weights=[odds[r] for r in pool_r])[0]
    item = random.choice(BY_RARITY[rarity])
    d['packs'].remove(pk)
    d['gained'][str(item)] = d['gained'].get(str(item), 0) + 1
    if item not in d['new']:
        d['new'].append(item)
    STATE.save()
    log(f'opened pack {pk["id"]} ({pk["box"]}): {NAMES.get(item)} [{item}] rarity {rarity}')
    # The reveal and its item details read the item's own fields from this reward (name, slot, brand, picture...), not
    # the catalog: send the catalog entry's attributes plus the reward fields.
    card = dict(ITEMS.get(item, {}))
    # The item details' second line is [ONLINE[TQ].brand_name]: the game fills brand_name (and
    # slot_type_name) itself for its own screens, a reward must carry them. "^r^" is the game's (R) markup.
    card['brand_name'] = BRANDS.get(int(card.get('brand_id', -1)), '')
    card['slot_type_name'] = SLOTS.get(int(card.get('slot_type_id', -1)), '')
    card['has_item'] = 1
    card.update(id=item, type_id=2, rarity_id=rarity, anim_index=0, quantity=1, position=0, role=0,
                marketplace_best_buy=0, quick_sell_value=0, no_sell=1, is_new=1)
    return '<items>' + f'<item {attrs(**card)}/>' + '</items>'


# ---- missions: where RTTS awards packs ------------------------------------------------------------------------------
# RTTS queues earned package mission ids in RAM: 15545 every 10 RTTS games (Standard), 17085 for
# challenge/boss rewards, a college's equipment id for its offer. Whichever of mlb_game.view_post_game,
# mlb_game.view_post_game2 or inventory.check_for_rewards succeeds next carries them as client_mission_ids
# ("15545,17085", one entry per award) and the client then CLEARS the queue whatever the answer says. So every one of
# the three must grant, one pack per entry, before answering.
COLLEGE_IDS = {m for m in MISSION_BOX if m not in (15545, 17085)}


def _mission_ids(text):
    return [int(x) for x in re.findall(r'\d+', str(text or '')) if x != '4294967295']


def _grant_missions(ids, source):
    d = STATE.d
    for m in ids:
        box = MISSION_BOX.get(m)
        if box:
            give(box, why=f'for mission {m} ({source})')
            if m in COLLEGE_IDS and m not in d['missions_granted']:
                d['missions_granted'].append(m)
        elif m:
            log(f'mission {m} ({source}): not an equipment package mission, nothing granted')
    STATE.save()


@service('mission.trigger')
def mission_trigger(conn, p):
    _grant_missions([int(p.get('mission_id') or 0)], 'mission.trigger')
    return ''


@service('mlb_game.view_post_game', 'mlb_game.view_post_game2')
def view_post_game(conn, p):
    conn.ctx['post_game_at'] = time.monotonic()     # the post-game screen asks every content type next (content_latest)
    return post_game(conn, p)


@service('inventory.check_for_rewards')
def post_game(conn, p):
    ids = _mission_ids(p.get('client_mission_ids'))
    if ids:
        log(f'client_mission_ids {ids}')
    _grant_missions(ids, 'post game / rewards check')
    return ''        # an empty answer: no reward popup; the packs are in inventory.view_packs from now on


@service('mission.reward_info')
def mission_reward_info(conn, p):
    # The screens read only mission[i].texture_name, by position, in the order of the requested mission_ids.
    ids = _mission_ids(p.get('mission_ids'))
    rows = [f'<mission {attrs(id=m, texture_name=BOXES[MISSION_BOX.get(m, "silver")][1])}/>' for m in ids]
    return '<missions_reward_info>' + ''.join(rows) + '</missions_reward_info>'


@service('mission.is_complete')
def mission_is_complete(conn, p):
    # A college offer's pack is given once: "true" (exactly) for those already granted, so the client stops queuing it.
    done = set(STATE.d['missions_granted'])
    rows = [f'<mission {attrs(id=m, is_complete="true" if m in done else "false")}/>'
            for m in _mission_ids(p.get('mission_ids'))]
    return '<missions_progress>' + ''.join(rows) + '</missions_progress>'


@service('mlb_login.check_daily')
def check_daily(conn, p):
    # ol_DailyLogin: neither first nor daily login -> the screen exits without a reward popup
    return '<login_data is_first_login="false" is_daily_login="false"/>'


# content_update.latest: the game decides from its own local <user>_<TYPE>.zip, not from the server; an empty answer
# keeps a local copy and leaves a missing one missing.
#
# It is also how the server sees the game come back to the main menu from Road to the Show: each login asks once about
# every content type, and RTTS is asked about again on the way out of the mode. That moment matters. Once Packages was
# opened, the game remembers Road to the Show as the place to return to when its online session ends, and the online
# modes of the main menu (Diamond Dynasty and the rest), which this server cannot serve, end it with a failed login.
# Back on the main menu that return leads nowhere: the game stays on an empty screen. So when the game is back on the
# main menu after Packages was opened, the server hangs up. A connection lost there is something the game handles
# well: one message, the title screen, and a new login from there.
#
# The end of every Road to the Show game asks about every content type too, RTTS included, within a second of
# mlb_game.view_post_game, while the progress screen (PostGameProgression) is up. A connection lost there is NOT
# handled: the game shows "lost connection to Road to the Show online services" and stays on the progress screen for
# good (seen on 1.0.20, second game of a session after Packages was opened). So no hang-up just after a post game.
BACK_ON_THE_MENU = 2.0      # seconds after the question, so the menu is up when the connection goes
AFTER_POST_GAME = 15.0      # seconds after mlb_game.view_post_game during which an RTTS question is the post game's


@service('content_update.latest')
def content_latest(conn, p):
    kind = p.get('content_update_type')
    asked = conn.ctx.setdefault('content_asked', set())
    if kind == 'RTTS' and kind in asked and conn.ctx.get('packages_opened'):
        if time.monotonic() - conn.ctx.get('post_game_at', float('-inf')) < AFTER_POST_GAME:
            log(f'{conn.tag()} RTTS content asked by the post-game screen: staying connected')
        else:
            del conn.ctx['packages_opened']
            threading.Timer(BACK_ON_THE_MENU, conn.hang_up, ['back on the main menu after Packages was opened']).start()
    asked.add(kind)
    return ''


@service('content_update.latest_retirement',
         'player.get_friend_list', 'player.get_block_list', 'high_priority_news_updates.view')
def empty_ok(conn, p):
    return ''


# ---- main menu tiles ------------------------------------------------------------------------------------------------
# GameModesMain's top area shows the stored dynamic_tiles response once online: an empty answer
# leaves it black. gmm/Tiles elements, fields as attributes: box_type 2 = wide 1200x440, 1 = square 440x440;
# sub_box_type 0 = the picture alone; background_texture = a texture name (LIVE.TEX); destination_index must be on
# every tile (absent = Diamond Dynasty): 19 = move to the Road to the Show mode, -1 = nothing. mark_viewed replaces the
# stored tiles too, so it gets the same answer.
MENU_TILES = (
    '<gmm>'
    '<Tiles id="1" box_type="2" sub_box_type="0" destination_index="19" background_texture="ann_feature_rtts" '
    'r="0" g="0" b="0" main_title="Road to the Show" main_desc="Earn equipment packages on your way to the Show."/>'
    '<Tiles id="2" box_type="1" sub_box_type="0" destination_index="-1" background_texture="box_equipment_gold" '
    'r="0" g="0" b="0" main_title="Equipment Packages" main_desc="Open them in RTTS: Equipment, Go to Packages."/>'
    '</gmm>')


@service('dynamic_tiles.view', 'dynamic_tiles.view_mobile', 'dynamic_tiles.mark_viewed')
def menu_tiles(conn, p):
    return MENU_TILES
