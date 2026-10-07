"""MCP server exposing The Sims 3 to Claude through the in-memory mailbox."""
from __future__ import annotations

import time
from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from .game import Game
from .mailbox import GameError, MailboxError

INSTRUCTIONS = """\
You are playing The Sims 3 through a live bridge into the running game (a script mod polled through
shared memory). There is no screen or mouse: everything goes through these tools.

- Start with `game_status`, then `look` (time, speed, household, funds, the active sim's needs -100..100,
  mood, moodlets, queue, and any open dialog).
- Only change the game when the user asks for it. Prefer normal play (interactions) over cheats unless the
  user wants cheats.
- Act like a player: `list_objects` to find things, `list_interactions(target, query)` to see the pie menu
  ("Prepare Food / Mac & Cheese", greyed-out items with reasons), then `do_interaction`. Social actions
  target another sim by name. Travel by targeting "lot:<id or name>" (see `list_lots`) or "home".
- Ids are strings; pass them back exactly as given.
- Time only runs when unpaused. Use `wait` to let time pass; it returns early on dialogs, low needs, or when
  the sim runs out of things to do, and pauses again afterwards.
- Dialogs block the game: if `look` shows dialog_open, call `pending_dialogs` then `respond_dialog`.
- Cheats/saving/dialog clicks run on their own game task: check `look`/`async_log` for the outcome.
"""

mcp = FastMCP("sims3", instructions=INSTRUCTIONS)
game = Game()


