#!/usr/bin/env python3
"""Jarvis — The Soup Kitchen Discord bot.

Features:
- Reaction-role verification (✅ in #rules → Free Member)
- Auto-assign Unverified role to new joiners
- Built-in commands when @mentioned
- AI-powered fallback responses via Claude API
"""

import os
import re

import anthropic
import discord

BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GUILD_ID = 1513190467796336830
RULES_CHANNEL_NAME = "rules"
VERIFY_EMOJI = "✅"
FREE_MEMBER_ROLE = "Free Member"
UNVERIFIED_ROLE = "Unverified"

WELCOME_DM = (
    "👑 Welcome to The Soup Kitchen. You've got access to the free channels. "
    "When you're ready for the full menu, check #how-to-get-access. "
    "Good trades feed everyone. 🍜"
)

SYSTEM_PROMPT = """You are Jarvis, the official bot for The Soup Kitchen trading Discord server.

Personality: confident, concise, disciplined — like a head chef running a clean kitchen. Use trading
language naturally. Keep responses short (1-3 sentences max). Use 🍜 or 👑 sparingly.

Server context:
- Free members get: #general-chat, #market-talk, #memes, #daily-levels, #watchlist, #charting
- Paid members unlock: #live-calls, #options-flow, #trade-recaps, #playbook, #recordings, #q-and-a
- To upgrade: check #how-to-get-access
- Rules are in #rules
- Post wins in #wins, journal trades in #trade-journal

Never give financial advice. If asked for a specific trade, say the kitchen serves levels and
frameworks, not financial advice. Direct them to the appropriate channel instead.

IMPORTANT: Users have roles. If a user has the Admin, Moderator, or Paid Member role, they already
have access to all paid channels — DO NOT tell them to upgrade or check #how-to-get-access. Treat
them as insiders. If an Admin asks you to do something, comply — they run the server. Only redirect
Free Member or Unverified users to #how-to-get-access."""

COMMANDS = {
    "help": (
        "👑 **Jarvis Commands**\n"
        "• `@Jarvis help` — show this menu\n"
        "• `@Jarvis rules` — server rules reminder\n"
        "• `@Jarvis access` — how to get paid access\n"
        "• `@Jarvis channels` — channel guide\n"
        "• `@Jarvis gm` — morning check-in\n\n"
        "Or just talk to me — I'm powered by AI. 🍜"
    ),
    "rules": (
        "📋 **Quick Rules Reminder**\n"
        "1. Respect everyone\n"
        "2. No unsolicited calls/signals/DMs\n"
        "3. No spam or self-promo\n"
        "4. Right conversations in the right channels\n"
        "5. No sharing paid content outside the server\n"
        "6. Listen more than you talk\n"
        "7. No blame culture\n\n"
        "Full rules in #rules. 🍜"
    ),
    "access": (
        "🔒 **Want the full menu?**\n"
        "Paid members unlock: live calls, options flow, trade recaps, "
        "the full playbook, recordings, and Q&A.\n\n"
        "Head to #how-to-get-access for details and the payment link. 👑"
    ),
    "channels": (
        "📊 **Channel Guide**\n"
        "**Free:**\n"
        "• #general-chat — community talk\n"
        "• #market-talk — market discussion\n"
        "• #daily-levels — key levels each day\n"
        "• #watchlist — what we're watching\n"
        "• #charting — chart breakdowns\n"
        "• #wins — post your W's\n"
        "• #trade-journal — log your trades\n\n"
        "**Paid (unlock in #how-to-get-access):**\n"
        "• #live-calls — real-time alerts\n"
        "• #options-flow — unusual activity\n"
        "• #trade-recaps — full breakdowns\n"
        "• #playbook — our framework\n"
        "• #recordings — past sessions\n"
        "• #q-and-a — ask questions 🍜"
    ),
    "gm": "☀️ GM! Markets are open, the kitchen is hot. Let's eat. 🍜👑",
}

intents = discord.Intents.default()
intents.members = True
intents.reactions = True
intents.message_content = True

client = discord.Client(intents=intents)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

verification_message_id = None


async def find_verification_message(guild):
    for channel in guild.text_channels:
        if channel.name == RULES_CHANNEL_NAME:
            async for message in channel.history(limit=50):
                if message.author == client.user:
                    for reaction in message.reactions:
                        if str(reaction.emoji) == VERIFY_EMOJI:
                            return message.id
    return None


async def get_ai_response(user_message, username, role_names=None):
    if claude_client is None:
        return "🍜 AI responses aren't configured yet. Try `@Jarvis help` for available commands."
    role_context = ""
    if role_names:
        role_context = f" (roles: {', '.join(role_names)})"
    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"{username}{role_context} says: {user_message}"}
            ],
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude API error: {e}")
        return "Kitchen's busy right now, try again in a sec. 🍜"


@client.event
async def on_ready():
    global verification_message_id
    print(f"Logged in as {client.user} (id: {client.user.id})")
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print(f"Guild {GUILD_ID} not found")
        return
    verification_message_id = await find_verification_message(guild)
    print(f"Watching verification message id: {verification_message_id}")
    print(f"AI responses: {'enabled' if claude_client else 'disabled (no ANTHROPIC_API_KEY)'}")


@client.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return
    role = discord.utils.get(member.guild.roles, name=UNVERIFIED_ROLE)
    if role:
        await member.add_roles(role)
        print(f"Assigned {UNVERIFIED_ROLE} role to {member}")


@client.event
async def on_raw_reaction_add(payload):
    if payload.guild_id != GUILD_ID:
        return
    if verification_message_id is None or payload.message_id != verification_message_id:
        return
    if str(payload.emoji) != VERIFY_EMOJI:
        return
    if payload.member is None or payload.member.bot:
        return

    guild = client.get_guild(GUILD_ID)
    role = discord.utils.get(guild.roles, name=FREE_MEMBER_ROLE)
    if role is None:
        print(f"Role '{FREE_MEMBER_ROLE}' not found")
        return

    await payload.member.add_roles(role)
    print(f"Assigned {FREE_MEMBER_ROLE} role to {payload.member}")

    try:
        await payload.member.send(WELCOME_DM)
        print(f"Sent welcome DM to {payload.member}")
    except discord.Forbidden:
        print(f"Could not DM {payload.member} (DMs closed)")


@client.event
async def on_message(message):
    if message.author.bot:
        return
    if message.guild is None or message.guild.id != GUILD_ID:
        return
    if client.user not in message.mentions:
        return

    content = re.sub(r"<@!?\d+>", "", message.content).strip().lower()

    for cmd, response in COMMANDS.items():
        if content == cmd:
            await message.reply(response, mention_author=False)
            return

    role_names = [r.name for r in message.author.roles if r.name != "@everyone"]
    async with message.channel.typing():
        ai_reply = await get_ai_response(content, message.author.display_name, role_names)
    await message.reply(ai_reply, mention_author=False)


if __name__ == "__main__":
    client.run(BOT_TOKEN)
