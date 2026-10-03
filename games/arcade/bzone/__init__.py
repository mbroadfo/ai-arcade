"""Battlezone (Atari 1980, MAME romset "bzone", rev 2; built for MAME 0.251 with tools/add_rom_files.py).

Workshop stages 0-2 (docs/GAME_WORKSHOP.md): what the Pi streams. The 6502's work RAM is 0x0000-0x03FF (MAME's
bzone driver memory map, `mame` provenance); vector RAM (0x2000-0x2FFF) and the math box are not read yet.
README.md says what is checked and what comes next.
"""
IMAGE = (0x0000, 0x0400)  # the RAM window a decoder reads: (base address, size)
REGIONS = [(0x0000, 0x03FF)]  # all of work RAM, every frame (validation and discovery)
AGENT_REGIONS = REGIONS  # 1 KB a frame; narrowed once the RAM map is known
