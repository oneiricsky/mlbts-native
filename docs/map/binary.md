# The game binary (Switch 1.0.20)

The port recompiles the game's ARM64 code to C (`recomp/gen.py`). Each recompiled function is `void f_<address>(Cpu *c)`, and `<address>` is its virtual address in the original module (`main` at `0x7000000000`, `sdk` at `0x7004c00000`). This page holds counts, address ranges and the functions the repo already names. The full per-function list (address, size, direct callees, caller count, indirect-branch count, SDK symbol name) is derived from game code, so it is built locally into `work/map/index/` by `tools/map_generated.py` and `tools/map_binary.py` and is not committed. `rtld` (8.5 KB) is not recompiled.

## Totals

| Module | Functions | Text range | Generated lines | Chunks |
|---|---|---|---|---|
| main | 94991 | 0x7000000000 - 0x7001c22800 | 8516488 | 198 |
| sdk | 40069 | 0x7004c00000 - 0x700524e230 | 2004597 | 40 |

Total 135060 functions; 71191 have no direct caller (called through tables, `rt_dispatch`, or exported); 31920 contain at least one indirect branch (`rt_dispatch`).

## Independent check against the original machine code

`tools/map_binary.py` scans the original `.text` for every direct `bl` and requires each target to be an indexed function.

| Module | bl instructions | distinct targets | not indexed | named symbols | not indexed |
|---|---|---|---|---|---|
| main | 541821 | 45361 | 0 | 39 | 0 |
| sdk | 74597 | 9790 | 0 | 19260 | 0 |

## Address ranges by generated chunk

