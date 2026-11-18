// fastball offline packages (packages.c): Road to the Show's Packages through a server on this PC, when
// MLB_OFFLINE_PACKAGES=1. Off by default.
#pragma once

void packages_start(void);    // boot, before the game's modules load: starts the server and takes over nn::socket
void packages_loaded(void);   // boot, once they are loaded and before any game code runs: the server's certificate
int packages_on(void);        // 1 while the game is told it is online, with the local server behind it

