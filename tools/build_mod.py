"""Compile mod/src/**/*.cs against the game assemblies and pack Sims3Mcp.package.

Requires build/refs/ (run tools/dump_assemblies.py with the game open once).
Usage: python tools/build_mod.py
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dbpf  # noqa: E402

CSC = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
REFS = ["mscorlib", "System", "System.Xml", "ScriptCore", "SimIFace", "Sims3Metadata",
        "Sims3GameplaySystems", "Sims3GameplayObjects", "Sims3StoreObjects", "UI"]
ASSEMBLY = "Sims3Mcp"
INSTANTIATOR = "Sims3Mcp.Instantiator"

TUNING_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<base>
  <Current_Tuning>
    <kInstantiator value="True" />
  </Current_Tuning>
</base>
"""


def main() -> None:
    ref_dir = os.path.join(ROOT, "build", "refs")
    missing = [r for r in REFS if not os.path.exists(os.path.join(ref_dir, r + ".dll"))]
    if missing:
        sys.exit(f"missing reference assemblies {missing}; run tools/dump_assemblies.py with the game open")
    sources = sorted(glob.glob(os.path.join(ROOT, "mod", "src", "**", "*.cs"), recursive=True))
    dll = os.path.join(ROOT, "build", ASSEMBLY + ".dll")
    cmd = [CSC, "/nologo", "/nostdlib+", "/noconfig", "/target:library", "/optimize+",
           "/langversion:5", "/warn:4", "/nowarn:414,169,649",
           f"/out:{dll}"]
    cmd += [f"/reference:{os.path.join(ref_dir, r + '.dll')}" for r in REFS]
    cmd += sources
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if out:
        print(out)
    if proc.returncode != 0:
        sys.exit("compile failed")

    with open(dll, "rb") as f:
        asm = f.read()
    pkg = dbpf.PackageWriter()
    pkg.add(dbpf.TYPE_S3SA, 0, dbpf.fnv64(ASSEMBLY), dbpf.s3sa_encode(asm))
    pkg.add(dbpf.TYPE_XML, 0, dbpf.fnv64(INSTANTIATOR), TUNING_XML)
    out_pkg = os.path.join(ROOT, "build", ASSEMBLY + ".package")
    pkg.save(out_pkg)
    print(f"built {out_pkg} ({len(asm)} byte assembly, {len(sources)} source files)")


if __name__ == "__main__":
    main()
