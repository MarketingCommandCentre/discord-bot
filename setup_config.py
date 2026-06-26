"""
Interactive setup script for the Marketing Command Centre Discord Bot.

Provisions a brand-new server's configuration from scratch and writes
``src/config/settings.json``. It logs into Discord with the existing
``DISCORD_TOKEN`` (read from ``.env``), then for each role and Kanban
category it will either link an existing object by name or create a new
one, capturing the resulting Discord IDs.

This script only writes ``settings.json`` -- it never touches ``.env`` or
any secrets. Run it once when standing up the bot on a new server:

    python setup_config.py

Re-running is safe: existing roles/categories are linked rather than
duplicated, and the previous settings.json is backed up first.

Copyright (C) 2026 Ibrahim Chehab

This file is part of the Marketing Command Centre Discord Bot.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import sys
import json
import shutil
import asyncio
from datetime import datetime

import discord
from dotenv import load_dotenv

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "src", "config", "settings.json")

# Standard top-level roles: config key -> default Discord role display name.
DEFAULT_ROLES = {
    "admin": "Admin",
    "content_creator": "Content Creator",
    "graphic_designer": "Graphic Designer",
    "social_media_manager": "Social Media Manager",
}

# Default department structure (key -> display name, optional subgroups).
DEFAULT_DEPARTMENTS = {
    "marketing": {"name": "Marketing Team", "subgroups": {}},
    "events": {
        "name": "Events",
        "subgroups": {
            "events-brothers": "Brothers Events",
            "events-sisters": "Sisters Events",
        },
    },
    "ie": {
        "name": "Islamic Education",
        "subgroups": {
            "ie-sisters": "Sisters IE",
            "ie-brothers": "Brothers IE",
        },
    },
    "charity": {"name": "Charity", "subgroups": {}},
    "dawah": {"name": "Dawah", "subgroups": {}},
}

# Kanban categories: status key -> (internal name stored in config, default
# Discord category channel display name). The bot matches categories by ID at
# runtime, so the display name is only used to find/create the channel here.
DEFAULT_CATEGORIES = {
    "queue": ("in_queue", "📥 In Queue"),
    "progress": ("in_progress", "🔄 In Progress"),
    "awaiting": ("awaiting_posting", "⏳ Awaiting Posting"),
    "done": ("done", "✅ Done"),
    "blocked": ("blocked", "🚫 Blocked"),
}

# Non-Discord config sections carried over verbatim as sane defaults. These
# hold no server-specific IDs and can be tweaked later by editing the JSON or
# via the bot's slash commands.
STATIC_DEFAULTS = {
    "request_types": {
        "post": {"emoji": "📸", "prefix": "[POST]", "color": 3447003, "role": "graphic_designer"},
        "reel": {"emoji": "📽️", "prefix": "[REEL]", "color": 15158332, "role": "content_creator"},
    },
    "priorities": {
        "low": {"emoji": "🟢", "color": 3066993},
        "medium": {"emoji": "🟡", "color": 15844367},
        "high": {"emoji": "🟠", "color": 15105570},
        "urgent": {"emoji": "🔴", "color": 15158332},
    },
    "bot_config": {
        "command_prefix": "!",
        "activity_name": "Managing Marketing Requests",
        "activity_type": "watching",
        "status": "online",
        "auto_sort_channels": True,
        "cycle_warnings_enabled": True,
        "max_request_title_length": 100,
        "max_request_description_length": 4000,
        "max_notes_length": 500,
        "show_upload_tips": True,
        "auto_pin_messages": True,
        "minimize_channel_messages": True,
        "fork_enabled": True,
        "fork_trigger_channels": ["fork-a-vc"],
        "fork_auto_cleanup_minutes": 5,
    },
    "embed_colors": {
        "info": 3447003, "success": 3066993, "warning": 15844367, "error": 15158332,
        "queue": 9807270, "progress": 3447003, "awaiting": 15844367, "done": 3066993,
    },
    "messages": {
        "request_created": "✅ Request created successfully! Check {channel}",
        "request_advanced": "✅ {channel} advanced to **{category}**!",
        "setup_complete": "🎉 Kanban board setup complete!",
        "no_permission": "❌ You don't have permission to use this command!",
        "invalid_date": "❌ Invalid date format! Please use MM/DD/YYYY (e.g., 12/25/2024)",
        "categories_missing": "❌ Kanban categories not set up! Ask an admin to run `/setup`.",
        "already_final_stage": "❌ Channel is already in the final stage!",
    },
    "date_formats": {"input": "%m/%d/%Y", "display": "%B %d, %Y", "channel": "%m/%d"},
}


# --- Prompt helpers (run blocking input() off the event loop) -----------------

async def ask(prompt: str, default: str = None) -> str:
    """Prompt for a line of input, returning ``default`` on empty input."""
    suffix = f" [{default}]" if default is not None else ""
    raw = await asyncio.to_thread(input, f"{prompt}{suffix}: ")
    raw = raw.strip()
    return raw if raw else (default or "")


async def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = (await asyncio.to_thread(input, f"{prompt} [{hint}]: ")).strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


# --- Discord lookup / provisioning helpers ------------------------------------

def find_by_name(items, name):
    """Case-insensitive name match over a collection of named Discord objects."""
    lowered = name.strip().lower()
    for item in items:
        if item.name.lower() == lowered:
            return item
    return None


async def get_or_create_role(guild: discord.Guild, name: str):
    """Link an existing role by name or create a new one. Returns (role, created)."""
    existing = find_by_name([r for r in guild.roles if not r.is_default()], name)
    if existing:
        print(f"   🔗 Linked existing role '{name}' (id {existing.id})")
        return existing, False
    try:
        role = await guild.create_role(name=name, reason="Marketing bot setup")
        print(f"   ✅ Created role '{name}' (id {role.id})")
        return role, True
    except discord.Forbidden:
        print(f"   ⚠️  Missing permission to create role '{name}'.")
        return await prompt_manual_id(guild, "role", name), False


async def get_or_create_category(guild: discord.Guild, name: str):
    """Link an existing category channel by name or create one. Returns (cat, created)."""
    existing = find_by_name(guild.categories, name)
    if existing:
        print(f"   🔗 Linked existing category '{name}' (id {existing.id})")
        return existing, False
    try:
        category = await guild.create_category(name=name, reason="Marketing bot setup")
        print(f"   ✅ Created category '{name}' (id {category.id})")
        return category, True
    except discord.Forbidden:
        print(f"   ⚠️  Missing permission to create category '{name}'.")
        return await prompt_manual_id(guild, "category", name), False


async def prompt_manual_id(guild: discord.Guild, kind: str, name: str):
    """Fallback: ask the user to paste an ID when auto-creation isn't possible."""
    while True:
        raw = await ask(f"   Enter an existing {kind} ID for '{name}' (or blank to skip)")
        if not raw:
            return None
        if raw.isdigit():
            obj = guild.get_role(int(raw)) if kind == "role" else guild.get_channel(int(raw))
            if obj is not None:
                return obj
        print("   Invalid ID, try again.")


