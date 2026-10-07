#!/usr/bin/env bash
# Decompile game assemblies to build/src/<Assembly>/ (requires .tools from setup).
# Usage: tools/decompile.sh [Assembly ...]   (default: main gameplay assemblies)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ILSPY="$(ls -d "$ROOT"/.tools/ilspy/tools/*/any)/ilspycmd.dll"
ASMS=("$@"); [ ${#ASMS[@]} -eq 0 ] && ASMS=(SimIFace ScriptCore UI Sims3GameplaySystems Sims3GameplayObjects)
for a in "${ASMS[@]}"; do
  out="$ROOT/build/src/$a"; mkdir -p "$out"
  "$ROOT/.tools/dotnet/dotnet.exe" "$ILSPY" -p -o "$out" -r "$ROOT/build/refs" "$ROOT/build/refs/$a.dll" > "$out.log" 2>&1 \
    && echo "$a: $(find "$out" -name '*.cs' | wc -l) files" || echo "$a: FAILED (see $out.log)"
done
