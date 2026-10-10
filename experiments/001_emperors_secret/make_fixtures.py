"""Create deterministic, visibly artificial 9:16 PNGs for offline contract checks only."""

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 720, 1280
FONT = {
    " ": ["00000"] * 7,
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
}


def chunk(kind: bytes, content: bytes) -> bytes:
    return (
        struct.pack(">I", len(content))
        + kind
        + content
        + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)
    )


def fixture_png(scene: int) -> bytes:
    backgrounds = [(28, 37, 40), (29, 34, 43), (24, 33, 41)]
    data = bytearray(bytes(backgrounds[scene - 1]) * (WIDTH * HEIGHT))

    def rectangle(left: int, top: int, right: int, bottom: int, rgb: tuple[int, int, int]):
        row = bytes(rgb) * (right - left)
        for y in range(top, bottom):
            start = (y * WIDTH + left) * 3
            data[start : start + len(row)] = row

    def label(message: str, x: int, y: int, scale: int, rgb: tuple[int, int, int]):
        for letter in message:
            for row_number, pattern in enumerate(FONT[letter]):
                for column, pixel in enumerate(pattern):
                    if pixel == "1":
                        rectangle(
                            x + column * scale,
                            y + row_number * scale,
                            x + (column + 1) * scale,
                            y + (row_number + 1) * scale,
                            rgb,
                        )
            x += 6 * scale

    # Flat geometry suggests the planned shot without impersonating generated imagery.
    rectangle(42, 180, 678, 1010, (61, 54, 54))  # archive wall
    rectangle(82, 260, 305, 820, (79, 55, 46))  # shelf
    rectangle(105, 290, 282, 307, (150, 111, 75))
    rectangle(105, 390, 282, 407, (150, 111, 75))
    rectangle(360, 250, 630, 800, (84, 62, 54))  # lattice door
    rectangle(389, 280, 402, 770, (145, 111, 74))
    rectangle(490, 280, 503, 770, (145, 111, 74))
    rectangle(590, 280, 603, 770, (145, 111, 74))
    rectangle(350, 490, 640, 503, (145, 111, 74))
    if scene == 3:
        rectangle(515, 255, 638, 790, (15, 20, 29))  # open secret doorway
    rectangle(95, 795, 625, 875, (99, 59, 42))  # archive desk
    rectangle(143, 730, 337, 770, (207, 182, 132))  # document
    rectangle(293, 738, 309, 763, (147, 49, 43))  # seal
    rectangle(469, 678, 482, 785, (226, 188, 113))  # candle
    rectangle(457, 653, 494, 677, (240, 164, 78))
    rectangle(398, 508, 456, 565, (198, 155, 125))  # schematic head
    rectangle(387, 556, 478, 789, (30, 91, 88))  # teal costume
    rectangle(425, 483, 456, 507, (23, 22, 26))  # hair
    rectangle(444, 478, 455, 508, (169, 182, 134))  # jade hairpin
    rectangle(50, 45, 670, 153, (88, 31, 39))
    label("MOCK FIXTURE", 111, 73, 7, (255, 239, 211))
    rectangle(50, 1060, 670, 1195, (88, 31, 39))
    label(f"SCENE 0{scene}", 171, 1093, 9, (255, 239, 211))
    raw = b"".join(b"\x00" + data[y * WIDTH * 3 : (y + 1) * WIDTH * 3] for y in range(HEIGHT))
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write fixtures and SHA-256 manifest")
    args = parser.parse_args()
    fixture_dir = ROOT / "fixtures"
    expected = {f"scene_0{scene}_start.mock.png": fixture_png(scene) for scene in (1, 2, 3)}
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in expected.items()}
    if args.write:
        fixture_dir.mkdir(exist_ok=True)
        for name, content in expected.items():
            (fixture_dir / name).write_bytes(content)
        (fixture_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print("Wrote three deterministic mock frames and manifest.")
    else:
        actual = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
        if actual != manifest or any(
            (fixture_dir / name).read_bytes() != content for name, content in expected.items()
        ):
            raise SystemExit(
                "Mock fixtures differ from deterministic source; run --write to repair."
            )
        print("Three deterministic mock frames match the manifest.")


if __name__ == "__main__":
    main()
