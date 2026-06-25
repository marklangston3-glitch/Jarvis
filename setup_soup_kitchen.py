#!/usr/bin/env python3
"""Scaffold the Soup Kitchen trading Discord server via the Discord REST API."""

import os
import time

import requests

BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = "1513190467796336830"

API_BASE = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json",
}

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
READ_MESSAGE_HISTORY = 1 << 16

OVERWRITE_ROLE = 0

ROLE_NAMES = ["Unverified", "Free Member", "Paid Member", "Moderator", "Admin"]

STRUCTURE = [
    ("📋 START HERE", ["rules", "announcements", "how-to-get-access"], None),
    ("💬 FREE LOUNGE", ["general-chat", "market-talk", "memes"], None),
    ("📊 FREE ANALYSIS", ["daily-levels", "watchlist", "charting"], None),
    ("🔒 PAID ALERTS", ["live-calls", "options-flow", "trade-recaps"], "paid"),
    ("🔒 PAID EDUCATION", ["playbook", "recordings", "q-and-a"], "paid"),
    ("🛠️ ADMIN", ["mod-chat", "bot-logs"], "admin"),
]


def request(method, path, **kwargs):
    url = f"{API_BASE}{path}"
    while True:
        resp = requests.request(method, url, headers=HEADERS, **kwargs)
        if resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 1)
            print(f"  rate limited, sleeping {retry_after}s")
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        time.sleep(0.5)
        if resp.text:
            return resp.json()
        return None


def create_role(name):
    print(f"Creating role: {name}")
    return request("POST", f"/guilds/{GUILD_ID}/roles", json={"name": name})


def create_category(name, overwrites):
    print(f"Creating category: {name}")
    return request(
        "POST",
        f"/guilds/{GUILD_ID}/channels",
        json={"name": name, "type": 4, "permission_overwrites": overwrites},
    )


def create_text_channel(name, parent_id, overwrites):
    print(f"  Creating channel: {name}")
    return request(
        "POST",
        f"/guilds/{GUILD_ID}/channels",
        json={"name": name, "type": 0, "parent_id": parent_id, "permission_overwrites": overwrites},
    )


def deny_view(role_id):
    return {"id": role_id, "type": OVERWRITE_ROLE, "allow": "0", "deny": str(VIEW_CHANNEL)}


def allow_view(role_id):
    allow = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY
    return {"id": role_id, "type": OVERWRITE_ROLE, "allow": str(allow), "deny": "0"}


def main():
    role_ids = {}
    for name in ROLE_NAMES:
        role = create_role(name)
        role_ids[name] = role["id"]

    everyone_id = GUILD_ID

    for category_name, channel_names, lock in STRUCTURE:
        if lock == "paid":
            overwrites = [
                deny_view(everyone_id),
                deny_view(role_ids["Unverified"]),
                deny_view(role_ids["Free Member"]),
                allow_view(role_ids["Paid Member"]),
                allow_view(role_ids["Moderator"]),
                allow_view(role_ids["Admin"]),
            ]
        elif lock == "admin":
            overwrites = [
                deny_view(everyone_id),
                deny_view(role_ids["Unverified"]),
                deny_view(role_ids["Free Member"]),
                deny_view(role_ids["Paid Member"]),
                allow_view(role_ids["Moderator"]),
                allow_view(role_ids["Admin"]),
            ]
        else:
            overwrites = []

        category = create_category(category_name, overwrites)
        category_id = category["id"]

        for channel_name in channel_names:
            create_text_channel(channel_name, category_id, overwrites)

    print("\nDone! Soup Kitchen server scaffolded.")


if __name__ == "__main__":
    main()
