"""read and rebuild dreamcast GDIs

Disc(gdi_path).read("1ST_READ.BIN") reads a file in the data track (track 3, raw
2352 byte mode 1 sectors, ISO9660 with absolute LBAs).

rebuild_track(src_track, dst_track, {iso_path: bytes}, start) writes a new track 3 with
some files replaced. files are put back in the same order, packed at the end of the disc
like the original. PVD, path tables and directories stay where they are, only the
directory records get the new extent/size. every sector gets a good header + EDC/ECC
(lib/ecc.py): new data is encoded, the old sectors that just moved get their new adress
"""
import os
import shlex
import struct

import ecc

RAW, DATA = 2352, 2048
CHUNK = 4096  # sectors per read / write


def encode(lba, data):
    """data (multiple of 2048) -> raw sectors from lba"""
    return b"".join(ecc.encode(data[i * DATA:(i + 1) * DATA], lba + i)
                    for i in range(len(data) // DATA))


def move(lba, raw):
    """raw sectors already encoded somewhere else -> same sectors but at lba"""
    return b"".join(ecc.move(raw[i * RAW:(i + 1) * RAW], lba + i)
                    for i in range(len(raw) // RAW))


def read_gdi(path):
    """-> [(number, lba, type, sector_size, file_path)]"""
    with open(path) as f:
        lines = [shlex.split(line) for line in f if line.strip()]
    tracks = []
    for t in lines[1:1 + int(lines[0][0])]:
        tracks.append((int(t[0]), int(t[1]), int(t[2]), int(t[3]),
                       os.path.join(os.path.dirname(path), t[4])))
    return tracks


class Track:
    def __init__(self, path, start):
        self.f = open(path, "rb")
        self.start = start
        self.sectors = os.path.getsize(path) // RAW

    def read_raw(self, lba, n=1):
        self.f.seek((lba - self.start) * RAW)
        return self.f.read(n * RAW)

    def read(self, lba, n=1):
        raw = self.read_raw(lba, n)
        return b"".join(raw[k * RAW + 16:k * RAW + 16 + DATA] for k in range(n))


def scan(trk, lba, size, prefix, files, dirs):
    """files[path] = [record_lba, offset_in_sector, extent, size]."""
    dirs.append((lba, size))
    for s in range((size + DATA - 1) // DATA):
        sec = trk.read(lba + s)
        pos = 0
        while pos < DATA:
            ln = sec[pos]
            if ln == 0:
                break
            ext, sz = struct.unpack_from("<I", sec, pos + 2)[0], struct.unpack_from("<I", sec, pos + 10)[0]
            flags, nl = sec[pos + 25], sec[pos + 32]
            name = sec[pos + 33:pos + 33 + nl]
            if name not in (b"\x00", b"\x01"):
                path = prefix + name.decode("ascii").split(";")[0]
                if flags & 2:
                    scan(trk, ext, sz, path + "/", files, dirs)
                else:
                    files[path] = [lba + s, pos, ext, sz]
            pos += ln
    return files


def root_files(trk):
    pvd = trk.read(trk.start + 16)
    assert pvd[1:6] == b"CD001", "no ISO9660 volume in track 3"
    root = pvd[156:190]
    dirs = []
    files = scan(trk, struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0],
                 "", {}, dirs)
    return pvd, files, dirs


class Disc:
    def __init__(self, gdi_path):
        self.gdi = gdi_path
        self.tracks = read_gdi(gdi_path)
        _, lba, _, size, path = self.tracks[2]
        assert size == RAW, "track 3 must be raw 2352-byte sectors"
        self.track = Track(path, lba)
        _, self.files, _ = root_files(self.track)
        self._cache = {}

    def read(self, path):
        if path not in self._cache:
            _, _, ext, sz = self.files[path]
            self._cache[path] = self.track.read(ext, nsec(sz))[:sz]
        return self._cache[path]


def nsec(size):
    return (size + DATA - 1) // DATA


def rebuild_track(src, dst, replace, start=45000, donors=(), log=print):
    """donors = other Discs. if a new file is just a copy of one of their files, we move
    their sectors instead of encoding it all again (way faster for the videos)"""
    trk = Track(src, start)
    track_end = start + trk.sectors
    pvd, files, dirs = root_files(trk)
    unknown = set(replace) - set(files)
    assert not unknown, unknown

    ptsize = struct.unpack_from("<I", pvd, 132)[0]
    meta = [(struct.unpack_from("<I", pvd, o)[0], ptsize) for o in (140, 144)]
    meta += [(struct.unpack_from(">I", pvd, o)[0], ptsize) for o in (148, 152)]
    meta += dirs
    meta_end = max(lba + nsec(sz) for lba, sz in meta if lba) + 16

    order = sorted(files, key=lambda p: files[p][2])
    sizes = {p: len(replace[p]) if p in replace else files[p][3] for p in order}
    total = sum(nsec(s) for s in sizes.values())
    data_end = max(files[p][2] + nsec(files[p][3]) for p in order)
    first = max(meta_end, data_end - total)
    assert first + total <= track_end, "track overflow"
    log(f"layout: {total} sectors of files at LBA {first}..{first + total} "
        f"(free before: {first - meta_end})")

    # volume stuff with the new directory records
    metadata = bytearray(trk.read(start, meta_end - start))
    lba = first
    new_ext = {}
    for p in order:
        new_ext[p] = lba
        rec_lba, off, _, _ = files[p]
        o = (rec_lba - start) * DATA + off
        struct.pack_into("<I", metadata, o + 2, lba)
        struct.pack_into(">I", metadata, o + 6, lba)
        struct.pack_into("<I", metadata, o + 10, sizes[p])
        struct.pack_into(">I", metadata, o + 14, sizes[p])
        lba += nsec(sizes[p])

    zero = ecc.encode(bytes(DATA), 0) * CHUNK  # empty sectors, moved where needed
    with open(dst, "wb") as out:
        out.write(encode(start, bytes(metadata)))
        lba = meta_end
        while lba < first:
            n = min(CHUNK, first - lba)
            out.write(move(lba, zero[:n * RAW]))
            lba += n
        for p in order:
            if p in replace:
                data = replace[p]
                donor = next((d for d in donors if p in d.files and d.read(p) == data), None)
                data += b"\x00" * (-len(data) % DATA)
                for i in range(0, len(data) // DATA, CHUNK):
                    chunk = data[i * DATA:(i + CHUNK) * DATA]
                    if donor:
                        raw = donor.track.read_raw(donor.files[p][2] + i, len(chunk) // DATA)
                        if donor.track.read(donor.files[p][2] + i, len(chunk) // DATA) == chunk:
                            out.write(move(lba + i, raw))
                            continue
                    out.write(encode(lba + i, chunk))
            else:
                ext, n_old = files[p][2], nsec(files[p][3])
                for i in range(0, n_old, CHUNK):
                    n = min(CHUNK, n_old - i)
                    out.write(move(lba + i, trk.read_raw(ext + i, n)))
            assert lba == new_ext[p]
            lba += nsec(sizes[p])
        while lba < track_end:
            n = min(CHUNK, track_end - lba)
            out.write(move(lba, zero[:n * RAW]))
            lba += n
