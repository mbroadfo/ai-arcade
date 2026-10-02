# MAME 0.251 ROM Audit

AI Arcade cabinet, Raspberry Pi 5, checked 2 October 2026. Which of the cabinet's 233 arcade ROMs the standalone MAME 0.251 (the AI-mode emulator) accepts, which can be rebuilt from files already in the collection, and exactly which chip dumps the rest are missing. Read-only: nothing on the Pi was changed.

None of the games listed as missing is broken: each still plays in the emulator the cabinet uses for it today (lr-mame2000, lr-mame2003 or AdvanceMAME, whose older ROM versions these files match). "Missing" means MAME 0.251 will not start it until it has those files.

## Where the collection stands

| | Games | |
| --- | ---: | --- |
| Accepted as they are | 117 | load in MAME 0.251 today |
| Rebuildable | 26 | every file is in the collection; needs renaming and repacking |
| Missing chip dumps | 90 | need files from a newer ROM set; still play in today's emulators |

The 90 are short 291 files between them, 136 different ones.

## Chip files shared by several games

Most of what is missing is small lookup chips (PROMs and PALs) dumped after these ROM sets were made. Several games share the same chip, so a few files unlock many games. A number in brackets is how many other files that game still needs.

| Missing files | Games | Unlocks |
| --- | ---: | --- |
| `2085.5e8e`<br>`prom.c14`<br>`prom.d14`<br>`prom.e14`<br>`prom.e8`<br>`prom.f14`<br>`prom.j14` | 14 | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `036408-01.k7`<br>`136002-125.6c`<br>`136002-125.6h`<br>`136002-125.d7`<br>`136002-125.n4` | 9 | bradley (+7), bwidow, bzone (+7), gravitar (+2), mhavoc, quantum (+1), redbaron (+8), spacduel, tempest (+7) |
| `316-0764.cpu-u15`<br>`pr-82.cpu-u15` | 6 | astrob (+2), elim2, spacfury (+1), startrek (+1), tacscan, zektor (+1) |
| `hrl14h-1.14h`<br>`hrl14h-1.h14`<br>`hrl14h.h14`<br>`hrl_14h-1.14h` | 5 | mtrap (+2), pepper2 (+2), spectar (+2), targ (+3), venture (+3) |
| `decoder_rom_4.3g` | 5 | bubbles (+1), joust (+1), robotron (+1), sinistar (+1), stargate (+1) |
| `036174-01.a1`<br>`036174-01.b1`<br>`036175-01.e1`<br>`036175-01.m1`<br>`036176-01.f1`<br>`036176-01.l1`<br>`036177-01.h1`<br>`036177-01.k1`<br>`036178-01.j1`<br>`036179-01.h1`<br>`036179-01.k1`<br>`036180-01.f1`<br>`036180-01.l1`<br>`136002-126.a1`<br>`136002-127.e1`<br>`136002-128.f1`<br>`136002-129.h1`<br>`136002-130.j1`<br>`136002-131.k1`<br>`136002-132.l1` | 4 | bradley (+1), bzone (+1), redbaron (+2), tempest (+1) |
| `hrl6d-1.d6`<br>`hrl6d.d6`<br>`prom.6d`<br>`stl_6d-1.6d` | 4 | mtrap (+2), spectar (+2), targ (+3), venture (+3) |
| `6331.speech-u30`<br>`pr84.speech-u30` | 4 | astrob (+2), spacfury (+1), startrek (+1), zektor (+1) |
| `decoder_rom_6.3c` | 4 | bubbles (+1), joust (+1), robotron (+1), sinistar (+1) |
| `034602-01.c8` | 3 | astdelux, asteroid, llander (+1) |
| `xbl.12h`<br>`xbl.2h`<br>`xbl.4k`<br>`xbl.5k`<br>`xbl.6k`<br>`xbl.7k`<br>`xbl.8k`<br>`xbl.9h`<br>`xml-3k_mmi_6331.bin` | 2 | cracksht, crossbow |
| `pp1-13.8e`<br>`pp1-14.9e`<br>`pp1_27.1l` | 2 | polepos (+1), polepos2 (+2) |
| `136001-213.e7`<br>`136001-213.p4` | 2 | centiped, milliped |
| `prom-1.7a`<br>`prom-2.8a` | 2 | fireone, starfire |
| `vel5c-1.c5`<br>`vel5c-11.c5` | 2 | mtrap (+2), venture (+3) |
| `136021-109.4b` | 2 | esb, starwars (+4) |
| `pal10l8.8n` | 2 | galaga3, gaplus |

## Rebuildable from files already in the collection

Every file the 0.251 set needs is somewhere in the collection: rename and repack them under the 0.251 name.

| Your zip | 0.251 set | Game | Files also taken from |
| --- | --- | --- | --- |
| `amidar` | `amidar1` | Amidar (older) | — |
| `battles` | `battles` | Battles (set 1) | `xevious` |
| `bnj` | `bnjm` | Bump 'n' Jump (Midway) | — |
| `bosco` | `bosco3` | Bosconian - Star Destroyer (version 3) | — |
| `carnival` | `carnival` | Carnival (upright, AY8912 music) | `pulsar` |
| `demoderb` | `demoderbc` | Demolition Derby (cocktail) | — |
| `digdug` | `digdug1` | Dig Dug (rev 1) | `jrpacman` |
| `dotron` | `dotrona` | Discs of Tron (Upright, 9/22/83) | — |
| `dowild` | `dowild` | Mr. Do's Wild Ride | `dorunrun` |
| `frontlin` | `frontlina` | Front Line (FL, 5 PCB version) | — |
| `gorf` | `gorf` | Gorf | — |
| `headon` | `headon` | Head On (2 players) | `depthch` |
| `jumpcoas` | `jumpcoasa` | Jump Coaster | — |
| `polaris` | `polarisb` | Polaris (first revision) | — |
| `puckman` | `puckmanb` | Puck Man (bootleg set 1) | — |
| `qbert` | `qbert` | Q*bert (US set 1) | — |
| `radarscp` | `radarscpc` | Radar Scope (TRS02?, rev. C) | — |
| `rallyx` | `rallyx` | Rally X (32k Ver.?) | `jungler` |
| `reactor` | `reactor` | Reactor | — |
| `sbagman` | `sbagman2` | Super Bagman (version 3?) | — |
| `sdungeon` | `sdungeon` | Space Dungeon | — |
| `spacefb` | `spacefbe2` | Space Firebird (rev. 03-e set 2) | — |
| `spaceod` | `spaceod2` | Space Odyssey (version 1) | — |
| `tapper` | `tapperb` | Tapper (Budweiser, 1/12/84) | — |
| `tron` | `tron2` | Tron (6/25) | — |
| `wow` | `wow` | Wizard of Wor | — |

