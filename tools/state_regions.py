"""Game RAM regions: written for the Pi's exporter, and rebuilt into the image a game decodes. Game-agnostic.

A region is (start, end, every) or (start, end, every, cpu, space): `every` is how many frames between refreshes, and
cpu/space name the MAME device and address space it is read from (default ":maincpu" and "program").
"""

DEFAULT_CPU, DEFAULT_SPACE = ":maincpu", "program"


def regions_lua(regions):
    """The regions.lua file tools/mame_state_export.lua reads: { {start, end, every, cpu, space}, ... }."""
    rows = []
    for r in regions:
        every = r[2] if len(r) > 2 else 1
        cpu = r[3] if len(r) > 3 else DEFAULT_CPU
        space = r[4] if len(r) > 4 else DEFAULT_SPACE
        rows.append(f'{{0x{r[0]:X}, 0x{r[1]:X}, {every}, "{cpu}", "{space}"}}')
    return "return {" + ", ".join(rows) + "}\n"


def expand(raw, regions, base, size):
    """Place each exported region (concatenated in order in `raw`) at its address in a zeroed image.

    regions: as in the game's AGENT_REGIONS. base/size: the image window the game's decoder expects (the game's IMAGE).
    One window per game: regions read from another address space must not overlap it (none does yet).
    """
    buf = bytearray(size)
    pos = 0
    for r in regions:
        start, end = r[0], r[1]
        length = end - start + 1
        buf[start - base: end - base + 1] = raw[pos: pos + length]
        pos += length
    return bytes(buf)
