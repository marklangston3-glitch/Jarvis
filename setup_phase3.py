#!/usr/bin/env python3
"""Phase 3 Setup — Jarvis Hub, Moose Market Milad, and Long-Term Plays channels.

Run once: python setup_phase3.py
Requires DISCORD_BOT_TOKEN env var.
"""

import asyncio
import os

import discord

BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = 1513190467796336830

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print(f"Guild {GUILD_ID} not found")
        await client.close()
        return

    print(f"Connected to {guild.name}")
    existing = {c.name: c for c in guild.channels}

    # ─── JARVIS HUB CATEGORY ───
    jarvis_cat = None
    for c in guild.categories:
        if c.name.lower() == "jarvis hub":
            jarvis_cat = c
            break
    if jarvis_cat is None:
        jarvis_cat = await guild.create_category("🤖 Jarvis Hub")
        print(f"Created category: Jarvis Hub")

    jarvis_channels = {
        "jarvis-alerts": "🚨 Breaking financial news & red folder alerts from Jarvis",
        "jarvis-market-data": "📊 Market data outputs — price, technicals, options, levels, movers",
        "jarvis-calendar": "📅 Economic calendar, daily market prep, earnings data",
    }
    for name, topic in jarvis_channels.items():
        if name not in existing:
            await guild.create_text_channel(name, category=jarvis_cat, topic=topic)
            print(f"Created #{name}")
        else:
            print(f"#{name} already exists")

    # ─── MOOSE MARKET MILAD CATEGORY ───
    moose_cat = None
    for c in guild.categories:
        if "moose" in c.name.lower():
            moose_cat = c
            break
    if moose_cat is None:
        moose_cat = await guild.create_category("🫎 Moose Market Milad")
        print(f"Created category: Moose Market Milad")

    moose_channels = {
        "moose-stage": "🎤 Main stage — Milad's market commentary & calls",
        "moose-trade-talk": "💬 Talk through trades live with the community",
        "moose-analysis": "📈 Breakdowns, analysis, and deep dives",
    }
    for name, topic in moose_channels.items():
        if name not in existing:
            await guild.create_text_channel(name, category=moose_cat, topic=topic)
            print(f"Created #{name}")
        else:
            print(f"#{name} already exists")

    # ─── LONG-TERM PLAYS (PAID) ───
    paid_cat = None
    for c in guild.categories:
        if "paid" in c.name.lower() or "premium" in c.name.lower() or "vip" in c.name.lower():
            paid_cat = c
            break

    if "long-term-plays" not in existing:
        paid_role = discord.utils.get(guild.roles, name="Paid Member")
        admin_role = discord.utils.get(guild.roles, name="Admin")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if paid_role:
            overwrites[paid_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        await guild.create_text_channel(
            "long-term-plays",
            category=paid_cat,
            topic="💎 Long-term investment plays — Paid members only",
            overwrites=overwrites,
        )
        print("Created #long-term-plays (paid only)")
    else:
        print("#long-term-plays already exists")

    print("\n✅ Phase 3 setup complete!")
    print("New structure:")
    print("  🤖 Jarvis Hub: #jarvis-alerts, #jarvis-market-data, #jarvis-calendar")
    print("  🫎 Moose Market Milad: #moose-stage, #moose-trade-talk, #moose-analysis")
    print("  💎 Paid: #long-term-plays")
    await client.close()


client.run(BOT_TOKEN)