| Chunk | Functions | First address | Last address | Generated lines |
|---|---|---|---|---|
| `main/main_0000.c` | 585 | 0x7000000000 | 0x700002d664 | 53488 |
| `main/main_0001.c` | 218 | 0x700002d7f8 | 0x700005aaa0 | 52167 |
| `main/main_0002.c` | 165 | 0x700005ad7c | 0x700007cf00 | 48459 |
| `main/main_0003.c` | 1 | 0x70000801b0 | 0x70000801b0 | 8238 |
| `main/main_0004.c` | 2 | 0x7000087700 | 0x7000087720 | 25 |
| `main/main_0005.c` | 1 | 0x7000087740 | 0x7000087740 | 7424 |
| `main/main_0006.c` | 1098 | 0x700008dfc0 | 0x70000bb414 | 56187 |
| `main/main_0007.c` | 420 | 0x70000bb41c | 0x70000e8200 | 52509 |
| `main/main_0008.c` | 560 | 0x70000e8358 | 0x7000116610 | 54236 |
| `main/main_0009.c` | 234 | 0x7000116620 | 0x7000143184 | 50546 |
| `main/main_0010.c` | 1 | 0x70001431e0 | 0x70001431e0 | 7051 |
| `main/main_0011.c` | 308 | 0x70001496a0 | 0x7000175b0c | 51447 |
| `main/main_0012.c` | 305 | 0x70001761a4 | 0x70001a3514 | 51882 |
| `main/main_0013.c` | 366 | 0x70001a3870 | 0x70001cf860 | 50957 |
| `main/main_0014.c` | 129 | 0x70001cfb64 | 0x70001ecb08 | 32920 |
| `main/main_0015.c` | 1 | 0x70001ecb90 | 0x70001ecb90 | 9349 |
| `main/main_0016.c` | 648 | 0x70001f5000 | 0x7000221d3c | 54827 |
| `main/main_0017.c` | 324 | 0x70002220d0 | 0x700024ede0 | 51587 |
| `main/main_0018.c` | 241 | 0x700024efa0 | 0x700026b274 | 32882 |
| `main/main_0019.c` | 1 | 0x700026b5e0 | 0x700026b5e0 | 5520 |
| `main/main_0020.c` | 444 | 0x7000270724 | 0x700029d5d8 | 51584 |
| `main/main_0021.c` | 95 | 0x700029d6b0 | 0x70002aef88 | 20470 |
| `main/main_0022.c` | 1 | 0x70002af6c0 | 0x70002af6c0 | 4787 |
| `main/main_0023.c` | 205 | 0x70002b3dc8 | 0x70002df244 | 48540 |
| `main/main_0024.c` | 333 | 0x70002df308 | 0x700030c0e0 | 50791 |
| `main/main_0025.c` | 364 | 0x700030c1c8 | 0x700032fb50 | 40988 |
| `main/main_0026.c` | 1 | 0x700032fd94 | 0x700032fd94 | 8427 |
| `main/main_0027.c` | 605 | 0x7000333f54 | 0x7000360f2c | 52941 |
| `main/main_0028.c` | 209 | 0x7000361010 | 0x700038e010 | 50825 |
| `main/main_0029.c` | 419 | 0x700038e04c | 0x70003baf0c | 52047 |
| `main/main_0030.c` | 563 | 0x70003baf6c | 0x70003e83fc | 53202 |
| `main/main_0031.c` | 686 | 0x70003e8414 | 0x7000415ebc | 54403 |
| `main/main_0032.c` | 395 | 0x70004160c0 | 0x7000442360 | 53487 |
| `main/main_0033.c` | 739 | 0x7000442f50 | 0x70004707bc | 54320 |
| `main/main_0034.c` | 396 | 0x70004708c0 | 0x700049c4e0 | 50648 |
| `main/main_0035.c` | 519 | 0x700049ca7c | 0x70004c9350 | 52637 |
| `main/main_0036.c` | 720 | 0x70004c9480 | 0x70004f5444 | 52550 |
| `main/main_0037.c` | 366 | 0x70004f5480 | 0x700050e180 | 29873 |
| `main/main_0038.c` | 1 | 0x700050e340 | 0x700050e340 | 6516 |
| `main/main_0039.c` | 385 | 0x7000514050 | 0x7000541308 | 53276 |
| `main/main_0040.c` | 200 | 0x70005413d0 | 0x700054b114 | 12308 |
| `main/main_0041.c` | 1 | 0x700054b390 | 0x700054b390 | 6527 |
| `main/main_0042.c` | 625 | 0x7000551970 | 0x700057f420 | 54471 |
| `main/main_0043.c` | 494 | 0x700057f740 | 0x70005ad300 | 54065 |
| `main/main_0044.c` | 428 | 0x70005ad670 | 0x70005da3e0 | 53344 |
| `main/main_0045.c` | 38 | 0x70005da810 | 0x70005dedd0 | 5195 |
| `main/main_0046.c` | 1 | 0x70005dee24 | 0x70005dee24 | 7744 |
| `main/main_0047.c` | 648 | 0x70005e6710 | 0x7000614230 | 55056 |
| `main/main_0048.c` | 550 | 0x70006142a0 | 0x7000641470 | 53935 |
| `main/main_0049.c` | 557 | 0x7000641520 | 0x700066e35c | 53122 |
| `main/main_0050.c` | 251 | 0x700066e400 | 0x7000692524 | 42272 |
| `main/main_0051.c` | 1 | 0x7000692550 | 0x7000692550 | 8432 |
| `main/main_0052.c` | 687 | 0x70006998b0 | 0x70006c5f0c | 54145 |
| `main/main_0053.c` | 772 | 0x70006c5f40 | 0x70006f3644 | 54761 |
| `main/main_0054.c` | 360 | 0x70006f37ec | 0x7000721de8 | 53631 |
| `main/main_0055.c` | 308 | 0x7000721e30 | 0x700074d290 | 52700 |
| `main/main_0056.c` | 599 | 0x700074eba0 | 0x700077ccf0 | 55355 |
| `main/main_0057.c` | 364 | 0x700077cd80 | 0x70007ab4b4 | 54334 |
| `main/main_0058.c` | 822 | 0x70007ab5f0 | 0x70007d94c0 | 55178 |
| `main/main_0059.c` | 566 | 0x70007d9640 | 0x7000806a94 | 54821 |
| `main/main_0060.c` | 288 | 0x7000806d28 | 0x700083431c | 52612 |
| `main/main_0061.c` | 300 | 0x700083435c | 0x7000860a30 | 51633 |
| `main/main_0062.c` | 679 | 0x7000860aa0 | 0x700088d720 | 54602 |
| `main/main_0063.c` | 652 | 0x700088da10 | 0x70008bb540 | 54755 |
| `main/main_0064.c` | 612 | 0x70008bb5e0 | 0x70008e9764 | 54515 |
| `main/main_0065.c` | 549 | 0x70008e9780 | 0x70009173bc | 53613 |
| `main/main_0066.c` | 933 | 0x70009174e0 | 0x7000944e50 | 55260 |
| `main/main_0067.c` | 443 | 0x7000945020 | 0x700097044c | 54225 |
| `main/main_0068.c` | 117 | 0x7000972e74 | 0x7000989930 | 28906 |
| `main/main_0069.c` | 1 | 0x700098c530 | 0x700098c530 | 11826 |
| `main/main_0070.c` | 1300 | 0x7000996f70 | 0x70009c3a20 | 56487 |
| `main/main_0071.c` | 576 | 0x70009c3a30 | 0x70009f1294 | 53928 |
| `main/main_0072.c` | 421 | 0x70009f129c | 0x7000a1f030 | 53652 |
| `main/main_0073.c` | 394 | 0x7000a1f270 | 0x7000a4a7c0 | 54112 |
| `main/main_0074.c` | 371 | 0x7000a4a81c | 0x7000a780c0 | 53945 |
| `main/main_0075.c` | 740 | 0x7000a781d0 | 0x7000aa594c | 55244 |
| `main/main_0076.c` | 881 | 0x7000aa5ed4 | 0x7000ad2ff0 | 54477 |
| `main/main_0077.c` | 1369 | 0x7000ad336c | 0x7000b00890 | 56555 |
| `main/main_0078.c` | 988 | 0x7000b00918 | 0x7000b2e1a8 | 54959 |
| `main/main_0079.c` | 913 | 0x7000b2e1c4 | 0x7000b5bdc0 | 54867 |
| `main/main_0080.c` | 1088 | 0x7000b5bdc4 | 0x7000b89c80 | 55952 |
| `main/main_0081.c` | 745 | 0x7000b89c9c | 0x7000bb7210 | 54235 |
| `main/main_0082.c` | 853 | 0x7000bb73b0 | 0x7000be3fd8 | 53832 |
| `main/main_0083.c` | 760 | 0x7000be3fdc | 0x7000c118f8 | 54043 |
| `main/main_0084.c` | 1036 | 0x7000c118fc | 0x7000c3f2e0 | 55432 |
| `main/main_0085.c` | 772 | 0x7000c3f320 | 0x7000c6cf68 | 54288 |
| `main/main_0086.c` | 914 | 0x7000c6cf80 | 0x7000c9a6f4 | 54843 |
| `main/main_0087.c` | 982 | 0x7000c9a718 | 0x7000cc72a8 | 54486 |
| `main/main_0088.c` | 616 | 0x7000cc72d0 | 0x7000cf4184 | 52977 |
| `main/main_0089.c` | 670 | 0x7000cf43ac | 0x7000d21ce8 | 54194 |
| `main/main_0090.c` | 486 | 0x7000d21d4c | 0x7000d4e318 | 52288 |
| `main/main_0091.c` | 925 | 0x7000d4e560 | 0x7000d7a9e8 | 53888 |
| `main/main_0092.c` | 625 | 0x7000d7aa24 | 0x7000da7150 | 52599 |
| `main/main_0093.c` | 717 | 0x7000da7160 | 0x7000dd33ec | 54226 |
| `main/main_0094.c` | 744 | 0x7000dd36f0 | 0x7000df9068 | 45874 |
| `main/main_0095.c` | 1 | 0x7000df9180 | 0x7000df9180 | 7217 |
| `main/main_0096.c` | 16 | 0x7000dffbf0 | 0x7000e077e0 | 8529 |
| `main/main_0097.c` | 1 | 0x7000e07820 | 0x7000e07820 | 8700 |
| `main/main_0098.c` | 2 | 0x7000e0f820 | 0x7000e0f980 | 215 |
| `main/main_0099.c` | 1 | 0x7000e0fb10 | 0x7000e0fb10 | 21030 |
| `main/main_0100.c` | 595 | 0x7000e232a0 | 0x7000e50248 | 52904 |
| `main/main_0101.c` | 56 | 0x7000e50264 | 0x7000e59ae0 | 10866 |
| `main/main_0102.c` | 1 | 0x7000e59c50 | 0x7000e59c50 | 5856 |
| `main/main_0103.c` | 133 | 0x7000e5efbc | 0x7000e8a974 | 50394 |
| `main/main_0104.c` | 395 | 0x7000e8c220 | 0x7000eb8850 | 51765 |
| `main/main_0105.c` | 430 | 0x7000eb8e60 | 0x7000ee52d0 | 51666 |
| `main/main_0106.c` | 39 | 0x7000ee538c | 0x7000eebf1c | 7377 |
| `main/main_0107.c` | 1 | 0x7000eebf38 | 0x7000eebf38 | 14188 |
| `main/main_0108.c` | 529 | 0x7000ef8760 | 0x7000f25220 | 52472 |
| `main/main_0109.c` | 658 | 0x7000f252e0 | 0x7000f4a750 | 45954 |
| `main/main_0110.c` | 1 | 0x7000f4b784 | 0x7000f4b784 | 4773 |
| `main/main_0111.c` | 337 | 0x7000f4faf4 | 0x7000f7d308 | 51207 |
| `main/main_0112.c` | 516 | 0x7000f7d55c | 0x7000fab34c | 53664 |
| `main/main_0113.c` | 128 | 0x7000fab380 | 0x7000fd9c34 | 50480 |
| `main/main_0114.c` | 1 | 0x7000fd9ca4 | 0x7000fd9ca4 | 52 |
| `main/main_0115.c` | 1 | 0x7000fd9d44 | 0x7000fd9d44 | 7517 |
| `main/main_0116.c` | 507 | 0x7000fe0cd0 | 0x700100e8b0 | 53462 |
| `main/main_0117.c` | 86 | 0x700100e958 | 0x700102b80c | 31379 |
| `main/main_0118.c` | 1 | 0x700102b87c | 0x700102b87c | 8574 |
| `main/main_0119.c` | 637 | 0x7001033850 | 0x70010609dc | 54127 |
| `main/main_0120.c` | 617 | 0x7001060b3c | 0x700108dd48 | 53945 |
| `main/main_0121.c` | 688 | 0x700108debc | 0x70010b275c | 44822 |
| `main/main_0122.c` | 1 | 0x70010b2780 | 0x70010b2780 | 9657 |
| `main/main_0123.c` | 292 | 0x70010bb0b8 | 0x70010e72cc | 50169 |
| `main/main_0124.c` | 1572 | 0x70010e735c | 0x7001114cc0 | 59010 |
| `main/main_0125.c` | 946 | 0x7001114d9c | 0x700113bea0 | 49062 |
| `main/main_0126.c` | 1 | 0x700113bf70 | 0x700113bf70 | 10777 |
| `main/main_0127.c` | 365 | 0x7001146780 | 0x70011746c0 | 52785 |
| `main/main_0128.c` | 355 | 0x7001174710 | 0x70011a2900 | 52645 |
| `main/main_0129.c` | 195 | 0x70011a2940 | 0x70011b7484 | 24102 |
| `main/main_0130.c` | 1 | 0x70011b7690 | 0x70011b7690 | 4550 |
| `main/main_0131.c` | 373 | 0x70011bb7f0 | 0x70011e89c0 | 52812 |
| `main/main_0132.c` | 791 | 0x70011e8bd0 | 0x7001217130 | 55673 |
| `main/main_0133.c` | 661 | 0x7001217178 | 0x7001245740 | 54773 |
| `main/main_0134.c` | 368 | 0x70012457c0 | 0x700125ce70 | 27572 |
| `main/main_0135.c` | 1 | 0x700125cf24 | 0x700125cf24 | 6743 |
| `main/main_0136.c` | 552 | 0x7001263240 | 0x70012918bc | 54620 |
| `main/main_0137.c` | 547 | 0x70012918f0 | 0x70012bfea0 | 54667 |
| `main/main_0138.c` | 302 | 0x70012bff70 | 0x70012ec9b8 | 50805 |
| `main/main_0139.c` | 407 | 0x70012ecad0 | 0x700131ab14 | 53600 |
| `main/main_0140.c` | 999 | 0x700131ab20 | 0x7001347190 | 54969 |
| `main/main_0141.c` | 731 | 0x7001347800 | 0x7001375450 | 54949 |
| `main/main_0142.c` | 604 | 0x7001375528 | 0x70013a21c0 | 52797 |
| `main/main_0143.c` | 368 | 0x70013a28c0 | 0x70013cf5c4 | 50652 |
| `main/main_0144.c` | 394 | 0x70013cf7d4 | 0x70013fb720 | 50870 |
| `main/main_0145.c` | 310 | 0x70013fc260 | 0x7001428510 | 51097 |
| `main/main_0146.c` | 460 | 0x70014285d8 | 0x70014552d0 | 52996 |
| `main/main_0147.c` | 847 | 0x7001455bd8 | 0x7001482f90 | 54922 |
| `main/main_0148.c` | 536 | 0x7001482fb8 | 0x70014b05b0 | 52203 |
| `main/main_0149.c` | 786 | 0x70014b0650 | 0x70014de824 | 53723 |
| `main/main_0150.c` | 1309 | 0x70014de890 | 0x700150d0c0 | 57863 |
| `main/main_0151.c` | 1145 | 0x700150d0d0 | 0x700153b35c | 56920 |
| `main/main_0152.c` | 688 | 0x700153b364 | 0x7001568ef0 | 55323 |
| `main/main_0153.c` | 643 | 0x70015690b0 | 0x70015972d0 | 53740 |
| `main/main_0154.c` | 820 | 0x7001597480 | 0x70015c4c80 | 54151 |
| `main/main_0155.c` | 536 | 0x70015c4f20 | 0x70015f35a0 | 53522 |
| `main/main_0156.c` | 691 | 0x70015f35b0 | 0x7001620fe0 | 54953 |
| `main/main_0157.c` | 483 | 0x7001621010 | 0x700164ed20 | 53678 |
| `main/main_0158.c` | 431 | 0x700164ed30 | 0x7001679d18 | 52306 |
| `main/main_0159.c` | 1 | 0x700167bb7c | 0x700167bb7c | 4685 |
| `main/main_0160.c` | 326 | 0x700167fdd4 | 0x70016acb80 | 52858 |
| `main/main_0161.c` | 317 | 0x70016ad4d0 | 0x70016d81ac | 49493 |
| `main/main_0162.c` | 356 | 0x70016d86e0 | 0x700170690c | 53503 |
| `main/main_0163.c` | 382 | 0x7001706920 | 0x7001734550 | 52941 |
| `main/main_0164.c` | 435 | 0x7001734754 | 0x70017624f0 | 53438 |
| `main/main_0165.c` | 527 | 0x7001762500 | 0x700178fb24 | 53350 |
| `main/main_0166.c` | 681 | 0x700178fb30 | 0x70017bd240 | 54631 |
| `main/main_0167.c` | 2566 | 0x70017bd2b0 | 0x70017ea400 | 61449 |
| `main/main_0168.c` | 3000 | 0x70017ea410 | 0x7001807628 | 45314 |
| `main/main_0169.c` | 2014 | 0x700180762c | 0x7001834f40 | 59725 |
| `main/main_0170.c` | 2164 | 0x7001835020 | 0x7001861e64 | 60654 |
| `main/main_0171.c` | 909 | 0x7001861fd4 | 0x700188e988 | 54220 |
| `main/main_0172.c` | 765 | 0x700188e990 | 0x70018bc410 | 54855 |
| `main/main_0173.c` | 507 | 0x70018bc590 | 0x70018ea3f0 | 54859 |
| `main/main_0174.c` | 190 | 0x70018ea820 | 0x7001918950 | 52274 |
| `main/main_0175.c` | 260 | 0x7001918c20 | 0x70019468fc | 52830 |
| `main/main_0176.c` | 160 | 0x7001946910 | 0x70019642c0 | 34331 |
| `main/main_0177.c` | 1 | 0x7001964690 | 0x7001964690 | 6814 |
| `main/main_0178.c` | 322 | 0x700196a80c | 0x7001998510 | 53439 |
| `main/main_0179.c` | 390 | 0x7001998680 | 0x70019c5818 | 52941 |
| `main/main_0180.c` | 426 | 0x70019c5b30 | 0x70019f3270 | 53210 |
| `main/main_0181.c` | 529 | 0x70019f33e0 | 0x7001a21f6c | 55078 |
| `main/main_0182.c` | 420 | 0x7001a21f88 | 0x7001a50470 | 54320 |
| `main/main_0183.c` | 479 | 0x7001a504d0 | 0x7001a7d4f0 | 53688 |
| `main/main_0184.c` | 742 | 0x7001a7d554 | 0x7001aa9d80 | 54872 |
| `main/main_0185.c` | 377 | 0x7001aa9f90 | 0x7001ad6bc0 | 52463 |
| `main/main_0186.c` | 323 | 0x7001ad6d10 | 0x7001b040a0 | 52257 |
| `main/main_0187.c` | 61 | 0x7001b04320 | 0x7001b13540 | 17401 |
| `main/main_0188.c` | 1 | 0x7001b13890 | 0x7001b13890 | 8159 |
| `main/main_0189.c` | 491 | 0x7001b1b030 | 0x7001b47bb8 | 52587 |
| `main/main_0190.c` | 483 | 0x7001b47c80 | 0x7001b74b94 | 51650 |
| `main/main_0191.c` | 281 | 0x7001b74bd0 | 0x7001b9fcd0 | 50069 |
| `main/main_0192.c` | 182 | 0x7001ba0600 | 0x7001bcc780 | 52492 |
| `main/main_0193.c` | 132 | 0x7001bccc10 | 0x7001bec310 | 37363 |
| `main/main_0194.c` | 1 | 0x7001bec3d0 | 0x7001bec3d0 | 5383 |
| `main/main_0195.c` | 277 | 0x7001bf12d8 | 0x7001c0c570 | 31769 |
| `main/main_0196.c` | 1 | 0x7001c0cc50 | 0x7001c0cc50 | 7639 |
| `main/main_0197.c` | 837 | 0x7001c14030 | 0x7001c227f0 | 19954 |
| `sdk/sdk_0000.c` | 610 | 0x7004c00000 | 0x7004c2d530 | 52816 |
| `sdk/sdk_0001.c` | 463 | 0x7004c2d560 | 0x7004c59a10 | 50963 |
| `sdk/sdk_0002.c` | 606 | 0x7004c59bf0 | 0x7004c86ab0 | 54102 |
| `sdk/sdk_0003.c` | 1068 | 0x7004c86ca0 | 0x7004cb4750 | 56485 |
| `sdk/sdk_0004.c` | 976 | 0x7004cb49b0 | 0x7004ce2d30 | 56124 |
| `sdk/sdk_0005.c` | 1017 | 0x7004ce2e10 | 0x7004d11340 | 56688 |
| `sdk/sdk_0006.c` | 757 | 0x7004d113b0 | 0x7004d3e5d0 | 57036 |
| `sdk/sdk_0007.c` | 1295 | 0x7004d3e608 | 0x7004d6c8a0 | 57654 |
| `sdk/sdk_0008.c` | 1540 | 0x7004d6c8b0 | 0x7004d9a47c | 57745 |
| `sdk/sdk_0009.c` | 1644 | 0x7004d9a4dc | 0x7004dc7dd0 | 58140 |
| `sdk/sdk_0010.c` | 1661 | 0x7004dc7f40 | 0x7004df4690 | 57396 |
| `sdk/sdk_0011.c` | 838 | 0x7004df4da0 | 0x7004e21940 | 52629 |
| `sdk/sdk_0012.c` | 867 | 0x7004e21950 | 0x7004e4e210 | 53857 |
| `sdk/sdk_0013.c` | 524 | 0x7004e4e600 | 0x7004e7c910 | 53861 |
| `sdk/sdk_0014.c` | 223 | 0x7004e7c9a0 | 0x7004ea98f0 | 50936 |
| `sdk/sdk_0015.c` | 457 | 0x7004ea9de0 | 0x7004ed7030 | 52970 |
| `sdk/sdk_0016.c` | 246 | 0x7004ed7050 | 0x7004f03d90 | 51168 |
| `sdk/sdk_0017.c` | 198 | 0x7004f03da0 | 0x7004f317c0 | 52181 |
| `sdk/sdk_0018.c` | 733 | 0x7004f31830 | 0x7004f5f308 | 56270 |
| `sdk/sdk_0019.c` | 448 | 0x7004f5f3a0 | 0x7004f82ca0 | 42377 |
| `sdk/sdk_0020.c` | 1 | 0x7004f82da0 | 0x7004f82da0 | 4915 |
| `sdk/sdk_0021.c` | 695 | 0x7004f87120 | 0x7004fb4b2c | 57090 |
| `sdk/sdk_0022.c` | 1446 | 0x7004fb4d2c | 0x7004fe308c | 57976 |
| `sdk/sdk_0023.c` | 1783 | 0x7004fe30a4 | 0x7005010ce0 | 59214 |
| `sdk/sdk_0024.c` | 1752 | 0x7005010d60 | 0x700503e060 | 58376 |
| `sdk/sdk_0025.c` | 991 | 0x700503e210 | 0x7005069a90 | 53245 |
| `sdk/sdk_0026.c` | 55 | 0x7005069aa0 | 0x70050746f0 | 13555 |
| `sdk/sdk_0027.c` | 1 | 0x7005075890 | 0x7005075890 | 5747 |
| `sdk/sdk_0028.c` | 1159 | 0x700507aa70 | 0x70050a8270 | 56244 |
| `sdk/sdk_0029.c` | 1520 | 0x70050a8540 | 0x70050d4c30 | 60668 |
| `sdk/sdk_0030.c` | 892 | 0x70050d4c60 | 0x7005102870 | 55851 |
| `sdk/sdk_0031.c` | 1643 | 0x70051028d8 | 0x700512fd30 | 58300 |
| `sdk/sdk_0032.c` | 844 | 0x70051305d0 | 0x700515e930 | 56439 |
| `sdk/sdk_0033.c` | 599 | 0x700515e940 | 0x700518b830 | 53607 |
| `sdk/sdk_0034.c` | 500 | 0x700518b880 | 0x70051b7e70 | 54166 |
| `sdk/sdk_0035.c` | 786 | 0x70051b7ed0 | 0x70051e6764 | 56580 |
| `sdk/sdk_0036.c` | 762 | 0x70051e6864 | 0x7005213c90 | 55447 |
| `sdk/sdk_0037.c` | 3000 | 0x7005213d30 | 0x7005238c50 | 56560 |
| `sdk/sdk_0038.c` | 3000 | 0x7005238c60 | 0x70052447d0 | 26999 |
| `sdk/sdk_0039.c` | 2469 | 0x70052447e0 | 0x700524e220 | 22220 |

