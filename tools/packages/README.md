# Road to the Show packages, offline

In Road to the Show the player earns equipment packs ("Packages") and opens them for bats, gloves and the rest. The
game does all of that through its online service, so offline the Packages screen never opens and nothing is ever
awarded. This folder is a small stand-in for that service which runs on the player's own PC. With it the game's own
Packages screen, pack opening and rewards work without a connection.

It is an option of the setup ("Add Road to the Show packages") and a button on its launcher screen, or
`--packages` / `--no-packages` on the setup's command line. It is off unless the player turns it on.

## What the player gets

- Three packs to start with (Standard, Gold, Diamond).
- The packs Road to the Show awards as the player goes: a Standard pack every ten games, and the packs of challenges,
  boss rewards and college offers (the game's own `MILESTONEREWARDS.XML`, `GAMEQUESTS.XML`, `AMATEURREWARDS.XML`).
- Opening a pack gives one equipment item, drawn by rarity: Standard 70 % Silver, 25 % Gold, 5 % Diamond; Gold 80 %
  Gold, 20 % Diamond; Diamond always Diamond.
- The equipment itself comes from [`tools/equipment`](../equipment/README.md), which the setup adds with this option.
  With packages on, none of it is owned at the start: the packs are how the player gets it.

What the player has (packs, the items they gave) is kept in `profile/offline-packages/state.json` in the install
folder and survives updates, repairs and turning the option off and on.

## How it works

The setup copies this folder to `<install folder>/packages`, together with the few files of its own Python that the
server needs (about 20 MB), and writes `MLB_OFFLINE_PACKAGES=1` into `mlb.cfg`. Then, each time the game starts
(`runtime/mlb/packages.c`):

1. The runtime starts `server.py` as a hidden child process. The server listens on `127.0.0.1` on a free port and
   says which. It ends when the game ends, however the game ends.
2. The game's network calls (`nn::socket`) are served on real sockets, with two rules: only The Show's server names
   resolve, all of them to `127.0.0.1`, and a connection to any other address is refused. Nothing leaves the PC, and
   the server itself connects to nothing.
3. The game is told that a network and a linked account are there, so it logs in. The account is made up; nothing is
   sent to Nintendo or to anyone else.
4. The game checks the server it logs in to against a list of certificates it trusts. That list is replaced, in the
   running game's memory only, by one certificate that `cert.py` made on this PC the first time. The game's check
   itself is not weakened or skipped. No certificate or key is shipped: every PC makes its own, the key never leaves
   `profile/offline-packages`, and only this game is told to trust it. Windows' own certificate store is not touched.
5. `login.py` answers the game's login, `services.py` its requests: the inventory, the packs, opening one.

If anything is missing or goes wrong at the start (no server, no Python, a game version whose certificate list is not
found), the runtime logs one line in `logs/mlb.log` and the game runs offline exactly as without the option. The
server's own log is `logs/packages-server.log`.

With the option off nothing here runs: no server is started, no network function is replaced and nothing in the game's
memory is changed.

## What it does not do, and what the player will notice

Only Road to the Show's Packages are served. The game believes it is online, though, and that shows in three places:

- **The online modes on the main menu** (Diamond Dynasty and the others) can be chosen, but there is nothing behind
  them. The game reports "Roster Download Failed", then "Login Failed", and returns to the main menu. It is then
  logged out; opening Packages in Road to the Show logs it in again by itself.
- **Leaving Road to the Show after Packages was opened.** Back on the main menu the game shows "Your connection to The
  Show Online has been lost" once and goes to its title screen; press a button and it logs in again. The server does
  this on purpose (`services.py`, `content_latest`). Once Packages was opened, the game remembers Road to the Show as
  the place to return to when its online session ends, and an online mode failing from the main menu would then leave
  it on an empty screen that only closing the game gets out of. A connection lost on the main menu is the one case
  the game recovers from by itself, so that is where the session is ended. Without Packages having been opened, the
  message does not come.
- **"The Show Shop" and "Community Marketplace" on the Packages screen** open empty. Stubs and buying packs are not
  there: packs only come from playing.

If the server stops while the game sits on the main menu, the game shows the same message and goes back to its title
screen, offline. A connection lost in the middle of Road to the Show is not recovered: on the progress screen after a
game it shows "lost connection to Road to the Show online services" and stays there. The end of every game asks the
same question as leaving the mode, so the server tells the two apart by the post-game request just before it.

This cannot be used to play online or to reach the real servers. No game data, key or certificate of the game is in
this folder. The protocol code was written from the game's behaviour on the player's own files; addresses in comments
refer to the 1.0.20 main module.

## Game versions

Checked on 1.0.20. On 1.0.15 it has not been run: the two places the runtime changes in the game's memory are found by
their shape, not by fixed addresses, and when they are not found the game stays offline as before; the protocol is
expected to be the same but that is not verified.

## By hand

```
python -I tools/packages/server.py --check --game <install folder>     # does the server work on this PC?
python -I tools/packages/server.py --game <install folder>             # run it in the foreground
python -I tools/packages/tests/test_packages.py                        # the tests: a client here plays the game's side
```

`MLB_PACKAGES_PYTHON` (environment or `mlb.cfg`) names another `python.exe` for the runtime to start the server
with; the setup sets it for an install made from a repository checkout, which has no Python to copy.

Standard library only: TLS and XML from Python, and the certificate is made with plain integer arithmetic (`cert.py`).

## Files

| File | |
| --- | --- |
| `server.py` | the listener, the connections, the player's state |
| `cert.py` | this PC's certificate and key (RSA 2048, SHA-256), made once |
| `codec.py`, `server_msgs.py`, `rpc.py` | the game's messages: framing, the login, requests and responses |
| `login.py`, `handlers.py`, `services.py`, `profile_state.py` | the answers |
| `core.py` | the log and the handler registry |
| `tests/` | 17 tests, no game needed |