## Missing chip dumps, game by game

Each zip is matched to the 0.251 set that uses the most of its files. Often that is an older revision under a new name (`asteroid` here is Asteroids rev 2, `asteroid2` in 0.251).

### `arkanoid` — Arkanoid (World, older)

same name in 0.251 · Taito Corporation Japan, 1986. 9 of 12 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `a75__06.ic14` | Microcontroller | `mcu:mcu` | 2 KB | `0be83647` | — |
| `arkanoid_mcu.ic14` | Microcontroller | `alt_mcus` | 2 KB | `4e44b50a` | — |
| `arkanoid1_68705p3.ic14` | Microcontroller | `alt_mcus` | 2 KB | `1b68e2d8` | — |

### `armora` — Armor Attack

same name in 0.251 · Cinematronics, 1980. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `astdelux` — Asteroids Deluxe (rev 3)

same name in 0.251 · Atari, 1980. 6 of 7 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `034602-01.c8` | Lookup chip (PROM) | `dvg:prom` | 256 B | `97953db8` | asteroid, llander |

### `asteroid` — Asteroids (rev 2)

0.251 set `asteroid2` · clone of `asteroid` · Atari, 1979. 4 of 5 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `034602-01.c8` | Lookup chip (PROM) | `dvg:prom` | 256 B | `97953db8` | astdelux, llander |

### `astrob` — Astro Blaster (version 3)

same name in 0.251 · Sega, 1981. 25 of 28 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pr84.speech-u30` | Lookup chip (PROM) | `speech:proms` | 32 B | `adcb81d0` | spacfury, startrek, zektor |
| `316-0806.video1-u52` | Lookup chip (PROM) | `proms` | 32 B | `358128b6` | — |
| `316-0764.cpu-u15` | Lookup chip (PROM) | `proms` | 32 B | `c609b79e` | elim2, spacfury, startrek, tacscan, zektor |

### `aztarac` — Aztarac

same name in 0.251 · Centuri, 1983. 14 of 17 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `l5.l5` | Lookup chip (PROM) | `proms` | 32 B | `317fb438` | — |
| `k8.k8` | Lookup chip (PROM) | `proms` | 4 KB | `596ad8d9` | — |
| `k9.k9` | Lookup chip (PROM) | `proms` | 4 KB | `b8544823` | — |

### `barrier` — Barrier

same name in 0.251 · Cinematronics (Vectorbeam license), 1979. 2 of 8 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `berzerk` — Berzerk (revision RC31)

0.251 set `berzerka` · clone of `berzerk` · Stern Electronics, 1980. 6 of 8 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `berzerk_r_vo_1c.1c` | Sound ROM | `speech` | 2 KB | `2cfe825d` | — |
| `berzerk_r_vo_2c.2c` | Sound ROM | `speech` | 2 KB | `d2b6324e` | — |

### `boxingb` — Boxing Bugs

same name in 0.251 · Cinematronics, 1981. 8 of 14 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `bradley` — Bradley Trainer

same name in 0.251 · Atari, 1980. 10 of 18 files come from this zip; 8 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `036408-01.k7` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bwidow, bzone, gravitar, mhavoc, quantum, redbaron, spacduel, tempest |
| `036174-01.b1` | Lookup chip (PROM) | `user2` | 32 B | `8b04f921` | bzone, redbaron, tempest |
| `036175-01.m1` | Lookup chip (PROM) | `user3` | 256 B | `2af82e87` | bzone, redbaron, tempest |
| `036176-01.l1` | Lookup chip (PROM) | `user3` | 256 B | `b31f6e24` | bzone, redbaron, tempest |
| `036177-01.k1` | Lookup chip (PROM) | `user3` | 256 B | `8119b847` | bzone, redbaron, tempest |
| `036178-01.j1` | Lookup chip (PROM) | `user3` | 256 B | `09f5a4d5` | bzone, redbaron, tempest |
| `036179-01.h1` | Lookup chip (PROM) | `user3` | 256 B | `823b61ae` | bzone, redbaron, tempest |
| `036180-01.f1` | Lookup chip (PROM) | `user3` | 256 B | `276eadd5` | bzone, redbaron, tempest |

### `bubbles` — Bubbles

same name in 0.251 · Williams, 1982. 13 of 15 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `decoder_rom_4.3g` | Lookup chip (PROM) | `proms` | 512 B | `e6631c23` | joust, robotron, sinistar, stargate |
| `decoder_rom_6.3c` | Lookup chip (PROM) | `proms` | 512 B | `83faf25e` | joust, robotron, sinistar |

### `bublbobl` — Bubble Bobble (bootleg of Japan Ver 0.0 with 8749)

0.251 set `bub8749` · clone of `bublbobl` · bootleg, 1986. 17 of 18 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `p8749h.bin` | Microcontroller | `mcu` | 2 KB | `4912c847` | — |

### `buckrog` — Buck Rogers: Planet of Zoom

same name in 0.251 · Sega, 1982. 18 of 23 files come from this zip, more from `subroc3d`; 4 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pr-5194.cpu-ic39` | Lookup chip (PROM) | `proms` | 32 B | `bc88cced` | — |
| `pr-5196.cpu-ic10` | Lookup chip (PROM) | `proms` | 512 B | `04204bcf` | — |
| `pr-5197.cpu-ic78` | Lookup chip (PROM) | `proms` | 512 B | `a42674af` | — |
| `pr-5233.cpu-ic95` | Lookup chip (PROM) | `proms` | 1 KB | `1cd08c4e` | — |