## SDK namespaces (from the `sdk` module's named symbols)

19260 named functions. Top namespaces by count:

| Namespace | Named functions |
|---|---|
| `(C or unscoped)` | 3829 |
| `nn::audio` | 1427 |
| `std::__1` | 1333 |
| `nn::fs` | 1202 |
| `nn::hid` | 965 |
| `nn::codec` | 918 |
| `nn::mii` | 847 |
| `nn::settings` | 605 |
| `nn::account` | 508 |
| `nn::os` | 433 |
| `nn::util` | 401 |
| `nn::socket` | 359 |
| `nn::ec` | 307 |
| `nn::crypto` | 285 |
| `nn::err` | 238 |
| `nn::web` | 221 |
| `nn::nifm` | 209 |
| `nn::irsensor` | 190 |
| `nn::vi` | 186 |
| `nn::swkbd` | 181 |
| `nn::time` | 178 |
| `nn::async` | 177 |
| `nn::sf` | 162 |
| `nn::friends` | 159 |
| `nn::album` | 126 |
| `nn::image` | 125 |
| `nn::ssl` | 124 |
| `nn::oe` | 122 |
| `nn::bcat` | 117 |
| `nn::prepo` | 116 |
| `nn::pctl` | 115 |
| `nn::applet` | 111 |
| `nn::diag` | 110 |
| `nn::lmem` | 106 |
| `android::Parcel` | 100 |
| `nn::Result nn` | 94 |
| `nn::htcs` | 85 |
| `nn::srepo` | 79 |
| `nn::nlibsdk` | 75 |
| `nn::ngc` | 74 |
| `nn::kpr` | 73 |
| `nn::nfp` | 70 |
| `android::SurfaceComposerClient` | 68 |
| `nn::ldn` | 68 |
| `android::Region` | 66 |
| `void nn::audio` | 62 |
| `nn::edid` | 58 |
| `android::String8` | 58 |
| `nn::la` | 56 |
| `nn::htc` | 55 |
| `nn::nsd` | 54 |
| `nn::fontll` | 50 |
| `nn::lm` | 50 |
| `nn::hidbus` | 43 |
| `nerd_gillette_internal::otete` | 43 |
| `nn::am` | 40 |
| `nn::hidconfig` | 39 |
| `nn::mem` | 39 |
| `long nn::socket` | 38 |
| `android::String16` | 35 |

