"""Debug CLI: send one command to the mod and print the JSON result.

    python -m sims3_mcp.cli ping
    python -m sims3_mcp.cli household_funds '{"add": 1000}'
"""
from __future__ import annotations

import json
import sys

from .mailbox import Mailbox
from .process import Process, find_pid


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    pid = find_pid()
    if pid is None:
        sys.exit("TS3.exe is not running")
    with Process(pid) as proc:
        box = Mailbox(proc)
        addr = box.locate()
        print(f"mailbox at 0x{addr:08X}", file=sys.stderr)
        print(json.dumps(box.call(cmd, args), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