def _call(cmd: str, args: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
    """Send a command to the mod, turning failures into readable tool errors."""
    clean = {k: v for k, v in (args or {}).items() if v is not None}
    try:
        return game.call(cmd, clean, timeout=timeout)
    except GameError as e:
        raise RuntimeError(f"game said: {e}") from e
    except MailboxError as e:
        raise RuntimeError(str(e)) from e


# ---------------------------------------------------------------- status & observation

@mcp.tool()
def game_status() -> dict:
    """Is the game running, is the mod's mailbox found, is a world loaded."""
    info = game.status()
    if info.get("mailbox"):
        try:
            info["mod"] = _call("ping")
        except RuntimeError as e:
            info["mod_error"] = str(e)
    return info


@mcp.tool()
def look() -> dict:
    """Main observation: time/speed, household funds and members, the selected sim's needs, mood,
    moodlets, career, interaction queue, and any open dialog."""
    return _call("look")


@mcp.tool()
def list_households(include_special: bool = False) -> list:
    """All households in the world (name, id, funds, members, home lot)."""
    return _call("list_households", {"include_special": include_special})


@mcp.tool()
def list_sims(scope: str = "household") -> list:
    """List sims. scope: 'household' (active household), 'lot' (sims on the active sim's lot), 'world'."""
    return _call("list_sims", {"scope": scope})


@mcp.tool()
def sim_details(sim: str | None = None) -> dict:
    """Full detail for a sim (name or id; default = selected sim): needs, mood, moodlets, skills,
    traits, career, lifetime happiness, wishes, queue."""
    return _call("sim_details", {"sim": sim})


@mcp.tool()
def list_lots(query: str | None = None) -> list:
    """All lots (residential and community) with ids usable as targets ('lot:<id>')."""
    return _call("list_lots", {"query": query})


@mcp.tool()
def list_objects(query: str | None = None, lot: str | None = None, radius: float | None = None,
                 include_sims: bool = True, limit: int = 150) -> list:
    """Objects on the active sim's lot (or `lot`, or within `radius` meters of the sim), nearest first.
    Filter by name with `query` (e.g. 'fridge', 'bed', 'computer')."""
    return _call("list_objects", {"query": query, "lot": lot, "radius": radius,
                                  "include_sims": include_sims, "limit": limit})


@mcp.tool()
def object_details(target: str) -> dict:
    """Details about an object (id), sim (name/id) or lot ('lot:<id>')."""
    return _call("object_details", {"target": target})


# ---------------------------------------------------------------- acting

@mcp.tool()
def list_interactions(target: str, query: str | None = None, sim: str | None = None,
                      include_disabled: bool = False) -> dict:
    """The pie menu the sim would see when clicking `target` (object id, sim name, 'lot:<id>', 'home',
    'terrain', 'self'). Labels include submenu paths. With `query`, entries that need a choice also list
    `pick_from` options."""
    return _call("list_interactions", {"target": target, "query": query, "sim": sim,
                                       "include_disabled": include_disabled})


@mcp.tool()
def do_interaction(target: str, interaction: str, sim: str | None = None,
                   pick: list[str] | None = None) -> dict:
    """Queue an interaction exactly like clicking it in the pie menu. `interaction` is a label (or a unique
    part of one) from list_interactions. `pick` chooses options for entries with pick_from."""
    return _call("do_interaction", {"target": target, "interaction": interaction, "sim": sim, "pick": pick})


@mcp.tool()
def cancel_interactions(sim: str | None = None, id: str | None = None) -> list:
    """Cancel one queued interaction (`id` from the queue) or all of them."""
    return _call("cancel_interactions", {"sim": sim, "id": id})


@mcp.tool()
def go_here(target: str | None = None, x: float | None = None, z: float | None = None,
            sim: str | None = None) -> list:
    """Walk the sim to an object/sim/lot (`target`) or to world coordinates x,z."""
    return _call("go_here", {"target": target, "x": x, "z": z, "sim": sim})


@mcp.tool()
def set_active_sim(sim: str) -> dict:
    """Select a different sim in your household (like clicking their portrait)."""
    return _call("set_active_sim", {"sim": sim})


@mcp.tool()
def set_speed(speed: str) -> dict:
    """Game speed: pause, normal, fast, ultra, or skip."""
    return _call("set_speed", {"speed": speed})


@mcp.tool()
def wait(sim_minutes: float = 60, speed: str = "fast", max_seconds: float = 300,
         wake_on: list[str] | None = None, low_motive: float = -40) -> dict:
    """Let game time pass, then pause. Returns early when something needs attention.
    wake_on (default all): 'dialog' (a dialog opened), 'needs' (any need below low_motive),
    'idle' (the selected sim has nothing queued)."""
    wake = set(wake_on or ["dialog", "needs", "idle"])
    start = _call("tick_status")
    if start.get("dialog_open"):
        return {"stopped": "dialog", "status": start, "hint": "answer pending_dialogs first"}
    _call("set_speed", {"speed": speed})
    t0 = time.monotonic()
    begin = float(start["minutes_total"])
    reason = "time"
    status = start
    try:
        while True:
            time.sleep(0.5)
            status = _call("tick_status")
            if float(status["minutes_total"]) - begin >= sim_minutes:
                break
            if "dialog" in wake and status.get("dialog_open"):
                reason = "dialog"
                break
            if "needs" in wake and status.get("lowest_value", 100) < low_motive:
                reason = f"low {status.get('lowest_motive')}"
                break
            if "idle" in wake and status.get("queue_count", 1) == 0 and time.monotonic() - t0 > 2:
                reason = "idle"
                break
            if time.monotonic() - t0 > max_seconds:
                reason = "max_seconds"
                break
    finally:
        try:
            if not status.get("dialog_open"):
                _call("set_speed", {"speed": "pause"})
        except RuntimeError:
            pass
    status["elapsed_sim_minutes"] = round(float(status["minutes_total"]) - begin, 1)
    return {"stopped": reason, "status": status}


# ---------------------------------------------------------------- stats & sims

@mcp.tool()
def household_funds(set: int | None = None, add: int | None = None, household: str | None = None) -> dict:
    """Read household money, or `set` it / `add` to it (negative to subtract)."""
    return _call("household_funds", {"set": set, "add": add, "household": household})


@mcp.tool()
def set_motive(motive: str = "all", value: float | None = None, sim: str | None = None) -> dict:
    """Set a need (Hunger, Energy, Social, Bladder, Hygiene, Fun, ...) to `value` (-100..100), or max it
    when value is omitted. motive='all' affects every need. sim='household' affects everyone."""
    return _call("set_motive", {"motive": motive, "value": value, "sim": sim})


@mcp.tool()
def set_skill(skill: str, level: int, sim: str | None = None) -> dict:
    """Set a skill level (adds the skill if missing). Skill ids from skill_options (e.g. Cooking, Logic)."""
    return _call("set_skill", {"skill": skill, "level": level, "sim": sim})


@mcp.tool()
def skill_options(sim: str | None = None) -> list:
    """All skills with the sim's current level (-1 = not learned)."""
    return _call("skill_options", {"sim": sim})


@mcp.tool()
def set_trait(trait: str, remove: bool = False, sim: str | None = None) -> list:
    """Add (or remove) a trait. Trait ids from trait_options."""
    return _call("set_trait", {"trait": trait, "remove": remove, "sim": sim})


@mcp.tool()
def trait_options(rewards: bool = False, sim: str | None = None) -> list:
    """All traits (or lifetime-reward traits with their cost) and whether the sim has them."""
    return _call("trait_options", {"rewards": rewards, "sim": sim})


@mcp.tool()
def moodlet(action: str = "list", moodlet: str | None = None, minutes: float | None = None,
            query: str | None = None, sim: str | None = None) -> Any:
    """Moodlets: action list | add (moodlet, optional minutes) | remove (moodlet) | search (query)."""
    return _call("moodlet", {"action": action, "moodlet": moodlet, "minutes": minutes,
                             "query": query, "sim": sim})


@mcp.tool()
def lifetime_happiness(add: float | None = None, buy_reward: str | None = None,
                       sim: str | None = None) -> dict:
    """Read lifetime happiness points, `add` points, or `buy_reward` (a reward trait id)."""
    return _call("lifetime_happiness", {"add": add, "buy_reward": buy_reward, "sim": sim})


@mcp.tool()
def relationships(sim: str | None = None) -> list:
    """A sim's relationships, best first (liking -100..100 and state)."""
    return _call("relationships", {"sim": sim})


@mcp.tool()
def modify_relationship(other: str, liking: float | None = None, add_liking: float | None = None,
                        state: str | None = None, sim: str | None = None) -> dict:
    """Change the relationship between `sim` and `other`: set `liking`, `add_liking`, or force a `state`
    (Friend, GoodFriend, BestFriend, RomanticInterest, Partner, Fiancee, Spouse, Enemy, ...)."""
    return _call("modify_relationship", {"other": other, "liking": liking, "add_liking": add_liking,
                                         "state": state, "sim": sim})


@mcp.tool()
def career(action: str = "info", career: str | None = None, sim: str | None = None) -> Any:
    """Jobs: action info | options (careers in this world) | join (career id) | promote | demote | quit."""
    return _call("career", {"action": action, "career": career, "sim": sim})


@mcp.tool()
def age_up(sim: str | None = None, confirm_elder_death: bool = False) -> dict:
    """Trigger the sim's age transition (elders die: requires confirm_elder_death)."""
    return _call("age_up", {"sim": sim, "confirm_elder_death": confirm_elder_death})


# ---------------------------------------------------------------- dialogs, cheats, saving

@mcp.tool()
def pending_dialogs() -> dict:
    """The open modal dialog (text, buttons, picker rows), if any."""
    return _call("pending_dialogs")


@mcp.tool()
def respond_dialog(button: str | None = None, pick: list[str] | None = None) -> dict:
    """Click a dialog button (by caption) and/or choose picker rows (`pick`, then OK is clicked)."""
    return _call("respond_dialog", {"button": button, "pick": pick})


@mcp.tool()
def cheat(command: str) -> dict:
    """Run a cheat-console command (e.g. 'motherlode', 'testingcheatsenabled true'). 'help' lists them."""
    return _call("cheat", {"command": command})


@mcp.tool()
def save_game(name: str | None = None) -> dict:
    """Save the game (optionally under a new save name)."""
    return _call("save_game", {"name": name})


@mcp.tool()
def async_log() -> list:
    """Results of recent background actions (cheats, saves, dialog clicks)."""
    return _call("async_log")


# ---------------------------------------------------------------- buy / sell

@mcp.tool()
def catalog_search(query: str = "", max_price: float | None = None, limit: int = 40) -> list:
    """Search the buy-mode catalog. Returns product keys for buy_object."""
    return _call("catalog_search", {"query": query, "max_price": max_price, "limit": limit}, timeout=60)


@mcp.tool()
def buy_object(product: str, near: str | None = None, to_inventory: bool = False, free: bool = False) -> dict:
    """Buy a catalog product and place it near `near` (object/sim) or the active sim, or put it in the
    family inventory. Charges the household unless free=true."""
    return _call("buy_object", {"product": product, "near": near, "to_inventory": to_inventory, "free": free})


@mcp.tool()
def sell_object(target: str) -> dict:
    """Sell an object (by id) for its current value."""
    return _call("sell_object", {"target": target})


@mcp.tool()
def move_object(target: str, near: str | None = None, x: float | None = None, z: float | None = None) -> dict:
    """Move an object near another object/sim, or to x,z."""
    return _call("move_object", {"target": target, "near": near, "x": x, "z": z})


@mcp.tool()
def place_object(product: str, x: float, z: float, y: float | None = None, facing: float = 0,
                 free: bool = False) -> dict:
    """Buy a product and put it exactly at x,(y),z facing `facing` degrees (0=+z, 90=+x, 180=-z, 270=-x).
    No placement search: you are responsible for a sensible spot. y defaults to terrain height."""
    return _call("place_object", {"product": product, "x": x, "y": y, "z": z, "facing": facing, "free": free},
                 timeout=60)


@mcp.tool()
def replace_object(target: str, product: str, dx: float = 0, dz: float = 0, turn: float = 0,
                   free: bool = False) -> dict:
    """Sell `target` and put `product` at its exact position and facing (optionally shifted by dx/dz and
    rotated by `turn` degrees). Best for like-for-like upgrades (bed -> better bed)."""
    return _call("replace_object", {"target": target, "product": product, "dx": dx, "dz": dz, "turn": turn,
                                    "free": free}, timeout=60)


@mcp.tool()
def set_transform(target: str, x: float | None = None, y: float | None = None, z: float | None = None,
                  dx: float = 0, dz: float = 0, facing: float | None = None) -> dict:
    """Move/rotate an object exactly (no placement search). Omitted coordinates keep their value."""
    return _call("set_transform", {"target": target, "x": x, "y": y, "z": z, "dx": dx, "dz": dz,
                                   "facing": facing})


@mcp.tool()
def put_on(surface: str, product: str | None = None, target: str | None = None, slot: int | None = None,
           free: bool = False) -> dict:
    """Put a new `product` (bought) or an existing object `target` into a free slot on `surface`
    (desk, counter, end table, shelf). `slot` picks a specific slot index."""
    return _call("put_on", {"surface": surface, "product": product, "target": target, "slot": slot, "free": free},
                 timeout=60)


# ---------------------------------------------------------------- build mode (native tools)

@mcp.tool()
def build_mode(on: bool = True) -> dict:
    """Enter build mode on the home lot (on=true) or go back to live mode (on=false). Runs async."""
    return _call("build_mode", {"on": on})


@mcp.tool()
def tile_info(x: float | None = None, z: float | None = None, lx: int | None = None, lz: int | None = None,
              level: int = 0, lx2: int | None = None, lz2: int | None = None) -> dict:
    """World x,z -> lot tile (lx,lz); or lot tile -> world position, room, solid floor, and (with lx2/lz2)
    whether a wall separates the two tiles."""
    return _call("tile_info", {"x": x, "z": z, "lx": lx, "lz": lz, "level": level, "lx2": lx2, "lz2": lz2})


@mcp.tool()
def calibrate() -> dict:
    """Fit the world->window-pixel mapping from floor picks (done automatically when the camera moves)."""
    return _call("calibrate", {})


@mcp.tool()
def tool_select(tool: int, product: str | None = None, preset: int | None = None) -> dict:
    """Activate a native build tool (0 wall, 2 floor paint, 4 object/door/window, 12 sledgehammer...) with an
    optional product key / preset, like picking it in the build catalog."""
    return _call("tool_select", {"tool": tool, "product": product, "preset": preset})


@mcp.tool()
def tool_drag(points: list, pixels: bool = False, frames: int = 3, button: int = 1000, modifiers: int = 0) -> dict:
    """Press at the first point, drag through the rest, release at the last. Points are world [x,z] (or window
    pixels with pixels=true). Draws walls, paints floor rectangles, or clicks to place. Runs async."""
    return _call("tool_drag", {"points": points, "pixels": pixels, "frames": frames, "button": button,
                               "modifiers": modifiers})


@mcp.tool()
def build_presets(kind: str = "floor", query: str | None = None, category: int | None = None,
                  limit: int = 40) -> list:
    """Floor ('floor') or wall ('wall') pattern presets for tool_select."""
    return _call("build_presets", {"kind": kind, "query": query, "category": category, "limit": limit}, timeout=60)


@mcp.tool()
def auto_roof() -> dict:
    """Let the game auto-roof the home lot."""
    return _call("auto_roof", {})


@mcp.tool()
def lot_layout(lot: str | None = None, query: str | None = None) -> dict:
    """Every object on the home lot (or `lot`) with id, position, facing, room, level, value, wall flag."""
    return _call("lot_layout", {"lot": lot, "query": query}, timeout=30)


# ---------------------------------------------------------------- escape hatch

@mcp.tool()
def reflect(op: str, path: str, value: Any = None, args: list | None = None, depth: int = 1,
            filter: str | None = None) -> Any:
    """Advanced: inspect or change anything in the game's C# by dotted path.
    op: get | set (value) | call (args) | members (filter) | find_types (path = search text).
    Roots: '@sim' (selected sim), '@household', '@lot', '@obj:<object id>', or a full type name,
    e.g. 'Sims3.Gameplay.Core.LotManager.ActiveLot.Name', '@sim.SimDescription.FirstName'."""
    ops = {"get": "reflect_get", "set": "reflect_set", "call": "reflect_call",
           "members": "reflect_members", "find_types": "reflect_find_types"}
    if op not in ops:
        raise RuntimeError(f"op must be one of {', '.join(ops)}")
    payload: dict[str, Any] = {"path": path, "depth": depth, "filter": filter, "value": value, "args": args}
    if op == "find_types":
        payload = {"query": path}
    return _call(ops[op], payload, timeout=60)


def main() -> None:
    mcp.run()
