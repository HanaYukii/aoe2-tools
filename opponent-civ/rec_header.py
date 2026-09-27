"""Read the lobby players out of an AoE2 DE recording (.aoe2record).

A recording starts with a DEFLATE-compressed header whose first block is the
DE lobby settings, including every player's name, civilization and team. Only
that block is decoded: it sits in the first few KB of the file, so the map,
scenario and body that follow are never touched.

Field layout follows aoc-mgz `fast/header.py::parse_de`, plus the per-player
string that save version 67.2 appended (aoc-mgz PR #147, unmerged as of
2026-09). Checked against save versions 67.2, 68.0 and 68.9.
"""
import struct
import zlib
from dataclasses import dataclass

MIN_SAVE = 66.3        # from 66.3 on, all 8 lobby slots are always stored
LOBBY_SLOTS = 8
READ_LIMIT = 256 * 1024
DECOMPRESS_LIMIT = 256 * 1024
DE_STRING_MARK = b'\x60\x0a'

TYPE_HUMAN = 2
TYPE_AI = 4
NO_TEAM = (0, 1)       # 0 in single player lobbies, 1 = "-" in multiplayer


class NotReady(Exception):
    """The header is not (fully) on disk yet; retry later."""


class Unsupported(Exception):
    """The header does not match the layout this parser knows."""


@dataclass(frozen=True)
class Player:
    number: int        # lobby slot, 1-8
    name: str
    civ_id: int
    team: int
    color_id: int
    profile_id: int
    type: int

    @property
    def is_human(self):
        return self.type == TYPE_HUMAN


@dataclass(frozen=True)
class Match:
    save_version: float
    build: int
    timestamp: int
    multiplayer: bool
    rated: bool
    hidden_civs: bool
    players: tuple


class _Reader:
    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def _need(self, n):
        if self.pos + n > len(self.buf):
            raise NotReady(f'header ends at {len(self.buf)}, need {self.pos + n}')

    def skip(self, n):
        self._need(n)
        self.pos += n

    def take(self, n):
        self._need(n)
        self.pos += n
        return self.buf[self.pos - n:self.pos]

    def unpack(self, fmt):
        size = struct.calcsize(fmt)
        self._need(size)
        values = struct.unpack_from(fmt, self.buf, self.pos)
        self.pos += size
        return values if len(values) > 1 else values[0]

    def de_string(self):
        if self.take(2) != DE_STRING_MARK:
            raise Unsupported(f'no string marker at offset {self.pos - 2}')
        length = self.unpack('<h')
        if length < 0:
            raise Unsupported(f'negative string length at offset {self.pos - 2}')
        return self.take(length).decode('utf-8', 'replace')


def read_match(path):
    """Parse the recording at `path`; raises NotReady or Unsupported."""
    with open(path, 'rb') as handle:
        return parse_match(handle.read(READ_LIMIT))


def parse_match(raw):
    if len(raw) < 16:
        raise NotReady(f'only {len(raw)} bytes on disk')
    try:
        buf = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw[8:], DECOMPRESS_LIMIT)
    except zlib.error as e:
        # Also what a preallocated, not-yet-written file looks like.
        raise NotReady(f'header does not inflate yet: {e}') from e
    return _parse_de(_Reader(buf))


def _parse_de(r):
    game = r.take(8)
    if not game.startswith(b'VER 9.4'):
        raise Unsupported(f'game version {game!r}')
    save = r.unpack('<f')
    if save == -1:
        save = r.unpack('<I') / (1 << 16)
    save = round(save, 2)
    if save < MIN_SAVE:
        raise Unsupported(f'save version {save} predates {MIN_SAVE}')

    build, timestamp = r.unpack('<II')
    r.skip(12)
    r.skip(4 * r.unpack('<I'))  # DLC ids
    r.skip(4 + 4 + 4 + 4 + 4)   # ?, map size, ?, map id, ?
    r.skip(4 * 4)               # victory, resources, starting age, ending age
    r.skip(12)
    r.skip(4 + 4 + 4)           # speed, treaty length, population
    num_players = r.unpack('<I')
    r.skip(14)
    r.skip(1 + 2 + 1)           # difficulty, random positions, all techs, ?
    r.skip(2)                   # lock teams, lock speed
    multiplayer = r.unpack('<b')
    r.skip(7)                   # cheats ... team positions
    r.skip(12 + 1 + 1)

    players = []
    for _ in range(LOBBY_SLOTS):
        r.skip(4)
        color_id = r.unpack('<i')
        r.skip(2)
        team = r.unpack('<b')
        r.skip(9)
        civ_id = r.unpack('<I')
        r.skip(4 * r.unpack('<I'))  # random-civ pool
        r.de_string()               # AI type
        r.skip(1)
        ai_name = r.de_string()
        r.de_string()               # censored name
        name = r.de_string() or ai_name
        type_ = r.unpack('<I')
        profile_id, number = r.unpack('<I4xi')
        r.skip(1 + 1 + 8 + 4)       # prefer random, ?, handicap, ?
        if save >= 67.2:
            r.de_string()
        if number > 0 and type_ in (TYPE_HUMAN, TYPE_AI):
            players.append(Player(number, name, civ_id, team, color_id, profile_id, type_))

    r.skip(12 + 4)
    rated, _allow_specs, _visibility, hidden_civs = r.unpack('<bbIb')

    if len(players) != num_players:
        raise Unsupported(f'lobby says {num_players} players, found {len(players)} slots')
    return Match(save, build, timestamp, multiplayer == 1, rated == 1, hidden_civs == 1,
                 tuple(sorted(players, key=lambda p: p.number)))


def split_sides(match, my_profile_id):
    """(me, allies, enemies) from `my_profile_id`'s point of view; me is None if absent."""
    me = next((p for p in match.players if p.profile_id == my_profile_id), None)
    if me is None:
        return None, [], list(match.players)
    others = [p for p in match.players if p is not me]
    allied = [p for p in others if me.team not in NO_TEAM and p.team == me.team]
    return me, allied, [p for p in others if p not in allied]
