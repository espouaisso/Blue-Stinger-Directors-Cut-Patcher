#!/usr/bin/env python3
"""Blue Stinger Director's Cut patcher

Takes the japanese game (exe, cameras, gameplay, scripts) and puts the western
text, textures and videos on top.

  python3 patch.py                                  finds the games in this folder and
                                                    builds every version it can
  python3 patch.py en JP.gdi US.gdi [out_dir]       english, like the US release
  python3 patch.py fr JP.gdi PAL_FR.gdi [out_dir]   french, with all the subs
"""
import hashlib
import os
import re
import shutil
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from bscode import CHARS, INDEX  # noqa: E402
from gdi import Disc, rebuild_track  # noqa: E402
from roomfmt import parse_text, text_offset  # noqa: E402

BASE = 0x8C010000

# md5 of 1ST_READ.BIN, to be sure we have the right discs
EXE_MD5 = {
    "jp": "c46d2bdcdb007b012a29234355af3612",     # JP v1.006
    "us": "255213081b4a4dc23a9c2949b7883cdf",     # US v1.000
    "palfr": "e7b7484c6151ee87c2d646ed46507273",  # PAL FR v1.000
}
PAL_EN_MD5 = "be66765ca7db0e24bc05a5826f5e5538"  # not supported, same text as US
NAMES = {"jp": "Japanese v1.006", "us": "US v1.000", "palfr": "PAL French v1.000"}
DISCS = {}

# --- JP exe offsets ---
JP_FONT_TABLE = 0x95DC8     # u16 count + sorted u16 codes (glyph index = position in the list)
# text styles, 16 bytes each (first 8 = glyph width, advance, line height etc)
# 0,1,3,5 = dialogue font. 2 and 4 are the HUD, they keep the JP values (if not the
# radio text overlaps)
JP_STYLE = 0x8EB68
DIALOGUE_STYLES = (0, 1, 3, 5)
HEAP_END_LIT = 0x7A84C      # &_end literal, read by the heap init (sbInitSystem)
NEW_REGION = 0x8C329600     # all the text goes here after _end, heap starts after it
JP_ITEMS, JP_PLACES, JP_PICKUP = 0x8ECB4, 0x8F632, 0x8F8F4
JP_TEXT_AREA = (0x8ECB4, 0x957B6)
# strings with no length, just 0xffff at the end, outside that area
# (JP start, nb of strings, which ones to swap). the bytes just before are the same
# in every release so thats how we find them in the US/FR exe
JP_RAW = [(0x97DC8, 7, (0, 1, 3, 4, 5, 6)),  # yes, no, (cursor), equip, use, info...
          (0x9819C, 1, (0,))]                # passcode help
RAW_ANCHOR = 0x30

# --- western exes, where the text is ---
SRC = {
    "us": dict(font_table=0x99414, style=0x8FFD8, items=0x90068, places=0x90ED8,
               units=(0x912B0, 0x98E10)),
    "palfr": dict(font_table=0x99C08, style=0x90168, items=0x901F8, places=0x90F4C,
                  units=(0x913D0, 0x99600)),
}

# in JP the item name comes first ("<item>を入手した") so we write our own
PICKUP = {
    "en": [" acquired.", "\nYou can’t carry any more."],
    "fr": [" : obtenu.", "\nTu ne peux plus en porter."],
}
# RSP05 = casino entrance. the 4 messages were removed in the western versions
RSP05 = {
    "en": ["No one under the age of 21\nis allowed beyond this point.", "Are you 21 or older?",
           "Come back when you’re older.", "Entry permitted."],
    "fr": ["Interdit aux moins de 21 ans\nau-delà de ce point.", "As-tu 21 ans ou plus ?",
           "Reviens quand tu seras grand.", "Entrée autorisée."],
}
# rooms where the PAL FR retimed the script (longer text, sync fix in RKA01) so the subs
# follow the voices. JP and US scripts are identical there so we just take the FR one
FR_RETIMED = ["BSDATA/" + r + ".BIN" for r in "RCG01 RKA01 RKA01C RKA04 RKR13".split()]
# RUT13A was never translated, same messages as RUT13
SAME_TEXT = {"BSDATA/RUT13A.BIN": "BSDATA/RUT13.BIN"}

