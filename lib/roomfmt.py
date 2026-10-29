"""room files (BSDATA/R*.BIN)

header = 9 u32 offsets. at hdr[4] there is the event script, 8 byte instructions, ends
with ff 00 00 00 00 00 00 00. the text block comes right after: u32 count, then
`count` strings, each one = u16 nglyphs, the u16 glyph codes, 0xffff (0xfffe = newline)
"""
import struct

SCRIPT_END = b"\xff\x00\x00\x00\x00\x00\x00\x00"


def header(d):
    return list(struct.unpack_from("<9I", d))


def text_offset(d):
    """offset of the text block (where the u32 count is)"""
    h = header(d)
    p = h[4]
    while p + 8 <= len(d):
        if d[p:p + 8] == SCRIPT_END:
            return p + 8
        p += 8
    raise ValueError("script terminator not found")


def parse_text(d, off):
    n = struct.unpack_from("<I", d, off)[0]
    p = off + 4
    strings = []
    for _ in range(n):
        ln = struct.unpack_from("<H", d, p)[0]
        glyphs = []
        q = p + 2
        while True:
            g = struct.unpack_from("<H", d, q)[0]
            q += 2
            if g == 0xFFFF:
                break
            glyphs.append(g)
        strings.append((ln, glyphs))
        p = q
    return strings, p