### `bwidow` — Black Widow

same name in 0.251 · Atari, 1982. 10 of 11 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136002-125.n4` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bzone, gravitar, mhavoc, quantum, redbaron, spacduel, tempest |

### `bzone` — Battle Zone (rev 1)

0.251 set `bzonea` · clone of `bzone` · Atari, 1980. 8 of 16 files come from this zip; 8 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `036408-01.k7` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, gravitar, mhavoc, quantum, redbaron, spacduel, tempest |
| `036174-01.b1` | Lookup chip (PROM) | `user2` | 32 B | `8b04f921` | bradley, redbaron, tempest |
| `036175-01.m1` | Lookup chip (PROM) | `user3` | 256 B | `2af82e87` | bradley, redbaron, tempest |
| `036176-01.l1` | Lookup chip (PROM) | `user3` | 256 B | `b31f6e24` | bradley, redbaron, tempest |
| `036177-01.k1` | Lookup chip (PROM) | `user3` | 256 B | `8119b847` | bradley, redbaron, tempest |
| `036178-01.j1` | Lookup chip (PROM) | `user3` | 256 B | `09f5a4d5` | bradley, redbaron, tempest |
| `036179-01.h1` | Lookup chip (PROM) | `user3` | 256 B | `823b61ae` | bradley, redbaron, tempest |
| `036180-01.f1` | Lookup chip (PROM) | `user3` | 256 B | `276eadd5` | bradley, redbaron, tempest |

### `ccastles` — Crystal Castles (version 4)

same name in 0.251 · Atari, 1983. 7 of 11 files come from this zip; 4 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `82s129-136022-108.7k` | Lookup chip (PROM) | `proms` | 256 B | `6ed31e3b` | — |
| `82s129-136022-109.6l` | Lookup chip (PROM) | `proms` | 256 B | `b3515f1a` | — |
| `82s129-136022-110.11l` | Lookup chip (PROM) | `proms` | 256 B | `068bdc7e` | — |
| `82s129-136022-111.10k` | Lookup chip (PROM) | `proms` | 256 B | `c29c18d9` | — |

### `cchasm` — Cosmic Chasm (set 1)

same name in 0.251 · Cinematronics / GCE, 1983. 17 of 19 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pal12l6.u76` | Logic chip (PAL/PLD) | `plds` | 52 B | `a30e02b7` | — |
| `pal12l6.u77` | Logic chip (PAL/PLD) | `plds` | 52 B | `458b9cdb` | — |

### `centiped` — Centipede (revision 3)

0.251 set `centiped3` · clone of `centiped` · Atari, 1980. 6 of 7 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136001-213.p4` | Lookup chip (PROM) | `proms` | 256 B | `6fa3093a` | milliped |

### `circus` — Circus / Acrobat TV

same name in 0.251 · Exidy / Taito, 1977. 13 of 15 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `dm74s570-d4.4d` | Lookup chip (PROM) | `extra_proms` | 512 B | `aad8da33` | — |
| `dm74s570-d5.5d` | Lookup chip (PROM) | `extra_proms` | 512 B | `ed2493fa` | — |

### `cracksht` — Crackshot (version 2.0)

same name in 0.251 · Exidy, 1985. 37 of 46 files come from this zip; 9 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `xbl.12h` | Lookup chip (PROM) | `user1` | 256 B | `375c8bfc` | crossbow |
| `xbl.9h` | Lookup chip (PROM) | `user1` | 256 B | `2e7d5562` | crossbow |
| `xbl.2h` | Lookup chip (PROM) | `user1` | 256 B | `b078c1e4` | crossbow |
| `xml-3k_mmi_6331.bin` | Lookup chip (PROM) | `user1` | 32 B | `afa289d1` | crossbow |
| `xbl.4k` | Lookup chip (PROM) | `user1` | 256 B | `31a9549c` | crossbow |
| `xbl.5k` | Lookup chip (PROM) | `user1` | 256 B | `1379bb2a` | crossbow |
| `xbl.6k` | Lookup chip (PROM) | `user1` | 256 B | `588969f7` | crossbow |
| `xbl.7k` | Lookup chip (PROM) | `user1` | 256 B | `eda360b8` | crossbow |
| `xbl.8k` | Lookup chip (PROM) | `user1` | 256 B | `9d434cb1` | crossbow |

### `crossbow` — Crossbow (version 2.0)

same name in 0.251 · Exidy, 1983. 48 of 57 files come from this zip; 9 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `xbl.12h` | Lookup chip (PROM) | `user1` | 256 B | `375c8bfc` | cracksht |
| `xbl.9h` | Lookup chip (PROM) | `user1` | 256 B | `2e7d5562` | cracksht |
| `xbl.2h` | Lookup chip (PROM) | `user1` | 256 B | `b078c1e4` | cracksht |
| `xml-3k_mmi_6331.bin` | Lookup chip (PROM) | `user1` | 32 B | `afa289d1` | cracksht |
| `xbl.4k` | Lookup chip (PROM) | `user1` | 256 B | `31a9549c` | cracksht |
| `xbl.5k` | Lookup chip (PROM) | `user1` | 256 B | `1379bb2a` | cracksht |
| `xbl.6k` | Lookup chip (PROM) | `user1` | 256 B | `588969f7` | cracksht |
| `xbl.7k` | Lookup chip (PROM) | `user1` | 256 B | `eda360b8` | cracksht |
| `xbl.8k` | Lookup chip (PROM) | `user1` | 256 B | `9d434cb1` | cracksht |

### `defender` — Defender (Red label)

same name in 0.251 · Williams, 1980. 12 of 14 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `decoder.2` | Lookup chip (PROM) | `proms` | 512 B | `8dd98da5` | — |
| `decoder.3` | Lookup chip (PROM) | `proms` | 512 B | `c3f45f70` | — |

### `demon` — Demon

same name in 0.251 · Rock-Ola, 1982. 5 of 11 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `dkong3` — Donkey Kong 3 (US)

same name in 0.251 · Nintendo of America, 1983. 15 of 16 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `dkc1-v.5e` | Lookup chip (PROM) | `adrdecode` | 32 B | `d3e2eaf8` | — |

### `elevator` — Elevator Action (EA, 5 PCB version, 1.1)

0.251 set `elevatora` · clone of `elevator` · Taito Corporation, 1983. 20 of 21 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `ww15.pal16l8.ic24.jed.bin` | Logic chip (PAL/PLD) | `pal` | 279 B | `c3ec20d6` | — |

### `elim2` — Eliminator (2 Players, set 1)

same name in 0.251 · Gremlin, 1981. 15 of 16 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pr-82.cpu-u15` | Lookup chip (PROM) | `proms` | 32 B | `c609b79e` | astrob, spacfury, startrek, tacscan, zektor |