# videos with text in the picture, different between JP and western
VIDEOS = ["E017", "E180", "E185A", "E185B", "E193", "E195", "ENDING", "NEWGAME"]
# OPENING.SFD = trailer only on the JP disc. we cut it to ~1 sec of black with no sound
# (still a valid stream so the game is happy), it frees ~97 MB for the PAL FR videos
# that are bigger
OPENING_FRAMES = 30
# save name in the dreamcast memory manager (shift-jis in the JP exe)
JP_VMU_DESC, VMU_DESC = 0x8A6B4, b"BLUESTINGER SAVE DATA       \0"

# texture packs with signs translated in the western release. None = all the textures
# that differ, a list = only those ones. characters, pin-ups, gore, photos, shop
# shelves and title screen stay japanese
SIGN_TEXTURES = dict.fromkeys(
    "RCS02 RDB00 RDE29 REL00 RGT01 RGT02 RGT03 RGT04 RKA02 RKE04 RKE05 RKE10 RKE12 RKE14 "
    "RKE25 RKE29 RKL00 RKL16 RKL17 RKL23 RKR00 RKR02 RKR06 RKR11 RMT00 RMT01 RSP04 RSP07 "
    "RSP08 RSP10 RSP12 RSP14 RUT00 RUT04 RUT06 RUT12 RUT12A RUT13 RUT13A RUT15 RUT15A "
    "RUT16 RUT16A RUT18 RUT18A RUT20 RUT20A RUT21 RUT21A RUT21B RUT22 RUT22A OID00A OID00B "
    "IME00 DCS04A DCS04B".split())
SIGN_TEXTURES["RCS00"] = [6]
FR_TEXTURES = {"PORTABLE": [2], "TNK": [0]}  # french menu labels + "EPUISE"


def rd(ver, path):
    return DISCS[ver].read(path)


def untwiddle(x, y):
    a = 0
    for i in range(10):
        a |= ((y >> i) & 1) << (2 * i) | ((x >> i) & 1) << (2 * i + 1)
    return a


# ---------- text ----------
def encode(s):
    """text -> JP glyph codes (JIS index, '\\n' = 0xfffe)"""
    return [0xFFFE if c == "\n" else INDEX[c] for c in s]


class FrenchCodes:
    """PAL FR text = latin-1 in u16. ASCII goes to the JIS codes, the rest (accents etc)
    gets private codes that use the glyphs of the FR font"""
    PRIVATE = 0x1C00

    def __init__(self):
        self.used = {}  # JP code -> latin-1 value, to find the glyph later

    def __call__(self, glyphs):
        out = []
        for c in glyphs:
            if c >= 0x100 or c < 0x20:  # newline, control codes
                out.append(c)
                continue
            ch = chr(c)
            code = 0 if ch in " \xa0" else INDEX.get(ch, self.PRIVATE + c)
            if code:
                self.used[code] = c
            out.append(code)
        return out


def own_text(s, conv):
    """our own strings, with the french converter (accents) or just JIS"""
    if isinstance(conv, FrenchCodes):
        return conv([0xFFFE if c == "\n" else ord(c) for c in s])
    return encode(s)


def pstr(g):
    """string with u16 length before and 0xffff at the end"""
    return struct.pack("<H", len(g) + 1) + struct.pack(f"<{len(g)}H", *g) + b"\xff\xff"


def text_block(strings):
    b = bytearray(struct.pack("<I", len(strings)))
    for g in strings:
        b += pstr(g)
    b += b"\x00" * (-len(b) % 4)
    return bytes(b)


def strings_at(d, p):
    """list of strings, ends with ffff"""
    out = []
    while struct.unpack_from("<H", d, p)[0] != 0xFFFF:
        n = struct.unpack_from("<H", d, p)[0]
        out.append(list(struct.unpack_from(f"<{n - 1}H", d, p + 2)))
        p += 2 * n + 2
    return out


