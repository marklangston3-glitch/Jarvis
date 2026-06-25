#!/usr/bin/env python3
"""Post welcome/rules/access messages into the Soup Kitchen Discord channels."""

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

MESSAGES = {
    "rules": """👑 WELCOME TO THE SOUP KITCHEN

Here we feed traders daily. Clean levels. Precise executions. No noise.

📋 THE RULES

1. Respect everyone — no exceptions
2. No unsolicited calls, signals, or DMs
3. No spam, self-promotion, or affiliate links
4. Keep conversations in the right channels
5. No sharing paid content outside this server
6. Listen more than you talk — especially as a new member
7. Bad trades happen. No blame culture here.

These rules exist to protect the quality of the kitchen.
Break them and you're out. Simple.

— The Soup Kitchen 🍜""",
    "how-to-get-access": """🔒 WANT THE FULL MENU?

Free members get the appetizer.
Paid members get the full course.

WHAT YOU UNLOCK WITH PAID ACCESS:
• 📡 #live-calls — real time trade alerts
• 🌊 #options-flow — unusual options activity
• 📊 #trade-recaps — full breakdown of every call
• 📖 #playbook — our complete trading framework
• 🎥 #recordings — past sessions and education
• ❓ #q-and-a — direct access to ask questions

HOW TO GET ACCESS:
1. Click the link below to join as a paid member
2. Complete payment
3. Your Paid Member role will be assigned automatically
4. Locked channels unlock instantly

[PAYMENT LINK COMING SOON]

Good trades feed everyone. 🍜👑""",
    "announcements": """👑 THE SOUP KITCHEN IS NOW OPEN

Welcome to the most disciplined trading community you'll find.

We don't guess. We don't chase. We plan, execute, and repeat.

Whether you're here for the free levels or you're ready for the full menu — you're in the right place.

Invite your people. The kitchen is open.

— The Soup Kitchen 🍜""",
}


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


def main():
    channels = request("GET", f"/guilds/{GUILD_ID}/channels")
    name_to_id = {c["name"]: c["id"] for c in channels if c["type"] == 0}

    for channel_name, content in MESSAGES.items():
        channel_id = name_to_id.get(channel_name)
        if not channel_id:
            print(f"Channel #{channel_name} not found, skipping")
            continue
        print(f"Posting to #{channel_name} ({channel_id})")
        request("POST", f"/channels/{channel_id}/messages", json={"content": content})

    print("\nDone! Messages posted.")


if __name__ == "__main__":
    main()
