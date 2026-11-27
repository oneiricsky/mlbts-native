// The trainer's hooks into the game (patch sets trainer_contact and trainer_pitch, tools/data/patches-1.0.20.txt).
#pragma once

void trainer_hooks_apply(void);      // boot, after rt_patches_init and before hostfn_seal: registers the host functions
int trainer_hooks_available(void);   // 1 when this build's generated code has the patch sets and they are registered
void trainer_hooks_switch(int on);   // any thread, while the game runs