# --- Main setup flow ----------------------------------------------------------

async def run_setup(guild: discord.Guild) -> dict:
    print(f"\n=== Configuring '{guild.name}' (id {guild.id}) ===\n")

    settings = {}

    # 1. Standard top-level roles -------------------------------------------------
    print("Step 1/5 — Standard roles")
    role_objs = {}
    settings["roles"] = {}
    for key, default_name in DEFAULT_ROLES.items():
        name = await ask(f" Role name for '{key}'", default_name)
        role, _ = await get_or_create_role(guild, name)
        role_objs[key] = role
        settings["roles"][key] = role.id if role else None

    # 2. Departments + sub-departments -------------------------------------------
    print("\nStep 2/5 — Departments")
    use_defaults = await ask_yes_no(
        " Use the default department set (marketing, events, ie, charity)?", True)
    departments_plan = dict(DEFAULT_DEPARTMENTS) if use_defaults else {}
    if not use_defaults:
        print(" Enter departments. Leave the key blank to finish.")
        while True:
            key = (await ask(" Department key (e.g. marketing)")).strip()
            if not key:
                break
            name = await ask(f" Display name for '{key}'", key.title())
            subgroups = {}
            if await ask_yes_no(f" Add sub-departments under '{key}'?", False):
                print(" Enter sub-departments. Leave the key blank to finish.")
                while True:
                    sub_key = (await ask("  Sub-department key")).strip()
                    if not sub_key:
                        break
                    sub_name = await ask(f"  Display name for '{sub_key}'", sub_key.title())
                    subgroups[sub_key] = sub_name
            departments_plan[key] = {"name": name, "subgroups": subgroups}

    settings["departments"] = {}
    settings["department_subgroups"] = {}
    for key, plan in departments_plan.items():
        print(f" Department '{key}':")
        role_name = await ask(f"  Role name for department '{key}'", plan["name"])
        role, _ = await get_or_create_role(guild, role_name)
        settings["departments"][key] = {
            "name": plan["name"],
            "members": [],
            "role_name": role_name,
            "role_id": role.id if role else None,
        }
        if plan["subgroups"]:
            settings["department_subgroups"][key] = {}
            for sub_key, sub_name in plan["subgroups"].items():
                sub_role_name = await ask(f"  Role name for sub-department '{sub_key}'", sub_name)
                sub_role, _ = await get_or_create_role(guild, sub_role_name)
                settings["department_subgroups"][key][sub_key] = {
                    "name": sub_name,
                    "members": [],
                    "role_name": sub_role_name,
                    "role_id": sub_role.id if sub_role else None,
                }

    # 3. Kanban category channels ------------------------------------------------
    print("\nStep 3/5 — Kanban categories")
    settings["categories"] = {}
    for key, (internal_name, default_display) in DEFAULT_CATEGORIES.items():
        display = await ask(f" Category channel name for '{key}'", default_display)
        category, _ = await get_or_create_category(guild, display)
        settings["categories"][key] = {
            "name": internal_name,
            "category_id": category.id if category else None,
        }

    # 4. Static (non-Discord) sections -------------------------------------------
    print("\nStep 4/5 — Bot behaviour defaults")
    static = json.loads(json.dumps(STATIC_DEFAULTS))  # deep copy
    static["bot_config"]["command_prefix"] = await ask(
        " Command prefix", static["bot_config"]["command_prefix"])
    static["bot_config"]["activity_name"] = await ask(
        " Bot activity / presence text", static["bot_config"]["activity_name"])
    static["bot_config"]["cycle_warnings_enabled"] = await ask_yes_no(
        " Warn requesters when a posting date falls outside the production cycle?", True)
    settings.update(static)

    # 5. Server config (reminder channel + marketing role) -----------------------
    print("\nStep 5/5 — Server config")
    marketing_default = str(role_objs["admin"].id) if role_objs.get("admin") else ""
    print(" Marketing role is pinged for reminders/announcements.")
    marketing_role_id = role_objs["admin"].id if role_objs.get("admin") else None
    if not await ask_yes_no(f" Use the '{DEFAULT_ROLES['admin']}' role as the marketing role?", True):
        mr = await ask(" Marketing role name", DEFAULT_DEPARTMENTS["marketing"]["name"])
        role, _ = await get_or_create_role(guild, mr)
        marketing_role_id = role.id if role else None

    reminder_channel_id = None
    reminder_name = (await ask(
        " Reminder text channel name (blank to skip)")).strip()
    if reminder_name:
        channel = find_by_name(
            [c for c in guild.channels if isinstance(c, discord.TextChannel)], reminder_name)
        if channel:
            reminder_channel_id = channel.id
            print(f"   🔗 Linked reminder channel '{reminder_name}' (id {channel.id})")
        else:
            print(f"   ⚠️  No text channel named '{reminder_name}' found; left unset.")

    settings["server_config"] = {
        "marketing_role_id": marketing_role_id,
        "reminder_channel_id": reminder_channel_id,
    }

    return settings


