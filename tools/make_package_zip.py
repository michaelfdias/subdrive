"""The player package as SubDrive CLI's update reads it: the contents of pacote/ at the root of a ZIP.

    python tools/make_package_zip.py pacotes/panasonic-ub450-150-154-uhd.zip out/SubDrive-1.0.0-pacote-UHD.zip 1.0.0
"""
import io, json, sys, zipfile
from pathlib import PurePosixPath


def main(source, target, version):
    with zipfile.ZipFile(source) as src:
        names = [n for n in src.namelist() if "/pacote/" in "/" + n and not n.endswith("/")]
        if not names:
            sys.exit("No pacote/ folder in %s" % source)
        cut = names[0].index("pacote/") + len("pacote/")
        files = {n[cut:]: src.read(n) for n in names}
    for n in files:
        p = PurePosixPath(n)
        if p.is_absolute() or ".." in p.parts:
            sys.exit("Unsafe name: %s" % n)
    if json.loads(files["manifest.json"])["version"] != version:
        sys.exit("The package is not version %s" % version)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in sorted(files):
            info = zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3; info.external_attr = 0o100644 << 16
            z.writestr(info, files[n])
    open(target, "wb").write(buf.getvalue())
    print(target, len(buf.getvalue()))


if __name__ == "__main__":
    main(*sys.argv[1:4])
