"""Install build/Sims3Mcp.package into Documents\\Electronic Arts\\The Sims 3\\Mods.

Creates the standard Mods\\Resource.cfg if there is none (an existing one is
left untouched). The game must be closed for the new package to load.
Usage: python tools/install_mod.py [--docs <path to The Sims 3 user folder>]
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESOURCE_CFG = """Priority 500
PackedFile *.package
PackedFile */*.package
PackedFile */*/*.package
PackedFile */*/*/*.package
PackedFile */*/*/*/*.package
"""


def documents_dir() -> str:
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
    return buf.value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=os.path.join(documents_dir(), "Electronic Arts", "The Sims 3"))
    args = ap.parse_args()
    if not os.path.isdir(args.docs):
        sys.exit(f"{args.docs} not found; launch The Sims 3 once so it creates its user folder")
    pkg = os.path.join(ROOT, "build", "Sims3Mcp.package")
    if not os.path.exists(pkg):
        sys.exit("build/Sims3Mcp.package missing; run tools/build_mod.py first")
    mods = os.path.join(args.docs, "Mods")
    packages = os.path.join(mods, "Packages")
    os.makedirs(packages, exist_ok=True)
    cfg = os.path.join(mods, "Resource.cfg")
    if not os.path.exists(cfg):
        with open(cfg, "w", newline="\r\n") as f:
            f.write(RESOURCE_CFG)
        print(f"created {cfg}")
    dest = os.path.join(packages, "Sims3Mcp.package")
    shutil.copyfile(pkg, dest)
    print(f"installed {dest}")


if __name__ == "__main__":
    main()