def write_settings(settings: dict) -> None:
    if os.path.exists(CONFIG_PATH):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{CONFIG_PATH}.bak.{stamp}"
        shutil.copy2(CONFIG_PATH, backup)
        print(f"\n💾 Backed up existing config to {os.path.basename(backup)}")
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print(f"✅ Wrote configuration to {CONFIG_PATH}")


async def select_guild(client: discord.Client) -> discord.Guild:
    guilds = client.guilds
    if not guilds:
        print("❌ The bot isn't in any server yet. Invite it first, then re-run.")
        return None
    if len(guilds) == 1:
        guild = guilds[0]
        if await ask_yes_no(f"Configure '{guild.name}'?", True):
            return guild
        return None
    print("The bot is in multiple servers:")
    for i, g in enumerate(guilds, 1):
        print(f"  {i}. {g.name} (id {g.id})")
    while True:
        raw = await ask("Pick a server number")
        if raw.isdigit() and 1 <= int(raw) <= len(guilds):
            return guilds[int(raw) - 1]
        print("Invalid choice.")


class SetupClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self._done = False

    async def on_ready(self):
        if self._done:
            return
        self._done = True
        print(f"🤖 Logged in as {self.user}")
        try:
            guild = await select_guild(self)
            if guild is None:
                return
            settings = await run_setup(guild)
            print("\n--- Summary ---")
            print(f" Roles:        {len(settings['roles'])}")
            print(f" Departments:  {len(settings['departments'])}")
            print(f" Sub-depts:    {sum(len(v) for v in settings['department_subgroups'].values())}")
            print(f" Categories:   {len(settings['categories'])}")
            if await ask_yes_no("\nWrite this configuration to settings.json?", True):
                write_settings(settings)
            else:
                print("Aborted — nothing written.")
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
        finally:
            await self.close()


def main():
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN not found. Set it in your .env file first.")
        sys.exit(1)

    print("Marketing Command Centre Bot — interactive config setup")
    print("This writes src/config/settings.json. It does not modify .env.\n")

    client = SetupClient()
    try:
        client.run(token, log_handler=None)
    except discord.LoginFailure:
        print("❌ Login failed — check that DISCORD_TOKEN is valid.")
        sys.exit(1)


if __name__ == "__main__":
    main()
