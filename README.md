# Sims3-MCP

**Let your favorite AI play The Sims 3.**

Sims3-MCP is an [MCP](https://modelcontextprotocol.io) server that connects an AI assistant (Claude Code,
Codex, Claude Desktop, or any other MCP client) to a running copy of **The Sims 3**. The AI can look at your
household, check your Sims' needs, click things the same way you would ("Have Quick Meal → Cereal", "Call
Sim → Chat"), run the clock, answer pop-up dialogs, build skills and careers, shop in buy mode, and run
cheats.

> "My Sim is exhausted and needs the bathroom. Take care of her, then find her a job in the Medical career."

It was inspired by [pevers/sims-mcp](https://github.com/pevers/sims-mcp) for The Sims 1.

---

## What it can do

| | |
|---|---|
| **Observe** | Time and speed, money, household members, needs, mood and moodlets, skills, traits, career, wishes, relationships, the action queue, open dialogs |
| **Play** | List nearby objects, see the real pie menu (including greyed-out options and why), queue actions, cancel them, walk somewhere, travel to other lots, switch Sims |
| **Time** | Pause, normal, fast or ultra. `wait` lets time pass and stops early when a need gets low, a dialog pops up, or the Sim has nothing left to do |
| **Stats** | Money, needs, skills, traits, moodlets, lifetime happiness and rewards, relationships, careers (join, promote, quit), aging up |
| **Buy mode** | Search the catalog, buy objects and place them exactly (position and facing), put things on counters and desks, replace, move or sell them |
| **Build mode** | Drive the game's own build tools: walls, floor paint, objects, sledgehammer, wall and floor presets, auto-roof |
| **Dialogs** | Read and answer pop-ups and pickers |
| **Cheats** | Any console cheat (`motherlode`, `testingcheatsenabled true`, …), plus saving the game |
| **Escape hatch** | `reflect`: read, change or call anything in the game's C# code by name |

---

## How it works (the "mailbox")

The Sims 3 has no API that outside programs can talk to, and its mod sandbox blocks network and file access.
So the two sides talk through a **shared mailbox in the game's memory**:

```
 Your AI ──MCP──> Python server ──(writes request into game memory)──┐
                                                                      ▼
                         The Sims 3:  [ MAILBOX  request → | ← response ]
                                                                      ▲
                       Sims3Mcp script mod ──(checks it every game tick, runs the request
                                              with the game's own functions, writes the answer)
```

1. A small **script mod** (`Sims3Mcp.package`) reserves a 1 MB block of memory inside the game and stamps a
   unique label on it.
2. The **Python MCP server** finds that block by scanning the game's memory
   (`ReadProcessMemory` / `WriteProcessMemory`, the same calls trainers use).
3. Python drops a JSON request into the mailbox. On the next game tick the mod picks it up and runs it using
   the game's **own functions**, the same ones the UI uses when you click something. It then writes the
   answer back.

Because the mod goes through the real game logic, everything behaves as if a player did it: the UI updates,
events fire, and saves stay safe. There's no DLL injection and no hard-coded memory addresses. If you restart
the game or load a different save, the server finds the new mailbox by itself.

---

## Requirements

- **Windows**, with **The Sims 3** on patch **1.67 or 1.69** (Steam, EA app, Origin or disc). It works with
  just the base game.
- **Python 3.10+**
- **.NET Framework 4.x**, which comes with Windows. It provides `csc.exe` for compiling the mod.

---

## Installation

### 1. Get the code and install the Python server

```powershell
git clone https://github.com/Critical-Reynolds/Sims3-MCP.git
cd Sims3-MCP
python -m venv .venv
.venv\Scripts\python -m pip install -e .
```

### 2. Build and install the mod

The mod is compiled against **your own copy** of the game, so no EA files are shipped in this repo.

```powershell
.venv\Scripts\python tools\extract_refs.py    # reads the game's script DLLs (doesn't modify the game)
.venv\Scripts\python tools\build_mod.py       # compiles the mod -> build\Sims3Mcp.package
.venv\Scripts\python tools\install_mod.py     # copies it into Documents\Electronic Arts\The Sims 3\Mods
```

> **Tip:** If your game isn't in `C:\Program Files\EA Games\The Sims 3`, run
> `tools\extract_refs.py --game "D:\Path\To\The Sims 3"`.
>
> **Tip:** You need to have started the game at least once, so its Documents folder exists.

### 3. Clear the script cache (important!)

With the game **closed**, delete:

```
Documents\Electronic Arts\The Sims 3\scriptCache.package
```

The game caches its list of scripts and may ignore a new mod until you do this. Do it again every time you
update the mod.

### 4. Start the game

Load a save. After a few seconds you should see the notification **"Sims3MCP 0.1.0 connected"**.

---

## Add it to your favorite AI

In every case the server is just this command:

```
<path-to>\Sims3-MCP\.venv\Scripts\python.exe -m sims3_mcp
```

Replace `C:\path\to\Sims3-MCP` below with wherever you cloned the repo.

### Claude Code

One command, and it's available in every project:

```powershell
claude mcp add sims3 --scope user -- C:\path\to\Sims3-MCP\.venv\Scripts\python.exe -m sims3_mcp
```

Then start `claude` and ask *"What's my Sim doing right now?"*. Run `/mcp` inside Claude Code to check the
connection.

### Codex (OpenAI Codex CLI)

```powershell
codex mcp add sims3 -- C:\path\to\Sims3-MCP\.venv\Scripts\python.exe -m sims3_mcp
```

Or add it by hand to `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.sims3]
command = 'C:\path\to\Sims3-MCP\.venv\Scripts\python.exe'
args = ["-m", "sims3_mcp"]
```

### Claude Desktop

Open **Settings → Developer → Edit Config** and add this to `claude_desktop_config.json`, then restart Claude
Desktop:

```json
{
  "mcpServers": {
    "sims3": {
      "command": "C:\\path\\to\\Sims3-MCP\\.venv\\Scripts\\python.exe",
      "args": ["-m", "sims3_mcp"]
    }
  }
}
```

### Anything else (Cursor, VS Code, Gemini CLI, …)

Any MCP client that supports **stdio** servers works. Point it at the command above.

---

## Things to try

- *"Look at my household and tell me what everyone needs."*
- *"My Sim is hungry. Make her something from the fridge, then let time run until she's done."*
- *"Find a job for her in the Medical career."*
- *"Have her call a friend and chat, then show me her relationships."*
- *"Buy a cheap bookshelf and put it in the living room."*
- *"Put a lamp on the desk, then build a small 4×4 room behind the house and auto-roof it."*
- *"Run motherlode, then save the game as 'AI Run'."*

The AI is told to change your game **only when you ask**. Still, **back up your saves** before experimenting!

---

## Tool list

| Area | Tools |
|---|---|
| Status | `game_status`, `look`, `async_log` |
| Sims & households | `list_households`, `list_sims`, `sim_details`, `set_active_sim`, `relationships` |
| Acting | `list_objects`, `object_details`, `list_interactions`, `do_interaction`, `cancel_interactions`, `go_here` |
| World & time | `list_lots`, `set_speed`, `wait` |
| Stats | `household_funds`, `set_motive`, `set_skill`, `skill_options`, `set_trait`, `trait_options`, `moodlet`, `lifetime_happiness`, `modify_relationship`, `career`, `age_up` |
| Dialogs | `pending_dialogs`, `respond_dialog` |
| Cheats & saving | `cheat`, `save_game` |
| Buy mode | `catalog_search`, `buy_object`, `place_object`, `put_on`, `replace_object`, `set_transform`, `move_object`, `sell_object`, `lot_layout` |
| Build mode | `build_mode`, `tool_select`, `tool_drag`, `build_presets`, `tile_info`, `calibrate`, `auto_roof` |
| Escape hatch | `reflect` |

That's 49 tools in all.

Targets for `list_interactions` / `do_interaction` can be:
- an object id
- a Sim's name
- `lot:<id>` (travel)
- `home`
- `terrain`
- `self`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No "connected" notification | Close the game, delete `scriptCache.package` (step 3), and restart. Check that `Mods\Resource.cfg` exists. |
| `mailbox not found` | Load into a world. The mailbox opens when a save finishes loading. |
| `timed out waiting` | The game is minimized on a loading screen, or a dialog is waiting. Try `pending_dialogs`. |
| `game said: …` | The game refused the action, and the message says why (e.g. the Sim's queue is full). |

---

## Development

- `python -m sims3_mcp.cli look`: send one raw command to the mod and print the JSON.
- `pip install -e .[dev]` then `pytest`: unit tests for the package format and the mailbox protocol (uses a
  simulated game).
- `tools\decompile.sh` decompiles the game's assemblies into `build\src` with ILSpy, for finding game APIs.
- Mod source is in `mod\src` (C#, compiled for the game's .NET 2.0 Mono). Server source is in
  `server\sims3_mcp`.

### Things learned the hard way

- **Script assemblies (S3SA) are XOR-chained.** Each byte is XORed with `table[seed]`, and `seed` advances by
  the ciphertext byte. The table is *not* modified while decoding. s3pe writes an all-zero table, which means
  the assembly is stored as plaintext.
- **The game only tunes assemblies marked `[assembly: Tunable]`.** Tuning is what runs a mod's
  `[Tunable]` static constructor.
- **Mono's heap is `PAGE_EXECUTE_READWRITE`.** Memory scans must include those pages.
- **A modal dialog puts the task that opened it to sleep until it closes.** Anything that might open one runs
  on its own task, never on the mailbox polling task.

---

## License & disclaimer

MIT. See [LICENSE](LICENSE).

This is a fan project and is not affiliated with or endorsed by Electronic Arts or Maxis. The Sims is a
trademark of Electronic Arts Inc. No game files are included in this repository; the mod is built against
your own installed copy.