### `esb` — The Empire Strikes Back

same name in 0.251 · Atari Games, 1985. 13 of 14 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136021-109.4b` | Lookup chip (PROM) | `avg:prom` | 256 B | `82fc3eb2` | starwars |

### `fireone` — Fire One

same name in 0.251 · Exidy, 1979. 14 of 16 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom-1.7a` | Lookup chip (PROM) | `proms` | 32 B | `ae1f4acd` | starfire |
| `prom-2.8a` | Lookup chip (PROM) | `proms` | 32 B | `9b713924` | starfire |

### `foodf` — Food Fight (rev 3)

same name in 0.251 · General Computer Corporation (Atari license), 1982. 11 of 13 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136020-112.2p` | Lookup chip (PROM) | `proms` | 256 B | `0aa962d6` | — |
| `foodf.nv` | Lookup chip (PROM) | `nvram` | 256 B | `a4186b13` | — |

### `galaga` — Nebulous Bee

0.251 set `nebulbee` · clone of `galaga` · bootleg, 1981. 11 of 15 files come from this zip; 4 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `nebulbee.01` | Program ROM | `maincpu` | 4 KB | `f405f2c4` | — |
| `nebulbee.02` | Program ROM | `maincpu` | 4 KB | `31022b60` | — |
| `nebulbee.04` | Program ROM | `maincpu` | 4 KB | `d76788a5` | — |
| `nebulbee.07` | Data ROM | `sub3` | 4 KB | `035e300c` | — |

### `galaga3` — Galaga 3 (GP3 rev. C)

0.251 set `galaga3a` · clone of `gaplus` · Namco, 1984. 19 of 20 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pal10l8.8n` | Logic chip (PAL/PLD) | `plds` | 44 B | `08e5b2fe` | gaplus |

### `galaga88` — Galaga '88

same name in 0.251 · Namco, 1987. 24 of 25 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `g82_p6.bin` | Data ROM | `user1` | 64 KB | `403d01c1` | — |

### `galxwars` — Galaxy Wars (Universal set 1)

same name in 0.251 · Universal, 1979. 6 of 8 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `01.1` | Lookup chip (PROM) | `proms` | 1 KB | `aac24f34` | — |
| `02.2` | Lookup chip (PROM) | `proms` | 1 KB | `2bdf83a0` | — |

### `gaplus` — Galaga 3 (GP3 rev. D)

0.251 set `galaga3` · clone of `gaplus` · Namco, 1984. 16 of 20 files come from this zip, more from `galaga3`; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pal10l8.8n` | Logic chip (PAL/PLD) | `plds` | 44 B | `08e5b2fe` | galaga3 |

### `gaunt2` — Gauntlet II

same name in 0.251 · Atari Games, 1986. 24 of 26 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136043-1104.6p` | Graphics ROM | `gfx1` | 16 KB | `bddc3dfc` | — |
| `82s129-136043-1103.4r` | Lookup chip (PROM) | `proms` | 256 B | `32ae1fa9` | — |

### `gauntlet` — Gauntlet (rev 14)

same name in 0.251 · Atari Games, 1985. 19 of 20 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136037-104.6p` | Graphics ROM | `gfx1` | 16 KB | `6c276a1d` | — |

### `gravitar` — Gravitar (version 3)

same name in 0.251 · Atari, 1982. 10 of 13 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136002-125.n4` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, bzone, mhavoc, quantum, redbaron, spacduel, tempest |
| `136010-111.r1` | Lookup chip (PROM) | `proms` | 32 B | `6bf2dc46` | — |
| `136010-112.r2` | Lookup chip (PROM) | `proms` | 32 B | `b6af29d1` | — |

### `joust` — Joust (Green label)

same name in 0.251 · Williams, 1982. 13 of 15 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `decoder_rom_4.3g` | Lookup chip (PROM) | `proms` | 512 B | `e6631c23` | bubbles, robotron, sinistar, stargate |
| `decoder_rom_6.3c` | Lookup chip (PROM) | `proms` | 512 B | `83faf25e` | bubbles, robotron, sinistar |

### `joust2` — Joust 2 - Survival of the Fittest (revision 2)

same name in 0.251 · Williams, 1986. 25 of 28 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `vid_82s123_ic14_a-5282-10295.2b` | Lookup chip (PROM) | `proms` | 32 B | `85057e40` | — |
| `vid_82s129_ic47_a-5282-10294.15d` | Lookup chip (PROM) | `proms` | 256 B | `efb03024` | — |
| `vid_82s147a_ic60_a-5282-10292.12f` | Lookup chip (PROM) | `proms` | 512 B | `0ea3f7fb` | — |

### `llander` — Lunar Lander (rev 2)

same name in 0.251 · Atari, 1979. 6 of 8 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `034597-01.m3` | Program ROM | `maincpu` | 2 KB | `ebb744f2` | — |
| `034602-01.c8` | Lookup chip (PROM) | `dvg:prom` | 256 B | `97953db8` | astdelux, asteroid |