def room_texts(lang, src, conv):
    """{path: [glyph lists]} for all the rooms, from the western disc"""
    texts = {}
    for p in sorted(DISCS["jp"].files):
        name = p[7:]
        if not (p.startswith("BSDATA/R") and p.endswith(".BIN")):
            continue
        if p in SAME_TEXT:
            continue
        j, s = rd("jp", p), rd(src, p)
        sj, _ = parse_text(j, text_offset(j))
        ss, _ = parse_text(s, text_offset(s))
        if len(sj) != len(ss):
            assert name == "RSP05.BIN" and len(sj) == len(RSP05[lang]), name
            texts[p] = [own_text(t, conv) for t in RSP05[lang]]
            continue
        texts[p] = [conv(g) for _, g in ss]
    for p, q in SAME_TEXT.items():
        texts[p] = texts[q]
    return texts


def build_rooms(texts, fr_scripts=()):
    out = {}
    for p, strings in texts.items():
        j = rd("jp", p)
        if p in fr_scripts:
            j = rd("palfr", p)  # same as JP until the script, then FR script
            assert j[:36] == rd("jp", p)[:36]
        new = j[:text_offset(j)] + text_block(strings)
        if new != j:
            out[p] = new
    return out


# ---------- exe ----------
SCRIPT_END = b"\xff\x00\x00\x00\x00\x00\x00\x00"


def exe_units(d, lo, hi):
    """mini scripts inside the exe: u32 n_instr, n_instr*8 bytes (last one = SCRIPT_END),
    then a text block. returns [(start, text_off, end)] for the ones inside [lo, hi)"""
    units = []
    p = d.find(SCRIPT_END, lo)
    while 0 <= p < hi:
        for k in range(200):
            s = p - 8 * k - 4
            if s >= lo and struct.unpack_from("<I", d, s)[0] == k + 1:
                try:
                    strs, e = parse_text(d, p + 8)
                except struct.error:
                    break
                if 0 < len(strs) < 100 and all(len(g) + 1 == ln for ln, g in strs):
                    units.append((s, p + 8, e))
                break
        p = d.find(SCRIPT_END, p + 1)
    return units


def raw_strings(d, p, n):
    """n strings in a row (ffff at the end of each) -> [(offset, glyphs)]"""
    out = []
    for _ in range(n):
        q = p
        while struct.unpack_from("<H", d, q)[0] != 0xFFFF:
            q += 2
        out.append((p, list(struct.unpack_from(f"<{(q - p) // 2}H", d, p))))
        p = q + 2
    return out


def relocate_exe_text(exe, lang, src, conv):
    """moves all the exe text to NEW_REGION with the western strings (JP scripts kept),
    fixes every pointer and puts the heap after. returns (exe, codes used)"""
    cfg = SRC[src]
    s = rd(src, "1ST_READ.BIN")
    ju = exe_units(exe, *JP_TEXT_AREA)
    su = exe_units(s, *cfg["units"])
    assert len(ju) == len(su) == 193, (len(ju), len(su))

    region = bytearray(32)  # word 0 = new _end, for the heap init
    moved = {}  # old offset in file -> new adress
    codes = set()

    def put(old, blob):
        region.extend(b"\x00" * (-len(region) % 4))
        moved[old] = NEW_REGION + len(region)
        region.extend(blob)

    def str_list(strings):
        strings = [conv(g) for g in strings]
        for g in strings:
            codes.update(g)
        return b"".join(pstr(g) for g in strings) + b"\xff\xff"

    put(JP_ITEMS, str_list(strings_at(s, cfg["items"])))
    put(JP_PLACES, str_list(strings_at(s, cfg["places"])))
    pickup = [own_text(t, conv) for t in PICKUP[lang]]
    codes.update(c for g in pickup for c in g)
    put(JP_PICKUP, b"".join(pstr(g) for g in pickup) + b"\xff\xff")
    for (js, jt, _), (_, st, _) in zip(ju, su):
        strings = [conv(g) for _, g in parse_text(s, st)[0]]
        for g in strings:
            codes.update(g)
        put(js, exe[js:jt] + text_block(strings))  # JP script + western text
    raw_moved = {}
    for start, n, swap in JP_RAW:
        anchor = exe[start - RAW_ANCHOR:start]
        assert s.count(anchor) == 1
        jp_strs, src_strs = raw_strings(exe, start, n), raw_strings(s, s.find(anchor) + RAW_ANCHOR, n)
        for i in swap:
            g = conv(src_strs[i][1])
            codes.update(g)
            region.extend(b"\x00" * (-len(region) % 4))
            raw_moved[jp_strs[i][0]] = NEW_REGION + len(region)
            region.extend(struct.pack(f"<{len(g)}H", *g) + b"\xff\xff")
    end = (NEW_REGION + len(region) + 31) & ~31
    struct.pack_into("<I", region, 0, end)

    out = bytearray(exe)
    n = 0
    for i in range(0, len(exe) - 3, 4):
        w = struct.unpack_from("<I", exe, i)[0] - BASE
        if JP_TEXT_AREA[0] <= w < JP_TEXT_AREA[1]:
            assert w in moved, hex(w)
            struct.pack_into("<I", out, i, moved[w])
            n += 1
        elif w in raw_moved:
            struct.pack_into("<I", out, i, raw_moved[w])
            n += 1
    assert struct.unpack_from("<I", exe, HEAP_END_LIT)[0] == 0x8C1D75D4
    struct.pack_into("<I", out, HEAP_END_LIT, NEW_REGION)
    out.extend(b"\x00" * (NEW_REGION - BASE - len(out)))
    out += region
    # western spacing for the dialogue styles
    for i in DIALOGUE_STYLES:
        j, w = JP_STYLE + 16 * i, cfg["style"] + 16 * i
        out[j:j + 8] = s[w:w + 8]
    print(f"exe text: {len(moved)} blocks ({len(region)} bytes) moved to {NEW_REGION:#x}, "
          f"{n} pointers patched, heap now starts after {end:#x}")
    return bytes(out), codes


