#!/usr/bin/env python3
"""Tasks 1-4: slowmode + new channels with starter messages, via Discord REST API."""

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

FAQ_MESSAGE = """❓ FREQUENTLY ASKED QUESTIONS

Q: Is this server free?
A: Yes. Free members get access to daily levels, watchlist, charting, and community channels.

Q: What do I get with paid access?
A: Live trade calls, options flow, trade recaps, full playbook, recordings, and Q&A access. See #how-to-get-access for details.

Q: How do I get the Paid Member role?
A: Complete payment via the link in #how-to-get-access. Your role is assigned automatically.

Q: Can I share content from the paid channels?
A: No. Sharing paid content outside this server is an immediate ban.

Q: How do I get help?
A: Post in #general-chat or DM a Moderator.

🍜 Good trades feed everyone."""

WINS_MESSAGE = """🏆 DROP YOUR WINS HERE

Made a clean trade? Nailed a level? Post it here.

Screenshot your PnL. Share your setups. Celebrate your consistency.

This is the proof that the kitchen works. 🍜👑"""

JOURNAL_MESSAGE = """📒 TRADE JOURNAL

Log your trades here daily. Entry, exit, reason, result.

The best traders in the world journal every trade. This is where you build that habit.

Format:
📈 Ticker:
⏰ Entry:
🚪 Exit:
📊 Result:
💭 Notes:

Consistency compounds. 🍜"""


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
    name_to_channel = {c["name"]: c for c in channels}

    general_chat = name_to_channel["general-chat"]
    print("Setting 30s slowmode on #general-chat")
    request("PATCH", f"/channels/{general_chat['id']}", json={"rate_limit_per_user": 30})

    start_here_id = name_to_channel["📋 START HERE"]["id"]
    free_lounge_id = name_to_channel["💬 FREE LOUNGE"]["id"]

    print("Creating #faq in 📋 START HERE")
    faq = request(
        "POST",
        f"/guilds/{GUILD_ID}/channels",
        json={"name": "faq", "type": 0, "parent_id": start_here_id},
    )
    request("POST", f"/channels/{faq['id']}/messages", json={"content": FAQ_MESSAGE})

    print("Creating #wins in 💬 FREE LOUNGE")
    wins = request(
        "POST",
        f"/guilds/{GUILD_ID}/channels",
        json={"name": "wins", "type": 0, "parent_id": free_lounge_id},
    )
    request("POST", f"/channels/{wins['id']}/messages", json={"content": WINS_MESSAGE})

    print("Creating #trade-journal in 💬 FREE LOUNGE")
    journal = request(
        "POST",
        f"/guilds/{GUILD_ID}/channels",
        json={"name": "trade-journal", "type": 0, "parent_id": free_lounge_id},
    )
    request("POST", f"/channels/{journal['id']}/messages", json={"content": JOURNAL_MESSAGE})

    rules = name_to_channel["rules"]
    print("Posting verification message in #rules")
    verify_msg = request(
        "POST",
        f"/channels/{rules['id']}/messages",
        json={"content": "✅ React to this message with ✅ to verify and unlock the free channels!"},
    )
    print("Adding ✅ reaction to verification message")
    request(
        "PUT",
        f"/channels/{rules['id']}/messages/{verify_msg['id']}/reactions/%E2%9C%85/@me",
    )

    print(f"\n--- Summary ---")
    print(f"#faq channel id: {faq['id']}")
    print(f"#wins channel id: {wins['id']}")
    print(f"#trade-journal channel id: {journal['id']}")
    print(f"#rules channel id: {rules['id']}")
    print(f"Verification message id: {verify_msg['id']}")
    print("\nDone with tasks 1-4 and verification message setup.")


if __name__ == "__main__":
    main()