### `marble` — Marble Madness (set 1)

same name in 0.251 · Atari Games, 1984. 30 of 42 files come from this zip; 10 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136032.105.l13` | Program ROM | `maincpu` | 16 KB | `79021d3c` | — |
| `136032.106.l12` | Program ROM | `maincpu` | 16 KB | `76ee86c4` | — |
| `136032.114.j11` | Program ROM | `maincpu` | 16 KB | `195c54ad` | — |
| `136032.115.j10` | Program ROM | `maincpu` | 16 KB | `7275b4dc` | — |
| `136032.101.e3` | Lookup chip (PROM) | `motherbrd_proms` | 256 B | `7e84972a` | — |
| `136032.102.e5` | Lookup chip (PROM) | `motherbrd_proms` | 256 B | `ebf1e0ae` | — |
| `136032.103.f7` | Lookup chip (PROM) | `motherbrd_proms` | 235 B | `92d6a0b4` | — |
| `136032.101.e3` | Lookup chip (PROM) | `motherbrd_proms` | 256 B | `7e84972a` | — |
| `136032.102.e5` | Lookup chip (PROM) | `motherbrd_proms` | 256 B | `ebf1e0ae` | — |
| `136032.103.f7` | Lookup chip (PROM) | `motherbrd_proms` | 235 B | `92d6a0b4` | — |

### `mario` — Mario Bros. (US, Revision G)

same name in 0.251 · Nintendo of America, 1983. 14 of 15 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `tma1-c-5p.5p` | Lookup chip (PROM) | `decoder_prom` | 32 B | `58d86098` | — |

### `mhavoc` — Major Havoc (rev 3)

same name in 0.251 · Atari, 1983. 8 of 9 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136002-125.6c` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, bzone, gravitar, quantum, redbaron, spacduel, tempest |

### `milliped` — Millipede

same name in 0.251 · Atari, 1982. 6 of 7 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136001-213.e7` | Lookup chip (PROM) | `proms` | 256 B | `6fa3093a` | centiped |

### `missile` — Missile Command (rev 2)

0.251 set `missile2` · clone of `missile` · Atari, 1980. 6 of 7 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `035826-01.l6` | Lookup chip (PROM) | `proms` | 32 B | `86a22140` | — |

### `mpatrol` — Moon Patrol

same name in 0.251 · Irem, 1982. 15 of 17 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `mpc-4.2a` | Logic chip (PAL/PLD) | `tx_pal` | 512 B | `07f99284` | — |
| `mp_7621-5.7h` | Lookup chip (PROM) | `unkprom` | 512 B | `cf1fd9d0` | — |

### `mrdo` — Mr. Do!

same name in 0.251 · Universal, 1982. 14 of 15 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `u001_pal16r6cn.j2` | Logic chip (PAL/PLD) | `pal16r6` | 260 B | `84dbe498` | — |

### `mtrap` — Mouse Trap (version 5)

same name in 0.251 · Exidy, 1981. 14 of 17 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `hrl14h.h14` | Lookup chip (PROM) | `proms` | 32 B | `f76b4fcf` | pepper2, spectar, targ, venture |
| `vel5c-11.c5` | Lookup chip (PROM) | `proms` | 256 B | `43b35bb7` | venture |
| `hrl6d.d6` | Lookup chip (PROM) | `proms` | 32 B | `e26f9053` | spectar, targ, venture |

### `omegrace` — Omega Race (set 1)

same name in 0.251 · Midway, 1981. 7 of 8 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `dvgprom.bin` | Lookup chip (PROM) | `dvg:prom` | 256 B | `d481e958` | — |

### `pacland` — Pac-Land (World)

same name in 0.251 · Namco, 1984. 18 of 19 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `cus60-60a1.mcu` | Microcontroller | `mcu` | 4 KB | `076ea82a` | — |

### `paperboy` — Paperboy (rev 3)

same name in 0.251 · Atari Games, 1984. 26 of 27 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `paperboy-eeprom.bin` | Lookup chip (PROM) | `eeprom` | 512 B | `756b90cc` | — |

### `pepper2` — Pepper II (version 8)

same name in 0.251 · Exidy, 1982. 11 of 14 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `hrl14h-1.h14` | Lookup chip (PROM) | `proms` | 32 B | `f76b4fcf` | mtrap, spectar, targ, venture |
| `p2l5c-1.c5` | Lookup chip (PROM) | `proms` | 256 B | `e1e867ae` | — |
| `p2l6d-1.d6` | Lookup chip (PROM) | `proms` | 32 B | `0da1bdf9` | — |

### `polepos` — Pole Position (Japan)

0.251 set `poleposj` · clone of `polepos` · Namco, 1982. 35 of 40 files come from this zip, more from `polepos2`; 4 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pp1_9b.6h` | Program ROM | `maincpu` | 8 KB | `94436b70` | — |
| `pp1_27.1l` | Graphics ROM | `gfx6` | 4 KB | `a61bff15` | polepos2 |
| `pp1-13.8e` | Lookup chip (PROM) | `proms` | 32 B | `4330a51b` | polepos2 |
| `pp1-14.9e` | Lookup chip (PROM) | `proms` | 32 B | `4330a51b` | polepos2 |

### `polepos2` — Pole Position II (Japan)

