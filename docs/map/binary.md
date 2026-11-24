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
| 0x7000030ec0 | 1 | 15 | 1074 | `CLAUDE.md:68` (+4 more) | and the picture's signs trace a clean field outline. msdfgen's error-correction pass (`f_7000030ec0`, with |
| 0x7000031e70 | 1 | 1 | 152 | `CLAUDE.md:69` (+5 more) | `f_7000031e70`, `f_7000033530`) then visits every pixel and computes `(a - 0.5) / (a - b)`; with infinities that is |
| 0x7000033530 | 1 | 1 | 113 | `CLAUDE.md:69` (+8 more) | `f_7000031e70`, `f_7000033530`) then visits every pixel and computes `(a - 0.5) / (a - b)`; with infinities that is |
| 0x70000336bc | 3 | 3 | 115 | `CLAUDE.md:87` (+7 more) | (`f_70000336bc`, `f_7000033530`); the divide-based range tests give NaN for an infinite pixel whatever its neighbours |
| 0x70000339a0 | 1 | 2 | 345 | `docs/map/binary.md:391` (+2 more) | \| 0x70000339a0 \| 1 \| 2 \| 345 \| `docs/reports/2026-11-23-msdf-skip.md:27` (+1 more) \| The pass (`f_7000030ec0`, that is main… |
| 0x7000095390 | 1 | 27 | 1083 | `docs/wiki/Match-start-freeze.md:19` | \| `f_7000095390` \| drives the step and logs "MSDF took ..." \| |
| 0x70000a7360 | 403 | 0 | 19 | `docs/map/binary.md:394` (+12 more) | \| 0x70000a7430 \| 24 \| 0 \| 19 \| `docs/map/binary.md:565` (+2 more) \| \\| 0x7000df2bb0 \\| 55 \\| 0 \\| 8 \\| `docs/map/bodie… |
| 0x70000a7430 | 24 | 0 | 19 | `docs/map/bodies/play-inning-game-over.md:66` | 1. Calls `f_70000a7360` and `f_70000a7430` and updates two settings objects through `f_7000df2bb0` and `f_7000df7b28` (3140-3225). |
| 0x70000a7fa0 | 288 | 0 | 9 | `docs/map/binary.md:395` (+4 more) | \| 0x70000a7fa0 \| 288 \| 0 \| 9 \| `docs/map/bodies/modes.md:118` (+3 more) \| branch guarded by f_70000a7fa0, which is a stub r… |
| 0x70000a8220 | 42 | 1 | 8 | `docs/map/binary.md:396` (+3 more) | \| 0x70000a8220 \| 42 \| 1 \| 8 \| `docs/map/binary.md:398` (+2 more) \| \\| 0x70000a82e0 \\| 9 \\| 0 \\| 9 \\| `docs/map/bodies/… |
| 0x70000a82d0 | 5 | 0 | 9 | `docs/map/binary.md:541` (+2 more) | \| 0x7000a6d050 \| 150 \| 9 \| 339 \| `docs/map/bodies/intro-states.md:92` \| \\| Slot 5 \\| [C] logs "ATT_SCREEN: OptionsOnRamp.… |
| 0x70000a82e0 | 9 | 0 | 9 | `docs/map/bodies/play-inning-game-over.md:75` (+1 more) | \| else `f_70000a8220()` or `f_70000a82e0()` is true \| sub-state 13 PRES_MOMENTS_OUTRO \| 3435 \| |
| 0x70000aa6c0 | 146 | 1 | 14 | `docs/map/bodies/intro-states.md:63` (+3 more) | \| Slot 5 \| [C] logs "ATT_SCREEN: Lineup intro." (`f_7001c1fb00`, 23 callers), stores a start time at `+0x8`, sets byte `+0x28` … |
| 0x70000aaae0 | 90 | 0 | 13 | `docs/map/binary.md:400` (+3 more) | \| 0x70000aaae0 \| 90 \| 0 \| 13 \| `docs/map/binary.md:492` (+2 more) \| \\| 0x700066cf68 \\| 11 \\| 1 \\| 23 \\| `docs/map/bodi… |
| 0x70000b4b4c | 119 | 0 | 338 | `docs/map/binary.md:401` (+4 more) | \| 0x70000b4b4c \| 119 \| 0 \| 338 \| `docs/map/bodies/ai-layer.md:37` (+3 more) \| `f_70000b4b4c` (`map_find callers 0x70000b4b4… |
| 0x70000b7d34 | 0 | 0 | 5 | `docs/map/binary.md:402` (+1 more) | \| 0x70000b7d34 \| 0 \| 0 \| 5 \| `docs/map/bodies/ai-layer.md:103` \| \\| `0x70000b7d34` \\| base slot 0, empty default \\| C \\… |
| 0x70000b7d3c | 0 | 0 | 7 | `docs/map/bodies/ai-layer.md:44` | \| 2, 3 \| "interface supported" constant pair; 33 tables use the shared `0x70000b8170`/`0x70000b8178`, 14 use the base 0 \| C \|… |
| 0x70000b7d4c | 0 | 0 | 7 | `docs/map/binary.md:404` (+1 more) | \| 0x70000b7d4c \| 0 \| 0 \| 7 \| `docs/map/bodies/ai-layer.md:45` \| \\| 4 \\| default 0; only one table (`0x700216c6a0`) overri… |
| 0x70000b8090 | 0 | 0 | 31 | `docs/map/binary.md:415` (+2 more) | \| 0x70000b8590 \| 0 \| 0 \| 22 \| `docs/map/bodies/ai-layer.md:46` \| \\| 5 \\| speed/rate query, optionally plus a class-id-spe… |
| 0x70000b8170 | 0 | 0 | 7 | `docs/map/bodies/ai-layer.md:44` | \| 2, 3 \| "interface supported" constant pair; 33 tables use the shared `0x70000b8170`/`0x70000b8178`, 14 use the base 0 \| C \|… |
| 0x70000b82b0 | 0 | 0 | 8 | `docs/map/binary.md:407` (+2 more) | \| 0x70000b82b0 \| 0 \| 0 \| 8 \| `docs/map/bodies/ai-layer.md:50` \| \\| 33–36 \\| float parameter writes (turn/accel style) \\|… |
| 0x70000b8370 | 0 | 0 | 9 | `docs/map/binary.md:408` (+3 more) | \| 0x70000b8370 \| 0 \| 0 \| 9 \| `docs/map/bodies/ai-layer.md:47` \| \\| 6–19 \\| state/anim predicates and ids \\| C \\| `f_700… |
| 0x70000b8388 | 0 | 0 | 13 | `docs/map/binary.md:408` (+3 more) | \| 0x70000b8370 \| 0 \| 0 \| 9 \| `docs/map/bodies/ai-layer.md:47` \| \\| 6–19 \\| state/anim predicates and ids \\| C \\| `f_700… |
| 0x70000b83bc | 0 | 0 | 13 | `docs/map/binary.md:407` (+2 more) | \| 0x70000b82b0 \| 0 \| 0 \| 8 \| `docs/map/bodies/ai-layer.md:50` \| \\| 33–36 \\| float parameter writes (turn/accel style) \\|… |
| 0x70000b8494 | 0 | 1 | 38 | `docs/map/binary.md:420` (+1 more) | \| 0x70000ba4d4 \| 0 \| 1 \| 43 \| `docs/map/bodies/ai-layer.md:54` \| \\| 73–75 \\| bulk loco-parameter fill (7 floats + flag at… |
| 0x70000b8540 | 0 | 0 | 7 | `docs/map/binary.md:412` (+3 more) | \| 0x70000b8540 \| 0 \| 0 \| 7 \| `docs/map/bodies/ai-layer.md:56` \| \\| 90–96 \\| capability flags and byte clears \\| C \\| `f… |
| 0x70000b8548 | 0 | 0 | 7 | `docs/map/binary.md:412` (+3 more) | \| 0x70000b8540 \| 0 \| 0 \| 7 \| `docs/map/bodies/ai-layer.md:56` \| \\| 90–96 \\| capability flags and byte clears \\| C \\| `f… |
| 0x70000b8578 | 0 | 0 | 12 | `docs/map/binary.md:414` (+1 more) | \| 0x70000b8578 \| 0 \| 0 \| 12 \| `docs/map/bodies/ai-layer.md:57` \| \\| 104–118 \\| flags plus id mapping \\| C \\| `f_70000b8… |
| 0x70000b8590 | 0 | 0 | 22 | `docs/map/bodies/ai-layer.md:46` | \| 5 \| speed/rate query, optionally plus a class-id-specific bonus (90.0) \| C \| `f_70000b8090`: `fsub32(x2, 0x6)` then `0x42b4… |
| 0x70000b85c0 | 0 | 0 | 18 | `docs/map/bodies/ai-layer.md:43` | \| 0, 1 \| movement-parameter getter pair, per move type (27 tables override, base returns 0) \| C \| `f_70000b8f68`: `x2 == 2` →… |
| 0x70000b8c44 | 0 | 0 | 59 | `docs/map/binary.md:408` (+3 more) | \| 0x70000b8370 \| 0 \| 0 \| 9 \| `docs/map/bodies/ai-layer.md:47` \| \\| 6–19 \\| state/anim predicates and ids \\| C \\| `f_700… |
| 0x70000b8efc | 0 | 0 | 8 | `docs/map/binary.md:412` (+3 more) | \| 0x70000b8540 \| 0 \| 0 \| 7 \| `docs/map/bodies/ai-layer.md:56` \| \\| 90–96 \\| capability flags and byte clears \\| C \\| `f… |
| 0x70000b8f68 | 0 | 0 | 13 | `docs/map/binary.md:416` (+1 more) | \| 0x70000b85c0 \| 0 \| 0 \| 18 \| `docs/map/bodies/ai-layer.md:43` \| \\| 0, 1 \\| movement-parameter getter pair, per move type… |
| 0x70000ba4d4 | 0 | 1 | 43 | `docs/map/bodies/ai-layer.md:54` | \| 73–75 \| bulk loco-parameter fill (7 floats + flag at +0x28) \| C \| `f_70000b8494`: writes `0x42dc0000` (110.0), `0xc23f6666`… |
| 0x70000e3b50 | 440 | 4 | 86 | `docs/map/binary.md:421` (+3 more) | \| 0x70000e3b50 \| 440 \| 4 \| 86 \| `docs/map/bodies/modes.md:54` (+2 more) \| main_0099.c:622 f_70000e3b50(c); // assign node+0… |
| 0x70000e895c | 117 | 1 | 49 | `docs/map/binary.md:422` (+1 more) | \| 0x70000e895c \| 117 \| 1 \| 49 \| `docs/map/bodies/modes.md:45` \| destroys it with the recursive tree destructor f_70000e895c… |
| 0x70000e8a00 | 125 | 3 | 113 | `docs/map/binary.md:423` (+4 more) | \| 0x70000e8a00 \| 125 \| 3 \| 113 \| `docs/map/bodies/modes.md:47` (+3 more) \| [C] The map node format, read from f_70000e8a00:… |
| 0x70000f3750 | 14 | 0 | 9 | `docs/map/binary.md:424` (+2 more) | \| 0x70000f3750 \| 14 \| 0 \| 9 \| `docs/map/bodies/fielding.md:29` (+1 more) \| `"Selecting flyball intervals for %d"` (`main_00… |
| 0x7000172590 | 19 | 35 | 844 | `docs/map/binary.md:425` (+1 more) | \| 0x7000172590 \| 19 \| 35 \| 844 \| `docs/map/bodies/fielding.md:40` \| against 4 and 2 (`main_0020.c:1883-1888`), and calls, i… |
| 0x7000178ca0 | 9 | 9 | 195 | `docs/map/binary.md:426` (+1 more) | \| 0x7000178ca0 \| 9 \| 9 \| 195 \| `docs/map/bodies/fielding.md:42` \| `f_7000178ca0` (string `"Working ring"`, 9 callers). Its … |
| 0x70001810cc | 5 | 27 | 377 | `docs/map/binary.md:427` (+1 more) | \| 0x70001810cc \| 5 \| 27 \| 377 \| `docs/map/bodies/fielding.md:41` \| `"Working Ring"`, `"Moving avoid"`, 19 callers), `f_7000… |
| 0x70001c8500 | 46 | 0 | 70 | `docs/map/bodies/pre-play-in-play.md:108` | \| 0x213 \| IN_PLAY (2) or POST_PITCH (3) \| reads flag bytes in the event data (x1): +0x29 set goes to POST_PITCH; +0x21, +0x2b,… |
| 0x70001db950 | 206 | 0 | 9 | `docs/map/binary.md:429` (+1 more) | \| 0x70001db950 \| 206 \| 0 \| 9 \| `docs/map/bodies/modes.md:76` \| [C] First the prologue resolves the record: with x1 (record … |
| 0x70001e8834 | 3 | 11 | 2158 | `docs/map/bodies/play-inning-game-over.md:148` (+1 more) | The EXIT handler `f_700109cf7c` (19034-19330, 292 lines) sets sub-state 10 and prints EXIT (19314-19315). It calls `f_700107e208`… |
| 0x70001f9560 | 2 | 6 | 2284 | `docs/map/binary.md:431` (+1 more) | \| 0x70001f9560 \| 2 \| 6 \| 2284 \| `docs/map/bodies/modes.md:77` \| f_70001f9560, and leaves through 0x7000e23264 if the resolv… |
| 0x7000231000 | 5 | 0 | 23 | `docs/map/bodies/intro-states.md:47` | \| Helper `f_700108ab40` \| [C] gets the singleton at `[0x700227e128]`, sets bit 0x800000 in a flag word at `[obj+0x34]` of `[0x7… |
| 0x70002803f0 | 283 | 2 | 10 | `docs/map/bodies/pre-play-in-play.md:124` (+1 more) | \| 6 \| Event 0x5b or 0x21a arrives: sub-state 3, POST_PITCH. The run function `f_7001094afc` checks the options object from `f_7… |
| 0x700029b5c8 | 65 | 2 | 10 | `docs/map/bodies/pre-play-in-play.md:124` | \| 6 \| Event 0x5b or 0x21a arrives: sub-state 3, POST_PITCH. The run function `f_7001094afc` checks the options object from `f_7… |
| 0x70002a15d4 | 6 | 4 | 74 | `docs/map/bodies/pre-play-in-play.md:124` | \| 6 \| Event 0x5b or 0x21a arrives: sub-state 3, POST_PITCH. The run function `f_7001094afc` checks the options object from `f_7… |
| 0x70002e2348 | 293 | 2 | 10 | `docs/map/bodies/play-inning-game-over.md:126` | 4. Calls `f_700109aa1c` (below) and then loops over a few checks on `f_70002e2348` (play data) that end in `f_700109ab58` when a … |
| 0x7000378c64 | 11 | 9 | 188 | `docs/map/binary.md:437` (+1 more) | \| 0x7000378c64 \| 11 \| 9 \| 188 \| `docs/map/bodies/fielding.md:50` \| - otherwise `f_700037cf68` is asked for a sub-target; wh… |
| 0x7000379ea0 | 5 | 59 | 1436 | `docs/map/binary.md:438` (+2 more) | \| 0x7000379ea0 \| 5 \| 59 \| 1436 \| `docs/map/bodies/fielding.md:48` (+1 more) \| - `f_7000379ea0(c)` — "Canned catch" — then `… |
| 0x700037cf68 | 6 | 3 | 71 | `docs/map/binary.md:437` (+1 more) | \| 0x7000378c64 \| 11 \| 9 \| 188 \| `docs/map/bodies/fielding.md:50` \| - otherwise `f_700037cf68` is asked for a sub-target; wh… |
| 0x7000389da4 | 1 | 23 | 491 | `docs/map/binary.md:441` (+1 more) | \| 0x700038a6e0 \| 1 \| 11 \| 182 \| `docs/map/bodies/fielding.md:52` \| - the fall-through path calls `f_7000389da4` (result mas… |
| 0x700038a6e0 | 1 | 11 | 182 | `docs/map/binary.md:441` (+1 more) | \| 0x700038a6e0 \| 1 \| 11 \| 182 \| `docs/map/bodies/fielding.md:52` \| - the fall-through path calls `f_7000389da4` (result mas… |
| 0x700038a97c | 1 | 26 | 572 | `docs/map/binary.md:443` (+1 more) | \| 0x700038f844 \| 1 \| 10 \| 118 \| `docs/map/bodies/fielding.md:53` \| then `f_700038a97c` ("Working catch ring") and `f_700038… |
| 0x700038f844 | 1 | 10 | 118 | `docs/map/binary.md:443` (+1 more) | \| 0x700038f844 \| 1 \| 10 \| 118 \| `docs/map/bodies/fielding.md:53` \| then `f_700038a97c` ("Working catch ring") and `f_700038… |
| 0x7000391000 | 1 | 17 | 413 | `docs/map/binary.md:444` (+1 more) | \| 0x7000391000 \| 1 \| 17 \| 413 \| `docs/map/bodies/fielding.md:49` \| - if a flag at `+0xe0` is set, `f_7000391000(c)` (predic… |
| 0x70003915c8 | 7 | 13 | 116 | `docs/map/binary.md:445` (+1 more) | \| 0x70003915c8 \| 7 \| 13 \| 116 \| `docs/map/bodies/fielding.md:51` \| called and then `f_70003915c8(c)` recurses on the copy (… |
| 0x70003aaf00 | 4 | 1 | 10 | `docs/map/bodies/play-inning-game-over.md:20` (+2 more) | Per-frame time: PLAY_OVER slot 7 adds the time step into `[state+8]` at main_0121.c:16719. INNING_OVER slot 7 keeps it in s8 and … |
| 0x70003e53e0 | 22 | 0 | 9 | `docs/map/bodies/pre-play-in-play.md:73` | \| next of `f_700106f0d0` \| 6 or 21 \| decided from `f_70003e53e0` and `f_70003e56bc` results \| 17796 to 17901 \| |
| 0x70003e56bc | 8 | 2 | 31 | `docs/map/bodies/pre-play-in-play.md:73` | \| next of `f_700106f0d0` \| 6 or 21 \| decided from `f_70003e53e0` and `f_70003e56bc` results \| 17796 to 17901 \| |
| 0x70003eea50 | ? | ? | ? | `docs/map/binary.md:449` (+2 more) | \| 0x70003eea50 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:10` \| // PXP_SAVE.BIN, PA_SAVE.BIN read back through "ReloadSaveD… |
| 0x7000413a6c | 17 | 2 | 87 | `docs/map/bodies/frontend.md:58` | \| 0x7000bd1bfc \| hub up-grade: move with level-up validity test \| I \| same 4-vector walk plus f_7000417144 (can this slot be … |
| 0x7000413c98 | 4 | 4 | 35 | `docs/map/binary.md:451` (+3 more) | \| 0x7000413c98 \| 4 \| 4 \| 35 \| `docs/map/bodies/frontend.md:60` \| \\| 0x7000bd1f64 \\| hub up-grade: cycle which column is f… |
| 0x7000413d0c | 6 | 3 | 32 | `docs/map/binary.md:451` (+3 more) | \| 0x7000413c98 \| 4 \| 4 \| 35 \| `docs/map/bodies/frontend.md:60` \| \\| 0x7000bd1f64 \\| hub up-grade: cycle which column is f… |
| 0x7000414040 | 5 | 4 | 41 | `docs/map/binary.md:462` (+3 more) | \| 0x7000440904 \| 11 \| 3 \| 46 \| `docs/map/bodies/frontend.md:65` \| \\| 0x7000bd3140 \\| hub up-grade: spend tokens to raise … |
| 0x7000414360 | 3 | 4 | 85 | `docs/map/binary.md:451` (+3 more) | \| 0x7000413c98 \| 4 \| 4 \| 35 \| `docs/map/bodies/frontend.md:60` \| \\| 0x7000bd1f64 \\| hub up-grade: cycle which column is f… |
| 0x7000414580 | 1 | 2 | 26 | `docs/map/bodies/frontend.md:64` | \| 0x7000bd3088 \| hub up-grade: push the focus onto the focused slot \| I \| 60 lines, reads this+0x108 column, picks the focuse… |
| 0x7000415600 | 10 | 35 | 568 | `docs/map/binary.md:456` (+2 more) | \| 0x7000415600 \| 10 \| 35 \| 568 \| `docs/map/bodies/frontend.md:67` \| \\| 0x7000bd35e0 \\| hub up-grade: refresh the list aft… |
| 0x70004160c0 | 3 | 4 | 654 | `docs/map/bodies/frontend.md:66` | \| 0x7000bd33a4 \| hub up-grade: second purchase path (different cost/commit args) \| I \| same grid walk, cost from f_7000416e70… |
| 0x7000416e70 | 5 | 0 | 23 | `docs/map/binary.md:457` (+2 more) | \| 0x70004160c0 \| 3 \| 4 \| 654 \| `docs/map/bodies/frontend.md:66` \| \\| 0x7000bd33a4 \\| hub up-grade: second purchase path (… |
| 0x7000416eb0 | 8 | 0 | 27 | `docs/map/bodies/frontend.md:62` | \| 0x7000bd2340 \| hub up-grade: recompute a per-slot flag byte array over 32 slots \| I \| loops x22 = 0..0x20 step 8 and x26 = … |
| 0x7000417144 | 7 | 0 | 21 | `docs/map/binary.md:450` (+2 more) | \| 0x7000413a6c \| 17 \| 2 \| 87 \| `docs/map/bodies/frontend.md:58` \| \\| 0x7000bd1bfc \\| hub up-grade: move with level-up val… |
| 0x70004408e4 | ? | ? | ? | `docs/map/binary.md:463` (+1 more) | \| 0x700045c704 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:13` (+1 more) \| // tokens through f_70004408e4, which stores them… |
| 0x7000440904 | 11 | 3 | 46 | `docs/map/bodies/frontend.md:65` | \| 0x7000bd3140 \| hub up-grade: spend tokens to raise the focused slot \| I \| id from the 4 vectors, cost f_7000414040, compare… |
| 0x700045c704 | ? | ? | ? | `docs/map/binary.md:463` (+2 more) | \| 0x700045c704 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:13` (+1 more) \| // tokens through f_70004408e4, which stores them… |
| 0x70004a87e0 | 23 | 5 | 76 | `docs/map/binary.md:494` (+3 more) | \| 0x70006abc34 \| 99 \| 1 \| 26 \| `docs/map/bodies/frontend.md:61` \| \\| 0x7000bd20cc \\| hub up-grade: rebuild the option lis… |
| 0x70004c0eac | 3 | 6 | 102 | `docs/map/bodies/frontend.md:32` | \| 0x70004c1048 \| deleting destructor (calls 0x70004c0eac, then `operator delete`) \| C \| `musttail return f_70005b19d0` after … |
| 0x70004c1e9c | 4 | 9 | 153 | `docs/map/bodies/frontend.md:29` | \| 0x70004c77bc \| screen class vtable slot 2 (0x700217e570): per-screen entry hook, tutorial setup \| C \| in vtable slot 2 of 1… |
| 0x70004c6f30 | 4 | 14 | 162 | `docs/map/bodies/frontend.md:29` | \| 0x70004c77bc \| screen class vtable slot 2 (0x700217e570): per-screen entry hook, tutorial setup \| C \| in vtable slot 2 of 1… |
| 0x70004c779c | ? | ? | ? | `docs/map/binary.md:468` (+1 more) | \| 0x70004c779c \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:15` \| // f_70004c779c (slot 0x700217d580, three arguments, no res… |
| 0x70004d2aac | 8 | 1 | 18 | `docs/map/binary.md:469` (+2 more) | \| 0x70004d2aac \| 8 \| 1 \| 18 \| `docs/map/binary.md:469` (+2 more) \| \\| 0x70004d2aac \\| 8 \\| 1 \\| 18 \\| `docs/map/bodies… |
| 0x70005398c0 | 233 | 0 | 33 | `docs/map/bodies/batter-up.md:136` (+2 more) | - Slot 5's first act is a call to `f_70005398c0` with the value 0xace9617f (main_0120.c:52150 to 52156). If it returns true the h… |
| 0x700054aab8 | 665 | 1 | 5 | `docs/map/bodies/intro-states.md:44` | \| Slot 5 \| [C] clears a global byte (`[0x7002284000+0x9a8]`), asks `f_70000a7360` (true when `[[0x7003abfa98]+0x18c]` is 1), bu… |
| 0x700055a820 | 544 | 8 | 571 | `docs/map/bodies/lighting.md:62` | \| 0x70012c54ec \| Lighting-manager getter (lazy 0x101e40 alloc) \| C \| global `0x70045a9dc0`; `x2 = 0x1e40 \\| 0x100000` -> `f_… |
| 0x700055afd0 | 65 | 1 | 13 | `docs/map/binary.md:498` (+1 more) | \| 0x70008889d0 \| 8 \| 3 \| 21 \| `docs/map/bodies/frontend.md:26` \| \\| 0x70008b84b0 \\| UI-engine pool allocator, 725 callers… |
| 0x7000570280 | ? | ? | ? | `docs/map/binary.md:474` (+1 more) | \| 0x7000570280 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:4` \| // What the game does [C, 1.0.15 addresses; read 2026-11-20]… |
| 0x7000570c50 | ? | ? | ? | `docs/map/binary.md:475` (+1 more) | \| 0x7000570c50 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:6` \| // The game keeps files there through its file layer (locati… |
| 0x70005717f0 | 5 | 1 | 39 | `docs/map/bodies/frontend.md:20` | \| 0x700089c9e0 \| uiEngine screen switch: prints the entry log, tears down old screen, delivers enter event \| C \| stores and p… |
| 0x70005748ac | 84 | 2 | 18 | `docs/map/bodies/intro-states.md:54` (+2 more) | \| Slot 5 \| [C] zeroes phase and step, stores a start time at `+0x8` (seconds: `f_70005748ac` returns an integer tick count; the… |
| 0x7000574c40 | 343 | 3 | 144 | `docs/map/binary.md:697` (+10 more) | \| 0x70010a3814 \| 1 \| 7 \| 73 \| `docs/map/bodies/intro-states.md:75` \| \\| Slot 7 \\| [C] eight phases at `+0x18`. Every phas… |
| 0x7000589d44 | 1 | 4 | 49 | `docs/map/bodies/frontend.md:20` | \| 0x700089c9e0 \| uiEngine screen switch: prints the entry log, tears down old screen, delivers enter event \| C \| stores and p… |
| 0x70005a1300 | 22 | 2 | 17 | `docs/map/binary.md:480` (+2 more) | \| 0x70005a1300 \| 22 \| 2 \| 17 \| `docs/map/bodies/lighting.md:50` (+1 more) \| 4. **GPU wait** — flag bit 9: `f_70005a1300(2)`… |
| 0x70005a1310 | ? | ? | ? | `docs/map/binary.md:481` (+2 more) | \| 0x70005a1310 \| ? \| ? \| ? \| `runtime/gfx/vk_exec_xfer.c:410` (+1 more) \| // nvnEventGetValue for such an event (f_70005a13… |
| 0x70005a1a90 | 47 | 1 | 65 | `docs/frame-rate.md:75` (+9 more) | thread polls an event word (`nvnEventGetValue`, 1.0.20 `f_70005a1a90`) until the GPU signal at the end of the frame |
| 0x70005a4634 | ? | ? | ? | `docs/graphics-plan.md:131` (+3 more) | `nvnTextureBuilderSetSize2D`: three 1440x810 targets made by f_70005a4b88, called from f_70005a4634). The output |
| 0x70005a4b88 | ? | ? | ? | `docs/graphics-plan.md:131` (+3 more) | `nvnTextureBuilderSetSize2D`: three 1440x810 targets made by f_70005a4b88, called from f_70005a4634). The output |
| 0x70005a5368 | ? | ? | ? | `docs/graphics-plan.md:128` (+2 more) | - **Internal resolution (`MLB_RENDER_SCALE`, 2026-11-13).** The scene's size is not computed: f_70005a5368 returns entry |
| 0x70005a5388 | 2 | 0 | 14 | `docs/map/binary.md:486` (+1 more) | \| 0x70005a5388 \| 2 \| 0 \| 14 \| `runtime/mlb/resolution.c:12` \| // 1.0.20 moved them (tools/addrmap.py, checked in the disass… |
| 0x70005b19d0 | 7741 | 1 | 8 | `docs/map/binary.md:465` (+1 more) | \| 0x70004c0eac \| 3 \| 6 \| 102 \| `docs/map/bodies/frontend.md:32` \| \\| 0x70004c1048 \\| deleting destructor (calls 0x70004c0… |
| 0x70005b30b0 | 634 | 1 | 8 | `docs/map/bodies/frontend.md:46` | \| 0x700041a290 \| loads `frontend//rtts//Goals.xml` into the goal table \| C \| stores `"frontend//rtts//Goals.xml"` and `"\nLoa… |
| 0x70005e6830 | 258 | 0 | 120 | `docs/map/binary.md:490` (+6 more) | \| 0x70005e69d0 \| 215 \| 0 \| 108 \| `docs/map/binary.md:491` (+6 more) \| \\| 0x70005e6b40 \\| 964 \\| 2 \\| 140 \\| `docs/map/… |
| 0x70005e69d0 | 215 | 0 | 108 | `docs/map/binary.md:491` (+5 more) | \| 0x70005e6b40 \| 964 \| 2 \| 140 \| `docs/map/bodies/batter-up.md:73` (+7 more) \| Slot 9 calls `f_70005e6830(id, bus, this, mo… |
| 0x70005e6b40 | 964 | 2 | 140 | `docs/map/bodies/batter-up.md:73` (+7 more) | Slot 9 calls `f_70005e6830(id, bus, this, mode)` for 17 ids on the bus at `[0x7002298000+0x428]`; slot 10 calls `f_70005e69d0(id,… |
| 0x700066cf68 | 11 | 1 | 23 | `docs/map/bodies/pre-play-in-play.md:70` | \| 1 \| 2, 13 or 14 \| 13 if `f_70000aaae0` is true and `[[0x700227e688]+0x28] == 0` and `f_700066cf68` is true; 14 if the last t… |
| 0x70006753d0 | 7 | 14 | 406 | `docs/map/binary.md:493` (+4 more) | \| 0x70006753d0 \| 7 \| 14 \| 406 \| `docs/map/bodies/modes.md:19` (+3 more) \| (4 groups × 23 stats, 10 × 0x30 bytes each) fille… |
| 0x70006abc34 | 99 | 1 | 26 | `docs/map/bodies/frontend.md:61` | \| 0x7000bd20cc \| hub up-grade: rebuild the option list from career data \| I \| only caller of 0x7000bd22e4; uses f_70004a87e0,… |
| 0x70006b9da4 | 71 | 1 | 19 | `docs/map/bodies/frontend.md:61` | \| 0x7000bd20cc \| hub up-grade: rebuild the option list from career data \| I \| only caller of 0x7000bd22e4; uses f_70004a87e0,… |
| 0x70008187f0 | 27 | 4 | 100 | `docs/map/bodies/frontend.md:37` | \| 0x700085cb60 \| uiElementDataTable: applies a dirty mask and pushes data to rows/cells \| C \| `"uiElementDataTable Mask 0x%lx… |
| 0x700085d6c0 | 2 | 4 | 80 | `docs/map/bodies/frontend.md:37` | \| 0x700085cb60 \| uiElementDataTable: applies a dirty mask and pushes data to rows/cells \| C \| `"uiElementDataTable Mask 0x%lx… |
| 0x70008889d0 | 8 | 3 | 21 | `docs/map/bodies/frontend.md:26` | \| 0x70008b84b0 \| UI-engine pool allocator, 725 callers \| C \| looks up pool 0x7002289f78, calls f_700055afd0(pool,id,1); on fa… |
| 0x7000888a50 | 11 | 0 | 5 | `docs/map/bodies/frontend.md:20` | \| 0x700089c9e0 \| uiEngine screen switch: prints the entry log, tears down old screen, delivers enter event \| C \| stores and p… |
| 0x70008898c4 | 94 | 0 | 16 | `docs/map/binary.md:500` (+1 more) | \| 0x70008898c4 \| 94 \| 0 \| 16 \| `docs/map/binary.md:500` (+1 more) \| \\| 0x70008898c4 \\| 94 \\| 0 \\| 16 \\| `docs/map/bodi… |
| 0x700089c720 | 156 | 4 | 85 | `docs/map/bodies/frontend.md:28` | \| 0x70004c6f30 \| front-end go-to-screen helper with screen special cases \| C \| compares the name with `"r_Progress"`, `"Profi… |
| 0x700089c9e0 | 5 | 22 | 364 | `docs/map/bodies/frontend.md:21` (+1 more) | \| 0x700089c720 \| uiEngine screen request by id (0xff is what the leave path passes), 156 callers \| C \| locks +0x218/+0x220 de… |
| 0x700089d4e0 | 325 | 2 | 25 | `docs/map/bodies/frontend.md:30` | \| 0x70004c7918 \| screen vtable slot 3: name match then leave hook \| C \| compares x1+0x60 with the std::string at this+0xc0 (S… |
| 0x70008a71f0 | 2 | 5 | 235 | `docs/map/bodies/frontend.md:20` | \| 0x700089c9e0 \| uiEngine screen switch: prints the entry log, tears down old screen, delivers enter event \| C \| stores and p… |
| 0x70008a846c | 13 | 5 | 58 | `docs/map/bodies/play-inning-game-over.md:80` | MERCY_RULE (value 1) is entered by `f_70010906bc` (main_0121.c:4137-4227). It calls `f_7000e23cec` with the current sub-state, se… |
| 0x70008b87c8 | 92 | 6 | 105 | `docs/map/bodies/frontend.md:21` | \| 0x700089c720 \| uiEngine screen request by id (0xff is what the leave path passes), 156 callers \| C \| locks +0x218/+0x220 de… |
| 0x70008bb110 | 452 | 2 | 51 | `docs/map/binary.md:507` (+1 more) | \| 0x70008bb110 \| 452 \| 2 \| 51 \| `docs/map/bodies/frontend.md:103` \| - The runtime side (how `MLB_*` / hid input reaches f_7… |
| 0x70008c6460 | ? | ? | ? | `docs/map/source/runtime-gfx.md:736` (+3 more) | \| `obs_release_read` \| 778-793 \| static void (Cpu *) \| rt_original, cfg_bool, kern_core_away, plat_sleep_ms, fence_done, gfx_… |
| 0x70008dc5b0 | ? | ? | ? | `docs/map/binary.md:509` (+1 more) | \| 0x70008dc5b0 \| ? \| ? \| ? \| `runtime/mlb/tutorials.c:7` \| // P = *(*(*0x7003abda98 + 0x198) + 0x318) (f_70008dc5b0 returns… |
| 0x70008e40a4 | 1 | 0 | 9 | `docs/map/bodies/intro-states.md:44` | \| Slot 5 \| [C] clears a global byte (`[0x7002284000+0x9a8]`), asks `f_70000a7360` (true when `[[0x7003abfa98]+0x18c]` is 1), bu… |
| 0x700092ae20 | 147 | 1 | 140 | `docs/map/binary.md:511` (+5 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x700092ce50 | 152 | 0 | 161 | `docs/map/binary.md:511` (+4 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x700093b09c | 0 | 2 | 68 | `docs/map/binary.md:513` (+1 more) | \| 0x700093b09c \| 0 \| 2 \| 68 \| `tools/packages/server_msgs.py:252` \| # 0x1b26202c -> CPartyManager::OnConductorAnswer(endpoi… |
| 0x7000946e20 | 1 | 3 | 24 | `docs/map/binary.md:514` (+1 more) | \| 0x7000946e20 \| 1 \| 3 \| 24 \| `tools/packages/profile_state.py:3` \| u8 counter} and only the server message 0xAFE1519A {u32… |
| 0x70009a6e58 | 3 | 5 | 32 | `docs/map/binary.md:515` (+2 more) | \| 0x70009a6e58 \| 3 \| 5 \| 32 \| `tools/packages/server_msgs.py:246` \| # echo choice: CPluginAuth+0x54 (= CNetSession+0x59, se… |
| 0x70009a7454 | 1 | 10 | 207 | `docs/map/binary.md:765` (+2 more) | \| 0x700151c1dc \| 3 \| 20 \| 358 \| `tools/packages/server_msgs.py:253` \| # - Service connect f_70009a7454: inet_ntop(Endpoint … |
| 0x70009a7800 | 0 | 4 | 48 | `docs/map/binary.md:517` (+1 more) | \| 0x70009a7800 \| 0 \| 4 \| 48 \| `tools/packages/server_msgs.py:251` \| # 0x07b7014f -> OnConductorAnswer(endpoint, plugin guid… |
| 0x70009b29b0 | 2 | 4 | 46 | `docs/map/binary.md:518` (+1 more) | \| 0x70009b29b0 \| 2 \| 4 \| 46 \| `tools/packages/server_msgs.py:162` \| keep_session=0 makes CNetPlayer wipe its cached Account… |
| 0x70009b2a54 | 1 | 0 | 8 | `docs/map/binary.md:515` (+2 more) | \| 0x70009a6e58 \| 3 \| 5 \| 32 \| `tools/packages/server_msgs.py:246` \| # echo choice: CPluginAuth+0x54 (= CNetSession+0x59, se… |
| 0x70009e7fb4 | 0 | 38 | 1031 | `docs/map/binary.md:520` (+2 more) | \| 0x70009e7fb4 \| 0 \| 38 \| 1031 \| `tools/packages/server_msgs.py:15` (+1 more) \| # auth connection (CPluginAuth, f_70009e7fb… |
| 0x70009e8e10 | 1 | 13 | 252 | `docs/map/binary.md:521` (+1 more) | \| 0x70009e8e10 \| 1 \| 13 \| 252 \| `tools/packages/server_msgs.py:247` \| # -> 0x0ca403f1; else f_70009e8e10 'AttemptLinkDevice… |
| 0x70009f100c | 2 | 9 | 174 | `docs/map/binary.md:522` (+3 more) | \| 0x70009f100c \| 2 \| 9 \| 174 \| `tools/packages/server_msgs.py:30` (+1 more) \| # conductor connection (conductor plugin f_70… |
| 0x70009f1400 | 0 | 0 | 69 | `docs/map/binary.md:522` (+3 more) | \| 0x70009f100c \| 2 \| 9 \| 174 \| `tools/packages/server_msgs.py:30` (+1 more) \| # conductor connection (conductor plugin f_70… |
| 0x70009f85a0 | 29 | 0 | 14 | `docs/map/binary.md:524` (+1 more) | \| 0x70009f85a0 \| 29 \| 0 \| 14 \| `tools/packages/rpc.py:8` \| f_70009f85a0 request_id = global counter @0x7003abf068 (returns … |
| 0x70009f85c0 | 6 | 8 | 234 | `docs/map/binary.md:525` (+4 more) | \| 0x70009f85c0 \| 6 \| 8 \| 234 \| `docs/map/source/tools-packages.md:119` (+2 more) \| \\| `pending_key` \\| 185-191 \\| \\| en… |
| 0x70009f8c4c | 0 | 4 | 46 | `docs/map/binary.md:526` (+1 more) | \| 0x70009f8c4c \| 0 \| 4 \| 46 \| `tools/packages/rpc.py:49` \| 0x7C335915 ServiceConnect C->S, sent once when the plugin attach… |
| 0x70009f8cf0 | 0 | 6 | 253 | `docs/map/binary.md:527` (+2 more) | \| 0x70009f8cf0 \| 0 \| 6 \| 253 \| `tools/packages/rpc.py:21` (+1 more) \| Timeout: f_70009f8cf0 synthesises a ServiceResponse w… |
| 0x70009f9070 | 0 | 13 | 378 | `docs/map/binary.md:525` (+4 more) | \| 0x70009f85c0 \| 6 \| 8 \| 234 \| `docs/map/source/tools-packages.md:119` (+2 more) \| \\| `pending_key` \\| 185-191 \\| \\| en… |
| 0x7000a12970 | 30 | 33 | 492 | `docs/map/binary.md:529` (+1 more) | \| 0x7000a12970 \| 30 \| 33 \| 492 \| `tools/packages/rpc.py:7` \| f_7000a12970 Transaction::Run "STARTING SERVICE [%s]" ... "SEN… |
| 0x7000a13298 | 0 | 16 | 281 | `docs/map/binary.md:530` (+7 more) | \| 0x7000a13298 \| 0 \| 16 \| 281 \| `docs/map/source/tools-packages.md:117` (+6 more) \| \\| `make_response_xml` \\| 152-159 \\|… |
| 0x7000a15440 | 11 | 13 | 177 | `docs/map/binary.md:531` (+1 more) | \| 0x7000a15440 \| 11 \| 13 \| 177 \| `tools/packages/rpc.py:9` \| f_7000a15440 params map -> JSON text (types 1..8); type-9 para… |
| 0x7000a32a5c | ? | ? | ? | `docs/map/binary.md:532` (+2 more) | \| 0x7000a32a5c \| ? \| ? \| ? \| `runtime/mlb/tutorials.c:11` (+1 more) \| // the name is there. f_7000a32a5c(P, name) adds a na… |
| 0x7000a32ce0 | ? | ? | ? | `docs/map/binary.md:533` (+1 more) | \| 0x7000a32ce0 \| ? \| ? \| ? \| `runtime/mlb/tutorials.c:10` \| // f_7000a32ce0(P, name) says whether a name is in the list; th… |
| 0x7000a3b7e0 | 32 | 7 | 63 | `docs/map/binary.md:534` (+2 more) | \| 0x7000a3b7e0 \| 32 \| 7 \| 63 \| `docs/map/bodies/modes.md:116` \| f_7000a3bcac, wrapped by begin/end calls f_7000a3c6e8 / f_7… |
| 0x7000a3bcac | 3 | 1 | 7 | `docs/map/binary.md:534` (+2 more) | \| 0x7000a3b7e0 \| 32 \| 7 \| 63 \| `docs/map/bodies/modes.md:116` \| f_7000a3bcac, wrapped by begin/end calls f_7000a3c6e8 / f_7… |
| 0x7000a3c190 | 32 | 13 | 143 | `docs/map/binary.md:534` (+2 more) | \| 0x7000a3b7e0 \| 32 \| 7 \| 63 \| `docs/map/bodies/modes.md:116` \| f_7000a3bcac, wrapped by begin/end calls f_7000a3c6e8 / f_7… |
| 0x7000a3c6e8 | 21 | 0 | 15 | `docs/map/binary.md:534` (+2 more) | \| 0x7000a3b7e0 \| 32 \| 7 \| 63 \| `docs/map/bodies/modes.md:116` \| f_7000a3bcac, wrapped by begin/end calls f_7000a3c6e8 / f_7… |
| 0x7000a49df8 | 3 | 2 | 24 | `docs/map/binary.md:538` (+1 more) | \| 0x7000a49df8 \| 3 \| 2 \| 24 \| `docs/map/binary.md:538` (+1 more) \| \\| 0x7000a49df8 \\| 3 \\| 2 \\| 24 \\| `docs/map/bodies… |
| 0x7000a52ee4 | 3 | 0 | 9 | `docs/map/bodies/pre-play-in-play.md:37` (+1 more) | Slot 3 writes -1 and slot 5 writes 1. Slot 7 also handles the value 0: it moves to 1 once `f_7000a52ee4` returns true. How the fi… |
| 0x7000a62db4 | 32 | 9 | 84 | `docs/map/binary.md:540` (+1 more) | \| 0x7000a62db4 \| 32 \| 9 \| 84 \| `tools/packages/rpc.py:19` \| msg.xml != "timedout"; parses msg.xml (f_7000a62db4: TinyXML2 d… |
| 0x7000a6d050 | 150 | 9 | 339 | `docs/map/bodies/intro-states.md:92` | \| Slot 5 \| [C] logs "ATT_SCREEN: OptionsOnRamp.", clears `+0x26`, `+0x8`, `+0x3a`, `+0x44`, sets `+0x30`, checks `f_70000a82d0`… |
| 0x7000a8325c | 15 | 0 | 17 | `docs/map/bodies/play-inning-game-over.md:127` (+1 more) | 5. Sets `[state+0x24]` to 1 (16220) when `f_70000a7360` or `f_7000a8325c` is true; otherwise sets it to 0 and prints WAIT (16228-… |
| 0x7000bd1da0 | ? | ? | ? | `docs/map/binary.md:544` (+1 more) | \| 0x7000bd3140 \| 0 \| 12 \| 177 \| `runtime/mlb/rtts_autosave.c:14` \| // returns. A trigger upgrade goes through f_7000bd1da0 … |
| 0x7000bd3140 | 0 | 12 | 177 | `docs/map/binary.md:544` (+1 more) | \| 0x7000bd3140 \| 0 \| 12 \| 177 \| `runtime/mlb/rtts_autosave.c:14` \| // returns. A trigger upgrade goes through f_7000bd1da0 … |
| 0x7000bd3f80 | 4 | 8 | 338 | `docs/map/binary.md:456` (+2 more) | \| 0x7000415600 \| 10 \| 35 \| 568 \| `docs/map/bodies/frontend.md:67` \| \\| 0x7000bd35e0 \\| hub up-grade: refresh the list aft… |
| 0x7000bd5398 | 1 | 0 | 53 | `docs/map/bodies/frontend.md:68` | \| 0x7000bd3f80 \| hub up-grade: rebuild the visible rows after a change \| I \| reads this+0x109 and this+0xa2, scans the global… |
| 0x7000bd559c | 8 | 27 | 1347 | `docs/map/bodies/frontend.md:59` (+3 more) | \| 0x7000bd1d98 \| hub up-grade: apply the focused upgrade (selection-object path) \| I \| x2 must be non-zero, reads the selecti… |
| 0x7000d197fc | ? | ? | ? | `docs/map/binary.md:548` (+1 more) | \| 0x7000d197fc \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:7` \| // CUSTOMCAMS_<n>.CAM custom batting cameras (looked up by f… |
| 0x7000d199bc | ? | ? | ? | `docs/map/binary.md:549` (+1 more) | \| 0x7000d199bc \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:8` \| // f_7000d199bc) \| |
| 0x7000d1e7b8 | 268 | 0 | 11 | `docs/map/bodies/intro-states.md:73` | \| Slot 5 \| [C] posts event 0x218, clears `+0x8`, `+0x22`, sets `+0x28` to 8, logs "ATT_SCREEN: Pitcher warmup." (`main_0121.c:2… |
| 0x7000d1eef4 | 22 | 9 | 294 | `docs/map/bodies/batter-up.md:125` | \| 33 \| `ead0` \| when two virtual queries pass and the sub-state is 0xb or 2, call `f_7000d1eef4(global, 1)`; always set step 3… |
| 0x7000d438d4 | 11 | 1 | 40 | `docs/map/bodies/pre-play-in-play.md:108` | \| 0x213 \| IN_PLAY (2) or POST_PITCH (3) \| reads flag bytes in the event data (x1): +0x29 set goes to POST_PITCH; +0x21, +0x2b,… |
| 0x7000d52680 | 7 | 8 | 235 | `docs/map/bodies/lighting.md:73` (+3 more) | \| 0x70012d0fcc \| Per-frame lighting request/gate \| C \| `LD8([x0+0xc43])`; `[x9+0xb8] == 0x78`; `LD8([x0+0xc2d])`; calls `f_70… |
| 0x7000d558b0 | 13 | 1 | 7 | `docs/map/bodies/intro-states.md:47` | \| Helper `f_700108ab40` \| [C] gets the singleton at `[0x700227e128]`, sets bit 0x800000 in a flag word at `[obj+0x34]` of `[0x7… |
| 0x7000d558b8 | 6 | 2 | 21 | `docs/map/bodies/intro-states.md:83` | \| Slot 5 \| [C] sets the input context to 0x11 (`f_7000f2598c`), clears a byte at `[0x7002294220]`, calls `f_7000d558b8` with th… |
| 0x7000d6d22c | 6 | 18 | 180 | `docs/map/bodies/batter-up.md:78` | \| 0x290 \| if a virtual call on this is true, calls `f_7000d6d22c` on a global, then resets the timer \| C \| |
| 0x7000d7412c | 16 | 2 | 15 | `docs/map/bodies/play-inning-game-over.md:189` | \| 0 NORMAL \| per-frame call through the object at `0x700227e128` (virtual slot 0x38, with the time step), then phases 0 to 5: w… |
| 0x7000d81dd8 | 121 | 0 | 9 | `docs/map/binary.md:607` (+4 more) | \| 0x700106d054 \| 0 \| 1 \| 35 \| `docs/map/bodies/pre-play-in-play.md:19` (+2 more) \| \\| 3 \\| `f_700106cfc4`: sets up the ob… |
| 0x7000d82738 | 1 | 0 | 11 | `docs/map/bodies/batter-up.md:116` | \| 6 \| `dca4` \| exit: clear flags, call `f_7000d82738` and `f_700134df20(0)`, sub-state 0 \| C \| |
| 0x7000d931e0 | 15 | 0 | 42 | `docs/map/bodies/intro-states.md:104` | \| `f_7000f2598c(obj, id, flag)` \| stores `id` at `[obj+0x28]` and calls `f_7000d931e0` with it when the id is 1 to 0x12 (it sto… |
| 0x7000d9b008 | 6 | 5 | 74 | `docs/map/binary.md:469` (+2 more) | \| 0x70004d2aac \| 8 \| 1 \| 18 \| `docs/map/binary.md:469` (+2 more) \| \\| 0x70004d2aac \\| 8 \\| 1 \\| 18 \\| `docs/map/bodies… |
| 0x7000daea5c | 5 | 1 | 15 | `docs/map/binary.md:562` (+1 more) | \| 0x7000daea5c \| 5 \| 1 \| 15 \| `docs/map/binary.md:562` (+1 more) \| \\| 0x7000daea5c \\| 5 \\| 1 \\| 15 \\| `docs/map/bodies… |
| 0x7000de6728 | ? | ? | ? | `docs/map/binary.md:563` (+1 more) | \| 0x7000de6728 \| ? \| ? \| ? \| `runtime/mlb/rtts_autosave.c:8` \| // f_7000de6728 (no arguments) is the career autosave the ga… |
| 0x7000df2818 | 91 | 7 | 151 | `docs/map/binary.md:564` (+1 more) | \| 0x7000df2818 \| 91 \| 7 \| 151 \| `docs/map/bodies/frontend.md:76` \| \\| 0x700183af10 \\| loads/copies a player profile (D_PL… |
| 0x7000df2bb0 | 55 | 0 | 8 | `docs/map/bodies/play-inning-game-over.md:66` (+1 more) | 1. Calls `f_70000a7360` and `f_70000a7430` and updates two settings objects through `f_7000df2bb0` and `f_7000df7b28` (3140-3225). |
| 0x7000df63a0 | 112 | 9 | 92 | `docs/map/binary.md:566` (+4 more) | \| 0x7000df63a0 \| 112 \| 9 \| 92 \| `docs/map/bodies/modes.md:13` (+3 more) \| 46 `pinpoint_*`, 12 `option_*`, mode/team/player … |
| 0x7000df7b28 | 7 | 0 | 7 | `docs/map/bodies/play-inning-game-over.md:66` | 1. Calls `f_70000a7360` and `f_70000a7430` and updates two settings objects through `f_7000df2bb0` and `f_7000df7b28` (3140-3225). |
| 0x7000df7d2c | 4 | 18 | 182 | `docs/map/binary.md:568` (+2 more) | \| 0x7000df7d2c \| 4 \| 18 \| 182 \| `docs/map/bodies/modes.md:14` (+1 more) \| section name. Its caller f_7000df7fc0 is reached … |
| 0x7000df7fc0 | 1 | 29 | 1142 | `docs/map/binary.md:568` (+7 more) | \| 0x7000df7d2c \| 4 \| 18 \| 182 \| `docs/map/bodies/modes.md:14` (+1 more) \| section name. Its caller f_7000df7fc0 is reached … |
| 0x7000e02b98 | 4 | 21 | 811 | `docs/map/bodies/pre-play-in-play.md:121` (+1 more) | \| 3 \| Each update of IN_PITCH, IN_PLAY and POST_PITCH adds the time step to a float at +0x30. If it passes 30.0 and +0x2e is 0,… |
| 0x7000e03780 | 4 | 19 | 489 | `docs/map/bodies/pre-play-in-play.md:121` (+2 more) | \| 3 \| Each update of IN_PITCH, IN_PLAY and POST_PITCH adds the time step to a float at +0x30. If it passes 30.0 and +0x2e is 0,… |
| 0x7000e03ea0 | 1 | 58 | 3886 | `docs/map/bodies/modes.md:229` | \| 0x7000df7fc0 \| Drives the record builder: 2 team calls, the end-of-game summary, then 80 batter + 80 pitcher calls; vtable 0x… |
| 0x7000e0fb10 | 1 | 57 | 21030 | `docs/map/binary.md:573` (+2 more) | \| 0x7000e0fb10 \| 1 \| 57 \| 21030 \| `docs/map/bodies/modes.md:120` (+1 more) \| [C] Who calls it: f_7000e0fb10 ← f_7000df7fc0 … |
| 0x7000e23cec | 56 | 1 | 26 | `docs/map/binary.md:505` (+22 more) | \| 0x70008a846c \| 13 \| 5 \| 58 \| `docs/map/bodies/play-inning-game-over.md:80` \| MERCY_RULE (value 1) is entered by `f_700109… |
| 0x7000e4c0d4 | 67 | 7 | 148 | `docs/map/binary.md:575` (+1 more) | \| 0x7000e4c0d4 \| 67 \| 7 \| 148 \| `docs/map/bodies/modes.md:289` \| - f_7000e4c0d4 (148L, 67 callers, only string "9AGQ_") is … |
| 0x7000e53620 | 1 | 4 | 18 | `docs/map/binary.md:576` (+3 more) | \| 0x7000e53620 \| 1 \| 4 \| 18 \| `docs/map/bodies/modes.md:214` (+2 more) \| up to 1350 players and a qsort_r). Its full refres… |
| 0x7000e53654 | 2 | 18 | 675 | `docs/map/binary.md:578` (+12 more) | \| 0x7000e54080 \| 3 \| 0 \| 211 \| `docs/map/bodies/modes.md:250` (+2 more) \| \\| 0x7000e53620 \\| Game-start sequence: calls f… |
| 0x7000e54080 | 3 | 0 | 211 | `docs/map/binary.md:578` (+4 more) | \| 0x7000e54080 \| 3 \| 0 \| 211 \| `docs/map/bodies/modes.md:250` (+2 more) \| \\| 0x7000e53620 \\| Game-start sequence: calls f… |
| 0x7000e543a4 | 3 | 4 | 156 | `docs/map/binary.md:578` (+10 more) | \| 0x7000e54080 \| 3 \| 0 \| 211 \| `docs/map/bodies/modes.md:250` (+2 more) \| \\| 0x7000e53620 \\| Game-start sequence: calls f… |
| 0x7000e545f0 | 3 | 10 | 406 | `docs/map/binary.md:578` (+3 more) | \| 0x7000e54080 \| 3 \| 0 \| 211 \| `docs/map/bodies/modes.md:250` (+2 more) \| \\| 0x7000e53620 \\| Game-start sequence: calls f… |
| 0x7000e54c00 | 2 | 11 | 685 | `docs/map/binary.md:581` (+11 more) | \| 0x7000e54c00 \| 2 \| 11 \| 685 \| `docs/map/binary.md:581` (+11 more) \| \\| 0x7000e54c00 \\| 2 \\| 11 \\| 685 \\| `docs/map/b… |
| 0x7000e5640c | 1 | 26 | 694 | `docs/map/binary.md:576` (+6 more) | \| 0x7000e53620 \| 1 \| 4 \| 18 \| `docs/map/bodies/modes.md:214` (+2 more) \| up to 1350 players and a qsort_r). Its full refres… |
| 0x7000e59c50 | 0 | 124 | 5856 | `docs/map/bodies/modes.md:249` | \| 0x7000e5640c \| Inning-change leaders refresh: calls f_7000e53654 then f_7000e543a4 (double build) \| [C] \| main_0101.c:7091/… |
| 0x7000eb466c | 10 | 1 | 25 | `docs/map/binary.md:660` (+1 more) | \| 0x7001093558 \| 1 \| 4 \| 101 \| `docs/map/bodies/play-inning-game-over.md:198` \| Slot 6 `f_70010934d8` (7560-7602) clears by… |
| 0x7000eb6abc | 1 | 5 | 53 | `docs/map/bodies/intro-states.md:84` | \| Slot 7 \| [C] each frame calls virtual +0x38 on the singleton at `[0x700227e128]`. When phase is 0 and step is 0 it calls `f_7… |
| 0x7000ecfe38 | 2 | 1 | 15 | `docs/map/binary.md:589` (+5 more) | \| 0x7000ed12b8 \| 1 \| 7 \| 88 \| `docs/map/bodies/intro-states.md:93` \| \\| Slot 7 \\| [C] ten phases at `+0x18`. It calls `f_… |
| 0x7000ecfe80 | 2 | 1 | 15 | `docs/map/binary.md:589` (+5 more) | \| 0x7000ed12b8 \| 1 \| 7 \| 88 \| `docs/map/bodies/intro-states.md:93` \| \\| Slot 7 \\| [C] ten phases at `+0x18`. It calls `f_… |
| 0x7000ed05b8 | 2 | 22 | 299 | `docs/map/bodies/intro-states.md:92` | \| Slot 5 \| [C] logs "ATT_SCREEN: OptionsOnRamp.", clears `+0x26`, `+0x8`, `+0x3a`, `+0x44`, sets `+0x30`, checks `f_70000a82d0`… |
| 0x7000ed12b8 | 1 | 7 | 88 | `docs/map/bodies/intro-states.md:93` | \| Slot 7 \| [C] ten phases at `+0x18`. It calls `f_7000ecfe38` and `f_7000ecfe80`, two 15-line functions whose strings are "Hide… |
| 0x7000ed13e8 | 1 | 11 | 144 | `docs/map/bodies/intro-states.md:93` | \| Slot 7 \| [C] ten phases at `+0x18`. It calls `f_7000ecfe38` and `f_7000ecfe80`, two 15-line functions whose strings are "Hide… |
| 0x7000ed15e8 | 1 | 7 | 102 | `docs/map/bodies/intro-states.md:93` | \| Slot 7 \| [C] ten phases at `+0x18`. It calls `f_7000ecfe38` and `f_7000ecfe80`, two 15-line functions whose strings are "Hide… |
| 0x7000ed1738 | 1 | 5 | 58 | `docs/map/bodies/intro-states.md:93` | \| Slot 7 \| [C] ten phases at `+0x18`. It calls `f_7000ecfe38` and `f_7000ecfe80`, two 15-line functions whose strings are "Hide… |
| 0x7000ed1800 | 1 | 8 | 299 | `docs/map/bodies/intro-states.md:93` | \| Slot 7 \| [C] ten phases at `+0x18`. It calls `f_7000ecfe38` and `f_7000ecfe80`, two 15-line functions whose strings are "Hide… |
| 0x7000ed2780 | 319 | 0 | 9 | `docs/map/bodies/play-inning-game-over.md:193` | \| 3 CHECK_SUB \| reads bytes `[ctx+0x784]`, `[ctx+0x125]` and the value `[ctx+0x12c]` (7173-7180), clears bit 22 of `[global 0x7… |
| 0x7000ed5528 | 8 | 4 | 79 | `docs/map/bodies/play-inning-game-over.md:90` | \| `[state+0x24]` \| result of `f_7000ed5528` (3227-3229) \| C \| |
| 0x7000ed562c | 1 | 15 | 148 | `docs/map/bodies/play-inning-game-over.md:193` (+3 more) | \| 3 CHECK_SUB \| reads bytes `[ctx+0x784]`, `[ctx+0x125]` and the value `[ctx+0x12c]` (7173-7180), clears bit 22 of `[global 0x7… |
| 0x7000f1ec9c | 1 | 1 | 10 | `docs/map/bodies/intro-states.md:63` | \| Slot 5 \| [C] logs "ATT_SCREEN: Lineup intro." (`f_7001c1fb00`, 23 callers), stores a start time at `+0x8`, sets byte `+0x28` … |
| 0x7000f2598c | 62 | 2 | 33 | `docs/map/binary.md:560` (+6 more) | \| 0x7000d931e0 \| 15 \| 0 \| 42 \| `docs/map/binary.md:560` (+1 more) \| \\| 0x7000d931e0 \\| 15 \\| 0 \\| 42 \\| `docs/map/bodi… |
| 0x7000f281b0 | 0 | 2 | 47 | `docs/map/bodies/batter-up.md:63` | \| +0x28 \| byte flag; slot 5 stores a call result here, outside code sets it 1 or 0, `e4ec` returns it \| C \| `f_7000f282b4`, `… |
| 0x7000f282b4 | 0 | 1 | 35 | `docs/map/binary.md:599` (+1 more) | \| 0x7000f281b0 \| 0 \| 2 \| 47 \| `docs/map/bodies/batter-up.md:63` \| \\| +0x28 \\| byte flag; slot 5 stores a call result here… |
| 0x7000f2868c | 1 | 2 | 22 | `docs/map/binary.md:601` (+1 more) | \| 0x7000f2868c \| 1 \| 2 \| 22 \| `docs/map/binary.md:601` (+1 more) \| \\| 0x7000f2868c \\| 1 \\| 2 \\| 22 \\| `docs/map/bodies… |
| 0x7000f29804 | 2 | 4 | 109 | `docs/map/bodies/batter-up.md:134` | - What the 7.0 second value times, and why a countdown ends in MANAGER_MODE: `e4ec` compares the timer with the float at the poin… |
| 0x7000f34134 | 1 | 0 | 12 | `docs/map/bodies/intro-states.md:84` | \| Slot 7 \| [C] each frame calls virtual +0x38 on the singleton at `[0x700227e128]`. When phase is 0 and step is 0 it calls `f_7… |
| 0x7000f622dc | 4 | 10 | 147 | `docs/map/bodies/intro-states.md:65` | \| Slot 7 \| [C] phase machine over phases 1 to 7 and steps 1 to 3. Each phase calls `f_7000e23cec(state, phase)` when it changes… |
| 0x7001029cd8 | ? | ? | ? | `docs/map/binary.md:449` (+2 more) | \| 0x70003eea50 \| ? \| ? \| ? \| `runtime/mlb/cache_storage.c:10` \| // PXP_SAVE.BIN, PA_SAVE.BIN read back through "ReloadSaveD… |
| 0x700106cfc4 | 0 | 2 | 42 | `docs/map/binary.md:558` (+3 more) | \| 0x7000d81dd8 \| 121 \| 0 \| 9 \| `docs/map/binary.md:607` (+4 more) \| \\| 0x700106d054 \\| 0 \\| 1 \\| 35 \\| `docs/map/bodie… |
| 0x700106d054 | 0 | 1 | 35 | `docs/map/bodies/pre-play-in-play.md:19` (+2 more) | \| 3 \| `f_700106cfc4`: sets up the object. Writes -1 to +0x18, fetches an object from `f_7000d81dd8` into +0x20, sets flags at +… |
| 0x700106d0c8 | 0 | 2 | 41 | `docs/map/binary.md:608` (+2 more) | \| 0x700106d0c8 \| 0 \| 2 \| 41 \| `docs/map/binary.md:662` (+1 more) \| \\| 0x7001093730 \\| 0 \\| 5 \\| 36 \\| `docs/map/bodies… |
| 0x700106d154 | 0 | 6 | 36 | `docs/map/binary.md:609` (+2 more) | \| 0x700106d154 \| 0 \| 6 \| 36 \| `docs/map/binary.md:663` (+1 more) \| \\| 0x70010937a0 \\| 0 \\| 3 \\| 32 \\| `docs/map/bodies… |
| 0x700106d1cc | 0 | 1 | 48 | `docs/map/binary.md:610` (+2 more) | \| 0x700106d1cc \| 0 \| 1 \| 48 \| `docs/map/binary.md:664` (+1 more) \| \\| 0x7001093804 \\| 0 \\| 1 \\| 123 \\| `docs/map/bodie… |
| 0x700106d438 | 0 | 1 | 40 | `docs/map/binary.md:611` (+2 more) | \| 0x700106d438 \| 0 \| 1 \| 40 \| `docs/map/binary.md:666` (+1 more) \| \\| 0x700109419c \\| 0 \\| 1 \\| 102 \\| `docs/map/bodie… |
| 0x700106d4c4 | 0 | 54 | 1270 | `docs/map/binary.md:612` (+2 more) | \| 0x700106d4c4 \| 0 \| 54 \| 1270 \| `docs/map/binary.md:612` (+1 more) \| \\| 0x700106d4c4 \\| 0 \\| 54 \\| 1270 \\| `docs/map/… |
| 0x700106e610 | 1 | 14 | 131 | `docs/map/binary.md:615` (+6 more) | \| 0x700106e968 \| 1 \| 8 \| 71 \| `docs/map/bodies/pre-play-in-play.md:5` (+7 more) \| What was read in full: the PRE_PLAY vtabl… |
| 0x700106e7e4 | 1 | 3 | 112 | `docs/map/binary.md:616` (+14 more) | \| 0x700106ea54 \| 1 \| 10 \| 88 \| `docs/map/binary.md:624` (+9 more) \| \\| 0x700106f598 \\| 1 \\| 5 \\| 65 \\| `docs/map/bodie… |
| 0x700106e968 | 1 | 8 | 71 | `docs/map/bodies/pre-play-in-play.md:5` (+7 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x700106ea54 | 1 | 10 | 88 | `docs/map/binary.md:624` (+9 more) | \| 0x700106f598 \| 1 \| 5 \| 65 \| `docs/map/bodies/pre-play-in-play.md:154` \| \\| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea… |
| 0x700106eb90 | 1 | 6 | 81 | `docs/map/bodies/pre-play-in-play.md:5` (+5 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x700106ecac | 1 | 13 | 257 | `docs/map/bodies/pre-play-in-play.md:5` (+6 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x700106f044 | 1 | 6 | 41 | `docs/map/binary.md:624` (+8 more) | \| 0x700106f598 \| 1 \| 5 \| 65 \| `docs/map/bodies/pre-play-in-play.md:154` \| \\| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea… |
| 0x700106f0d0 | 1 | 12 | 106 | `docs/map/binary.md:447` (+7 more) | \| 0x70003e53e0 \| 22 \| 0 \| 9 \| `docs/map/binary.md:447` (+2 more) \| \\| 0x70003e53e0 \\| 22 \\| 0 \\| 9 \\| `docs/map/bodies… |
| 0x700106f250 | 1 | 11 | 70 | `docs/map/binary.md:624` (+8 more) | \| 0x700106f598 \| 1 \| 5 \| 65 \| `docs/map/bodies/pre-play-in-play.md:154` \| \\| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea… |
| 0x700106f340 | 1 | 8 | 92 | `docs/map/binary.md:624` (+8 more) | \| 0x700106f598 \| 1 \| 5 \| 65 \| `docs/map/bodies/pre-play-in-play.md:154` \| \\| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea… |
| 0x700106f480 | 1 | 4 | 81 | `docs/map/binary.md:624` (+8 more) | \| 0x700106f598 \| 1 \| 5 \| 65 \| `docs/map/bodies/pre-play-in-play.md:154` \| \\| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea… |
| 0x700106f598 | 1 | 5 | 65 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x700106f670 | 1 | 6 | 94 | `docs/map/bodies/pre-play-in-play.md:46` (+1 more) | \| 5 \| AUTO_FAST_FORWARD \| `f_700106f670` at 16394 \| I \| |
| 0x700106f7b0 | 1 | 24 | 207 | `docs/map/bodies/pre-play-in-play.md:47` (+1 more) | \| 6 \| AUTO_SUB \| set by `f_700106eb90` and `f_700106f0d0`; `f_700106f7b0` at 16489 \| C \| |
| 0x700106faac | 1 | 17 | 194 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x700106fd4c | 1 | 4 | 70 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x700106fe40 | 1 | 4 | 68 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x700106ff28 | 1 | 12 | 110 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x70010700a8 | 1 | 4 | 93 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x7001070de0 | 1 | 11 | 172 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x7001071230 | 4 | 16 | 101 | `docs/map/bodies/pre-play-in-play.md:154` | \| PRE_PLAY handlers `f_700106e7e4`, `f_700106ea54`, `f_700106f044`, `f_700106f250`, `f_700106f340`, `f_700106f480`, `f_700106f59… |
| 0x700107e208 | 2 | 11 | 447 | `docs/map/binary.md:430` (+2 more) | \| 0x70001e8834 \| 3 \| 11 \| 2158 \| `docs/map/bodies/play-inning-game-over.md:148` (+1 more) \| The EXIT handler `f_700109cf7c`… |
| 0x7001087120 | 3 | 0 | 11 | `docs/map/bodies/intro-states.md:84` | \| Slot 7 \| [C] each frame calls virtual +0x38 on the singleton at `[0x700227e128]`. When phase is 0 and step is 0 it calls `f_7… |
| 0x700108ab40 | 1 | 11 | 90 | `docs/map/binary.md:432` (+4 more) | \| 0x7000231000 \| 5 \| 0 \| 23 \| `docs/map/bodies/intro-states.md:47` \| \\| Helper `f_700108ab40` \\| [C] gets the singleton a… |
| 0x700108adb0 | 0 | 0 | 12 | `docs/map/bodies/intro-states.md:46` | \| Phase change \| [C] event 0x7e arrives at `f_700108adb0`, which stores 4 into `[state+0xc]` when the event id is 0x7e (`main_0… |
| 0x700108b628 | 0 | 73 | 587 | `docs/map/bodies/play-inning-game-over.md:214` (+3 more) | \| BATTER_UP to IN_PLAY to PLAY_OVER \| the earlier handler read (`f_700108b628`); PLAY_OVER slot 5 is entered after a play and s… |
| 0x700108f7c4 | 0 | 5 | 53 | `docs/map/bodies/play-inning-game-over.md:32` | \| GAME_OVER \| `f_700108f904`, 414 lines: enter, picks the first sub-state \| `f_700108ff50`, 549 lines: per-frame jump table \|… |
| 0x700108f87c | 4 | 2 | 39 | `docs/map/bodies/play-inning-game-over.md:34` | GAME_OVER has two more per-frame pieces. Slot 33 (`f_70010920f4`, main_0121.c:6080) is a second jump table for sub-states 4 to 13… |
| 0x700108f904 | 0 | 51 | 414 | `docs/map/binary.md:639` (+3 more) | \| 0x700108f7c4 \| 0 \| 5 \| 53 \| `docs/map/bodies/play-inning-game-over.md:32` \| \\| GAME_OVER \\| `f_700108f904`, 414 lines: … |
| 0x700108ff50 | 0 | 34 | 549 | `docs/map/binary.md:639` (+7 more) | \| 0x700108f7c4 \| 0 \| 5 \| 53 \| `docs/map/bodies/play-inning-game-over.md:32` \| \\| GAME_OVER \\| `f_700108f904`, 414 lines: … |
| 0x70010906bc | 1 | 8 | 91 | `docs/map/binary.md:505` (+3 more) | \| 0x70008a846c \| 13 \| 5 \| 58 \| `docs/map/bodies/play-inning-game-over.md:80` \| MERCY_RULE (value 1) is entered by `f_700109… |
| 0x70010907f8 | 1 | 4 | 68 | `docs/map/bodies/play-inning-game-over.md:44` (+1 more) | \| 2 \| WAIT_FOR_MESSAGE \| `f_70010907f8` (4288) \| |
| 0x7001090a58 | 1 | 2 | 117 | `docs/map/bodies/play-inning-game-over.md:95` | Almost every presentation sub-state in GAME_OVER ends by setting sub-state 10, POST_GAME_MENU: `f_700108ff50` (3864), `f_7001090a… |
| 0x7001090d88 | 1 | 12 | 173 | `docs/map/bodies/play-inning-game-over.md:95` | Almost every presentation sub-state in GAME_OVER ends by setting sub-state 10, POST_GAME_MENU: `f_700108ff50` (3864), `f_7001090a… |
| 0x7001090fec | 1 | 7 | 143 | `docs/map/bodies/play-inning-game-over.md:48` (+1 more) | \| 6 \| PRES_GROUP_B \| `f_7001090fec` (4946) \| |
| 0x70010911d8 | 1 | 4 | 97 | `docs/map/bodies/play-inning-game-over.md:49` (+2 more) | \| 7 \| PRES_COPYRIGHT \| `f_70010911d8` (5022) \| |
| 0x7001091330 | 1 | 17 | 173 | `docs/map/bodies/play-inning-game-over.md:95` | Almost every presentation sub-state in GAME_OVER ends by setting sub-state 10, POST_GAME_MENU: `f_700108ff50` (3864), `f_7001090a… |
| 0x70010915a0 | 1 | 8 | 97 | `docs/map/bodies/play-inning-game-over.md:95` | Almost every presentation sub-state in GAME_OVER ends by setting sub-state 10, POST_GAME_MENU: `f_700108ff50` (3864), `f_7001090a… |
| 0x70010918e8 | 1 | 6 | 48 | `docs/map/bodies/play-inning-game-over.md:95` | Almost every presentation sub-state in GAME_OVER ends by setting sub-state 10, POST_GAME_MENU: `f_700108ff50` (3864), `f_7001090a… |
| 0x7001091e78 | 1 | 4 | 52 | `docs/map/binary.md:652` (+1 more) | \| 0x7001091e78 \| 1 \| 4 \| 52 \| `docs/map/binary.md:652` (+1 more) \| \\| 0x7001091e78 \\| 1 \\| 4 \\| 52 \\| `docs/map/bodies… |
| 0x7001091fb4 | 1 | 3 | 33 | `docs/map/binary.md:653` (+1 more) | \| 0x7001091fb4 \| 1 \| 3 \| 33 \| `docs/map/binary.md:653` (+1 more) \| \\| 0x7001091fb4 \\| 1 \\| 3 \\| 33 \\| `docs/map/bodies… |
| 0x70010920f4 | 1 | 11 | 260 | `docs/map/binary.md:640` (+2 more) | \| 0x700108f87c \| 4 \| 2 \| 39 \| `docs/map/bodies/play-inning-game-over.md:34` \| GAME_OVER has two more per-frame pieces. Slot… |
| 0x7001092518 | 0 | 15 | 163 | `docs/map/binary.md:655` (+3 more) | \| 0x7001092518 \| 0 \| 15 \| 163 \| `docs/map/binary.md:656` (+2 more) \| \\| 0x700109276c \\| 0 \\| 34 \\| 789 \\| `docs/map/bo… |
| 0x700109276c | 0 | 34 | 789 | `docs/map/bodies/play-inning-game-over.md:31` (+2 more) | \| INNING_OVER \| `f_7001092518`, 163 lines: enter \| `f_700109276c`, 789 lines: per-frame switch \| no handler of its own among … |
| 0x7001093278 | 1 | 11 | 76 | `docs/map/bodies/play-inning-game-over.md:191` | \| 4 \| begin posts event 0x121 again and calls `f_7001093390` (7469) and `f_7001093278` (7393); update waits on the presentation… |
| 0x7001093390 | 1 | 9 | 91 | `docs/map/bodies/play-inning-game-over.md:191` | \| 4 \| begin posts event 0x121 again and calls `f_7001093390` (7469) and `f_7001093278` (7393); update waits on the presentation… |
| 0x70010934d8 | 0 | 3 | 43 | `docs/map/binary.md:584` (+2 more) | \| 0x7000eb466c \| 10 \| 1 \| 25 \| `docs/map/binary.md:660` (+1 more) \| \\| 0x7001093558 \\| 1 \\| 4 \\| 101 \\| `docs/map/bodi… |
| 0x7001093558 | 1 | 4 | 101 | `docs/map/bodies/play-inning-game-over.md:198` | Slot 6 `f_70010934d8` (7560-7602) clears byte `[state+0x20]` and, through the object at `0x7002296000+0x848`, calls `f_7000eb466c… |
| 0x70010936ec | 0 | 1 | 23 | `docs/map/bodies/pre-play-in-play.md:19` | \| 3 \| `f_700106cfc4`: sets up the object. Writes -1 to +0x18, fetches an object from `f_7000d81dd8` into +0x20, sets flags at +… |
| 0x7001093730 | 0 | 5 | 36 | `docs/map/bodies/pre-play-in-play.md:20` | \| 5 \| `f_700106d0c8`: starts the state. Sets sub-state 1, zeroes +0x8, logs the name of sub-state 1. If +0x28 is set it writes … |
| 0x70010937a0 | 0 | 3 | 32 | `docs/map/bodies/pre-play-in-play.md:21` | \| 6 \| `f_700106d154`: ends the state. Clears a byte in the `+0x20` object (+0x25), zeroes a global byte (0x7002ca4061), writes … |
| 0x7001093804 | 0 | 1 | 123 | `docs/map/bodies/pre-play-in-play.md:23` | \| 9 \| `f_700106d1cc`: subscribes the object to 7 event ids. Lines 15530 to 15577 \| `f_7001093804`: subscribes to 22 event ids.… |
| 0x70010939dc | 0 | 27 | 558 | `docs/map/bodies/pre-play-in-play.md:5` (+2 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x700109419c | 0 | 1 | 102 | `docs/map/bodies/pre-play-in-play.md:24` | \| 10 \| `f_700106d438`: the same 7 ids with `f_70005e69d0` (unsubscribe, I). Lines 15705 to 15744 \| `f_700109419c`: not read \|… |
| 0x700109448c | 0 | 11 | 176 | `docs/map/bodies/pre-play-in-play.md:11` (+1 more) | The earlier note that the 558-line `f_70010939dc` is an IN_PLAY vtable slot was wrong. It is not in the vtable. It is the event h… |
| 0x70010946dc | 1 | 6 | 71 | `docs/map/bodies/pre-play-in-play.md:5` (+2 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x70010947cc | 1 | 6 | 83 | `docs/map/bodies/pre-play-in-play.md:5` (+2 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x70010948ec | 1 | 8 | 71 | `docs/map/bodies/pre-play-in-play.md:5` (+2 more) | What was read in full: the PRE_PLAY vtable slots 3, 5, 6, 9, 10 and the first 150 lines of slot 7; the handlers `f_700106e610`, `… |
| 0x70010949d8 | 1 | 6 | 83 | `docs/map/binary.md:671` (+2 more) | \| 0x70010949d8 \| 1 \| 6 \| 83 \| `docs/map/binary.md:671` (+2 more) \| \\| 0x70010949d8 \\| 1 \\| 6 \\| 83 \\| `docs/map/bodies… |
| 0x7001094afc | 1 | 11 | 116 | `docs/map/binary.md:433` (+6 more) | \| 0x70002803f0 \| 283 \| 2 \| 10 \| `docs/map/bodies/pre-play-in-play.md:124` (+1 more) \| \\| 6 \\| Event 0x5b or 0x21a arrives… |
| 0x7001094c88 | 1 | 46 | 865 | `docs/map/bodies/pre-play-in-play.md:123` (+1 more) | \| 5 \| While in IN_PLAY the update calls `f_7001094c88(dt)`, an 865-line function. When it returns true, the state goes to PLAY_… |
| 0x7001095b00 | 1 | 31 | 459 | `docs/map/bodies/pre-play-in-play.md:124` (+1 more) | \| 6 \| Event 0x5b or 0x21a arrives: sub-state 3, POST_PITCH. The run function `f_7001094afc` checks the options object from `f_7… |
| 0x7001097118 | 1 | 6 | 67 | `docs/map/bodies/intro-states.md:65` | \| Slot 7 \| [C] phase machine over phases 1 to 7 and steps 1 to 3. Each phase calls `f_7000e23cec(state, phase)` when it changes… |
| 0x7001097210 | 1 | 9 | 119 | `docs/map/bodies/intro-states.md:65` | \| Slot 7 \| [C] phase machine over phases 1 to 7 and steps 1 to 3. Each phase calls `f_7000e23cec(state, phase)` when it changes… |
| 0x70010973c0 | 1 | 9 | 79 | `docs/map/bodies/intro-states.md:65` | \| Slot 7 \| [C] phase machine over phases 1 to 7 and steps 1 to 3. Each phase calls `f_7000e23cec(state, phase)` when it changes… |
| 0x700109a680 | 0 | 1 | 15 | `docs/map/bodies/play-inning-game-over.md:30` | \| PLAY_OVER \| `f_700109a6a8`, 197 lines: enter \| `f_700109af70`, 1,255 lines: per-frame switch \| `f_700109a680`: set sub-stat… |
| 0x700109a6a8 | 0 | 26 | 197 | `docs/map/binary.md:678` (+5 more) | \| 0x700109a680 \| 0 \| 1 \| 15 \| `docs/map/binary.md:678` (+2 more) \| \\| 0x700109a680 \\| 0 \\| 1 \\| 15 \\| `docs/map/bodies… |
| 0x700109aa1c | 1 | 4 | 90 | `docs/map/binary.md:436` (+8 more) | \| 0x70002e2348 \| 293 \| 2 \| 10 \| `docs/map/binary.md:436` (+2 more) \| \\| 0x70002e2348 \\| 293 \\| 2 \\| 10 \\| `docs/map/bo… |
| 0x700109ab58 | 4 | 7 | 63 | `docs/map/bodies/play-inning-game-over.md:126` | 4. Calls `f_700109aa1c` (below) and then loops over a few checks on `f_70002e2348` (play data) that end in `f_700109ab58` when a … |
| 0x700109ade4 | 1 | 9 | 115 | `docs/map/bodies/play-inning-game-over.md:146` | The WAIT sub-state decides how long to hold. Phase 0 computes `[state+0x2c]`, a number of seconds, from the play-result values `[… |
| 0x700109af70 | 0 | 70 | 1255 | `docs/map/bodies/play-inning-game-over.md:30` (+1 more) | \| PLAY_OVER \| `f_700109a6a8`, 197 lines: enter \| `f_700109af70`, 1,255 lines: per-frame switch \| `f_700109a680`: set sub-stat… |
| 0x700109c0b8 | 1 | 6 | 75 | `docs/map/bodies/play-inning-game-over.md:106` (+1 more) | \| 1 \| no name \| stored by slot 5 at 16220; its update handler `f_700109c0b8` hands over to 0 \| |
| 0x700109c1b4 | 1 | 12 | 170 | `docs/map/bodies/play-inning-game-over.md:137` (+2 more) | \| 3 PRES_LOAD \| `f_700109c1b4` (18030) \| `f_700109c414` (18200) \| by `[state+0x20]`: 0xb gives 5, 0xa gives 10, else 4 or 2 (… |
| 0x700109c414 | 1 | 6 | 83 | `docs/map/bodies/play-inning-game-over.md:137` | \| 3 PRES_LOAD \| `f_700109c1b4` (18030) \| `f_700109c414` (18200) \| by `[state+0x20]`: 0xb gives 5, 0xa gives 10, else 4 or 2 (… |
| 0x700109c534 | 1 | 5 | 62 | `docs/map/bodies/play-inning-game-over.md:138` | \| 4 PRES_ENDOFPLAY \| `f_700109c534` (18283) \| `f_700109c608` (18345) \| 10 EXIT (16932); `f_700109c608` can also set 3 (18450,… |
| 0x700109c608 | 1 | 7 | 143 | `docs/map/bodies/play-inning-game-over.md:138` (+1 more) | \| 4 PRES_ENDOFPLAY \| `f_700109c534` (18283) \| `f_700109c608` (18345) \| 10 EXIT (16932); `f_700109c608` can also set 3 (18450,… |
| 0x700109c800 | 1 | 4 | 54 | `docs/map/binary.md:689` (+1 more) | \| 0x700109c800 \| 1 \| 4 \| 54 \| `docs/map/binary.md:689` (+1 more) \| \\| 0x700109c800 \\| 1 \\| 4 \\| 54 \\| `docs/map/bodies… |
| 0x700109c8bc | 1 | 17 | 231 | `docs/map/bodies/play-inning-game-over.md:141` | \| 2 POST_PLAY \| `f_7000e23cec(this,2)`, event 0x11b once \| `f_700109c8bc` (18542) \| 10 EXIT (17061) \| |
| 0x700109cbe8 | 1 | 3 | 91 | `docs/map/binary.md:691` (+1 more) | \| 0x700109cbe8 \| 1 \| 3 \| 91 \| `docs/map/binary.md:691` (+1 more) \| \\| 0x700109cbe8 \\| 1 \\| 3 \\| 91 \\| `docs/map/bodies… |
| 0x700109cd28 | 1 | 8 | 73 | `docs/map/bodies/play-inning-game-over.md:143` | \| 8 CHALLENGE_PLAY_PROMPT \| `f_700109cd28` (18864) \| `f_700109ce30` (18937) \| 9 (19028) \| |
| 0x700109ce30 | 1 | 4 | 97 | `docs/map/bodies/play-inning-game-over.md:143` | \| 8 CHALLENGE_PLAY_PROMPT \| `f_700109cd28` (18864) \| `f_700109ce30` (18937) \| 9 (19028) \| |
| 0x700109cf7c | 1 | 19 | 292 | `docs/map/binary.md:430` (+3 more) | \| 0x70001e8834 \| 3 \| 11 \| 2158 \| `docs/map/bodies/play-inning-game-over.md:148` (+1 more) \| The EXIT handler `f_700109cf7c`… |
| 0x700109d498 | 0 | 1 | 38 | `docs/map/bodies/play-inning-game-over.md:144` | \| 9 CHALLENGE_PLAY \| inline at 17626-17700 \| `f_700109d498` (19394) \| not read \| |
| 0x70010a301c | 2 | 11 | 107 | `docs/map/bodies/intro-states.md:73` (+1 more) | \| Slot 5 \| [C] posts event 0x218, clears `+0x8`, `+0x22`, sets `+0x28` to 8, logs "ATT_SCREEN: Pitcher warmup." (`main_0121.c:2… |
| 0x70010a3814 | 1 | 7 | 73 | `docs/map/bodies/intro-states.md:75` | \| Slot 7 \| [C] eight phases at `+0x18`. Every phase change is `st64[x19+0x18] = value` followed by `f_7000574c40` (the logger, … |
| 0x70010a3908 | 1 | 10 | 159 | `docs/map/bodies/intro-states.md:75` | \| Slot 7 \| [C] eight phases at `+0x18`. Every phase change is `st64[x19+0x18] = value` followed by `f_7000574c40` (the logger, … |
| 0x70010a5544 | 16 | 0 | 18 | `docs/map/binary.md:699` (+1 more) | \| 0x70010a5544 \| 16 \| 0 \| 18 \| `docs/map/binary.md:699` (+1 more) \| \\| 0x70010a5544 \\| 16 \\| 0 \\| 18 \\| `docs/map/bodi… |
| 0x70010c3298 | ? | ? | ? | `docs/map/binary.md:700` (+1 more) | \| 0x70010c3298 \| ? \| ? \| ? \| `runtime/gfx/vk_exec_xfer.c:17` \| // TOTK resets and reports it 3 to 8 times a frame in the fi… |
| 0x70010e62c4 | 13 | 2 | 27 | `docs/map/bodies/play-inning-game-over.md:129` (+1 more) | `f_700109aa1c` (16299-16388) decides how this play will be presented. It starts `[state+0x20]` at 6 (16308), then asks the presen… |
| 0x70010e6318 | 6 | 2 | 27 | `docs/map/bodies/intro-states.md:55` | \| Slot 7 \| [C] drives a presentation object at `[0x7003b22ad0]` through three steps. Step 0 starts it (virtual call at +0x80 on… |
| 0x70010e672c | 4 | 2 | 27 | `docs/map/bodies/play-inning-game-over.md:129` (+1 more) | `f_700109aa1c` (16299-16388) decides how this play will be presented. It starts `[state+0x20]` at 6 (16308), then asks the presen… |
| 0x7001267d20 | ? | ? | ? | `docs/graphics-plan.md:134` (+1 more) | title screen; **200 % crashes** at about frame 1400 with a null write in f_7001267d20 (a game allocation that failed, |
| 0x7001268e08 | 2 | 0 | 71 | `docs/map/bodies/lighting.md:63` | \| 0x70012c56e0 \| Manager constructor (sub-objects, 15 callers) \| C \| callees `f_70012e3b10` ("LightingEnvironment"), `f_70012… |
| 0x700128d2a0 | 1 | 8 | 270 | `docs/map/binary.md:706` (+2 more) | \| 0x700128d2a0 \| 1 \| 8 \| 270 \| `docs/walkup-freeze.md:37` (+1 more) \| (`main+0x12e0db4..0x12e0e24`). The counter's only rea… |
| 0x70012c54ec | 173 | 4 | 57 | `docs/map/binary.md:707` (+12 more) | \| 0x70012c54ec \| 173 \| 4 \| 57 \| `docs/map/binary.md:710` (+10 more) \| \\| 0x70012d0fcc \\| 9 \\| 3 \\| 91 \\| `docs/map/bod… |
| 0x70012c56e0 | 15 | 7 | 518 | `docs/map/bodies/lighting.md:62` | \| 0x70012c54ec \| Lighting-manager getter (lazy 0x101e40 alloc) \| C \| global `0x70045a9dc0`; `x2 = 0x1e40 \\| 0x100000` -> `f_… |
| 0x70012c5e9c | 2 | 1 | 264 | `docs/map/bodies/lighting.md:63` | \| 0x70012c56e0 \| Manager constructor (sub-objects, 15 callers) \| C \| callees `f_70012e3b10` ("LightingEnvironment"), `f_70012… |
| 0x70012d0fcc | 9 | 3 | 91 | `docs/map/binary.md:707` (+6 more) | \| 0x70012c54ec \| 173 \| 4 \| 57 \| `docs/map/binary.md:710` (+10 more) \| \\| 0x70012d0fcc \\| 9 \\| 3 \\| 91 \\| `docs/map/bod… |
| 0x70012d1e04 | 10 | 4 | 187 | `docs/map/bodies/lighting.md:73` (+7 more) | \| 0x70012d0fcc \| Per-frame lighting request/gate \| C \| `LD8([x0+0xc43])`; `[x9+0xb8] == 0x78`; `LD8([x0+0xc2d])`; calls `f_70… |
| 0x70012d20a0 | 1 | 2 | 61 | `docs/map/bodies/play-inning-game-over.md:125` (+5 more) | 3. Calls `f_70012c54ec` (the lighting manager) and then `f_70012d20a0` (16110): this starts the background lighting bake after ea… |
| 0x70012e0150 | 1 | 54 | 1653 | `docs/map/binary.md:386` (+8 more) | \| 0x700000b140 \| 0 \| 12 \| 84 \| `docs/walkup-freeze.md:14` \| `f_70012e0150` runs (once a frame, from `f_700000b140`). \| |
| 0x70012e3b10 | 1 | 11 | 122 | `docs/map/binary.md:705` (+2 more) | \| 0x7001268e08 \| 2 \| 0 \| 71 \| `docs/map/bodies/lighting.md:63` \| \\| 0x70012c56e0 \\| Manager constructor (sub-objects, 15 … |
| 0x70012f3f38 | 9 | 1 | 28 | `docs/map/bodies/intro-states.md:45` | \| Slot 7 \| [C] phase 1 sets phase 2 and runs helper `f_700108ab40`. Phase 4 has three steps: step 0 calls `f_70012f3f38(0x78, .… |
| 0x70012f3f8c | 5 | 3 | 139 | `docs/map/bodies/intro-states.md:66` | \| Slot 6 \| [C] clears `+0x20` and `+0x29`, and when `[[0x700227e6b8]+0x20]` is 0, a global byte is 0 and two values match, star… |
| 0x700133fcc0 | 95 | 1 | 60 | `docs/map/bodies/batter-up.md:126` (+2 more) | \| 34, 35 \| `ebd8`, `ec30` \| thunks calling `f_700133fcc0` with fixed arguments \| C \| |
| 0x70013400e0 | 45 | 1 | 40 | `docs/map/bodies/intro-states.md:84` (+1 more) | \| Slot 7 \| [C] each frame calls virtual +0x38 on the singleton at `[0x700227e128]`. When phase is 0 and step is 0 it calls `f_7… |
| 0x7001340720 | ? | ? | ? | `docs/map/binary.md:719` (+2 more) | \| 0x7001340720 \| ? \| ? \| ? \| `runtime/mlb/hid.c:676` \| // MLB's pad update (1.0.20 f_7001341c20, 1.0.15 f_7001340720; read … |
| 0x7001341c20 | 2 | 4 | 238 | `docs/map/binary.md:719` (+2 more) | \| 0x7001340720 \| ? \| ? \| ? \| `runtime/mlb/hid.c:676` \| // MLB's pad update (1.0.20 f_7001341c20, 1.0.15 f_7001340720; read … |
| 0x700134df20 | 4 | 0 | 5 | `docs/map/bodies/batter-up.md:116` (+3 more) | \| 6 \| `dca4` \| exit: clear flags, call `f_7000d82738` and `f_700134df20(0)`, sub-state 0 \| C \| |
| 0x70014aea4c | 11 | 3 | 27 | `docs/map/bodies/play-inning-game-over.md:182` | 4. Calls `f_7000574c40` and the newline helper, and if the counter equals 7 calls `f_70014aea4c(1)` and `f_70014af940` (6570-6579… |
| 0x70014af940 | 2 | 0 | 21 | `docs/map/bodies/play-inning-game-over.md:182` | 4. Calls `f_7000574c40` and the newline helper, and if the counter equals 7 calls `f_70014aea4c(1)` and `f_70014af940` (6570-6579… |
| 0x70014bdc08 | 26 | 3 | 109 | `docs/map/binary.md:724` (+6 more) | \| 0x70014bdc08 \| 26 \| 3 \| 109 \| `docs/map/source/tools-packages.md:120` (+3 more) \| \\| `decode_account_session` \\| 195-19… |
| 0x70014bde34 | 26 | 5 | 193 | `docs/map/binary.md:725` (+1 more) | \| 0x70014bde34 \| 26 \| 5 \| 193 \| `tools/packages/server_msgs.py:88` \| """AccountSession (f_70014bdc08 ser / f_70014bde34 des… |
| 0x70014be240 | 0 | 1 | 34 | `docs/map/source/tools-packages.md:181` (+1 more) | \| `parse_token_echo` \| 189-199 \| \| Reader, _done, get, read, u8, u64, hex, string (+1) \| 0xde3ac304 / 0x0ca403f1 / 0x66baea3… |
| 0x70014be374 | 0 | 1 | 55 | `docs/map/source/tools-packages.md:181` (+1 more) | \| `parse_token_echo` \| 189-199 \| \| Reader, _done, get, read, u8, u64, hex, string (+1) \| 0xde3ac304 / 0x0ca403f1 / 0x66baea3… |
| 0x70014be5a4 | 0 | 2 | 39 | `docs/map/source/tools-packages.md:181` (+1 more) | \| `parse_token_echo` \| 189-199 \| \| Reader, _done, get, read, u8, u64, hex, string (+1) \| 0xde3ac304 / 0x0ca403f1 / 0x66baea3… |
| 0x70014be6f8 | 0 | 1 | 22 | `docs/map/binary.md:729` (+2 more) | \| 0x70014be6f8 \| 0 \| 1 \| 22 \| `tools/packages/server_msgs.py:248` \| # - SessionResponse deser f_70014be6f8 / f_70014be818 (… |
| 0x70014be818 | 0 | 1 | 58 | `docs/map/binary.md:729` (+2 more) | \| 0x70014be6f8 \| 0 \| 1 \| 22 \| `tools/packages/server_msgs.py:248` \| # - SessionResponse deser f_70014be6f8 / f_70014be818 (… |
| 0x70014c2930 | 8 | 2 | 137 | `docs/map/binary.md:511` (+6 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x70014c2b00 | 7 | 4 | 175 | `docs/map/binary.md:732` (+1 more) | \| 0x70014c2b00 \| 7 \| 4 \| 175 \| `tools/packages/server_msgs.py:76` \| """Token (f_70014c2930 ser / f_70014c2b00 deser): strin… |
| 0x70014c3c40 | 0 | 1 | 25 | `docs/map/binary.md:733` (+1 more) | \| 0x70014c3c40 \| 0 \| 1 \| 25 \| `tools/packages/server_msgs.py:244` \| # - LoginResponse deser f_70014c3c40: u8 ok @+8, Token … |
| 0x70014c8a18 | 0 | 0 | 9 | `docs/map/binary.md:734` (+1 more) | \| 0x70014c8a18 \| 0 \| 0 \| 9 \| `tools/packages/codec.py:37` \| MSG_AUTH_TOKEN = 0x1397A1DF # client->server, body: string (NSA… |
| 0x70014dd530 | 0 | 2 | 16 | `docs/map/binary.md:735` (+1 more) | \| 0x70014dd530 \| 0 \| 2 \| 16 \| `tools/packages/rpc.py:55` \| 0xE54920EB S->C (no vtable found; factory f_70014dd530) OnMessag… |
| 0x70014e2b00 | 7 | 2 | 199 | `docs/map/binary.md:736` (+1 more) | \| 0x70014e2b00 \| 7 \| 2 \| 199 \| `tools/packages/codec.py:21` \| Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_700… |
| 0x7001502b4c | 2 | 0 | 44 | `docs/map/binary.md:736` (+4 more) | \| 0x70014e2b00 \| 7 \| 2 \| 199 \| `tools/packages/codec.py:21` \| Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_700… |
| 0x7001502bd4 | 2 | 0 | 64 | `docs/map/binary.md:738` (+2 more) | \| 0x7001502bd4 \| 2 \| 0 \| 64 \| `docs/map/binary.md:738` (+2 more) \| \\| 0x7001502bd4 \\| 2 \\| 0 \\| 64 \\| `tools/packages/… |
| 0x7001502d14 | 1 | 0 | 51 | `docs/map/binary.md:739` (+2 more) | \| 0x7001502d14 \| 1 \| 0 \| 51 \| `tools/packages/codec.py:8` \| u8 magic = 0xA5 (f_7001502d14 writes, f_7001502db4 checks) \| |
| 0x7001502db4 | 1 | 0 | 58 | `docs/map/binary.md:739` (+2 more) | \| 0x7001502d14 \| 1 \| 0 \| 51 \| `tools/packages/codec.py:8` \| u8 magic = 0xA5 (f_7001502d14 writes, f_7001502db4 checks) \| |
| 0x7001502e74 | 0 | 0 | 24 | `docs/map/binary.md:736` (+1 more) | \| 0x70014e2b00 \| 7 \| 2 \| 199 \| `tools/packages/codec.py:21` \| Body primitives (see f_7001502e74 u8, f_7001502b4c u32, f_700… |
| 0x70015032d8 | 0 | 0 | 9 | `docs/map/binary.md:742` (+1 more) | \| 0x70015032d8 \| 0 \| 0 \| 9 \| `tools/packages/codec.py:39` \| MSG_PING = 0x9A77845F # server->client: makes the client send a… |
| 0x700150330c | 0 | 0 | 10 | `docs/map/binary.md:743` (+1 more) | \| 0x700150330c \| 0 \| 0 \| 10 \| `tools/packages/codec.py:38` \| MSG_HEARTBEAT = 0xD4D9E1AD # client->server every 15 s idle, b… |
| 0x7001503a1c | 0 | 0 | 31 | `docs/map/binary.md:744` (+1 more) | \| 0x7001503a1c \| 0 \| 0 \| 31 \| `tools/packages/rpc.py:52` \| 0xC031F812 C->S? body: u64 (Serialize f_7001503a1c) - sender not… |
| 0x7001503b2c | 0 | 1 | 7 | `docs/map/binary.md:745` (+1 more) | \| 0x7001503b2c \| 0 \| 1 \| 7 \| `tools/packages/rpc.py:51` \| 0x94E26BC1 C->S? body: AccountSession (Serialize f_7001503b2c) - … |
| 0x7001503bd0 | 0 | 3 | 191 | `docs/map/binary.md:747` (+1 more) | \| 0x7001503f50 \| 0 \| 4 \| 172 \| `tools/packages/rpc.py:12` \| message 0x801FB56C ServiceRequest (Serialize f_7001503bd0, Dese… |
| 0x7001503f50 | 0 | 4 | 172 | `docs/map/binary.md:747` (+1 more) | \| 0x7001503f50 \| 0 \| 4 \| 172 \| `tools/packages/rpc.py:12` \| message 0x801FB56C ServiceRequest (Serialize f_7001503bd0, Dese… |
| 0x70015041b0 | 0 | 1 | 39 | `docs/map/binary.md:749` (+1 more) | \| 0x700150422c \| 0 \| 1 \| 49 \| `tools/packages/rpc.py:15` \| message 0x30D39658 ServiceResponse (Serialize f_70015041b0, Dese… |
| 0x700150422c | 0 | 1 | 49 | `docs/map/binary.md:749` (+1 more) | \| 0x700150422c \| 0 \| 1 \| 49 \| `tools/packages/rpc.py:15` \| message 0x30D39658 ServiceResponse (Serialize f_70015041b0, Dese… |
| 0x70015042d4 | 0 | 1 | 28 | `docs/map/binary.md:750` (+1 more) | \| 0x70015042d4 \| 0 \| 1 \| 28 \| `tools/packages/rpc.py:53` \| 0xDF31986F ? body: u32, string (Serialize f_70015042d4) - not ha… |
| 0x70015043a0 | 1 | 1 | 66 | `docs/map/binary.md:751` (+1 more) | \| 0x70015043a0 \| 1 \| 1 \| 66 \| `tools/packages/rpc.py:48` \| Other messages registered by the Service plugin (f_70015043a0 gr… |
| 0x7001505770 | 1 | 1 | 38 | `docs/map/binary.md:752` (+1 more) | \| 0x7001505770 \| 1 \| 1 \| 38 \| `tools/packages/rpc.py:56` \| 0xF63439D4 / 0x23BF9620 (group f_7001505770) S->C: OnMessage loo… |
| 0x7001505f6c | 0 | 1 | 7 | `docs/map/binary.md:753` (+3 more) | \| 0x7001505f6c \| 0 \| 1 \| 7 \| `docs/map/source/tools-packages.md:182` (+1 more) \| \\| `parse_conductor_query` \\| 202-204 \\… |
| 0x70015061bc | 0 | 1 | 7 | `docs/map/binary.md:753` (+3 more) | \| 0x7001505f6c \| 0 \| 1 \| 7 \| `docs/map/source/tools-packages.md:182` (+1 more) \| \\| `parse_conductor_query` \\| 202-204 \\… |
| 0x700151a26c | 6 | 4 | 172 | `docs/map/binary.md:755` (+2 more) | \| 0x700151a26c \| 6 \| 4 \| 172 \| `tools/packages/rpc.py:37` \| params_json format (f_700151a26c begin '{', f_700151aa40 key '"… |
| 0x700151a4d4 | 8 | 3 | 104 | `docs/map/binary.md:756` (+1 more) | \| 0x700151a4d4 \| 8 \| 3 \| 104 \| `tools/packages/rpc.py:38` \| 0x7002206578 ["", ","], f_700151a4d4 end '}'), values by param … |
| 0x700151aa40 | 9 | 4 | 71 | `docs/map/binary.md:755` (+2 more) | \| 0x700151a26c \| 6 \| 4 \| 172 \| `tools/packages/rpc.py:37` \| params_json format (f_700151a26c begin '{', f_700151aa40 key '"… |
| 0x700151ab30 | 27 | 5 | 130 | `docs/map/binary.md:758` (+1 more) | \| 0x700151ab30 \| 27 \| 5 \| 130 \| `tools/packages/rpc.py:40` \| 2 int -> %d (f_700151ab30) \| |
| 0x700151ad00 | 1 | 5 | 130 | `docs/map/binary.md:759` (+1 more) | \| 0x700151ad00 \| 1 \| 5 \| 130 \| `tools/packages/rpc.py:42` \| 4 int64 -> %ld (f_700151ad00) \| |
| 0x700151aed0 | 11 | 5 | 130 | `docs/map/binary.md:760` (+1 more) | \| 0x700151aed0 \| 11 \| 5 \| 130 \| `tools/packages/rpc.py:41` \| 3 uint -> %u (f_700151aed0) \| |
| 0x700151b0a0 | 3 | 5 | 130 | `docs/map/binary.md:761` (+1 more) | \| 0x700151b0a0 \| 3 \| 5 \| 130 \| `tools/packages/rpc.py:43` \| 5 uint64 -> %lu (f_700151b0a0) \| |
| 0x700151b7b0 | 7 | 5 | 263 | `docs/map/binary.md:762` (+1 more) | \| 0x700151b7b0 \| 7 \| 5 \| 263 \| `tools/packages/rpc.py:45` \| 8 string -> "raw text" (f_700151b7b0 called with escape=0: NOT … |
| 0x700151bb48 | 2 | 5 | 134 | `docs/map/binary.md:763` (+1 more) | \| 0x700151bb48 \| 2 \| 5 \| 134 \| `tools/packages/rpc.py:39` \| 1 bool -> true / false (f_700151bb48, table @0x7001da9f88) \| |
| 0x700151bd28 | 5 | 5 | 132 | `docs/map/binary.md:764` (+1 more) | \| 0x700151bd28 \| 5 \| 5 \| 132 \| `tools/packages/rpc.py:44` \| 6 float, 7 double -> %f (f_700151bd28) \| |
| 0x700151c1dc | 3 | 20 | 358 | `docs/map/binary.md:765` (+2 more) | \| 0x700151c1dc \| 3 \| 20 \| 358 \| `tools/packages/server_msgs.py:253` \| # - Service connect f_70009a7454: inet_ntop(Endpoint … |
| 0x700151c884 | 10 | 5 | 137 | `docs/map/binary.md:766` (+1 more) | \| 0x700151c884 \| 10 \| 5 \| 137 \| `tools/packages/rpc.py:11` \| pending_key(request_id, service) then f_7001530fb0 -> f_700151… |
| 0x700151cd40 | 1 | 10 | 156 | `docs/map/binary.md:768` (+3 more) | \| 0x700151d2a0 \| 1 \| 12 \| 170 \| `tools/packages/codec.py:7` \| 1. Stream blocks (olClient transport, f_700151cd40 send / f_7… |
| 0x700151d2a0 | 1 | 12 | 170 | `docs/map/binary.md:768` (+1 more) | \| 0x700151d2a0 \| 1 \| 12 \| 170 \| `tools/packages/codec.py:7` \| 1. Stream blocks (olClient transport, f_700151cd40 send / f_7… |
| 0x700151d520 | 1 | 12 | 190 | `docs/map/binary.md:738` (+2 more) | \| 0x7001502bd4 \| 2 \| 0 \| 64 \| `docs/map/binary.md:738` (+2 more) \| \\| 0x7001502bd4 \\| 2 \\| 0 \\| 64 \\| `tools/packages/… |
| 0x7001530fb0 | 42 | 1 | 10 | `docs/map/binary.md:766` (+1 more) | \| 0x700151c884 \| 10 \| 5 \| 137 \| `tools/packages/rpc.py:11` \| pending_key(request_id, service) then f_7001530fb0 -> f_700151… |
| 0x70015310d0 | 2 | 2 | 118 | `docs/map/binary.md:771` (+3 more) | \| 0x70015310d0 \| 2 \| 2 \| 118 \| `docs/map/source/tools-packages.md:157` (+2 more) \| \\| `expires_epoch` \\| 62-72 \\| \\| ti… |
| 0x7001531280 | 9 | 1 | 22 | `docs/map/source/tools-packages.md:156` (+2 more) | \| `expires_str` \| 55-59 \| \| strftime, gmtime, time \| 'YYYY-MM-DDTHH:MM:SS' (UTC). Must be > now + 30 s on the client clock (… |
| 0x70015351a4 | 47 | 1 | 35 | `docs/map/binary.md:511` (+4 more) | \| 0x700092ae20 \| 147 \| 1 \| 140 \| `tools/packages/codec.py:22` (+1 more) \| f_70015351a4 raw bytes, f_700092ce50/f_700092ae20… |
| 0x7001535e00 | 10 | 7 | 161 | `docs/map/binary.md:765` (+2 more) | \| 0x700151c1dc \| 3 \| 20 \| 358 \| `tools/packages/server_msgs.py:253` \| # - Service connect f_70009a7454: inet_ntop(Endpoint … |
| 0x7001538ed0 | 5 | 1 | 7 | `docs/map/binary.md:775` (+1 more) | \| 0x7001538ed0 \| 5 \| 1 \| 7 \| `tools/packages/server_msgs.py:114` \| (client does ntohs() on it before connecting, f_7001538e… |
| 0x70015391b4 | 1 | 0 | 100 | `docs/map/binary.md:776` (+1 more) | \| 0x70015391b4 \| 1 \| 0 \| 100 \| `tools/packages/server_msgs.py:112` \| (client types it IPv4 iff hi==0 and lo>>32 == 0xffff, … |
| 0x70015395cc | 9 | 0 | 57 | `docs/map/binary.md:777` (+3 more) | \| 0x70015395cc \| 9 \| 0 \| 57 \| `docs/map/source/tools-packages.md:169` (+1 more) \| \\| `endpoint` \\| 108-118 \\| \\| bytes,… |
| 0x7001539684 | 9 | 1 | 44 | `docs/map/binary.md:777` (+3 more) | \| 0x70015395cc \| 9 \| 0 \| 57 \| `docs/map/source/tools-packages.md:169` (+1 more) \| \\| `endpoint` \\| 108-118 \\| \\| bytes,… |
| 0x70015410b4 | 3004 | 1 | 23 | `docs/map/bodies/frontend.md:31` | \| 0x70004c0eac \| screen base ctor: installs base vtables, releases sub-objects \| C \| object+0/+8 = *0x7002281bc0+0x10 and +0x… |
| 0x70016527d8 | 1 | 7 | 142 | `docs/map/binary.md:780` (+1 more) | \| 0x70016527d8 \| 1 \| 7 \| 142 \| `tools/packages/rpc.py:54` \| 0x9FD30956 S->C body: string, string (OnMessage branch: clears … |
| 0x70016703f0 | 773 | 0 | 9 | `docs/map/bodies/play-inning-game-over.md:146` (+2 more) | The WAIT sub-state decides how long to hold. Phase 0 computes `[state+0x2c]`, a number of seconds, from the play-result values `[… |
| 0x70017c19d0 | 1 | 1 | 217 | `docs/map/regions/E-0x7001400000-0x70017fffff.md:109` | - The meaning of "s9Amp" and "S_CONTACT_HUM" / "S_CONTACT_CPU" (f_70017c19d0) is unknown [H]. |
| 0x70017c1d20 | 1 | 5 | 127 | `docs/map/regions/E-0x7001400000-0x70017fffff.md:60` (+1 more) | - A table walker: f_70017c1d20 (127 lines) loops over a table of 32-byte records, reading 16-bit and 32-bit fields, and calls two… |
| 0x70017c6740 | 1 | 8 | 133 | `docs/map/regions/E-0x7001400000-0x70017fffff.md:58` | - Player profile and appearance: "D_PLAYER_ACC", "D_PLR_PROFILE", "PACKED_U32", "ACCESSORY_COLORS", "FACE_HAIR_STYLE", "NAME_STYL… |
| 0x70017c690c | 1 | 30 | 5057 | `docs/map/regions/E-0x7001400000-0x70017fffff.md:58` | - Player profile and appearance: "D_PLAYER_ACC", "D_PLR_PROFILE", "PACKED_U32", "ACCESSORY_COLORS", "FACE_HAIR_STYLE", "NAME_STYL… |
| 0x70017d71ac | 0 | 1 | 5 | `docs/map/binary.md:786` (+2 more) | \| 0x70017d71ac \| 0 \| 1 \| 5 \| `docs/map/regions/E-0x7001400000-0x70017fffff.md:52` (+1 more) \| - f_70017d71ac (5 lines): tai… |
| 0x70017d71b0 | 0 | 0 | 9 | `docs/map/binary.md:787` (+2 more) | \| 0x70017d71b0 \| 0 \| 0 \| 9 \| `docs/map/regions/E-0x7001400000-0x70017fffff.md:50` (+1 more) \| - f_70017d71b0 (9 lines): rea… |
| 0x70017d71c4 | 0 | 1 | 18 | `docs/map/binary.md:788` (+2 more) | \| 0x70017d71c4 \| 0 \| 1 \| 18 \| `docs/map/regions/E-0x7001400000-0x70017fffff.md:51` (+1 more) \| - f_70017d71c4 (about 20 lin… |
| 0x70017da880 | 1 | 1 | 85 | `docs/map/regions/E-0x7001400000-0x70017fffff.md:61` | - Scouting and interest: "INTEREST_LEVEL", "SCOUTED_VALUE" in f_70017da880 [C strings, [I] scouting logic]. |
| 0x700181a6bc | 1154 | 0 | 22 | `docs/map/bodies/play-inning-game-over.md:89` | \| `[state+0x20]` \| 16-bit value read at offset 0x130 of the result of `f_700181a6bc` (3245-3249) \| C \| |
| 0x700181a6fc | 310 | 0 | 18 | `docs/map/bodies/frontend.md:61` | \| 0x7000bd20cc \| hub up-grade: rebuild the option list from career data \| I \| only caller of 0x7000bd22e4; uses f_70004a87e0,… |
| 0x700181c784 | 59 | 1 | 19 | `docs/map/bodies/intro-states.md:73` | \| Slot 5 \| [C] posts event 0x218, clears `+0x8`, `+0x22`, sets `+0x28` to 8, logs "ATT_SCREEN: Pitcher warmup." (`main_0121.c:2… |
| 0x7001824b74 | 2265 | 0 | 60 | `docs/map/binary.md:793` (+5 more) | \| 0x7001824b74 \| 2265 \| 0 \| 60 \| `docs/map/bodies/modes.md:82` (+4 more) \| [C] Then the mode display name is selected by th… |
| 0x700183eafc | 487 | 1 | 12 | `docs/map/bodies/intro-states.md:73` | \| Slot 5 \| [C] posts event 0x218, clears `+0x8`, `+0x22`, sets `+0x28` to 8, logs "ATT_SCREEN: Pitcher warmup." (`main_0121.c:2… |
| 0x70018444f0 | 35 | 6 | 177 | `docs/map/bodies/frontend.md:74` | \| 0x700181bef0 \| recalculates every player's rank \| C \| logs `"Running RecalcAllRanks logic over %d players\n"`, calls f_7001… |
| 0x70018450e8 | 2849 | 3 | 33 | `docs/map/bodies/frontend.md:74` | \| 0x700181bef0 \| recalculates every player's rank \| C \| logs `"Running RecalcAllRanks logic over %d players\n"`, calls f_7001… |
| 0x700184abb4 | 268 | 0 | 35 | `docs/map/bodies/play-inning-game-over.md:181` | 3. Otherwise reads the half-inning counter `[global 0x700227e6b8 + 0x20]`. It rotates it right by 1 to get a count, takes bit 0 a… |
| 0x70019fb800 | 1 | 2 | 43 | `docs/map/bodies/lighting.md:76` (+4 more) | \| 0x70012d1e04 \| Switch vs bake decision; writes 0xef01 \| C \| `ST32([x19+0xd3c], 0xef01)`; `[x8+0x674] = s9`, `[x8+0x101400] … |
| 0x70019fb880 | 1 | 8 | 239 | `docs/map/binary.md:799` (+2 more) | \| 0x70019fb880 \| 1 \| 8 \| 239 \| `tools/data/patches-1.0.20.txt:34` \| # that turns a set of stadium props off or on (f_70019f… |
| 0x70019fbbb0 | 1 | 12 | 337 | `docs/map/binary.md:799` (+2 more) | \| 0x70019fb880 \| 1 \| 8 \| 239 \| `tools/data/patches-1.0.20.txt:34` \| # that turns a set of stadium props off or on (f_70019f… |
| 0x7001a3bf20 | 3 | 16 | 206 | `docs/map/binary.md:801` (+1 more) | \| 0x7001a3bf20 \| 3 \| 16 \| 206 \| `docs/map/bodies/lighting.md:94` \| \\| 0x70019fb880 \\| Stadium light-rig prop; sets `+0xc3… |
| 0x7001c1fb00 | 23 | 0 | 9 | `docs/map/binary.md:399` (+2 more) | \| 0x70000aa6c0 \| 146 \| 1 \| 14 \| `docs/map/bodies/intro-states.md:63` (+3 more) \| \\| Slot 5 \\| [C] logs "ATT_SCREEN: Lineu… |
| 0x7001c1fb40 | 455 | 0 | 9 | `docs/map/bodies/play-inning-game-over.md:5` (+3 more) | The generated C was read with the shell filter in the Tracing playbook. Two helper roles are my reading [I]: `f_7001c1fb40` takes… |
| 0x7001c1fb70 | 2215 | 0 | 9 | `docs/map/bodies/lighting.md:62` | \| 0x70012c54ec \| Lighting-manager getter (lazy 0x101e40 alloc) \| C \| global `0x70045a9dc0`; `x2 = 0x1e40 \\| 0x100000` -> `f_… |
| 0x7001c1fc90 | 55 | 0 | 9 | `docs/map/bodies/batter-up.md:32` (+2 more) | The names come from a jump table in the setter `0x700108b500`. It stores the new value at `[this+0x18]`, its second argument at `… |
| 0x7001c1ff00 | 336 | 0 | 9 | `docs/map/bodies/frontend.md:30` | \| 0x70004c7918 \| screen vtable slot 3: name match then leave hook \| C \| compares x1+0x60 with the std::string at this+0xc0 (S… |
| 0x7001c20270 | 117 | 0 | 9 | `docs/map/binary.md:807` (+1 more) | \| 0x7001c20270 \| 117 \| 0 \| 9 \| `docs/map/bodies/modes.md:65` \| line 581), convert it with f_7001c20270 (`std::to_string`, s… |
| 0x7001c207a0 | 52 | 0 | 9 | `docs/map/bodies/frontend.md:59` | \| 0x7000bd1d98 \| hub up-grade: apply the focused upgrade (selection-object path) \| I \| x2 must be non-zero, reads the selecti… |
| 0x70051242a8 | ? | ? | ? | `docs/map/binary.md:809` (+2 more) | \| 0x70051242a8 \| ? \| ? \| ? \| `runtime/core/kernel.c:343` \| // - Horizon's preemption disable: the SDK's spin locks (1.2.1 s… |
| 0x7005124360 | ? | ? | ? | `docs/map/binary.md:809` (+2 more) | \| 0x70051242a8 \| ? \| ? \| ? \| `runtime/core/kernel.c:343` \| // - Horizon's preemption disable: the SDK's spin locks (1.2.1 s… |