# ---------- font ----------
CELL, PER_ROW, PER_PAGE = 32, 8, 64


def font_table(exe, off):
    n = struct.unpack_from("<H", exe, off)[0]
    return list(struct.unpack_from(f"<{n}H", exe, off + 2))


def nt_pages(d):
    return [m.start() for m in re.finditer(b"PVRT", d)]


def read_glyph(d, pvrt, idx):
    data = pvrt + 16
    gx, gy = (idx % PER_ROW) * CELL, (idx // PER_ROW) * CELL
    cell = []
    for y in range(CELL):
        for x in range(CELL):
            t = untwiddle(gx + x, gy + y)
            b = d[data + t // 2]
            cell.append((b >> 4) if t & 1 else (b & 15))
    return cell


def write_glyph(buf, pvrt, idx, cell):
    data = pvrt + 16
    gx, gy = (idx % PER_ROW) * CELL, (idx // PER_ROW) * CELL
    for y in range(CELL):
        for x in range(CELL):
            t = untwiddle(gx + x, gy + y)
            v = cell[y * CELL + x]
            a = data + t // 2
            buf[a] = (buf[a] & 0x0F) | (v << 4) if t & 1 else (buf[a] & 0xF0) | v


def glyph(d, pages, idx):
    return read_glyph(d, pages[idx // PER_PAGE], idx % PER_PAGE)


def western_glyphs(src, fr_codes):
    """{JP code: glyph cell} taken from the western font"""
    exe, font = rd(src, "1ST_READ.BIN"), rd(src, "BSDATA/TPOMMON.NT")
    tab, pages = font_table(exe, SRC[src]["font_table"]), nt_pages(font)
    if src == "us":  # US uses the same codes as JP
        return {c: glyph(font, pages, i) for i, c in enumerate(tab)}
    return {code: glyph(font, pages, tab.index(c)) for code, c in fr_codes.used.items()}


def build_font(exe, needed, new_cells):
    """rebuilds the JP font with the western glyphs. kanji we dont use are droped to make room"""
    jtab = font_table(exe, JP_FONT_TABLE)
    jfont = rd("jp", "BSDATA/TPOMMON.NT")
    jpages = nt_pages(jfont)
    missing = sorted(c for c in needed if c < 0xFE00 and c not in jtab and c not in new_cells)
    assert not missing, [hex(c) for c in missing]
    add = [c for c in new_cells if c not in jtab]
    first_kanji = INDEX["亜"]
    droppable = [c for c in reversed(jtab)
                 if first_kanji <= c < len(CHARS) and c not in needed and c not in new_cells]
    assert len(droppable) >= len(add)
    drop = set(droppable[:len(add)])
    cells = {c: glyph(jfont, jpages, i) for i, c in enumerate(jtab) if c not in drop}
    cells.update(new_cells)
    codes = sorted(cells)
    assert len(codes) <= len(jtab) <= len(jpages) * PER_PAGE
    buf = bytearray(jfont)
    for i, c in enumerate(codes):
        write_glyph(buf, jpages[i // PER_PAGE], i % PER_PAGE, cells[c])
    out = bytearray(exe)
    struct.pack_into("<H", out, JP_FONT_TABLE, len(codes))
    struct.pack_into(f"<{len(codes)}H", out, JP_FONT_TABLE + 2, *codes)
    print(f"font: {len(new_cells)} western glyphs ({len(add)} new), {len(drop)} unused kanji dropped")
    return bytes(out), bytes(buf)


# ---------- textures ----------
def nt_entries(d):
    n = struct.unpack_from("<I", d, 0)[0]
    offs = list(struct.unpack_from(f"<{n}I", d, 4)) + [len(d)]
    return [d[offs[k]:offs[k + 1]] for k in range(n)]


def nt_build(entries):
    head = 4 + 4 * len(entries)
    offs, p = [], head
    for e in entries:
        offs.append(p)
        p += len(e)
    return struct.pack(f"<I{len(entries)}I", len(entries), *offs) + b"".join(entries)


def pvrt_part(entry):
    return entry[entry.index(b"PVRT"):]


def swap_textures(src, packs):
    """puts the western textures in the JP packs (JP GBIX ids are kept)"""
    out, count = {}, 0
    for name, idx in packs.items():
        p = f"BSDATA/{name}.NT"
        je, se = nt_entries(rd("jp", p)), nt_entries(rd(src, p))
        if idx is None:
            assert len(je) == len(se), name
            idx = [k for k in range(len(je)) if pvrt_part(je[k]) != pvrt_part(se[k])]
        for k in idx:
            je[k] = je[k][:je[k].index(b"PVRT")] + pvrt_part(se[k])
            je[k] += b"\x00" * (-len(je[k]) % 4)
        count += len(idx)
        out[p] = nt_build(je)
    print(f"textures: {count} replaced in {len(out)} packs")
    return out


# ---------- video ----------
def short_video(sfd, frames):
    """keeps the sofdec header + the 2048 byte packs until `frames` pictures, then the
    original end of stream sector"""
    pos = 0
    for _ in range(frames + 1):
        pos = sfd.index(b"\x00\x00\x01\x00", pos + 1)
    cut = 0x2000 + ((pos - 0x2000) // 2048 + 1) * 2048
    end = sfd.rindex(b"\x00\x00\x01\xb9") // 2048 * 2048
    return sfd[:cut] + sfd[end:end + 2048]


class Bits:
    def __init__(self):
        self.v, self.n = 0, 0

    def put(self, bits):
        for c in bits:
            self.v = self.v << 1 | (c == "1")
            self.n += 1

    def bytes(self):
        pad = -self.n % 8
        return (self.v << pad).to_bytes((self.n + pad) // 8, "big")


MB_ESCAPE = "00000001000"  # macroblock_address_increment + 33


def black_slices(ptype, mb_w, mb_h):
    """MPEG-1 slices for a black picture. I = black macroblocks (DC only). P/B = one slice,
    first and last macroblock are "forward MC, not coded" with 0 motion, all the others
    skipped"""
    if ptype == 1:  # one slice for the whole picture
        bits = Bits()
        bits.put("01000" + "0")  # quantizer_scale 8, extra_bit_slice
        for mb in range(mb_w * mb_h):
            bits.put("1" + "1")  # adress increment 1, intra
            # Y DC: predictor 1024, black is Y=16 -> coef 128 -> diff -112 (size 7)
            bits.put(("111110" + "0001111" if mb == 0 else "100") + "10")
            for _ in range(3):
                bits.put("100" + "10")  # Y diff 0, end of block
            bits.put("00" + "10")  # Cb diff 0
            bits.put("00" + "10")  # Cr diff 0
        return bytes([0, 0, 1, 1]) + bits.bytes()
    coded = "001" if ptype == 2 else "0010"  # forward MC, not coded
    bits = Bits()
    bits.put("01000" + "0")
    bits.put("1" + coded + "1" + "1")  # 1st MB, motion (0,0)
    skip = mb_w * mb_h - 1
    while skip > 33:
        bits.put(MB_ESCAPE)
        skip -= 33
    incr = ["1", "011", "010", "0011", "0010", "00011", "00010", "0000111", "0000110",
            "00001011", "00001010", "00001001", "00001000", "00000111", "00000110",
            "0000010111", "0000010110", "0000010101", "0000010100", "0000010011",
            "0000010010", "00000100011", "00000100010", "00000100001", "00000100000",
            "00000011111", "00000011110", "00000011101", "00000011100", "00000011011",
            "00000011010", "00000011001", "00000011000"][skip - 1]
    bits.put(incr + coded + "1" + "1")  # last MB
    return bytes([0, 0, 1, 1]) + bits.bytes()


def es_chunks(sfd, sid):
    """[(offset, length)] of the payloads of stream `sid` in the mpeg-1 program stream"""
    chunks, p = [], 0x2000
    while sfd[p:p + 4] == b"\x00\x00\x01\xba":
        q = p + 12
        while q < p + 2048 and sfd[q:q + 3] == b"\x00\x00\x01" and sfd[q + 3] != 0xB9:
            ln = struct.unpack_from(">H", sfd, q + 4)[0]
            if sfd[q + 3] == sid:
                h = q + 6
                while sfd[h] == 0xFF:
                    h += 1
                if sfd[h] >> 6 == 1:
                    h += 2
                h += {2: 5, 3: 10}.get(sfd[h] >> 4, 1)
                chunks.append((h, q + 6 + ln - h))
            q += 6 + ln
        p += 2048
    return chunks


def blacken(sfd):
    """same stream but black pictures and ADX audio with no sound"""
    out = bytearray(sfd)
    vch = es_chunks(sfd, 0xE0)
    es = b"".join(sfd[o:o + n] for o, n in vch)
    w = (es[4] << 4 | es[5] >> 4) + 15 >> 4
    h = ((es[5] & 15) << 8 | es[6]) + 15 >> 4
    starts = [m.start() for m in re.finditer(b"\x00\x00\x01", es)]
    chunk_end, pos = [], 0
    for _, n in vch:
        pos += n
        chunk_end.append(pos)
    new = bytearray(len(es))
    cursor = 0
    for k, s in enumerate(starts):
        code = es[s + 3]
        if 1 <= code <= 0xAF:
            continue  # slices are made again
        nxt = starts[k + 1] if k + 1 < len(starts) else len(es)
        unit = es[s:nxt]  # sequence / GOP / extension / picture header, we keep them
        if code == 0x00:
            unit += black_slices(es[s + 5] >> 3 & 7, w, h)
        # try to stay at the same offset. it can move a bit later but has to start in the
        # same packet, if not the timestamps dont match the picture anymore
        at = max(s, cursor)
        same = next(e for e in chunk_end if e > s)
        if at >= same or at + len(unit) > len(es):
            break  # cut at the end, drop it
        new[at:at + len(unit)] = unit
        cursor = at + len(unit)
    pos = 0
    for o, n in vch:
        out[o:o + n] = new[pos:pos + n]
        pos += n
    ach = es_chunks(sfd, 0xC0)
    adx = b"".join(sfd[o:o + n] for o, n in ach)
    assert adx[:2] == b"\x80\x00"
    data = struct.unpack_from(">H", adx, 2)[0] + 4
    pos = 0
    for o, n in ach:
        for i in range(n):
            if pos + i >= data:
                out[o + i] = 0
        pos += n
    return bytes(out)


# ---------- main ----------
def open_disc(key, gdi):
    disc = Disc(gdi)
    md5 = hashlib.md5(disc.read("1ST_READ.BIN")).hexdigest()
    if md5 != EXE_MD5[key]:
        sys.exit(f"{gdi}: this is not Blue Stinger {NAMES[key]} (1ST_READ.BIN md5 {md5})")
    DISCS[key] = disc
    return disc


def find_games(top):
    """looks for every .gdi under `top` and finds out which game it is with the md5"""
    found = {}
    for root, dirs, names in os.walk(top):
        dirs[:] = [d for d in dirs if not d.startswith(("Blue Stinger Director's Cut", "."))]
        for n in sorted(names):
            if not n.lower().endswith(".gdi"):
                continue
            gdi = os.path.join(root, n)
            try:
                md5 = hashlib.md5(Disc(gdi).read("1ST_READ.BIN")).hexdigest()
            except Exception as e:
                print(f"skipped {gdi}: can't read it ({e})")
                continue
            key = next((k for k, v in EXE_MD5.items() if v == md5), None)
            if key is None:
                other = " (PAL english, use the US version)" if md5 == PAL_EN_MD5 else ""
                print(f"skipped {gdi}: not a supported version{other}")
            elif key not in found:
                print(f"found {NAMES[key]}: {gdi}")
                found[key] = gdi
    return found


def auto():
    """no arguments: build all the versions we can with the games in this folder"""
    top = os.path.dirname(os.path.abspath(__file__))
    found = find_games(top)
    todo = [(lang, src) for lang, src in (("en", "us"), ("fr", "palfr")) if src in found]
    if "jp" not in found or not todo:
        print("\nI need the japanese game + the US and/or PAL FR game.")
        print("Unzip your GDIs in the 'Put ... game here' folders (the .gdi and the tracks).")
        sys.exit(1)
    for lang, src in todo:
        print(f"\n=== {lang.upper()} version ===")
        build(lang, found["jp"], found[src], None, top)
        for d in DISCS.values():
            d._cache.clear()


def build(lang, jp_gdi, src_gdi, outdir=None, where="."):
    src = {"en": "us", "fr": "palfr"}[lang]
    name = {"en": "Blue Stinger Director's Cut (EN)", "fr": "Blue Stinger Director's Cut (FR)"}[lang]
    outdir = outdir or os.path.join(where, name)
    jp = open_disc("jp", jp_gdi)
    open_disc(src, src_gdi)
    conv = FrenchCodes() if lang == "fr" else (lambda g: list(g))

    texts = room_texts(lang, src, conv)
    files = build_rooms(texts, FR_RETIMED if lang == "fr" else ())
    print(f"{len(files)} rooms with {lang.upper()} text")
    exe, codes = relocate_exe_text(rd("jp", "1ST_READ.BIN"), lang, src, conv)
    for strings in texts.values():
        for g in strings:
            codes.update(g)
    exe, font = build_font(exe, codes, western_glyphs(src, conv))
    exe = bytearray(exe)
    assert exe[JP_VMU_DESC + 28] == 0 and len(VMU_DESC) == 29
    exe[JP_VMU_DESC:JP_VMU_DESC + 29] = VMU_DESC
    files["1ST_READ.BIN"] = bytes(exe)
    files["BSDATA/TPOMMON.NT"] = font
    files.update(swap_textures(src, SIGN_TEXTURES))
    if lang == "fr":
        files.update(swap_textures(src, FR_TEXTURES))
    for v in VIDEOS:
        files[f"BSDATA/{v}.SFD"] = rd(src, f"BSDATA/{v}.SFD")
    files["BSDATA/OPENING.SFD"] = blacken(short_video(rd("jp", "BSDATA/OPENING.SFD"),
                                                      OPENING_FRAMES))

    os.makedirs(outdir, exist_ok=True)
    (_, _, t1, s1, f1), (_, l2, t2, s2, f2), (_, l3, t3, s3, f3) = jp.tracks[:3]
    shutil.copyfile(f1, os.path.join(outdir, "track01.bin"))
    shutil.copyfile(f2, os.path.join(outdir, "track02.raw"))
    print("writing track03.bin...")
    rebuild_track(f3, os.path.join(outdir, "track03.bin"), files, l3, donors=[DISCS[src]])
    with open(os.path.join(outdir, name + ".gdi"), "w", newline="\r\n") as f:
        f.write(f"3\n1 0 {t1} {s1} track01.bin 0\n2 {l2} {t2} {s2} track02.raw 0\n"
                f"3 {l3} {t3} {s3} track03.bin 0\n")
    print(f"done: {os.path.abspath(outdir)}")


def main():
    if len(sys.argv) == 1:
        return auto()
    if len(sys.argv) not in (4, 5) or sys.argv[1] not in ("en", "fr"):
        sys.exit(__doc__)
    build(*sys.argv[1:4], sys.argv[4] if len(sys.argv) > 4 else None)


if __name__ == "__main__":
    main()