same name in 0.251 · Namco, 1983. 39 of 44 files come from this zip; 5 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pp1_27.1l` | Graphics ROM | `gfx6` | 4 KB | `a61bff15` | polepos |
| `pp1-13.8e` | Lookup chip (PROM) | `proms` | 32 B | `4330a51b` | polepos |
| `pp1-14.9e` | Lookup chip (PROM) | `proms` | 32 B | `4330a51b` | polepos |
| `pp4_15.6a` | Data ROM | `engine` | 8 KB | `7d93bc1c` | — |
| `pp4_16.5a` | Data ROM | `engine` | 8 KB | `7d93bc1c` | — |

### `punchout` — Punch-Out!! (Rev A)

0.251 set `punchouta` · clone of `punchout` · Nintendo, 1984. 33 of 39 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `chp1-b-7e_pink.7e` | Lookup chip (PROM) | `proms` | 512 B | `fddaa777` | — |
| `chp1-b-8e_pink.8e` | Lookup chip (PROM) | `proms` | 512 B | `c3d5d71f` | — |
| `chp1-b-8f_pink.8f` | Lookup chip (PROM) | `proms` | 512 B | `a3037155` | — |
| `chp1-b-6e_white.6e` | Lookup chip (PROM) | `proms` | 512 B | `ddac5f0e` | — |
| `chp1-b-6f_white.6f` | Lookup chip (PROM) | `proms` | 512 B | `846c6261` | — |
| `chp1-b-7f_white.7f` | Lookup chip (PROM) | `proms` | 512 B | `1682dd30` | — |

### `qbertqub` — Q*bert's Qubes

same name in 0.251 · Mylstar, 1983. 10 of 12 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `qq-snd1.bin` | Program ROM | `r1sound:audiocpu` | 2 KB | `e704b450` | — |
| `qq-snd2.bin` | Program ROM | `r1sound:audiocpu` | 2 KB | `c6a98bf8` | — |

### `quantum` — Quantum (rev 2)

same name in 0.251 · General Computer Corporation (Atari license), 1982. 10 of 12 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136002-125.6h` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, bzone, gravitar, mhavoc, redbaron, spacduel, tempest |
| `cf2038n.1b` | Logic chip (PAL/PLD) | `plds` | 235 B | `b372fa4f` | — |

### `redbaron` — Red Baron (Revised Hardware)

same name in 0.251 · Atari, 1980. 8 of 17 files come from this zip; 9 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `036408-01.k7` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, bzone, gravitar, mhavoc, quantum, spacduel, tempest |
| `036174-01.a1` | Lookup chip (PROM) | `user2` | 32 B | `8b04f921` | bradley, bzone, tempest |
| `036175-01.e1` | Lookup chip (PROM) | `user3` | 256 B | `2af82e87` | bradley, bzone, tempest |
| `036176-01.f1` | Lookup chip (PROM) | `user3` | 256 B | `b31f6e24` | bradley, bzone, tempest |
| `036177-01.h1` | Lookup chip (PROM) | `user3` | 256 B | `8119b847` | bradley, bzone, tempest |
| `036178-01.j1` | Lookup chip (PROM) | `user3` | 256 B | `09f5a4d5` | bradley, bzone, tempest |
| `036179-01.k1` | Lookup chip (PROM) | `user3` | 256 B | `823b61ae` | bradley, bzone, tempest |
| `036180-01.l1` | Lookup chip (PROM) | `user3` | 256 B | `276eadd5` | bradley, bzone, tempest |
| `036464-01.a5` | Lookup chip (PROM) | `prom` | 32 B | `42875b18` | — |

### `ripoff` — Rip Off

same name in 0.251 · Cinematronics, 1980. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `robotron` — Robotron: 2084 (Solid Blue label)

same name in 0.251 · Williams / Vid Kidz, 1982. 13 of 15 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `decoder_rom_4.3g` | Lookup chip (PROM) | `proms` | 512 B | `e6631c23` | bubbles, joust, sinistar, stargate |
| `decoder_rom_6.3c` | Lookup chip (PROM) | `proms` | 512 B | `83faf25e` | bubbles, joust, sinistar |

### `sinistar` — Sinistar (revision 3)

same name in 0.251 · Williams, 1982. 16 of 18 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `decoder_rom_4.3g` | Lookup chip (PROM) | `proms` | 512 B | `e6631c23` | bubbles, joust, robotron, stargate |
| `decoder_rom_6.3c` | Lookup chip (PROM) | `proms` | 512 B | `83faf25e` | bubbles, joust, robotron |

### `solarq` — Solar Quest (rev 10 8 81)

same name in 0.251 · Cinematronics, 1981. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `spacduel` — Space Duel (version 2)

same name in 0.251 · Atari, 1980. 7 of 8 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136002-125.n4` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, bzone, gravitar, mhavoc, quantum, redbaron, tempest |

### `spacewar` — Space Wars

same name in 0.251 · Cinematronics, 1977. 2 of 8 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, speedfrk, starcas, starhawk, sundance, tailg, warrior, wotw |

### `spacfury` — Space Fury (revision C)

same name in 0.251 · Sega, 1981. 14 of 17 files come from this zip, more from `startrek`; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `6331.speech-u30` | Lookup chip (PROM) | `speech:proms` | 32 B | `adcb81d0` | astrob, startrek, zektor |
| `pr-82.cpu-u15` | Lookup chip (PROM) | `proms` | 32 B | `c609b79e` | astrob, elim2, startrek, tacscan, zektor |

### `spectar` — Spectar (revision 3)

same name in 0.251 · Exidy, 1980. 7 of 10 files come from this zip; 3 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `spl5c-2.5c` | Lookup chip (PROM) | `proms` | 256 B | `9ca2e061` | — |
| `prom.6d` | Lookup chip (PROM) | `proms` | 32 B | `e26f9053` | mtrap, targ, venture |
| `hrl14h-1.14h` | Lookup chip (PROM) | `proms` | 32 B | `f76b4fcf` | mtrap, pepper2, targ, venture |

### `speedfrk` — Speed Freak

same name in 0.251 · Vectorbeam, 1979. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, starcas, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, starcas, starhawk, sundance, tailg, warrior, wotw |

### `spnchout` — Super Punch-Out!! (Rev B)

same name in 0.251 · Nintendo, 1984. 33 of 39 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `chs1-b-7e_pink.7e` | Lookup chip (PROM) | `proms` | 512 B | `4c7e3a67` | — |
| `chs1-b-8e_pink.8e` | Lookup chip (PROM) | `proms` | 512 B | `ec659313` | — |
| `chs1-b-8f_pink.8f` | Lookup chip (PROM) | `proms` | 512 B | `8b493c09` | — |
| `chs1-b-6e_white.6e` | Lookup chip (PROM) | `proms` | 512 B | `8efd867f` | — |
| `chs1-b-6f_white.6f` | Lookup chip (PROM) | `proms` | 512 B | `279d6cbc` | — |
| `chs1-b-7f_white.7f` | Lookup chip (PROM) | `proms` | 512 B | `cad6b7ad` | — |

### `spyhunt` — Spy Hunter

same name in 0.251 · Bally Midway, 1983. 24 of 25 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `spy-hunter_cpu_pg5_2-9-84.11d` | Program ROM | `maincpu` | 16 KB | `88aa1e99` | — |

### `ssi` — Super Space Invaders '91 (World, revised code, Rev 1)

same name in 0.251 · Taito Corporation Japan, 1990. 5 of 7 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `c64-10.ic42` | Logic chip (PAL/PLD) | `plds` | 279 B | `08e8c3d6` | — |
| `c64-11.ic43` | Logic chip (PAL/PLD) | `plds` | 279 B | `f116413e` | — |

### `starcas` — Star Castle (version 3)

same name in 0.251 · Cinematronics, 1980. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starhawk, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starhawk, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starhawk, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starhawk, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starhawk, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starhawk, sundance, tailg, warrior, wotw |

### `starfire` — Star Fire (set 1)

same name in 0.251 · Exidy, 1979. 11 of 13 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom-1.7a` | Lookup chip (PROM) | `proms` | 32 B | `ae1f4acd` | fireone |
| `prom-2.8a` | Lookup chip (PROM) | `proms` | 32 B | `9b713924` | fireone |

