"""Read one file out of a SquashFS 4.0 image (gzip), as found inside the player's official firmware.

Only reading, only what SubDrive needs: walk the directories, read a regular file.
"""
import struct
import zlib

MAGIC = b"hsqs"


class SquashError(ValueError):
    pass


class SquashFS:
    def __init__(self, data: bytes):
        if data[:4] != MAGIC or len(data) < 96:
            raise SquashError("not a SquashFS image")
        (_, self.inodes, _, self.block_size, self.fragments, compressor, _, self.flags, _, major, _minor,
         self.root, self.bytes_used, _ids, _xattr, self.inode_table, self.dir_table, self.frag_table, _export
         ) = struct.unpack_from("<5I6H8Q", data, 0)
        if major != 4 or compressor != 1:
            raise SquashError("unsupported SquashFS (version %d, compressor %d)" % (major, compressor))
        self.data = data
        self._frag_entries = None

    # -------------------------------------------------------------- metadata
    def _meta_block(self, pos):
        header, = struct.unpack_from("<H", self.data, pos)
        size = header & 0x7FFF
        raw = self.data[pos + 2:pos + 2 + size]
        block = raw if header & 0x8000 else zlib.decompress(raw)
        return block, pos + 2 + size

    def _meta(self, table, block, offset, length):
        pos, out = table + block, bytearray()
        chunk, pos = self._meta_block(pos)
        out += chunk[offset:]
        while len(out) < length:
            chunk, pos = self._meta_block(pos)
            out += chunk
        return bytes(out[:length])

    def _inode(self, ref):
        block, offset = ref >> 16, ref & 0xFFFF
        head = self._meta(self.inode_table, block, offset, 16 + 56)
        kind, = struct.unpack_from("<H", head, 0)
        if kind == 1:   # basic directory
            start, _, size, off, _ = struct.unpack_from("<IIHHI", head, 16)
            return ("dir", start, off, size)
        if kind == 8:   # extended directory
            _, size, start, _, _, off, _ = struct.unpack_from("<IIIIHHI", head, 16)
            return ("dir", start, off, size)
        if kind in (2, 9):
            if kind == 2:
                start, frag, frag_off, size = struct.unpack_from("<IIII", head, 16)
                fixed = 32
            else:
                start, size, _, _, frag, frag_off, _ = struct.unpack_from("<QQQIIII", head, 16)
                fixed = 56
            whole = size // self.block_size if frag != 0xFFFFFFFF else -(-size // self.block_size)
            full = self._meta(self.inode_table, block, offset, fixed + 4 * whole)
            sizes = struct.unpack_from("<%dI" % whole, full, fixed)
            return ("file", start, size, sizes, frag, frag_off)
        return ("other",)

    def _entries(self, inode):
        _, start, offset, size = inode
        raw = self._meta(self.dir_table, start, offset, max(0, size - 3))
        p, out = 0, {}
        while p < len(raw):
            count, iblock, _ = struct.unpack_from("<III", raw, p); p += 12
            for _ in range(count + 1):
                ioff, _, _, nsize = struct.unpack_from("<HhHH", raw, p); p += 8
                name = raw[p:p + nsize + 1].decode("utf-8", "replace"); p += nsize + 1
                out[name] = (iblock << 16) | ioff
        return out

    # -------------------------------------------------------------- files
    def _fragment(self, index):
        if self._frag_entries is None:
            count = -(-self.fragments // 512)
            pointers = struct.unpack_from("<%dQ" % count, self.data, self.frag_table)
            entries = bytearray()
            for ptr in pointers:
                block, _ = self._meta_block(ptr)
                entries += block
            self._frag_entries = bytes(entries)
        start, size, _ = struct.unpack_from("<QII", self._frag_entries, index * 16)
        raw = self.data[start:start + (size & 0xFFFFFF)]
        return raw if size & 0x1000000 else zlib.decompress(raw)

    def read(self, path: str, limit=64 * 1024 * 1024) -> bytes:
        inode = self._inode(self.root)
        parts = [p for p in path.strip("/").split("/") if p]
        for k, part in enumerate(parts):
            if inode[0] != "dir":
                raise SquashError("not a folder: " + "/".join(parts[:k]))
            entries = self._entries(inode)
            if part not in entries:
                raise SquashError("missing: " + "/".join(parts[:k + 1]))
            inode = self._inode(entries[part])
        if inode[0] != "file":
            raise SquashError("not a file: " + path)
        _, start, size, sizes, frag, frag_off = inode
        if size > limit:
            raise SquashError("file too large")
        out, pos = bytearray(), start
        for s in sizes:
            length = s & 0xFFFFFF
            if length == 0:
                out += bytes(self.block_size)
                continue
            raw = self.data[pos:pos + length]; pos += length
            out += raw if s & 0x1000000 else zlib.decompress(raw)
        if frag != 0xFFFFFFFF:
            tail = size - len(out)
            out += self._fragment(frag)[frag_off:frag_off + tail]
        return bytes(out[:size])


def find_image(blob: bytes) -> bytes:
    """The single SquashFS image inside a firmware file."""
    off = blob.find(MAGIC)
    if off < 0 or blob.find(MAGIC, off + 1) >= 0:
        raise SquashError("expected exactly one SquashFS image")
    size = struct.unpack_from("<5I6H8Q", blob, off)[12]
    if off + size > len(blob):
        raise SquashError("image outside the firmware file")
    return blob[off:off + size]
