"""Rebuild a game's RAM image from the compact region export the Pi streams. Game-agnostic."""


def expand(raw, regions, base=0x4000, size=0x1000):
    """Place each exported region (concatenated in order in `raw`) at its address in a zeroed image.

    regions: [(start, end, every)] as in the game's AGENT_REGIONS; base/size describe the image the
    game's decoder expects (defaults suit the Pac-Man family: 0x4000..0x4FFF).
    """
    buf = bytearray(size)
    pos = 0
    for start, end, _every in regions:
        length = end - start + 1
        buf[start - base: end - base + 1] = raw[pos: pos + length]
        pos += length
    return bytes(buf)