### `stargate` — Stargate

same name in 0.251 · Williams / Vid Kidz, 1981. 13 of 15 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `decoder_rom_4.3g` | Lookup chip (PROM) | `proms` | 512 B | `e6631c23` | bubbles, joust, robotron, sinistar |
| `decoder_rom_5.3c` | Lookup chip (PROM) | `proms` | 512 B | `f921c5fe` | — |

### `starhawk` — Starhawk

same name in 0.251 · Cinematronics, 1979. 2 of 9 files come from this zip; 7 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |
| `2085.5e8e` | Lookup chip (PROM) | `soundboard:sound_nl:2085.5e8e` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, sundance, tailg, warrior, wotw |

### `startrek` — Star Trek

same name in 0.251 · Sega, 1982. 28 of 30 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `6331.speech-u30` | Lookup chip (PROM) | `speech:proms` | 32 B | `adcb81d0` | astrob, spacfury, zektor |
| `pr-82.cpu-u15` | Lookup chip (PROM) | `proms` | 32 B | `c609b79e` | astrob, elim2, spacfury, tacscan, zektor |

### `starwars` — Star Wars (set 1)

same name in 0.251 · Atari, 1983. 8 of 13 files come from this zip; 5 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136021-109.4b` | Lookup chip (PROM) | `avg:prom` | 256 B | `82fc3eb2` | esb |
| `136021-110.7h` | Lookup chip (PROM) | `user2` | 1 KB | `810e040e` | — |
| `136021-111.7j` | Lookup chip (PROM) | `user2` | 1 KB | `ae69881c` | — |
| `136021-112.7k` | Lookup chip (PROM) | `user2` | 1 KB | `ecf22628` | — |
| `136021-113.7l` | Lookup chip (PROM) | `user2` | 1 KB | `83febfde` | — |

### `sundance` — Sundance

same name in 0.251 · Cinematronics, 1979. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, tailg, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, tailg, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, tailg, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, tailg, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, tailg, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, tailg, warrior, wotw |

### `tacscan` — Tac/Scan

same name in 0.251 · Sega, 1982. 22 of 24 files come from this zip, more from `startrek`; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pr-82.cpu-u15` | Lookup chip (PROM) | `proms` | 32 B | `c609b79e` | astrob, elim2, spacfury, startrek, zektor |

### `tailg` — Tailgunner

same name in 0.251 · Cinematronics, 1979. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, warrior, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, warrior, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, warrior, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, warrior, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, warrior, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, warrior, wotw |

### `tankbatt` — Tank Battalion

same name in 0.251 · Namco, 1980. 5 of 6 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `bct1-1.l3` | Lookup chip (PROM) | `proms` | 256 B | `d17518bc` | — |

### `targ` — Targ

same name in 0.251 · Exidy, 1980. 6 of 10 files come from this zip; 4 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `hrl_5c-1.5c` | Lookup chip (PROM) | `proms` | 256 B | `a24290d0` | — |
| `stl_6d-1.6d` | Lookup chip (PROM) | `proms` | 32 B | `e26f9053` | mtrap, spectar, venture |
| `hrl_14h-1.14h` | Lookup chip (PROM) | `proms` | 32 B | `f76b4fcf` | mtrap, pepper2, spectar, venture |
| `hra2b-1` | Lookup chip (PROM) | `targ` | 32 B | `38e8024b` | — |

### `tempest` — Tempest (rev 3)

0.251 set `tempest3` · clone of `tempest` · Atari, 1980. 12 of 20 files come from this zip; 8 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `136002-125.d7` | Lookup chip (PROM) | `avg:prom` | 256 B | `5903af03` | bradley, bwidow, bzone, gravitar, mhavoc, quantum, redbaron, spacduel |
| `136002-126.a1` | Lookup chip (PROM) | `user2` | 32 B | `8b04f921` | bradley, bzone, redbaron |
| `136002-132.l1` | Lookup chip (PROM) | `user3` | 256 B | `2af82e87` | bradley, bzone, redbaron |
| `136002-131.k1` | Lookup chip (PROM) | `user3` | 256 B | `b31f6e24` | bradley, bzone, redbaron |
| `136002-130.j1` | Lookup chip (PROM) | `user3` | 256 B | `8119b847` | bradley, bzone, redbaron |
| `136002-129.h1` | Lookup chip (PROM) | `user3` | 256 B | `09f5a4d5` | bradley, bzone, redbaron |
| `136002-128.f1` | Lookup chip (PROM) | `user3` | 256 B | `823b61ae` | bradley, bzone, redbaron |
| `136002-127.e1` | Lookup chip (PROM) | `user3` | 256 B | `276eadd5` | bradley, bzone, redbaron |

