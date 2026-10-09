#!/usr/bin/env python3
"""ワールドの待合ロビー(namespace worlds の lobby)の足場を Sponge v3 schematic で書き出す。

11x1x11 の石レンガの床に、縁を滑らかな石、四隅と中央の十字にシーランタン(明かり)を置いただけのもの。
NBT は手書き(依存ライブラリ無し)。ブロックはブロックステートの要らないものだけを使う。

    python3 scripts/make_lobby_schem.py /tmp/lobby.schem
    base64 -w0 /tmp/lobby.schem   # → kubernetes/sites/site1/apps/worlds/lobby.yaml の binaryData.lobby.schem

gzip のヘッダに時刻を入れない(mtime=0)ので、同じ内容なら毎回同じバイト列になる。
"""
import gzip
import struct
import sys

W, H, L = 11, 1, 11
# Minecraft 26.x 世代の DataVersion(ianua-silvae の SchematicReader は値を見ずに読む)
DATA_VERSION = 4325


def s(name):  # NBT の文字列
    b = name.encode()
    return struct.pack(">H", len(b)) + b


def tag(t, name, payload):
    return bytes([t]) + s(name) + payload


def short(n, v):
    return tag(2, n, struct.pack(">h", v))


def int_(n, v):
    return tag(3, n, struct.pack(">i", v))


def bytearr(n, data):
    return tag(7, n, struct.pack(">i", len(data)) + bytes(data))


def intarr(n, vals):
    return tag(11, n, struct.pack(">i", len(vals)) + b"".join(struct.pack(">i", v) for v in vals))


def compound(n, *children):
    return tag(10, n, b"".join(children) + b"\x00")


def list_empty(n, elem=10):
    return tag(9, n, bytes([elem]) + struct.pack(">i", 0))


PALETTE = {"minecraft:stone_bricks": 0, "minecraft:smooth_stone": 1, "minecraft:sea_lantern": 2}
LIGHTS = {(0, 0), (0, L - 1), (W - 1, 0), (W - 1, L - 1), (W // 2, 2), (W // 2, L - 3), (2, L // 2), (W - 3, L // 2)}


def block(x, z):
    if (x, z) in LIGHTS:
        return PALETTE["minecraft:sea_lantern"]
    if x in (0, W - 1) or z in (0, L - 1):
        return PALETTE["minecraft:smooth_stone"]
    return PALETTE["minecraft:stone_bricks"]


def main():
    # Sponge v3 の並びは (y, z, x)。パレットの番号はすべて 128 未満なので varint は 1 バイト
    data = [block(x, z) for _ in range(H) for z in range(L) for x in range(W)]
    root = compound("", compound(
        "Schematic",
        int_("Version", 3), int_("DataVersion", DATA_VERSION),
        short("Width", W), short("Height", H), short("Length", L),
        intarr("Offset", [0, 0, 0]),
        compound(
            "Blocks",
            compound("Palette", *[int_(k, v) for k, v in PALETTE.items()]),
            bytearr("Data", data),
            list_empty("BlockEntities"),
        ),
    ))
    with open(sys.argv[1], "wb") as f:
        f.write(gzip.compress(root, mtime=0))


if __name__ == "__main__":
    main()