216 more namespaces not shown.

## `main` module named symbols

| Address | Symbol |
|---|---|
| 0x7001c1f920 | `malloc` |
| 0x70000165ac | `std::__1::basic_stringbuf<char, std::__1::char_traits<char>, std::__1::allocator<char>>::seekoff(lo…` |
| 0x70009ded50 | `int std::__1::uniform_int_distribution<int>::operator()<std::__1::mersenne_twister_engine<unsigned …` |
| 0x7000016db4 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::setbuf(char*, long)` |
| 0x7000000010 | `_init` |
| 0x7000017520 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::overflow(int)` |
| 0x70005b3100 | `operator delete[](void*, std::nothrow_t const&)` |
| 0x70005b30e0 | `operator delete[](void*)` |
| 0x70005b30f0 | `operator delete(void*, std::nothrow_t const&)` |
| 0x7000000320 | `nndetailRoGetRoDataStart` |
| 0x7001c1fa50 | `aligned_alloc` |
| 0x70005b30d0 | `operator new[](unsigned long, std::nothrow_t const&)` |
| 0x7000000880 | `nnMain` |
| 0x70005b30c0 | `operator new(unsigned long, std::nothrow_t const&)` |
| 0x7000017020 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::sync()` |
| 0x7000016cb4 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::imbue(std::__1::locale const&)` |
| 0x70005b30b0 | `operator new[](unsigned long)` |
| 0x7000016794 | `std::__1::basic_stringbuf<char, std::__1::char_traits<char>, std::__1::allocator<char>>::overflow(i…` |
| 0x70005b19e0 | `nninitStartup` |
| 0x7000016f98 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::seekpos(std::__1::fpos<__mbstate_t>, un…` |
| 0x7000017238 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::underflow()` |
| 0x70018c7860 | `strtok_r` |
| 0x70000166d8 | `std::__1::basic_stringbuf<char, std::__1::char_traits<char>, std::__1::allocator<char>>::underflow()` |
| 0x70005b19d0 | `operator delete(void*)` |
| 0x7000017bf4 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::basic_filebuf()` |
| 0x7000016c90 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::~basic_filebuf()` |
| 0x7000000170 | `_fini` |
| 0x70000179f0 | `std::__1::basic_stringbuf<char, std::__1::char_traits<char>, std::__1::allocator<char>>::str() const` |
| 0x70000174c0 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::pbackfail(int)` |
| 0x7000000250 | `__nnDetailNintendoSdkRuntimeObjectFileRefer` |
| 0x7000016728 | `std::__1::basic_stringbuf<char, std::__1::char_traits<char>, std::__1::allocator<char>>::pbackfail(…` |
| 0x7000000330 | `nndetailRoGetRoDataEnd` |
| 0x7001c1f990 | `calloc` |
| 0x7000016c04 | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::~basic_filebuf()` |
| 0x7000000340 | `__nnDetailNintendoSdkRuntimeObjectFile` |
| 0x70005b30a0 | `operator new(unsigned long)` |
| 0x7001c1f970 | `free` |
| 0x7001c1fa00 | `realloc` |
| 0x7000016ecc | `std::__1::basic_filebuf<char, std::__1::char_traits<char>>::seekoff(long long, std::__1::ios_base::…` |

## Functions the repo already names by address

Every `f_70…` address that appears in a doc, source file or script, with what the line says. Callers, callees and size come from the index.

| Address | Callers | Direct callees | Lines | Mentioned in | Context |
|---|---|---|---|---|---|
| 0x7000000000 | 0 | 0 | 6 | `docs/map/binary.md:385` (+1 more) | \| 0x7000000000 \| 0 \| 0 \| 6 \| `tools/prof_report.py:26` \| # " 0001:000e8c00 f_7000000000 00000001400e9c00 main_0000.o" \| |
| 0x700000b140 | 0 | 12 | 84 | `docs/map/binary.md:386` (+2 more) | \| 0x700000b140 \| 0 \| 12 \| 84 \| `docs/walkup-freeze.md:14` \| `f_70012e0150` runs (once a frame, from `f_700000b140`). \| |
| 0x7000030ec0 | 1 | 15 | 1074 | `docs/map/binary.md:387` (+3 more) | \| 0x7000030ec0 \| 1 \| 15 \| 1074 \| `CLAUDE.md:68` (+1 more) \| and the picture's signs trace a clean field outline. msdfgen's … |
| 0x7000031e70 | 1 | 1 | 152 | `docs/map/binary.md:388` (+4 more) | \| 0x7000031e70 \| 1 \| 1 \| 152 \| `CLAUDE.md:69` (+1 more) \| `f_7000031e70`, `f_7000033530`) then visits every pixel and compu… |
| 0x7000033530 | 1 | 1 | 113 | `docs/map/binary.md:388` (+7 more) | \| 0x7000031e70 \| 1 \| 1 \| 152 \| `CLAUDE.md:69` (+1 more) \| `f_7000031e70`, `f_7000033530`) then visits every pixel and compu… |
| 0x70000336bc | 3 | 3 | 115 | `docs/map/binary.md:390` (+6 more) | \| 0x70000336bc \| 3 \| 3 \| 115 \| `CLAUDE.md:87` (+4 more) \| (`f_70000336bc`, `f_7000033530`); the divide-based range tests gi… |
| 0x70000339a0 | 1 | 2 | 345 | `docs/map/binary.md:391` (+1 more) | \| 0x70000339a0 \| 1 \| 2 \| 345 \| `docs/reports/2026-11-23-msdf-skip.md:27` \| The pass (`f_7000030ec0`, that is main+0x30ec0, … |
| 0x70003eea50 | ? | ? | ? | `docs/map/binary.md:392` (+2 more) | \| 0x70003eea50 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:10` \| // PXP_SAVE.BIN, PA_SAVE.BIN read back through "ReloadSaveD… |
| 0x70004408e4 | ? | ? | ? | `docs/map/binary.md:393` (+2 more) | \| 0x70004408e4 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:13` \| // tokens through f_70004408e4, which stores them as a u16 … |
| 0x700045c704 | ? | ? | ? | `docs/map/binary.md:393` (+3 more) | \| 0x70004408e4 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:13` \| // tokens through f_70004408e4, which stores them as a u16 … |
| 0x70004c779c | ? | ? | ? | `docs/map/binary.md:395` (+1 more) | \| 0x70004c779c \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:15` \| // f_70004c779c (slot 0x700217d580, three arguments, no res… |
| 0x7000570280 | ? | ? | ? | `docs/map/binary.md:396` (+1 more) | \| 0x7000570280 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:4` \| // What the game does [C, 1.0.15 addresses; read 2026-11-20]… |
| 0x7000570c50 | ? | ? | ? | `docs/map/binary.md:397` (+1 more) | \| 0x7000570c50 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:6` \| // The game keeps files there through its file layer (locati… |
| 0x70005a1300 | 22 | 2 | 17 | `docs/map/binary.md:398` (+1 more) | \| 0x70005a1300 \| 22 \| 2 \| 17 \| `docs/walkup-freeze.md:23` \| (`f_70005a1300(2)`, `f_70005a1a90()`). That is the freeze, the … |
| 0x70005a1310 | ? | ? | ? | `docs/map/binary.md:399` (+2 more) | \| 0x70005a1310 \| ? \| ? \| ? \| `runtime/gfx/vk_exec_xfer.c:410` (+1 more) \| // nvnEventGetValue for such an event (f_70005a13… |
| 0x70005a1a90 | 47 | 1 | 65 | `docs/map/binary.md:398` (+6 more) | \| 0x70005a1300 \| 22 \| 2 \| 17 \| `docs/walkup-freeze.md:23` \| (`f_70005a1300(2)`, `f_70005a1a90()`). That is the freeze, the … |
| 0x70005a4634 | ? | ? | ? | `docs/map/binary.md:401` (+3 more) | \| 0x70005a4634 \| ? \| ? \| ? \| `docs/graphics-plan.md:131` (+1 more) \| `nvnTextureBuilderSetSize2D`: three 1440x810 targets m… |
| 0x70005a4b88 | ? | ? | ? | `docs/map/binary.md:401` (+3 more) | \| 0x70005a4634 \| ? \| ? \| ? \| `docs/graphics-plan.md:131` (+1 more) \| `nvnTextureBuilderSetSize2D`: three 1440x810 targets m… |
| 0x70005a5368 | ? | ? | ? | `docs/map/binary.md:403` (+2 more) | \| 0x70005a5368 \| ? \| ? \| ? \| `docs/graphics-plan.md:128` (+1 more) \| - **Internal resolution (`MLB_RENDER_SCALE`, 2026-11-1… |
| 0x70005a5388 | 2 | 0 | 14 | `docs/map/binary.md:404` (+1 more) | \| 0x70005a5388 \| 2 \| 0 \| 14 \| `runtime/mlb/resolution.c:12` \| // 1.0.20 moved them (tools/addrmap.py, checked in the disass… |
| 0x70008c6460 | ? | ? | ? | `docs/map/source/runtime-gfx.md:736` (+3 more) | \| `obs_release_read` \| 778-793 \| static void (Cpu *) \| rt_original, cfg_bool, kern_core_away, plat_sleep_ms, fence_done, gfx_… |
| 0x70008dc5b0 | ? | ? | ? | `docs/map/binary.md:406` (+1 more) | \| 0x70008dc5b0 \| ? \| ? \| ? \| `runtime/mlb/tutorials.c:7` \| // P = *(*(*0x7003abda98 + 0x198) + 0x318) (f_70008dc5b0 returns… |
| 0x700092ae20 | 147 | 1 | 140 | `docs/map/binary.md:407` (+5 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x700092ce50 | 152 | 0 | 161 | `docs/map/binary.md:407` (+4 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x700093b09c | 0 | 2 | 68 | `docs/map/binary.md:409` (+1 more) | \| 0x700093b09c \| 0 \| 2 \| 68 \| `tools/packages/server_msgs.py:252` \| # 0x1b26202c -> CPartyManager::OnConductorAnswer(endpoi… |
| 0x7000946e20 | 1 | 3 | 24 | `docs/map/binary.md:410` (+1 more) | \| 0x7000946e20 \| 1 \| 3 \| 24 \| `tools/packages/profile_state.py:3` \| u8 counter} and only the server message 0xAFE1519A {u32… |
| 0x70009a6e58 | 3 | 5 | 32 | `docs/map/binary.md:411` (+2 more) | \| 0x70009a6e58 \| 3 \| 5 \| 32 \| `tools/packages/server_msgs.py:246` \| # echo choice: CPluginAuth+0x54 (= CNetSession+0x59, se… |
| 0x70009a7454 | 1 | 10 | 207 | `docs/map/binary.md:412` (+3 more) | \| 0x70009a7454 \| 1 \| 10 \| 207 \| `tools/packages/server_msgs.py:253` \| # - Service connect f_70009a7454: inet_ntop(Endpoint … |
| 0x70009a7800 | 0 | 4 | 48 | `docs/map/binary.md:413` (+1 more) | \| 0x70009a7800 \| 0 \| 4 \| 48 \| `tools/packages/server_msgs.py:251` \| # 0x07b7014f -> OnConductorAnswer(endpoint, plugin guid… |
| 0x70009b29b0 | 2 | 4 | 46 | `docs/map/binary.md:414` (+1 more) | \| 0x70009b29b0 \| 2 \| 4 \| 46 \| `tools/packages/server_msgs.py:162` \| keep_session=0 makes CNetPlayer wipe its cached Account… |
| 0x70009b2a54 | 1 | 0 | 8 | `docs/map/binary.md:411` (+2 more) | \| 0x70009a6e58 \| 3 \| 5 \| 32 \| `tools/packages/server_msgs.py:246` \| # echo choice: CPluginAuth+0x54 (= CNetSession+0x59, se… |
| 0x70009e7fb4 | 0 | 38 | 1031 | `docs/map/binary.md:416` (+2 more) | \| 0x70009e7fb4 \| 0 \| 38 \| 1031 \| `tools/packages/server_msgs.py:15` (+1 more) \| # auth connection (CPluginAuth, f_70009e7fb… |
| 0x70009e8e10 | 1 | 13 | 252 | `docs/map/binary.md:417` (+1 more) | \| 0x70009e8e10 \| 1 \| 13 \| 252 \| `tools/packages/server_msgs.py:247` \| # -> 0x0ca403f1; else f_70009e8e10 'AttemptLinkDevice… |
| 0x70009f100c | 2 | 9 | 174 | `docs/map/binary.md:418` (+3 more) | \| 0x70009f100c \| 2 \| 9 \| 174 \| `tools/packages/server_msgs.py:30` (+1 more) \| # conductor connection (conductor plugin f_70… |
| 0x70009f1400 | 0 | 0 | 69 | `docs/map/binary.md:418` (+3 more) | \| 0x70009f100c \| 2 \| 9 \| 174 \| `tools/packages/server_msgs.py:30` (+1 more) \| # conductor connection (conductor plugin f_70… |
| 0x70009f85a0 | 29 | 0 | 14 | `docs/map/binary.md:420` (+1 more) | \| 0x70009f85a0 \| 29 \| 0 \| 14 \| `tools/packages/rpc.py:8` \| f_70009f85a0 request_id = global counter @0x7003abf068 (returns … |
| 0x70009f85c0 | 6 | 8 | 234 | `docs/map/binary.md:421` (+4 more) | \| 0x70009f85c0 \| 6 \| 8 \| 234 \| `docs/map/source/tools-packages.md:119` (+2 more) \| \\| `pending_key` \\| 185-191 \\| \\| en… |
| 0x70009f8c4c | 0 | 4 | 46 | `docs/map/binary.md:422` (+1 more) | \| 0x70009f8c4c \| 0 \| 4 \| 46 \| `tools/packages/rpc.py:49` \| 0x7C335915 ServiceConnect C->S, sent once when the plugin attach… |
| 0x70009f8cf0 | 0 | 6 | 253 | `docs/map/binary.md:423` (+2 more) | \| 0x70009f8cf0 \| 0 \| 6 \| 253 \| `tools/packages/rpc.py:21` (+1 more) \| Timeout: f_70009f8cf0 synthesises a ServiceResponse w… |
| 0x70009f9070 | 0 | 13 | 378 | `docs/map/binary.md:421` (+4 more) | \| 0x70009f85c0 \| 6 \| 8 \| 234 \| `docs/map/source/tools-packages.md:119` (+2 more) \| \\| `pending_key` \\| 185-191 \\| \\| en… |
| 0x7000a12970 | 30 | 33 | 492 | `docs/map/binary.md:425` (+1 more) | \| 0x7000a12970 \| 30 \| 33 \| 492 \| `tools/packages/rpc.py:7` \| f_7000a12970 Transaction::Run "STARTING SERVICE [%s]" ... "SEN… |
| 0x7000a13298 | 0 | 16 | 281 | `docs/map/binary.md:426` (+7 more) | \| 0x7000a13298 \| 0 \| 16 \| 281 \| `docs/map/source/tools-packages.md:117` (+6 more) \| \\| `make_response_xml` \\| 152-159 \\|… |
| 0x7000a15440 | 11 | 13 | 177 | `docs/map/binary.md:427` (+1 more) | \| 0x7000a15440 \| 11 \| 13 \| 177 \| `tools/packages/rpc.py:9` \| f_7000a15440 params map -> JSON text (types 1..8); type-9 para… |
| 0x7000a32a5c | ? | ? | ? | `docs/map/binary.md:428` (+2 more) | \| 0x7000a32a5c \| ? \| ? \| ? \| `runtime/mlb/tutorials.c:11` (+1 more) \| // the name is there. f_7000a32a5c(P, name) adds a na… |
| 0x7000a32ce0 | ? | ? | ? | `docs/map/binary.md:429` (+1 more) | \| 0x7000a32ce0 \| ? \| ? \| ? \| `runtime/mlb/tutorials.c:10` \| // f_7000a32ce0(P, name) says whether a name is in the list; th… |
| 0x7000a62db4 | 32 | 9 | 84 | `docs/map/binary.md:430` (+1 more) | \| 0x7000a62db4 \| 32 \| 9 \| 84 \| `tools/packages/rpc.py:19` \| msg.xml != "timedout"; parses msg.xml (f_7000a62db4: TinyXML2 d… |
| 0x7000bd1da0 | ? | ? | ? | `docs/map/binary.md:431` (+2 more) | \| 0x7000bd1da0 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:14` \| // returns. A trigger upgrade goes through f_7000bd1da0 (1.… |
| 0x7000bd3140 | 0 | 12 | 177 | `docs/map/binary.md:431` (+2 more) | \| 0x7000bd1da0 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:14` \| // returns. A trigger upgrade goes through f_7000bd1da0 (1.… |
| 0x7000d197fc | ? | ? | ? | `docs/map/binary.md:433` (+1 more) | \| 0x7000d197fc \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:7` \| // CUSTOMCAMS_<n>.CAM custom batting cameras (looked up by f… |
| 0x7000d199bc | ? | ? | ? | `docs/map/binary.md:434` (+1 more) | \| 0x7000d199bc \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:8` \| // f_7000d199bc) \| |
| 0x7000d52680 | 7 | 8 | 235 | `docs/map/binary.md:435` (+1 more) | \| 0x7000d52680 \| 7 \| 8 \| 235 \| `docs/walkup-freeze.md:11` \| batter and inning, `f_7000d52680`), and the lighting is baked a… |
| 0x7000de6728 | ? | ? | ? | `docs/map/binary.md:436` (+1 more) | \| 0x7000de6728 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:8` \| // f_7000de6728 (no arguments) is the career autosave the ga… |
| 0x7000e53620 | 1 | 4 | 18 | `docs/map/binary.md:437` (+3 more) | \| 0x7000e53620 \| 1 \| 4 \| 18 \| `docs/walkup-freeze.md:56` (+1 more) \| game-start sequence `f_7000e53620` both call `f_7000e5… |
| 0x7000e53654 | 2 | 18 | 675 | `docs/map/binary.md:437` (+6 more) | \| 0x7000e53620 \| 1 \| 4 \| 18 \| `docs/walkup-freeze.md:56` (+1 more) \| game-start sequence `f_7000e53620` both call `f_7000e5… |
| 0x7000e54080 | 3 | 0 | 211 | `docs/map/binary.md:439` (+3 more) | \| 0x7000e54080 \| 3 \| 0 \| 211 \| `docs/walkup-freeze.md:88` (+1 more) \| right after the first build (entry of `f_7000e54080`)… |
| 0x7000e543a4 | 3 | 4 | 156 | `docs/map/binary.md:440` (+3 more) | \| 0x7000e543a4 \| 3 \| 4 \| 156 \| `docs/walkup-freeze.md:57` (+2 more) \| (`main+0xe53808`), and then `f_7000e543a4`, which bui… |
| 0x7000e545f0 | 3 | 10 | 406 | `docs/map/binary.md:439` (+2 more) | \| 0x7000e54080 \| 3 \| 0 \| 211 \| `docs/walkup-freeze.md:88` (+1 more) \| right after the first build (entry of `f_7000e54080`)… |
| 0x7000e54c00 | 2 | 11 | 685 | `docs/map/binary.md:442` (+6 more) | \| 0x7000e54c00 \| 2 \| 11 \| 685 \| `docs/walkup-freeze.md:54` (+4 more) \| broadcast "moments" refresh: `f_7000e5640c` (from th… |
| 0x7000e5640c | 1 | 26 | 694 | `docs/map/binary.md:442` (+3 more) | \| 0x7000e54c00 \| 2 \| 11 \| 685 \| `docs/walkup-freeze.md:54` (+4 more) \| broadcast "moments" refresh: `f_7000e5640c` (from th… |
| 0x7001029cd8 | ? | ? | ? | `docs/map/binary.md:392` (+2 more) | \| 0x70003eea50 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:10` \| // PXP_SAVE.BIN, PA_SAVE.BIN read back through "ReloadSaveD… |
| 0x700108b628 | 0 | 73 | 587 | `docs/map/binary.md:445` (+2 more) | \| 0x700108b628 \| 0 \| 73 \| 587 \| `docs/walkup-freeze.md:19` (+1 more) \| 2. **When the next pitch's batter-up state starts**,… |
| 0x700109a6a8 | 0 | 26 | 197 | `docs/map/binary.md:446` (+1 more) | \| 0x700109a6a8 \| 0 \| 26 \| 197 \| `docs/walkup-freeze.md:17` \| `f_700109a6a8`) sets flags `0xec01`, and the bake runs one ste… |
| 0x70010c3298 | ? | ? | ? | `docs/map/binary.md:447` (+1 more) | \| 0x70010c3298 \| ? \| ? \| ? \| `runtime/gfx/vk_exec_xfer.c:17` \| // TOTK resets and reports it 3 to 8 times a frame in the fi… |
| 0x7001267d20 | ? | ? | ? | `docs/map/binary.md:448` (+1 more) | \| 0x7001267d20 \| ? \| ? \| ? \| `docs/graphics-plan.md:134` \| title screen; **200 % crashes** at about frame 1400 with a null … |
| 0x700128d2a0 | 1 | 8 | 270 | `docs/map/binary.md:449` (+2 more) | \| 0x700128d2a0 \| 1 \| 8 \| 270 \| `docs/walkup-freeze.md:37` (+1 more) \| (`main+0x12e0db4..0x12e0e24`). The counter's only rea… |
| 0x70012c54ec | 173 | 4 | 57 | `docs/map/binary.md:450` (+2 more) | \| 0x70012c54ec \| 173 \| 4 \| 57 \| `docs/walkup-freeze.md:12` (+1 more) \| (`f_70012c54ec`, an object of 0x101e40 bytes) keeps … |
| 0x70012d0fcc | 9 | 3 | 91 | `docs/map/binary.md:451` (+3 more) | \| 0x70012d0fcc \| 9 \| 3 \| 91 \| `docs/walkup-freeze.md:20` (+1 more) \| `f_70012d0fcc(manager, 1)` at `main+0x108bbb8`. The `1… |
| 0x70012d1e04 | 10 | 4 | 187 | `docs/map/binary.md:451` (+8 more) | \| 0x70012d0fcc \| 9 \| 3 \| 91 \| `docs/walkup-freeze.md:20` (+1 more) \| `f_70012d0fcc(manager, 1)` at `main+0x108bbb8`. The `1… |
| 0x70012d20a0 | 1 | 2 | 61 | `docs/map/binary.md:453` (+2 more) | \| 0x70012d20a0 \| 1 \| 2 \| 61 \| `docs/walkup-freeze.md:16` (+1 more) \| 1. **After every play** the game bakes the new time in… |
| 0x70012e0150 | 1 | 54 | 1653 | `docs/map/binary.md:386` (+7 more) | \| 0x700000b140 \| 0 \| 12 \| 84 \| `docs/walkup-freeze.md:14` \| `f_70012e0150` runs (once a frame, from `f_700000b140`). \| |
| 0x7001340720 | ? | ? | ? | `docs/map/binary.md:455` (+2 more) | \| 0x7001340720 \| ? \| ? \| ? \| `runtime/mlb/hid.c:676` \| // MLB's pad update (1.0.20 f_7001341c20, 1.0.15 f_7001340720; read … |
| 0x7001341c20 | 2 | 4 | 238 | `docs/map/binary.md:455` (+2 more) | \| 0x7001340720 \| ? \| ? \| ? \| `runtime/mlb/hid.c:676` \| // MLB's pad update (1.0.20 f_7001341c20, 1.0.15 f_7001340720; read … |
| 0x70014bdc08 | 26 | 3 | 109 | `docs/map/binary.md:457` (+7 more) | \| 0x70014bdc08 \| 26 \| 3 \| 109 \| `docs/map/source/tools-packages.md:120` (+3 more) \| \\| `decode_account_session` \\| 195-19… |
| 0x70014bde34 | 26 | 5 | 193 | `docs/map/binary.md:458` (+1 more) | \| 0x70014bde34 \| 26 \| 5 \| 193 \| `tools/packages/server_msgs.py:88` \| """AccountSession (f_70014bdc08 ser / f_70014bde34 des… |
| 0x70014be240 | 0 | 1 | 34 | `docs/map/source/tools-packages.md:181` (+1 more) | \| `parse_token_echo` \| 189-199 \| \| Reader, _done, get, read, u8, u64, hex, string (+1) \| 0xde3ac304 / 0x0ca403f1 / 0x66baea3… |
| 0x70014be374 | 0 | 1 | 55 | `docs/map/source/tools-packages.md:181` (+1 more) | \| `parse_token_echo` \| 189-199 \| \| Reader, _done, get, read, u8, u64, hex, string (+1) \| 0xde3ac304 / 0x0ca403f1 / 0x66baea3… |
| 0x70014be5a4 | 0 | 2 | 39 | `docs/map/source/tools-packages.md:181` (+1 more) | \| `parse_token_echo` \| 189-199 \| \| Reader, _done, get, read, u8, u64, hex, string (+1) \| 0xde3ac304 / 0x0ca403f1 / 0x66baea3… |
| 0x70014be6f8 | 0 | 1 | 22 | `docs/map/binary.md:462` (+2 more) | \| 0x70014be6f8 \| 0 \| 1 \| 22 \| `tools/packages/server_msgs.py:248` \| # - SessionResponse deser f_70014be6f8 / f_70014be818 (… |
| 0x70014be818 | 0 | 1 | 58 | `docs/map/binary.md:462` (+2 more) | \| 0x70014be6f8 \| 0 \| 1 \| 22 \| `tools/packages/server_msgs.py:248` \| # - SessionResponse deser f_70014be6f8 / f_70014be818 (… |
| 0x70014c2930 | 8 | 2 | 137 | `docs/map/binary.md:407` (+6 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x70014c2b00 | 7 | 4 | 175 | `docs/map/binary.md:465` (+1 more) | \| 0x70014c2b00 \| 7 \| 4 \| 175 \| `tools/packages/server_msgs.py:76` \| """Token (f_70014c2930 ser / f_70014c2b00 deser): strin… |
| 0x70014c3c40 | 0 | 1 | 25 | `docs/map/binary.md:466` (+1 more) | \| 0x70014c3c40 \| 0 \| 1 \| 25 \| `tools/packages/server_msgs.py:244` \| # - LoginResponse deser f_70014c3c40: u8 ok @+8, Token … |
| 0x70014c8a18 | 0 | 0 | 9 | `docs/map/binary.md:467` (+1 more) | \| 0x70014c8a18 \| 0 \| 0 \| 9 \| `tools/packages/codec.py:37` \| MSG_AUTH_TOKEN = 0x1397A1DF # client->server, body: string (NSA… |
| 0x70014dd530 | 0 | 2 | 16 | `docs/map/binary.md:468` (+1 more) | \| 0x70014dd530 \| 0 \| 2 \| 16 \| `tools/packages/rpc.py:55` \| 0xE54920EB S->C (no vtable found; factory f_70014dd530) OnMessag… |
| 0x70014e2b00 | 7 | 2 | 199 | `docs/map/binary.md:469` (+2 more) | \| 0x70014e2b00 \| 7 \| 2 \| 199 \| `tools/packages/codec.py:21` \| Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_700… |
| 0x7001502b4c | 2 | 0 | 44 | `docs/map/binary.md:469` (+6 more) | \| 0x70014e2b00 \| 7 \| 2 \| 199 \| `tools/packages/codec.py:21` \| Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_700… |
| 0x7001502bd4 | 2 | 0 | 64 | `docs/map/binary.md:470` (+3 more) | \| 0x7001502b4c \| 2 \| 0 \| 44 \| `tools/packages/codec.py:16` (+1 more) \| 2. Messages (f_700151d520 parse, f_7001502b4c/f_7001… |
| 0x7001502d14 | 1 | 0 | 51 | `docs/map/binary.md:472` (+2 more) | \| 0x7001502d14 \| 1 \| 0 \| 51 \| `tools/packages/codec.py:8` \| u8 magic = 0xA5 (f_7001502d14 writes, f_7001502db4 checks) \| |
| 0x7001502db4 | 1 | 0 | 58 | `docs/map/binary.md:472` (+2 more) | \| 0x7001502d14 \| 1 \| 0 \| 51 \| `tools/packages/codec.py:8` \| u8 magic = 0xA5 (f_7001502d14 writes, f_7001502db4 checks) \| |
| 0x7001502e74 | 0 | 0 | 24 | `docs/map/binary.md:469` (+2 more) | \| 0x70014e2b00 \| 7 \| 2 \| 199 \| `tools/packages/codec.py:21` \| Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_700… |
| 0x70015032d8 | 0 | 0 | 9 | `docs/map/binary.md:475` (+1 more) | \| 0x70015032d8 \| 0 \| 0 \| 9 \| `tools/packages/codec.py:39` \| MSG_PING = 0x9A77845F # server->client: makes the client send a… |
| 0x700150330c | 0 | 0 | 10 | `docs/map/binary.md:476` (+1 more) | \| 0x700150330c \| 0 \| 0 \| 10 \| `tools/packages/codec.py:38` \| MSG_HEARTBEAT = 0xD4D9E1AD # client->server every 15 s idle, b… |
| 0x7001503a1c | 0 | 0 | 31 | `docs/map/binary.md:477` (+1 more) | \| 0x7001503a1c \| 0 \| 0 \| 31 \| `tools/packages/rpc.py:52` \| 0xC031F812 C->S? body: u64 (Serialize f_7001503a1c) - sender not… |
| 0x7001503b2c | 0 | 1 | 7 | `docs/map/binary.md:478` (+1 more) | \| 0x7001503b2c \| 0 \| 1 \| 7 \| `tools/packages/rpc.py:51` \| 0x94E26BC1 C->S? body: AccountSession (Serialize f_7001503b2c) - … |
| 0x7001503bd0 | 0 | 3 | 191 | `docs/map/binary.md:479` (+2 more) | \| 0x7001503bd0 \| 0 \| 3 \| 191 \| `tools/packages/rpc.py:12` \| message 0x801FB56C ServiceRequest (Serialize f_7001503bd0, Dese… |
| 0x7001503f50 | 0 | 4 | 172 | `docs/map/binary.md:479` (+2 more) | \| 0x7001503bd0 \| 0 \| 3 \| 191 \| `tools/packages/rpc.py:12` \| message 0x801FB56C ServiceRequest (Serialize f_7001503bd0, Dese… |
| 0x70015041b0 | 0 | 1 | 39 | `docs/map/binary.md:481` (+2 more) | \| 0x70015041b0 \| 0 \| 1 \| 39 \| `tools/packages/rpc.py:15` \| message 0x30D39658 ServiceResponse (Serialize f_70015041b0, Dese… |
| 0x700150422c | 0 | 1 | 49 | `docs/map/binary.md:481` (+2 more) | \| 0x70015041b0 \| 0 \| 1 \| 39 \| `tools/packages/rpc.py:15` \| message 0x30D39658 ServiceResponse (Serialize f_70015041b0, Dese… |
| 0x70015042d4 | 0 | 1 | 28 | `docs/map/binary.md:483` (+1 more) | \| 0x70015042d4 \| 0 \| 1 \| 28 \| `tools/packages/rpc.py:53` \| 0xDF31986F ? body: u32, string (Serialize f_70015042d4) - not ha… |
| 0x70015043a0 | 1 | 1 | 66 | `docs/map/binary.md:484` (+1 more) | \| 0x70015043a0 \| 1 \| 1 \| 66 \| `tools/packages/rpc.py:48` \| Other messages registered by the Service plugin (f_70015043a0 gr… |
| 0x7001505770 | 1 | 1 | 38 | `docs/map/binary.md:485` (+1 more) | \| 0x7001505770 \| 1 \| 1 \| 38 \| `tools/packages/rpc.py:56` \| 0xF63439D4 / 0x23BF9620 (group f_7001505770) S->C: OnMessage loo… |
| 0x7001505f6c | 0 | 1 | 7 | `docs/map/binary.md:486` (+3 more) | \| 0x7001505f6c \| 0 \| 1 \| 7 \| `docs/map/source/tools-packages.md:182` (+1 more) \| \\| `parse_conductor_query` \\| 202-204 \\… |
| 0x70015061bc | 0 | 1 | 7 | `docs/map/binary.md:486` (+3 more) | \| 0x7001505f6c \| 0 \| 1 \| 7 \| `docs/map/source/tools-packages.md:182` (+1 more) \| \\| `parse_conductor_query` \\| 202-204 \\… |
| 0x700151a26c | 6 | 4 | 172 | `docs/map/binary.md:488` (+2 more) | \| 0x700151a26c \| 6 \| 4 \| 172 \| `tools/packages/rpc.py:37` \| params_json format (f_700151a26c begin '{', f_700151aa40 key '"… |
| 0x700151a4d4 | 8 | 3 | 104 | `docs/map/binary.md:489` (+1 more) | \| 0x700151a4d4 \| 8 \| 3 \| 104 \| `tools/packages/rpc.py:38` \| 0x7002206578 ["", ","], f_700151a4d4 end '}'), values by param … |
| 0x700151aa40 | 9 | 4 | 71 | `docs/map/binary.md:488` (+2 more) | \| 0x700151a26c \| 6 \| 4 \| 172 \| `tools/packages/rpc.py:37` \| params_json format (f_700151a26c begin '{', f_700151aa40 key '"… |
| 0x700151ab30 | 27 | 5 | 130 | `docs/map/binary.md:491` (+1 more) | \| 0x700151ab30 \| 27 \| 5 \| 130 \| `tools/packages/rpc.py:40` \| 2 int -> %d (f_700151ab30) \| |
| 0x700151ad00 | 1 | 5 | 130 | `docs/map/binary.md:492` (+1 more) | \| 0x700151ad00 \| 1 \| 5 \| 130 \| `tools/packages/rpc.py:42` \| 4 int64 -> %ld (f_700151ad00) \| |
| 0x700151aed0 | 11 | 5 | 130 | `docs/map/binary.md:493` (+1 more) | \| 0x700151aed0 \| 11 \| 5 \| 130 \| `tools/packages/rpc.py:41` \| 3 uint -> %u (f_700151aed0) \| |
| 0x700151b0a0 | 3 | 5 | 130 | `docs/map/binary.md:494` (+1 more) | \| 0x700151b0a0 \| 3 \| 5 \| 130 \| `tools/packages/rpc.py:43` \| 5 uint64 -> %lu (f_700151b0a0) \| |
| 0x700151b7b0 | 7 | 5 | 263 | `docs/map/binary.md:495` (+1 more) | \| 0x700151b7b0 \| 7 \| 5 \| 263 \| `tools/packages/rpc.py:45` \| 8 string -> "raw text" (f_700151b7b0 called with escape=0: NOT … |
| 0x700151bb48 | 2 | 5 | 134 | `docs/map/binary.md:496` (+1 more) | \| 0x700151bb48 \| 2 \| 5 \| 134 \| `tools/packages/rpc.py:39` \| 1 bool -> true / false (f_700151bb48, table @0x7001da9f88) \| |
| 0x700151bd28 | 5 | 5 | 132 | `docs/map/binary.md:497` (+1 more) | \| 0x700151bd28 \| 5 \| 5 \| 132 \| `tools/packages/rpc.py:44` \| 6 float, 7 double -> %f (f_700151bd28) \| |
| 0x700151c1dc | 3 | 20 | 358 | `docs/map/binary.md:412` (+3 more) | \| 0x70009a7454 \| 1 \| 10 \| 207 \| `tools/packages/server_msgs.py:253` \| # - Service connect f_70009a7454: inet_ntop(Endpoint … |
| 0x700151c884 | 10 | 5 | 137 | `docs/map/binary.md:499` (+2 more) | \| 0x700151c884 \| 10 \| 5 \| 137 \| `tools/packages/rpc.py:11` \| pending_key(request_id, service) then f_7001530fb0 -> f_700151… |
| 0x700151cd40 | 1 | 10 | 156 | `docs/map/binary.md:500` (+4 more) | \| 0x700151cd40 \| 1 \| 10 \| 156 \| `docs/map/source/tools-packages.md:30` (+2 more) \| \\| `encode_block` \\| 117-126 \\| \\| l… |
| 0x700151d2a0 | 1 | 12 | 170 | `docs/map/binary.md:501` (+1 more) | \| 0x700151d2a0 \| 1 \| 12 \| 170 \| `tools/packages/codec.py:7` \| 1. Stream blocks (olClient transport, f_700151cd40 send / f_7… |
| 0x700151d520 | 1 | 12 | 190 | `docs/map/binary.md:470` (+3 more) | \| 0x7001502b4c \| 2 \| 0 \| 44 \| `tools/packages/codec.py:16` (+1 more) \| 2. Messages (f_700151d520 parse, f_7001502b4c/f_7001… |
| 0x7001530fb0 | 42 | 1 | 10 | `docs/map/binary.md:499` (+2 more) | \| 0x700151c884 \| 10 \| 5 \| 137 \| `tools/packages/rpc.py:11` \| pending_key(request_id, service) then f_7001530fb0 -> f_700151… |
| 0x70015310d0 | 2 | 2 | 118 | `docs/map/binary.md:504` (+3 more) | \| 0x70015310d0 \| 2 \| 2 \| 118 \| `docs/map/source/tools-packages.md:157` (+2 more) \| \\| `expires_epoch` \\| 62-72 \\| \\| ti… |
| 0x7001531280 | 9 | 1 | 22 | `docs/map/source/tools-packages.md:156` (+2 more) | \| `expires_str` \| 55-59 \| \| strftime, gmtime, time \| 'YYYY-MM-DDTHH:MM:SS' (UTC). Must be > now + 30 s on the client clock (… |
| 0x70015351a4 | 47 | 1 | 35 | `docs/map/binary.md:407` (+4 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x7001535e00 | 10 | 7 | 161 | `docs/map/binary.md:412` (+3 more) | \| 0x70009a7454 \| 1 \| 10 \| 207 \| `tools/packages/server_msgs.py:253` \| # - Service connect f_70009a7454: inet_ntop(Endpoint … |
| 0x7001538ed0 | 5 | 1 | 7 | `docs/map/binary.md:508` (+1 more) | \| 0x7001538ed0 \| 5 \| 1 \| 7 \| `tools/packages/server_msgs.py:114` \| (client does ntohs() on it before connecting, f_7001538e… |
| 0x70015391b4 | 1 | 0 | 100 | `docs/map/binary.md:509` (+1 more) | \| 0x70015391b4 \| 1 \| 0 \| 100 \| `tools/packages/server_msgs.py:112` \| (client types it IPv4 iff hi==0 and lo>>32 == 0xffff, … |
| 0x70015395cc | 9 | 0 | 57 | `docs/map/binary.md:510` (+3 more) | \| 0x70015395cc \| 9 \| 0 \| 57 \| `docs/map/source/tools-packages.md:169` (+1 more) \| \\| `endpoint` \\| 108-118 \\| \\| bytes,… |
| 0x7001539684 | 9 | 1 | 44 | `docs/map/binary.md:510` (+3 more) | \| 0x70015395cc \| 9 \| 0 \| 57 \| `docs/map/source/tools-packages.md:169` (+1 more) \| \\| `endpoint` \\| 108-118 \\| \\| bytes,… |
| 0x70016527d8 | 1 | 7 | 142 | `docs/map/binary.md:512` (+1 more) | \| 0x70016527d8 \| 1 \| 7 \| 142 \| `tools/packages/rpc.py:54` \| 0x9FD30956 S->C body: string, string (OnMessage branch: clears … |
| 0x70019fb800 | 1 | 2 | 43 | `docs/map/binary.md:513` (+3 more) | \| 0x70019fb800 \| 1 \| 2 \| 43 \| `docs/walkup-freeze.md:40` (+2 more) \| tail-calling `f_70019fb800` with the time (`main+0x12d… |
| 0x70019fb880 | 1 | 8 | 239 | `docs/map/binary.md:514` (+2 more) | \| 0x70019fb880 \| 1 \| 8 \| 239 \| `tools/data/patches-1.0.20.txt:34` \| # that turns a set of stadium props off or on (f_70019f… |
| 0x70019fbbb0 | 1 | 12 | 337 | `docs/map/binary.md:514` (+2 more) | \| 0x70019fb880 \| 1 \| 8 \| 239 \| `tools/data/patches-1.0.20.txt:34` \| # that turns a set of stadium props off or on (f_70019f… |
| 0x70051242a8 | ? | ? | ? | `docs/map/binary.md:516` (+2 more) | \| 0x70051242a8 \| ? \| ? \| ? \| `runtime/core/kernel.c:343` \| // - Horizon's preemption disable: the SDK's spin locks (1.2.1 s… |
| 0x7005124360 | ? | ? | ? | `docs/map/binary.md:516` (+2 more) | \| 0x70051242a8 \| ? \| ? \| ? \| `runtime/core/kernel.c:343` \| // - Horizon's preemption disable: the SDK's spin locks (1.2.1 s… |
