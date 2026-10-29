"""CD-ROM mode 1 sectors (sync, header, EDC, ECC P/Q), just python

encode(data, lba)   encodes a 2048 byte sector
move(raw, lba)      same sector at another adress. EDC and ECC are linear so we only add
                    the effect of the header bytes that changed (much faster)
"""
import struct
from operator import itemgetter

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"

# EDC = CRC-32, poly 0xD8018001 (reflected), init 0, no xor at the end
EDC_LUT = []
for _i in range(256):
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if _e & 1 else 0)
    EDC_LUT.append(_e)


def edc(buf):
    e, lut = 0, EDC_LUT
    for c in buf:
        e = (e >> 8) ^ lut[(e ^ c) & 0xFF]
    return e


# ECC = reed-solomon on GF(2^8), poly 0x11D
F = bytearray(256)  # x * 2
B = bytearray(256)  # inverse of x * 3
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    F[_i] = _j
    B[_i ^ _j] = _i
F, B = bytes(F), bytes(B)

# Q parity reads the sector in diagonal, byte order for each of the 43 steps
_Q_ORDER = itemgetter(*[((m >> 1) * 86 + (m & 1) + 88 * k) % 2236
                        for k in range(43) for m in range(52)])


def _parity(rows, n):
    a = b = 0
    for t in rows:
        a ^= t
        b ^= t
        a = int.from_bytes(a.to_bytes(n, "big").translate(F), "big")
    a = int.from_bytes((int.from_bytes(a.to_bytes(n, "big").translate(F), "big") ^ b)
                       .to_bytes(n, "big").translate(B), "big")
    return a.to_bytes(n, "big") + (a ^ b).to_bytes(n, "big")


def ecc(body):
    """body = bytes 12..0x81C of the sector (header, data, EDC, 8 zeros) -> P + Q (276 bytes)"""
    p = _parity([int.from_bytes(body[86 * k:86 * k + 86], "big") for k in range(24)], 86)
    q_in = bytes(_Q_ORDER(body + p))
    q = _parity([int.from_bytes(q_in[52 * k:52 * k + 52], "big") for k in range(43)], 52)
    return p + q


def msf(lba):
    a = lba + 150
    return bytes(((v // 10) << 4 | v % 10) for v in (a // 4500, a // 75 % 60, a % 75))


def encode(data, lba):
    head = SYNC + msf(lba) + b"\x01" + data
    body = head + struct.pack("<I", edc(head)) + bytes(8)
    return body + ecc(body[12:])


# what each bit of the header adress (bytes 12..14) and of the EDC (0x810..0x813) changes
def _tables():
    zero_edc = bytes(0x810)
    edc_t, ecc_t = [], {}
    for p in (12, 13, 14):
        bits = []
        for k in range(8):
            buf = bytearray(zero_edc)
            buf[p] = 1 << k
            bits.append(edc(buf))
        edc_t.append(_combine(bits))
    for p in (12, 13, 14, 0x810, 0x811, 0x812, 0x813):
        bits = []
        for k in range(8):
            body = bytearray(0x810)
            body[p - 12] = 1 << k
            bits.append(int.from_bytes(ecc(bytes(body)), "big"))
        ecc_t[p] = _combine(bits)
    return edc_t, ecc_t


def _combine(bits):
    t = [0] * 256
    for v in range(1, 256):
        low = v & -v
        t[v] = t[v ^ low] ^ bits[low.bit_length() - 1]
    return t


EDC_T, ECC_T = _tables()


def move(raw, lba):
    new = msf(lba)
    d = [raw[12 + i] ^ new[i] for i in range(3)]
    de = EDC_T[0][d[0]] ^ EDC_T[1][d[1]] ^ EDC_T[2][d[2]]
    dp = ECC_T[12][d[0]] ^ ECC_T[13][d[1]] ^ ECC_T[14][d[2]]
    for i in range(4):
        dp ^= ECC_T[0x810 + i][de >> (8 * i) & 0xFF]
    e = struct.unpack_from("<I", raw, 0x810)[0] ^ de
    par = int.from_bytes(raw[0x81C:], "big") ^ dp
    return (raw[:12] + new + raw[15:0x810] + struct.pack("<I", e) + raw[0x814:0x81C]
            + par.to_bytes(276, "big"))