### `turbo` — Turbo (program 1513-1515)

same name in 0.251 · Sega, 1981. 32 of 38 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `pr-1119.cpu-ic50` | Lookup chip (PROM) | `proms` | 512 B | `57ebd4bc` | — |
| `pr-1120.cpu-ic62` | Lookup chip (PROM) | `proms` | 512 B | `8dd4c8a8` | — |

### `ultratnk` — Ultra Tank

same name in 0.251 · Atari (Kee Games), 1978. 10 of 12 files come from this zip; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `30218-01.j10` | Lookup chip (PROM) | `proms` | 32 B | `d7a2c7b4` | — |
| `30024-01.p8` | Lookup chip (PROM) | `user1` | 512 B | `e71d2e22` | — |

### `venture` — Venture (version 5 set 1)

same name in 0.251 · Exidy, 1981. 13 of 17 files come from this zip; 4 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `vel_11d-2.11d` | Graphics ROM | `gfx1` | 2 KB | `ea6fd981` | — |
| `hrl14h-1.h14` | Lookup chip (PROM) | `proms` | 32 B | `f76b4fcf` | mtrap, pepper2, spectar, targ |
| `vel5c-1.c5` | Lookup chip (PROM) | `proms` | 256 B | `43b35bb7` | mtrap |
| `hrl6d-1.d6` | Lookup chip (PROM) | `proms` | 32 B | `e26f9053` | mtrap, spectar, targ |

### `warlords` — Warlords

same name in 0.251 · Atari, 1980. 8 of 9 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `037161-01.m6` | Lookup chip (PROM) | `proms` | 256 B | `4cd24c85` | — |

### `warrior` — Warrior

same name in 0.251 · Vectorbeam, 1979. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, wotw |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, wotw |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, wotw |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, wotw |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, wotw |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, wotw |

### `wotw` — War of the Worlds

same name in 0.251 · Cinematronics, 1981. 4 of 10 files come from this zip; 6 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `prom.f14` | Lookup chip (PROM) | `proms` | 256 B | `9edbf536` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior |
| `prom.e14` | Lookup chip (PROM) | `proms` | 32 B | `29dbfb87` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior |
| `prom.d14` | Lookup chip (PROM) | `proms` | 32 B | `9a05afbf` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior |
| `prom.c14` | Lookup chip (PROM) | `proms` | 32 B | `07492cda` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior |
| `prom.j14` | Lookup chip (PROM) | `proms` | 32 B | `a481ca71` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior |
| `prom.e8` | Lookup chip (PROM) | `proms` | 32 B | `791ec9e1` | armora, barrier, boxingb, demon, ripoff, solarq, spacewar, speedfrk, starcas, starhawk, sundance, tailg, warrior |

### `xevious` — Xevious (Namco)

same name in 0.251 · Namco, 1982. 26 of 27 files come from this zip; 1 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `xvi-3.1f` | Logic chip (PAL/PLD) | `pals_vidbd` | 279 B | `9192d57a` | — |

### `zektor` — Zektor (revision B)

same name in 0.251 · Sega, 1982. 26 of 29 files come from this zip, more from `startrek`; 2 missing.

| Missing file | What it is | Board region | Size | CRC32 | Also needed by |
| --- | --- | --- | ---: | --- | --- |
| `6331.speech-u30` | Lookup chip (PROM) | `speech:proms` | 32 B | `adcb81d0` | astrob, spacfury, startrek |
| `pr-82.cpu-u15` | Lookup chip (PROM) | `proms` | 32 B | `c609b79e` | astrob, elim2, spacfury, startrek, tacscan |

## Already accepted by MAME 0.251

`anteater`, `armorcar`, `astinvad`, `astrof`, `atlantis`, `bagman`, `bking`, `blkhole`, `blockade`, `blstroid`, `blueprnt`, `bombjack`, `boothill`, `brubber`, `btime`, `canyon`, `cavenger`, `cclimber`, `congo`, `cosmicg`, `crush`, `depthch`, `digdug2`, `digger`, `dkong`, `dkongjr`, `docastle`, `dodgem`, `dorunrun`, `exterm`, `fnkyfish`, `frogger`, `galaxian`, `gridlee`, `gunfight`, `gyruss`, `hustler`, `insector`, `invad2ct`, `invaders`, `invadpt2`, `invinco`, `irobot`, `jack`, `jedi`, `journey`, `jrpacman`, `jumpbug`, `junglek`, `jungler`, `kangaroo`, `ladybug`, `lazercmd`, `lnc`, `lrescue`, `mappy`, `minefld`, `mineswpr`, `monsterb`, `moonal2`, `mooncrst`, `moonwar`, `mplanets`, `mshuttle`, `mspacman`, `natodef`, `nitedrvr`, `nyny`, `orbitron`, `pacman`, `pacplus`, `panic`, `pengo`, `phoenix`, `pisces`, `pitfall2`, `pleiads`, `pooyan`, `popeye`, `pulsar`, `qix`, `r2dtank`, `redalert`, `satansat`, `sbrkout`, `scobra`, `scramble`, `seawolf`, `seawolf2`, `sharkatt`, `shollow`, `skydiver`, `skyraid`, `snapjack`, `solarfox`, `spacecr`, `spiders`, `starcrus`, `starforc`, `starjack`, `starshp1`, `streakng`, `subroc3d`, `subs`, `superbug`, `superpac`, `swimmer`, `szaxxon`, `tankfrce`, `thehand`, `thief`, `timeplt`, `tutankhm`, `vanguard`, `wacko`, `warofbug`, `zaxxon`
