"""Battlezone's work RAM -> named game state (the decoded layer: what the game holds, nothing concluded).

Names follow Atari's source (RAM_MAP.md). Atari keeps several values as a pair: the player's tank at +0, the enemy
("robot") at +2 (the source indexes them as NAME,X with X = 0 or 2). Positions are signed 16-bit world units;
angles are 8-bit, 256 to a full circle (the 9th bit, LANGLE bit 7, is kept as `angle9`).
"""
from dataclasses import dataclass

BASE = 0x0000
IMAGE = (BASE, 0x0400)

CREDITS, COINS = 0x0E, 0x21
TANGLE, LANGLE = 0x2A, 0x27  # angles: tank at +0, enemy at +2 (TANGLE+2 = $2C)
TPOSX, TPOSY = 0x2D, 0x31  # 2 bytes each: tank at +0, enemy at +2
FIRECT = 0x24
SHELLX, SHELLY = 0xA8, 0xAC
HITS = 0xB8  # 2 bytes each: the tank's hits (the score) at +0, the enemy's hits on the tank at +2
CRACK, EIRNGE, R2D3FL, LIVES, GOVER, ATRACT = 0xC7, 0xC9, 0xCB, 0xCC, 0xCD, 0xCE
SAPOSX, SAPOSY, SAUCER = 0xD5, 0xD7, 0xDE
FRAME = 0xC6
TDIST = 0x02E8


def u16(image, address):
    return image[address] | image[address + 1] << 8


def s16(image, address):
    v = u16(image, address)
    return v - 0x10000 if v & 0x8000 else v


@dataclass(frozen=True)
class Tank:
    x: int
    y: int
    angle: int  # 0-255
    shell: tuple  # (x, y) of its shell; the source says nothing of a "no shell" value yet (verify)


@dataclass(frozen=True)
class BattlezoneState:
    playing: bool  # ATRACT = FF in a game, 00 in the attract demo
    game_over: bool  # GOVER: game over / high-score table showing
    credits: int
    coins: int  # coins toward the next credit
    lives: int
    hits: int  # the player's hits, raw 16-bit (the score; display units to verify)
    hits_taken: int  # the enemy's hits on the player
    dying: int  # CRACK: the cracked-windshield counter, nonzero while the death plays
    enemy_in_range: int  # EIRNGE, raw
    missile: int  # R2D3FL, raw: the homing missile ("buzz bomb")
    saucer: int  # SAUCER flag, raw
    saucer_pos: tuple
    tank: Tank
    enemy: Tank
    enemy_distance: int  # TDIST: high byte of the distance, from the radar routine
    angle9: int  # the tank's 9-bit angle (0-511)
    frame: int


def decode(image):
    image = bytes(image)
    tank = Tank(s16(image, TPOSX), s16(image, TPOSY), image[TANGLE], (s16(image, SHELLX), s16(image, SHELLY)))
    enemy = Tank(s16(image, TPOSX + 2), s16(image, TPOSY + 2), image[TANGLE + 2],
                 (s16(image, SHELLX + 2), s16(image, SHELLY + 2)))
    return BattlezoneState(
        playing=image[ATRACT] == 0xFF, game_over=bool(image[GOVER]), credits=image[CREDITS], coins=image[COINS],
        lives=image[LIVES], hits=u16(image, HITS), hits_taken=u16(image, HITS + 2), dying=image[CRACK],
        enemy_in_range=image[EIRNGE], missile=image[R2D3FL], saucer=image[SAUCER],
        saucer_pos=(s16(image, SAPOSX), s16(image, SAPOSY)), tank=tank, enemy=enemy,
        enemy_distance=image[TDIST], angle9=image[TANGLE] << 1 | image[LANGLE] >> 7, frame=image[FRAME])
