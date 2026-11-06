"""Write subdrive-release.json and its signature for a version (used when publishing).

    SUBDRIVE_SIGNING_KEY=<64 hex digits> python tools/make_release_index.py \
        --version 1.0.0 --channel stable --notes notes.txt --out dist/ \
        program-windows-x86_64=dist/SubDrive-Windows.exe package-panasonic-ub450-150-154-uhd=dist/....zip ...

The key is read from the environment only, never from a file in the repository.
"""
import argparse, hashlib, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subdrive import ed25519, update  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--channel", choices=("stable", "beta"), required=True)
    ap.add_argument("--notes", type=Path, help="one note per line (Portuguese, shown to the user)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("files", nargs="+", metavar="key=path")
    a = ap.parse_args(argv)
    seed = bytes.fromhex(os.environ.get("SUBDRIVE_SIGNING_KEY", ""))
    if len(seed) != 32:
        sys.exit("SUBDRIVE_SIGNING_KEY must hold the 32-byte key in hex")
    if update.version_key(a.version) is None:
        sys.exit("invalid version")
    if (a.channel == "beta") != ("-" in a.version):
        sys.exit("beta versions have a pre-release tag (1.1.0-beta.1); final versions do not")
    files = {}
    for item in a.files:
        key, _, path = item.partition("=")
        data = Path(path).read_bytes()
        files[key] = {"name": Path(path).name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    notes = [l.strip() for l in a.notes.read_text(encoding="utf-8").splitlines() if l.strip()] if a.notes else []
    index = json.dumps({"schema": 1, "version": a.version, "channel": a.channel, "notes": notes, "files": files},
                       indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / update.INDEX).write_bytes(index)
    (a.out / update.SIGNATURE).write_bytes(ed25519.sign(seed, index))
    print("public key:", ed25519.public_key(seed).hex())


if __name__ == "__main__":
    main()
