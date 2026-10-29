"""blue stinger text encoding. a glyph code = index of the char in the list of the
valid JIS X 0208 cells (row by row, the empty ones are skipped)
0xFFFE = newline, 0xFFFF = end of string
"""


def _build():
    chars = []
    for row in range(1, 95):
        for cell in range(1, 95):
            b = bytes([0xA0 + row, 0xA0 + cell])
            try:
                c = b.decode("euc_jp")
            except UnicodeDecodeError:
                continue
            if 8 <= row <= 15 or row >= 85:
                continue  # row 8 = box drawing, not in the game table. after 84 = nothing
            chars.append(c)
    return chars


CHARS = _build()
INDEX = {c: i for i, c in enumerate(CHARS)}
# normal ASCII -> the fullwidth ones
for _a, _f in zip("".join(chr(c) for c in range(0x21, 0x7F)),
                  "".join(chr(c) for c in range(0xFF01, 0xFF5F))):
    if _f in INDEX:
        INDEX.setdefault(_a, INDEX[_f])
INDEX.setdefault(" ", 0)
# ASCII chars not in JIS X 0208, same as what the US version does
for _a, _j in (("'", "’"), ('"', "”"), ("-", "−"), ("~", "〜")):
    INDEX.setdefault(_a, INDEX[_j])


def decode(glyphs):
    out = []
    for g in glyphs:
        if g == 0xFFFE:
            out.append("\n")
        elif g < len(CHARS):
            out.append(CHARS[g])
        else:
            out.append(f"<{g:04x}>")
    return "".join(out)
