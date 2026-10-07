"""Extract the game's script assemblies into build/refs/ for compiling the mod.

Reads (never modifies) the game's .package files. Usage:
    python tools/extract_refs.py [--game "C:\\Program Files\\EA Games\\The Sims 3"]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbpf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME = r"C:\Program Files\EA Games\The Sims 3"
PACKAGES = ["simcore.package", "scripts.package", "gameplay.package"]


def assembly_name(path: str) -> str:
    """Ask .NET for the assembly's simple name (PowerShell, no extra deps)."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"[Reflection.AssemblyName]::GetAssemblyName('{path}').Name"],
        capture_output=True, text=True, check=True)
    return out.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    args = ap.parse_args()
    bin_dir = os.path.join(args.game, "Game", "Bin")
    out_dir = os.path.join(ROOT, "build", "refs")
    os.makedirs(out_dir, exist_ok=True)
    for pkg_name in PACKAGES:
        pkg = dbpf.Package(os.path.join(bin_dir, pkg_name))
        for e in pkg.find(dbpf.TYPE_S3SA):
            asm = dbpf.s3sa_decode(pkg.read(e))
            tmp = os.path.join(out_dir, f"{e.instance:016X}.tmp")
            with open(tmp, "wb") as f:
                f.write(asm)
            name = assembly_name(tmp)
            final = os.path.join(out_dir, name + ".dll")
            os.replace(tmp, final)
            print(f"{pkg_name:18} {e.instance:016X} -> {name}.dll ({len(asm)} bytes)")


if __name__ == "__main__":
    main()
