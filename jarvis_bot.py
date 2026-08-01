#!/usr/bin/env python3
"""Jarvis — The Soup Kitchen Discord bot.

Features:
- Reaction-role verification (✅ in #rules → Free Member)
- Auto-assign Unverified role to new joiners
- Built-in commands + market data when @mentioned
- AI-powered fallback responses via Claude API
- Free market data: prices, options, technicals, news, earnings, crypto, fear/greed
"""

import asyncio
import os
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import anthropic
import discord
from discord.ext import tasks
import requests as http_requests
import yfinance as yf

ET = ZoneInfo("America/New_York")

BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GUILD_ID = 1513190467796336830
RULES_CHANNEL_NAME = "rules"
DAILY_CHANNEL_NAME = "watchlist"
WELCOME_CHANNEL_NAME = "welcome"
VERIFY_EMOJI = "✅"
FREE_MEMBER_ROLE = "Free Member"
UNVERIFIED_ROLE = "Unverified"

# ─── JARVIS HUB SUB-CHANNELS ───
JARVIS_ALERTS_CHANNEL = "jarvis-alerts"
JARVIS_DATA_CHANNEL = "jarvis-market-data"
JARVIS_CALENDAR_CHANNEL = "jarvis-calendar"

# ─── COMMAND → SUB-CHANNEL ROUTING ───
COMMAND_ROUTING = {
    "price": JARVIS_DATA_CHANNEL,
    "technicals": JARVIS_DATA_CHANNEL,
    "ta": JARVIS_DATA_CHANNEL,
    "options": JARVIS_DATA_CHANNEL,
    "flow": JARVIS_DATA_CHANNEL,
    "levels": JARVIS_DATA_CHANNEL,
    "info": JARVIS_DATA_CHANNEL,
    "movers": JARVIS_DATA_CHANNEL,
    "sectors": JARVIS_DATA_CHANNEL,
    "market": JARVIS_DATA_CHANNEL,
    "crypto": JARVIS_DATA_CHANNEL,
    "coin": JARVIS_DATA_CHANNEL,
    "fear": JARVIS_DATA_CHANNEL,
    "greed": JARVIS_DATA_CHANNEL,
    "earnings": JARVIS_CALENDAR_CHANNEL,
    "news": JARVIS_ALERTS_CHANNEL,
    "calendar": JARVIS_CALENDAR_CHANNEL,
    "econ": JARVIS_CALENDAR_CHANNEL,
    "prep": JARVIS_CALENDAR_CHANNEL,
}

# ─── NEWS SCANNER ───
NEWS_RSS_FEEDS = {
    "Forex Factory": "https://www.forexfactory.com/rss",
    "WSJ Markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "WSJ World": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "Reuters Business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
}
seen_news_ids = set()

WELCOME_DM = (
    "👑 Welcome to The Soup Kitchen. You've got access to the free channels. "
    "When you're ready for the full menu, check #how-to-get-access. "
    "Good trades feed everyone. 🍜"
)

SYSTEM_PROMPT = """You are Jarvis, the official AI for The Soup Kitchen trading Discord server.

Personality: confident, sharp, a little witty — like a head chef who reads Bloomberg and lifts.
You answer EVERYTHING. Market questions, life questions, sports takes, gym advice, food recs,
random trivia — nothing is off the menu. Keep answers concise (3-5 sentences max unless depth
is needed). Use 🍜 or 👑 sparingly. Never be robotic or dismissive — if someone asks something,
engage with a real answer and a bit of personality.

MARKET QUESTIONS — go deep:
- For questions about events (FOMC dates, CPI, earnings, options expiry, economic calendar),
  give the actual date/time/expectation if you know it.
- For "what will X do" questions, give a data-driven take — reference key levels, trend,
  sentiment, catalysts. Frame it as analysis, not a trade call.
- For stock/crypto/macro questions, reason through it like a disciplined trader would:
  technicals, fundamentals, macro context, risk.
- Remind users for live data to use: @Jarvis price, @Jarvis technicals, @Jarvis earnings, etc.

GENERAL QUESTIONS — answer them genuinely:
- Sports takes: give a real opinion, back it with reasoning.
- Gym/fitness: give solid, practical advice based on the goal.
- Food/diet: give a direct rec, not a disclaimer.
- Life questions, random trivia, debates: engage, have a take, be useful.
- If you truly don't know something (recent news after your knowledge cutoff), say so honestly
  and suggest where to look.

Never give specific financial advice ("buy this now"). Frame market views as analysis.

Server context:
- Free members: #general-chat, #market-talk, #memes, #daily-levels, #watchlist, #charting
- Jarvis Hub: #jarvis-alerts (news), #jarvis-market-data (data), #jarvis-calendar (prep/calendar)
- Moose Market Milad: #moose-stage, #moose-trade-talk, #moose-analysis
- Paid: #live-calls, #options-flow, #trade-recaps, #playbook, #recordings, #q-and-a, #long-term-plays
- Upgrade: #how-to-get-access | Rules: #rules | Wins: #wins | Journal: #trade-journal

IMPORTANT: Admins/Paid Members already have full access — never redirect them to #how-to-get-access.
Only redirect Free Members or Unverified users there.

LEADERBOARD & CROWN SYSTEM — YOU OWN THIS:
- You run the weekly PnL leaderboard and crown two winners every Friday at 5:00 PM ET.
- 👑 Top Trader = highest net PnL for the week. 🔥 Most Consistent = most green days logged.
- Members log trades with /pnl. Use /scoreboard to see the live standings anytime.
- Admins/co-founders can trigger the crown early with "@Jarvis crown now".
- When anyone asks about their leaderboard position or standing, tell them to use /scoreboard
  or offer to check — do NOT say you don't have access. You have full access to this data.
- Never say crowning or scoreboard resets are "above your pay grade" or need manual admin action."""

HELP_TEXT = (
    "👑 **Jarvis Commands**\n\n"
    "**📊 Market Data** → routed to #jarvis-market-data:\n"
    "• `@Jarvis price SPY` — live quote + daily change\n"
    "• `@Jarvis technicals SPY` — RSI, MACD, SMAs, VWAP\n"
    "• `@Jarvis options SPY` — options chain snapshot\n"
    "• `@Jarvis options movers` — top 10 most active contracts market-wide\n"
    "• `@Jarvis levels SPY` — key support/resistance levels\n"
    "• `@Jarvis info AAPL` — company overview\n"
    "• `@Jarvis movers` — top gainers & losers today\n"
    "• `@Jarvis sectors` — sector performance\n"
    "• `@Jarvis crypto BTC` — crypto price\n"
    "• `@Jarvis fear` — Fear & Greed Index\n"
    "• `@Jarvis market` — market overview (SPY, QQQ, VIX)\n\n"
    "**📅 Calendar & Prep** → routed to #jarvis-calendar:\n"
    "• `@Jarvis earnings AAPL` — next earnings + recent EPS\n"
    "• `@Jarvis calendar` — today's US economic events\n"
    "• `@Jarvis prep` — full morning market prep\n\n"
    "**🚨 News & Alerts** → routed to #jarvis-alerts:\n"
    "• `@Jarvis news AAPL` — latest headlines\n"
    "• Breaking news auto-scanned from WSJ, Reuters, Forex Factory\n\n"
    "**🛠️ Server:**\n"
    "• `@Jarvis rules` — server rules\n"
    "• `@Jarvis access` — how to get paid access\n"
    "• `@Jarvis channels` — channel guide\n"
    "• `@Jarvis gm` — morning check-in\n"
    "• `@Jarvis disclaimer` — financial disclaimer\n\n"
    "Prompt me from **any channel** — I'll route outputs to the right place. 🍜"
)

STATIC_COMMANDS = {
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
        "📊 **Channel Guide**\n\n"
        "**🤖 Jarvis Hub:**\n"
        "• #jarvis-alerts — breaking news & red folder alerts\n"
        "• #jarvis-market-data — price, technicals, options, levels\n"
        "• #jarvis-calendar — economic calendar, market prep, earnings\n\n"
        "**🫎 Moose Market Milad:**\n"
        "• #moose-stage — main stage\n"
        "• #moose-trade-talk — talk through trades live\n"
        "• #moose-analysis — breakdowns & analysis\n\n"
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
        "• #q-and-a — ask questions\n"
        "• #long-term-plays — long-term investment plays 🍜"
    ),
    "gm": "☀️ GM! Markets are open, the kitchen is hot. Let's eat. 🍜👑",
    "disclaimer": (
        "⚠️ **DISCLAIMER — The Soup Kitchen**\n\n"
        "Nothing in this server constitutes financial advice. All market data, trade ideas, "
        "levels, alerts, and commentary shared here — by members, moderators, or Jarvis — "
        "are for **educational and informational purposes only**.\n\n"
        "• We are **not** licensed financial advisors.\n"
        "• Past performance does **not** guarantee future results.\n"
        "• You are solely responsible for your own trading decisions.\n"
        "• Always do your own research (DYOR) before entering any trade.\n"
        "• Never risk more than you can afford to lose.\n\n"
        "By participating in this server, you acknowledge that you trade **at your own risk**. "
        "The Soup Kitchen and its staff are not liable for any financial losses.\n\n"
        "Trade smart. Manage risk. The kitchen feeds those who feed themselves. 🍜"
    ),
}

intents = discord.Intents.default()
intents.members = True
intents.reactions = True
intents.message_content = True

client = discord.Client(intents=intents)
claude_client      = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
claude_async_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

verification_message_id = None


def fmt(val, prefix="$", decimals=2):
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if abs(val) >= 1_000_000_000:
            return f"{prefix}{val / 1_000_000_000:.1f}B"
        if abs(val) >= 1_000_000:
            return f"{prefix}{val / 1_000_000:.1f}M"
        return f"{prefix}{val:,.{decimals}f}"
    return str(val)


def pct(val):
    if val is None:
        return "N/A"
    arrow = "🟢" if val >= 0 else "🔴"
    return f"{arrow} {val:+.2f}%"


# ─── MARKET DATA COMMANDS ───


def cmd_price(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
        if price is None:
            return f"❌ Couldn't find price data for **{ticker.upper()}**."
        change = price - prev if prev else 0
        change_pct = (change / prev * 100) if prev else 0
        high = info.get("regularMarketDayHigh") or info.get("dayHigh")
        low = info.get("regularMarketDayLow") or info.get("dayLow")
        vol = info.get("regularMarketVolume") or info.get("volume")
        avg_vol = info.get("averageDailyVolume10Day") or info.get("averageVolume")
        mkt_cap = info.get("marketCap")
        name = info.get("shortName", ticker.upper())

        lines = [
            f"📈 **{name}** ({ticker.upper()})",
            f"**Price:** {fmt(price)} ({pct(change_pct)})",
            f"**Change:** {fmt(change)} today",
            f"**Range:** {fmt(low)} — {fmt(high)}",
            f"**Volume:** {fmt(vol, prefix='', decimals=0)}",
        ]
        if avg_vol:
            vol_ratio = vol / avg_vol if vol and avg_vol else 0
            lines.append(f"**Avg Volume:** {fmt(avg_vol, prefix='', decimals=0)} ({vol_ratio:.1f}x)")
        if mkt_cap:
            lines.append(f"**Mkt Cap:** {fmt(mkt_cap)}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching price for **{ticker.upper()}**: {e}"


def cmd_technicals(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="3mo", interval="1d")
        if hist.empty:
            return f"❌ No data for **{ticker.upper()}**."

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]
        last = close.iloc[-1]

        sma_20 = close.rolling(20).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
        ema_9 = close.ewm(span=9).mean().iloc[-1]
        ema_21 = close.ewm(span=21).mean().iloc[-1]

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))

        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        macd_line = (ema_12 - ema_26).iloc[-1]
        signal_line = (ema_12 - ema_26).ewm(span=9).mean().iloc[-1]
        macd_hist = macd_line - signal_line

        tp = (high + low + close) / 3
        vwap = (tp * volume).rolling(20).sum() / volume.rolling(20).sum()
        vwap_val = vwap.iloc[-1]

        bb_mid = sma_20
        bb_std = close.rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std

        atr_tr = []
        for i in range(1, len(hist)):
            tr = max(
                high.iloc[i] - low.iloc[i],
                abs(high.iloc[i] - close.iloc[i - 1]),
                abs(low.iloc[i] - close.iloc[i - 1]),
            )
            atr_tr.append(tr)
        atr = sum(atr_tr[-14:]) / 14

        rsi_emoji = "🟢" if rsi < 30 else "🔴" if rsi > 70 else "🟡"
        macd_emoji = "🟢" if macd_hist > 0 else "🔴"
        trend = "🟢 BULLISH" if ema_9 > ema_21 and last > sma_50 else "🔴 BEARISH" if ema_9 < ema_21 and last < sma_50 else "🟡 NEUTRAL"

        return (
            f"📊 **{ticker.upper()} Technical Analysis**\n"
            f"**Trend:** {trend}\n"
            f"**Price:** {fmt(last)}\n\n"
            f"**Moving Averages:**\n"
            f"• EMA 9: {fmt(ema_9)} {'(above)' if last > ema_9 else '(below)'}\n"
            f"• EMA 21: {fmt(ema_21)} {'(above)' if last > ema_21 else '(below)'}\n"
            f"• SMA 20: {fmt(sma_20)} {'(above)' if last > sma_20 else '(below)'}\n"
            f"• SMA 50: {fmt(sma_50)} {'(above)' if last > sma_50 else '(below)'}\n\n"
            f"**Indicators:**\n"
            f"• RSI(14): {rsi_emoji} {rsi:.1f}\n"
            f"• MACD: {macd_emoji} {macd_line:.3f} (Signal: {signal_line:.3f})\n"
            f"• VWAP(20): {fmt(vwap_val)}\n"
            f"• ATR(14): {fmt(atr)}\n\n"
            f"**Bollinger Bands:**\n"
            f"• Upper: {fmt(bb_upper)}\n"
            f"• Mid: {fmt(bb_mid)}\n"
            f"• Lower: {fmt(bb_lower)}"
        )
    except Exception as e:
        return f"❌ Error computing technicals for **{ticker.upper()}**: {e}"


def cmd_options(ticker):
    try:
        t = yf.Ticker(ticker)
        dates = t.options
        if not dates:
            return f"❌ No options data for **{ticker.upper()}**."

        nearest = dates[0]
        chain = t.option_chain(nearest)
        calls = chain.calls
        puts = chain.puts
        info = t.info
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)

        total_call_vol = int(calls["volume"].sum()) if "volume" in calls.columns else 0
        total_put_vol = int(puts["volume"].sum()) if "volume" in puts.columns else 0
        total_call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
        total_put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0
        pc_ratio = total_put_vol / total_call_vol if total_call_vol > 0 else 0

        top_calls = calls.nlargest(5, "volume")[["strike", "lastPrice", "volume", "openInterest", "impliedVolatility"]] if "volume" in calls.columns else calls.head(0)
        top_puts = puts.nlargest(5, "volume")[["strike", "lastPrice", "volume", "openInterest", "impliedVolatility"]] if "volume" in puts.columns else puts.head(0)

        lines = [
            f"📋 **{ticker.upper()} Options** (exp: {nearest})",
            f"**Spot:** {fmt(price)}",
            f"**P/C Ratio:** {pc_ratio:.2f}",
            f"**Call Vol / OI:** {total_call_vol:,} / {total_call_oi:,}",
            f"**Put Vol / OI:** {total_put_vol:,} / {total_put_oi:,}",
            "",
            "**🟢 Top Calls by Volume:**",
        ]
        for _, r in top_calls.iterrows():
            iv = r.get("impliedVolatility", 0) or 0
            lines.append(f"• ${r['strike']:.0f}C — Vol: {int(r.get('volume', 0) or 0):,} | OI: {int(r.get('openInterest', 0) or 0):,} | IV: {iv * 100:.0f}%")
        lines.append("")
        lines.append("**🔴 Top Puts by Volume:**")
        for _, r in top_puts.iterrows():
            iv = r.get("impliedVolatility", 0) or 0
            lines.append(f"• ${r['strike']:.0f}P — Vol: {int(r.get('volume', 0) or 0):,} | OI: {int(r.get('openInterest', 0) or 0):,} | IV: {iv * 100:.0f}%")

        if len(dates) > 1:
            lines.append(f"\n*{len(dates)} expirations available: {', '.join(dates[:5])}...*")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching options for **{ticker.upper()}**: {e}"


def cmd_levels(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d")
        if hist.empty:
            return f"❌ No data for **{ticker.upper()}**."

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        last = close.iloc[-1]

        day_high = high.iloc[-1]
        day_low = low.iloc[-1]
        prev_high = high.iloc[-2] if len(high) > 1 else day_high
        prev_low = low.iloc[-2] if len(low) > 1 else day_low
        prev_close = close.iloc[-2] if len(close) > 1 else last

        pp = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * pp - prev_low
        s1 = 2 * pp - prev_high
        r2 = pp + (prev_high - prev_low)
        s2 = pp - (prev_high - prev_low)
        r3 = prev_high + 2 * (pp - prev_low)
        s3 = prev_low - 2 * (prev_high - pp)

        sma_20 = close.rolling(20).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
        sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

        week_high = high.tail(5).max()
        week_low = low.tail(5).min()
        month_high = high.tail(21).max()
        month_low = low.tail(21).min()
        high_52w = high.max()
        low_52w = low.min()

        lines = [
            f"🎯 **{ticker.upper()} Key Levels**",
            f"**Last:** {fmt(last)}",
            "",
            "**Pivot Points (Daily):**",
            f"• R3: {fmt(r3)}",
            f"• R2: {fmt(r2)}",
            f"• R1: {fmt(r1)}",
            f"• **Pivot: {fmt(pp)}**",
            f"• S1: {fmt(s1)}",
            f"• S2: {fmt(s2)}",
            f"• S3: {fmt(s3)}",
            "",
            "**Moving Averages:**",
            f"• SMA 20: {fmt(sma_20)}",
            f"• SMA 50: {fmt(sma_50)}",
        ]
        if sma_200:
            lines.append(f"• SMA 200: {fmt(sma_200)}")
        lines += [
            "",
            "**Range:**",
            f"• Today: {fmt(day_low)} — {fmt(day_high)}",
            f"• Week: {fmt(week_low)} — {fmt(week_high)}",
            f"• Month: {fmt(month_low)} — {fmt(month_high)}",
            f"• 52-Week: {fmt(low_52w)} — {fmt(high_52w)}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error computing levels for **{ticker.upper()}**: {e}"


def cmd_earnings(ticker):
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        info = t.info
        name = info.get("shortName", ticker.upper())

        lines = [f"📅 **{name} ({ticker.upper()}) Earnings**"]

        if cal is not None and not (hasattr(cal, 'empty') and cal.empty):
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    if isinstance(ed, list):
                        lines.append(f"**Next Earnings:** {ed[0].strftime('%b %d, %Y') if hasattr(ed[0], 'strftime') else ed[0]}")
                    else:
                        lines.append(f"**Next Earnings:** {ed}")
                est = cal.get("Earnings Average")
                if est:
                    lines.append(f"**EPS Estimate:** {fmt(est)}")
                rev = cal.get("Revenue Average")
                if rev:
                    lines.append(f"**Rev Estimate:** {fmt(rev)}")

        eps_trail = info.get("trailingEps")
        eps_fwd = info.get("forwardEps")
        pe = info.get("trailingPE")
        fwd_pe = info.get("forwardPE")

        if eps_trail:
            lines.append(f"**Trailing EPS:** {fmt(eps_trail)}")
        if eps_fwd:
            lines.append(f"**Forward EPS:** {fmt(eps_fwd)}")
        if pe:
            lines.append(f"**P/E (trailing):** {pe:.1f}")
        if fwd_pe:
            lines.append(f"**P/E (forward):** {fwd_pe:.1f}")

        earnings_hist = t.earnings_dates
        if earnings_hist is not None and not earnings_hist.empty:
            recent = earnings_hist.head(4)
            lines.append("\n**Recent Earnings:**")
            for date, row in recent.iterrows():
                est = row.get("EPS Estimate")
                act = row.get("Reported EPS")
                surprise = row.get("Surprise(%)")
                date_str = date.strftime("%b %d, %Y") if hasattr(date, "strftime") else str(date)
                beat = ""
                if surprise is not None and not (isinstance(surprise, float) and surprise != surprise):
                    beat = f" {'✅' if surprise >= 0 else '❌'} {surprise:+.1f}%"
                est_str = f"{est:.2f}" if est is not None and not (isinstance(est, float) and est != est) else "N/A"
                act_str = f"{act:.2f}" if act is not None and not (isinstance(act, float) and act != act) else "N/A"
                lines.append(f"• {date_str}: Est {est_str} → Act {act_str}{beat}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching earnings for **{ticker.upper()}**: {e}"


def cmd_news(ticker):
    try:
        t = yf.Ticker(ticker)
        news = t.news
        if not news:
            return f"❌ No recent news for **{ticker.upper()}**."
        lines = [f"📰 **{ticker.upper()} Latest News**\n"]
        for item in news[:7]:
            content = item.get("content", item)
            title = content.get("title", "Untitled")
            link = content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else content.get("canonicalUrl", content.get("link", ""))
            provider = content.get("provider", {})
            publisher = provider.get("displayName", "") if isinstance(provider, dict) else content.get("publisher", "")
            pub_date = content.get("pubDate", "")
            time_str = ""
            if pub_date and isinstance(pub_date, str):
                try:
                    dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    time_str = f" ({dt.astimezone(ET).strftime('%b %d, %I:%M %p')})"
                except Exception:
                    pass
            elif isinstance(pub_date, (int, float)):
                dt = datetime.fromtimestamp(pub_date)
                time_str = f" ({dt.strftime('%b %d, %I:%M %p')})"
            lines.append(f"• **{title}**\n  {publisher}{time_str}\n  {link}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching news for **{ticker.upper()}**: {e}"


def cmd_info(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        name = info.get("shortName", ticker.upper())
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        mkt_cap = info.get("marketCap")
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        pe = info.get("trailingPE")
        fwd_pe = info.get("forwardPE")
        div_yield = info.get("dividendYield")
        beta = info.get("beta")
        avg_vol = info.get("averageVolume")
        high_52 = info.get("fiftyTwoWeekHigh")
        low_52 = info.get("fiftyTwoWeekLow")
        summary = info.get("longBusinessSummary", "")
        if len(summary) > 300:
            summary = summary[:300] + "..."

        lines = [
            f"🏢 **{name}** ({ticker.upper()})",
            f"**Sector:** {sector} | **Industry:** {industry}",
            f"**Price:** {fmt(price)} | **Mkt Cap:** {fmt(mkt_cap)}",
        ]
        if pe:
            lines.append(f"**P/E:** {pe:.1f} | **Fwd P/E:** {fwd_pe:.1f}" if fwd_pe else f"**P/E:** {pe:.1f}")
        if beta:
            lines.append(f"**Beta:** {beta:.2f}")
        if div_yield:
            lines.append(f"**Div Yield:** {div_yield * 100:.2f}%")
        if avg_vol:
            lines.append(f"**Avg Volume:** {fmt(avg_vol, prefix='', decimals=0)}")
        if high_52 and low_52:
            lines.append(f"**52-Week Range:** {fmt(low_52)} — {fmt(high_52)}")
        if summary:
            lines.append(f"\n*{summary}*")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching info for **{ticker.upper()}**: {e}"


def cmd_crypto(symbol):
    try:
        coin_map = {
            "btc": "bitcoin", "eth": "ethereum", "sol": "solana", "doge": "dogecoin",
            "xrp": "ripple", "ada": "cardano", "avax": "avalanche-2", "matic": "polygon",
            "dot": "polkadot", "link": "chainlink", "shib": "shiba-inu", "ltc": "litecoin",
            "uni": "uniswap", "atom": "cosmos", "near": "near", "bnb": "binancecoin",
            "arb": "arbitrum", "op": "optimism", "apt": "aptos", "sui": "sui",
            "pepe": "pepe", "wif": "dogwifcoin",
        }
        coin_id = coin_map.get(symbol.lower(), symbol.lower())
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        resp = http_requests.get(url, params={"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"}, timeout=10)
        if resp.status_code != 200:
            return f"❌ Couldn't find crypto **{symbol.upper()}**. Try the full name (e.g., bitcoin)."
        data = resp.json()
        md = data.get("market_data", {})
        price = md.get("current_price", {}).get("usd")
        change_24h = md.get("price_change_percentage_24h")
        change_7d = md.get("price_change_percentage_7d")
        change_30d = md.get("price_change_percentage_30d")
        mkt_cap = md.get("market_cap", {}).get("usd")
        vol = md.get("total_volume", {}).get("usd")
        high_24h = md.get("high_24h", {}).get("usd")
        low_24h = md.get("low_24h", {}).get("usd")
        ath = md.get("ath", {}).get("usd")
        ath_pct = md.get("ath_change_percentage", {}).get("usd")
        rank = data.get("market_cap_rank")
        name = data.get("name", symbol.upper())

        lines = [
            f"🪙 **{name}** ({symbol.upper()}) — Rank #{rank}",
            f"**Price:** {fmt(price)}",
            f"**24h:** {pct(change_24h)} | **7d:** {pct(change_7d)} | **30d:** {pct(change_30d)}",
            f"**24h Range:** {fmt(low_24h)} — {fmt(high_24h)}",
            f"**Volume (24h):** {fmt(vol)}",
            f"**Mkt Cap:** {fmt(mkt_cap)}",
            f"**ATH:** {fmt(ath)} ({ath_pct:+.1f}% from ATH)" if ath and ath_pct else "",
        ]
        return "\n".join(l for l in lines if l)
    except Exception as e:
        return f"❌ Error fetching crypto for **{symbol.upper()}**: {e}"


def cmd_fear():
    try:
        resp = http_requests.get("https://api.alternative.me/fng/?limit=1&format=json", timeout=10)
        data = resp.json()["data"][0]
        value = int(data["value"])
        label = data["value_classification"]
        if value <= 25:
            emoji = "😱"
        elif value <= 45:
            emoji = "😰"
        elif value <= 55:
            emoji = "😐"
        elif value <= 75:
            emoji = "😊"
        else:
            emoji = "🤑"

        bar = "█" * (value // 5) + "░" * (20 - value // 5)
        return (
            f"🌡️ **Fear & Greed Index**\n\n"
            f"{emoji} **{value}/100 — {label}**\n"
            f"`[{bar}]`\n\n"
            f"0 = Extreme Fear | 100 = Extreme Greed"
        )
    except Exception as e:
        return f"❌ Error fetching Fear & Greed Index: {e}"


def cmd_options_movers():
    try:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "SPY", "QQQ",
                    "NFLX", "COIN", "SOFI", "PLTR", "NIO", "RIVN", "MARA", "SQ", "ROKU",
                    "SNAP", "UBER", "CRWD", "NET", "DKNG", "RBLX", "HOOD", "UPST",
                    "IWM", "DIA", "BABA", "BAC", "F", "T", "INTC", "PYPL", "DIS"]
        all_contracts = []
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                dates = t.options
                if not dates:
                    continue
                chain = t.option_chain(dates[0])
                for _, r in chain.calls.iterrows():
                    vol = r.get("volume", 0) or 0
                    if vol > 0:
                        iv = r.get("impliedVolatility", 0) or 0
                        oi = r.get("openInterest", 0) or 0
                        all_contracts.append((ticker, f"${r['strike']:.0f}C", dates[0], int(vol), int(oi), iv, r.get("lastPrice", 0)))
                for _, r in chain.puts.iterrows():
                    vol = r.get("volume", 0) or 0
                    if vol > 0:
                        iv = r.get("impliedVolatility", 0) or 0
                        oi = r.get("openInterest", 0) or 0
                        all_contracts.append((ticker, f"${r['strike']:.0f}P", dates[0], int(vol), int(oi), iv, r.get("lastPrice", 0)))
            except Exception:
                continue

        all_contracts.sort(key=lambda x: x[3], reverse=True)
        top = all_contracts[:10]

        if not top:
            return "❌ Couldn't fetch options flow data right now."

        lines = ["🔥 **Top 10 Most Active Options Contracts**\n"]
        for i, (ticker, strike, exp, vol, oi, iv, price) in enumerate(top, 1):
            lines.append(
                f"**{i}.** **{ticker}** {strike} (exp {exp})\n"
                f"   Vol: {vol:,} | OI: {oi:,} | IV: {iv * 100:.0f}% | Last: {fmt(price)}"
            )
        lines.append("\n*Scanned nearest expiration across 35+ tickers*")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching options movers: {e}"


def cmd_movers():
    try:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "SPY", "QQQ",
                    "NFLX", "BABA", "COIN", "SOFI", "PLTR", "NIO", "RIVN", "MARA", "SQ", "ROKU",
                    "SNAP", "UBER", "ABNB", "CRWD", "SNOW", "NET", "DKNG", "RBLX", "HOOD", "UPST"]
        data = yf.download(tickers, period="2d", group_by="ticker", progress=False)

        results = []
        for t in tickers:
            try:
                closes = data[t]["Close"].dropna()
                if len(closes) >= 2:
                    prev = closes.iloc[-2]
                    curr = closes.iloc[-1]
                    pct_change = (curr - prev) / prev * 100
                    results.append((t, curr, pct_change))
            except Exception:
                continue

        results.sort(key=lambda x: x[2], reverse=True)
        gainers = results[:5]
        losers = results[-5:][::-1]

        lines = ["📈 **Top Movers Today**\n", "**🟢 Gainers:**"]
        for t, p, c in gainers:
            lines.append(f"• **{t}** — {fmt(p)} ({pct(c)})")
        lines.append("\n**🔴 Losers:**")
        for t, p, c in losers:
            lines.append(f"• **{t}** — {fmt(p)} ({pct(c)})")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching movers: {e}"


def cmd_sectors():
    try:
        sector_etfs = {
            "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
            "Energy": "XLE", "Consumer Disc.": "XLY", "Industrials": "XLI",
            "Consumer Staples": "XLP", "Utilities": "XLU", "Real Estate": "XLRE",
            "Materials": "XLB", "Comm. Services": "XLC",
        }
        tickers = list(sector_etfs.values())
        data = yf.download(tickers, period="2d", group_by="ticker", progress=False)

        results = []
        for name, etf in sector_etfs.items():
            try:
                closes = data[etf]["Close"].dropna()
                if len(closes) >= 2:
                    prev = closes.iloc[-2]
                    curr = closes.iloc[-1]
                    pct_change = (curr - prev) / prev * 100
                    results.append((name, etf, curr, pct_change))
            except Exception:
                continue

        results.sort(key=lambda x: x[3], reverse=True)
        lines = ["🏭 **Sector Performance Today**\n"]
        for name, etf, price, change in results:
            emoji = "🟢" if change >= 0 else "🔴"
            lines.append(f"{emoji} **{name}** ({etf}) — {fmt(price)} ({change:+.2f}%)")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching sectors: {e}"


def cmd_market():
    try:
        tickers = ["SPY", "QQQ", "DIA", "IWM", "VIX"]
        names = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones", "IWM": "Russell 2000", "VIX": "VIX"}
        # VIX is ^VIX in yfinance
        yf_tickers = ["SPY", "QQQ", "DIA", "IWM", "^VIX"]
        data = yf.download(yf_tickers, period="2d", group_by="ticker", progress=False)

        lines = ["🌍 **Market Overview**\n"]
        for t, yt in zip(tickers, yf_tickers):
            try:
                closes = data[yt]["Close"].dropna()
                if len(closes) >= 2:
                    prev = closes.iloc[-2]
                    curr = closes.iloc[-1]
                    change = (curr - prev) / prev * 100
                    lines.append(f"• **{names[t]}** ({t}): {fmt(curr)} ({pct(change)})")
            except Exception:
                continue
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching market overview: {e}"


# ─── ECONOMIC CALENDAR ───


def fetch_economic_calendar():
    try:
        today = datetime.now(ET).strftime("%Y-%m-%d")
        url = f"https://api.tradingeconomics.com/calendar/country/United%20States/{today}/{today}"
        resp = http_requests.get(url, params={"c": "guest:guest", "f": "json"}, timeout=15)
        if resp.status_code != 200:
            return None
        events = resp.json()
        if not events:
            return None
        important = []
        for ev in events:
            name = ev.get("Event", "").replace("United States ", "")
            te_time = ev.get("Date", "")
            actual = ev.get("Actual", "")
            forecast = ev.get("Forecast", "")
            previous = ev.get("Previous", "")
            importance = ev.get("Importance", 0)
            if importance and importance >= 2:
                time_str = ""
                if te_time:
                    try:
                        dt = datetime.fromisoformat(te_time.replace("Z", "+00:00"))
                        time_str = dt.astimezone(ET).strftime("%I:%M %p")
                    except Exception:
                        pass
                actual_str = str(actual) if actual not in (None, "", "None") else "—"
                forecast_str = str(forecast) if forecast not in (None, "", "None") else "—"
                prev_str = str(previous) if previous not in (None, "", "None") else "—"
                important.append((time_str, name, actual_str, forecast_str, prev_str))
        return important
    except Exception:
        return None


def cmd_calendar():
    events = fetch_economic_calendar()
    if not events:
        return "📅 No major US economic events scheduled for today."
    lines = [f"📅 **US Economic Calendar — {datetime.now(ET).strftime('%b %d, %Y')}**\n"]
    for t, name, actual, forecast, prev in events:
        time_part = f"**{t}** — " if t else ""
        result = ""
        if actual != "—":
            result = f" → **{actual}**"
            if forecast != "—":
                try:
                    a = float(actual.replace("%", "").replace("K", "").replace("M", "").replace("B", ""))
                    f = float(forecast.replace("%", "").replace("K", "").replace("M", "").replace("B", ""))
                    result += " ✅" if a >= f else " ❌"
                except Exception:
                    pass
        lines.append(
            f"• {time_part}**{name}**\n"
            f"  Forecast: {forecast} | Previous: {prev}{result}"
        )
    return "\n".join(lines)


# ─── DAILY MARKET PREP ───

HIGH_IMPACT_KEYWORDS = ["cpi", "ppi", "gdp", "payroll", "fomc", "federal reserve", "rate decision", "nonfarm", "unemployment"]


def build_market_prep():
    """Returns a list of up to 3 Discord messages forming the complete morning brief."""
    now = datetime.now(ET)
    date_str = now.strftime("%A, %b %d, %Y")

    scan_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
                    "NFLX", "COIN", "SOFI", "PLTR", "NIO", "RIVN", "MARA", "SQ",
                    "SNAP", "UBER", "CRWD", "NET", "DKNG", "RBLX", "HOOD", "UPST",
                    "BABA", "BAC", "F", "INTC", "PYPL", "DIS"]
    index_tickers = ["SPY", "QQQ", "DIA", "IWM"]

    # ── Batch: get reliable previous closes from history (avoids stale .info fields) ──
    prev_closes = {}
    try:
        all_tickers = index_tickers + scan_tickers
        batch = yf.download(all_tickers, period="5d", interval="1d", group_by="ticker", progress=False, auto_adjust=True)
        for t in all_tickers:
            try:
                closes = batch[t]["Close"].dropna()
                if len(closes) > 0:
                    prev_closes[t] = float(closes.iloc[-1])
            except Exception:
                pass
    except Exception:
        pass

    # ── Collect: indices ──────────────────────────────────────────────────────
    index_rows = []  # (name, ticker, price, pre_price, pre_change, reg_change)
    for ticker, name in [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow Jones"), ("IWM", "Russell 2000")]:
        try:
            info = yf.Ticker(ticker).info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            pre = info.get("preMarketPrice")
            prev = prev_closes.get(ticker) or info.get("regularMarketPreviousClose") or info.get("previousClose")
            pre_change = None
            reg_change = (price - prev) / prev * 100 if price and prev else None
            if pre and prev and price:
                c = (pre - prev) / prev * 100
                if abs(c) <= 25 and 0.5 <= pre / price <= 2.0:
                    pre_change = c
            index_rows.append((name, ticker, price, pre, pre_change, reg_change))
        except Exception:
            index_rows.append((name, ticker, None, None, None, None))

    # ── Collect: VIX ─────────────────────────────────────────────────────────
    vix_price = None
    try:
        vix_info = yf.Ticker("^VIX").info
        vix_price = vix_info.get("regularMarketPrice") or vix_info.get("previousClose")
    except Exception:
        pass

    # ── Collect: Fear & Greed ─────────────────────────────────────────────────
    fg_value, fg_label = None, None
    try:
        fg_resp = http_requests.get("https://api.alternative.me/fng/?limit=1&format=json", timeout=8)
        fg_data = fg_resp.json()["data"][0]
        fg_value = int(fg_data["value"])
        fg_label = fg_data["value_classification"]
    except Exception:
        pass

    # ── Collect: pre-market movers ────────────────────────────────────────────
    pre_results = []
    for ticker in scan_tickers:
        try:
            info = yf.Ticker(ticker).info
            pre = info.get("preMarketPrice")
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            # Use batch-downloaded close for reliable prev; fall back to .info
            prev = prev_closes.get(ticker) or info.get("regularMarketPreviousClose") or info.get("previousClose")
            if pre and prev and prev > 0 and price:
                c = (pre - prev) / prev * 100
                if abs(c) <= 25 and 0.5 <= pre / price <= 2.0:
                    pre_results.append((ticker, pre, c))
        except Exception:
            continue
    pre_results.sort(key=lambda x: x[2], reverse=True)
    gainers = [r for r in pre_results if r[2] > 0.5][:3]
    losers = [r for r in pre_results if r[2] < -0.5][-3:][::-1]

    # ── Collect: economic calendar ────────────────────────────────────────────
    events = fetch_economic_calendar() or []

    # ── Collect: earnings today ───────────────────────────────────────────────
    today = now.date()
    earnings_today = []
    for ticker in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
                   "NFLX", "BAC", "JPM", "GS", "COIN", "PLTR", "CRWD", "NET", "SNOW"]:
        try:
            cal = yf.Ticker(ticker).calendar
            if cal and isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed and isinstance(ed, list) and len(ed) > 0:
                    ed_date = ed[0].date() if hasattr(ed[0], "date") else None
                    if ed_date == today:
                        est = cal.get("Earnings Average")
                        est_str = f" (Est: {fmt(est)} EPS)" if est else ""
                        earnings_today.append(f"{ticker}{est_str}")
        except Exception:
            continue

    # ── Collect: SPY pivot levels ─────────────────────────────────────────────
    spy_levels = {}
    try:
        hist = yf.Ticker("SPY").history(period="5d", interval="1d")
        if not hist.empty and len(hist) >= 2:
            ph, pl, pc = hist["High"].iloc[-2], hist["Low"].iloc[-2], hist["Close"].iloc[-2]
            pp = (ph + pl + pc) / 3
            spy_levels = {"pivot": pp, "r1": 2*pp - pl, "r2": pp + (ph - pl), "s1": 2*pp - ph, "s2": pp - (ph - pl)}
    except Exception:
        pass

    # ── Determine tone ────────────────────────────────────────────────────────
    spy_change = next((pre_c if pre_c is not None else reg_c for _, t, _, _, pre_c, reg_c in index_rows if t == "SPY"), None)
    high_impact_today = [e for e in events if any(kw in e[1].lower() for kw in HIGH_IMPACT_KEYWORDS)]

    if vix_price and spy_change is not None:
        if spy_change > 0.5 and vix_price < 18:
            tone = "🟢 **Bullish open** — futures up, VIX calm. Look for early continuation or buy dips after 9:45 AM."
        elif spy_change < -0.5 and vix_price > 20:
            tone = "🔴 **Risk-off morning** — futures red, VIX elevated. Reduce size, protect capital, watch key support."
        elif vix_price > 25:
            tone = "⚠️ **High vol regime** — VIX > 25. Wider stops, smaller size. Expect whipsaws in both directions."
        elif abs(spy_change) < 0.2:
            tone = "🟡 **Coiled open** — tight pre-market. Wait for the first 15-min range before taking sides."
        else:
            direction = "higher" if spy_change > 0 else "lower"
            tone = f"🟡 **Modest {direction} open** — confirm direction at the bell before committing full size."
    elif vix_price and vix_price > 25:
        tone = "⚠️ **High vol regime** — VIX > 25. Size down across the board."
    else:
        tone = "🟡 **Await open** — watch the first 15-min candle for directional bias."

    if high_impact_today:
        ev = high_impact_today[0]
        tone += f"\n🚨 **{ev[1]}** at {ev[0]} — major catalyst, expect a volatility spike around this release."

    # ── Message 1: Overview + Tone ────────────────────────────────────────────
    m1 = [f"☀️ **Good Morning, Kitchen — {date_str}**\n"]
    m1.append("**🌍 Futures / Index Check:**")
    for name, ticker, price, pre_price, pre_change, reg_change in index_rows:
        if pre_change is not None and pre_price:
            m1.append(f"• **{name}** ({ticker}): Pre-mkt {fmt(pre_price)} ({pct(pre_change)})")
        elif price is not None and reg_change is not None:
            m1.append(f"• **{name}** ({ticker}): {fmt(price)} ({pct(reg_change)})")
    if vix_price:
        vix_emoji = "🟢" if vix_price < 18 else "🟡" if vix_price < 25 else "🔴"
        vix_label = "Low vol — clear skies" if vix_price < 18 else "Caution zone" if vix_price < 25 else "HIGH VOL — size down"
        m1.append(f"• **VIX**: {vix_emoji} {vix_price:.2f} *({vix_label})*")

    if fg_value is not None:
        fg_emoji = "😱" if fg_value <= 25 else "😰" if fg_value <= 45 else "😐" if fg_value <= 55 else "😊" if fg_value <= 75 else "🤑"
        m1.append(f"\n**🌡️ Market Sentiment:** {fg_emoji} Fear & Greed **{fg_value}/100** — *{fg_label}*")

    m1.append(f"\n**🎯 Tone for Today:**\n{tone}")

    # ── Message 2: Catalysts ──────────────────────────────────────────────────
    m2 = ["**📈 Pre-Market Movers:**"]
    if gainers:
        m2.append("🟢 Gainers:")
        for t, p, c in gainers:
            m2.append(f"  • **{t}** — {fmt(p)} ({pct(c)})")
    if losers:
        m2.append("🔴 Losers:")
        for t, p, c in losers:
            m2.append(f"  • **{t}** — {fmt(p)} ({pct(c)})")
    if not gainers and not losers:
        m2.append("  *Flat pre-market — no major movers yet.*")

    m2.append("\n**📅 Key Events Today:**")
    if events:
        for ev_time, ev_name, actual, forecast, prev in events[:6]:
            time_part = f"**{ev_time}** — " if ev_time else ""
            flag = " 🚨" if any(kw in ev_name.lower() for kw in HIGH_IMPACT_KEYWORDS) else ""
            m2.append(f"  • {time_part}**{ev_name}**{flag}  (Exp: {forecast} | Prev: {prev})")
    else:
        m2.append("  *No major economic releases scheduled today.*")

    if earnings_today:
        m2.append("\n**📣 Earnings Today:**")
        for e in earnings_today:
            m2.append(f"  • {e}")

    # ── Message 3: Levels + What to Watch ────────────────────────────────────
    m3 = []
    if spy_levels:
        m3.append("**🎯 SPY Daily Pivot Levels:**")
        m3.append(f"  R2: **{fmt(spy_levels['r2'])}**  |  R1: **{fmt(spy_levels['r1'])}**")
        m3.append(f"  ⚡ Pivot: **{fmt(spy_levels['pivot'])}**")
        m3.append(f"  S1: **{fmt(spy_levels['s1'])}**  |  S2: **{fmt(spy_levels['s2'])}**")
        m3.append("")

    m3.append("**🔑 What to Watch:**")
    if spy_levels:
        m3.append(f"• SPY above pivot **{fmt(spy_levels['pivot'])}** = bulls in control; break below = shift defensive")
    if vix_price:
        if vix_price < 18:
            m3.append("• VIX calm — trending/momentum strategies favored; don't overthink entries")
        elif vix_price < 25:
            m3.append("• VIX elevated — wait for confirmation before entries; don't chase opens")
        else:
            m3.append("• VIX spiking — breakouts fail more; mean-reversion setups in play; keep stops wide")
    if gainers:
        top = gainers[0]
        m3.append(f"• **{top[0]}** leading pre-mkt at {pct(top[2])} — check for news/catalyst before fading or chasing")
    if losers:
        bot = losers[0]
        m3.append(f"• **{bot[0]}** off {pct(bot[2])} pre-mkt — gap fill potential; watch prior day support")
    if high_impact_today:
        ev = high_impact_today[0]
        m3.append(f"• Avoid new positions into **{ev[1]}** ({ev[0]}) — wait for the number, then react")
    if earnings_today:
        tickers_str = ", ".join(earnings_today[:3])
        m3.append(f"• Earnings in play today: **{tickers_str}** — size accordingly into close")
    if not gainers and not losers and not high_impact_today and not earnings_today:
        m3.append("• No major catalysts flagged — standard session, trade your levels and manage size")

    m3.append("\n*Prep your levels. Manage your risk. Let's eat.* 🍜👑")

    return ["\n".join(m1), "\n".join(m2), "\n".join(m3)]


# ─── NEWS SCANNER ───


def fetch_breaking_news():
    import xml.etree.ElementTree as ElementTree
    new_articles = []
    for source, url in NEWS_RSS_FEEDS.items():
        try:
            resp = http_requests.get(url, timeout=10, headers={"User-Agent": "JarvisBot/1.0"})
            if resp.status_code != 200:
                continue
            root = ElementTree.fromstring(resp.content)
            for item in root.iter("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                if title_el is None:
                    continue
                title = title_el.text or ""
                link = link_el.text if link_el is not None else ""
                pub_date = pub_el.text if pub_el is not None else ""
                news_id = f"{source}:{title[:80]}"
                if news_id in seen_news_ids:
                    continue
                seen_news_ids.add(news_id)
                is_market_moving = any(kw in title.lower() for kw in [
                    "breaking", "urgent", "fed ", "federal reserve", "rate", "inflation",
                    "cpi", "ppi", "gdp", "jobs", "payroll", "unemployment", "tariff",
                    "crash", "surge", "plunge", "halt", "war", "sanction", "default",
                    "recession", "rally", "sell-off", "selloff", "billion", "trillion",
                    "sec ", "regulation", "bank", "oil", "opec", "treasury", "bond",
                    "earnings", "guidance", "downgrade", "upgrade", "ipo", "merger",
                    "acquisition", "layoff", "bankruptcy", "stimulus", "debt ceiling",
                ])
                if is_market_moving:
                    new_articles.append((source, title, link, pub_date))
        except Exception:
            continue
    if len(seen_news_ids) > 500:
        oldest = list(seen_news_ids)[:200]
        for k in oldest:
            seen_news_ids.discard(k)
    return new_articles


# ─── SCHEDULED TASKS ───


@tasks.loop(time=time(hour=9, minute=0, tzinfo=ET))
async def daily_market_prep():
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        return
    channel = discord.utils.get(guild.text_channels, name=JARVIS_CALENDAR_CHANNEL)
    if channel is None:
        channel = discord.utils.get(guild.text_channels, name=DAILY_CHANNEL_NAME)
    if channel is None:
        print(f"Channel #{JARVIS_CALENDAR_CHANNEL} not found for daily prep")
        return
    try:
        messages = await asyncio.to_thread(build_market_prep)
        for msg in messages:
            if len(msg) > 2000:
                msg = msg[:1997] + "..."
            await channel.send(msg)
            await asyncio.sleep(0.5)
        print(f"Posted daily market prep ({len(messages)} messages) to #{channel.name}")
    except Exception as e:
        print(f"Failed to post daily prep: {e}")


@daily_market_prep.before_loop
async def before_daily_prep():
    await client.wait_until_ready()


@tasks.loop(minutes=5)
async def news_scanner():
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        return
    channel = discord.utils.get(guild.text_channels, name=JARVIS_ALERTS_CHANNEL)
    if channel is None:
        print(f"Channel #{JARVIS_ALERTS_CHANNEL} not found for news alerts")
        return
    try:
        articles = await asyncio.to_thread(fetch_breaking_news)
        for source, title, link, pub_date in articles:
            alert = (
                f"🚨 **BREAKING — {source}**\n"
                f"**{title}**\n"
            )
            if link:
                alert += f"{link}\n"
            if len(alert) > 2000:
                alert = alert[:1997] + "..."
            await channel.send(alert)
            await asyncio.sleep(1)
        if articles:
            print(f"Posted {len(articles)} breaking news alerts to #{JARVIS_ALERTS_CHANNEL}")
    except Exception as e:
        print(f"News scanner error: {e}")


@news_scanner.before_loop
async def before_news_scanner():
    await client.wait_until_ready()
    await asyncio.to_thread(fetch_breaking_news)


# ─── BOT EVENTS ───


async def find_verification_message(guild):
    for channel in guild.text_channels:
        if channel.name == RULES_CHANNEL_NAME:
            async for message in channel.history(limit=50):
                if message.author == client.user:
                    for reaction in message.reactions:
                        if str(reaction.emoji) == VERIFY_EMOJI:
                            return message.id
    return None


async def _alert_bot_logs(detail: str):
    """Post an alert to #bot-logs tagging @Admin when Anthropic auth/credit/rate issues occur."""
    try:
        guild = client.get_guild(GUILD_ID)
        if not guild:
            return
        ch = discord.utils.get(guild.text_channels, name="bot-logs")
        if not ch:
            return
        admin_role = discord.utils.get(guild.roles, name="Admin")
        mention = admin_role.mention if admin_role else "@Admin"
        await ch.send(
            f"⚠️ {mention} **Jarvis AI error** — members are seeing the fallback response.\n"
            f"```{detail[:1800]}```"
        )
    except Exception:
        pass  # never let the alerter itself crash the bot


async def get_ai_response(user_message, username, role_names=None):
    if claude_async_client is None:
        return "🍜 AI responses aren't configured yet. Try `@Jarvis help` for available commands."
    role_context = f" (roles: {', '.join(role_names)})" if role_names else ""
    try:
        response = await claude_async_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"{username}{role_context} says: {user_message}"}
            ],
        )
        return response.content[0].text
    except Exception as e:
        import traceback as _tb
        full_tb = _tb.format_exc()
        err_str  = str(e)
        err_type = type(e).__name__

        # Classify the error for a clear log line
        if hasattr(e, "status_code"):
            sc = e.status_code
            if sc == 401:
                label = "AUTH ERROR (401) — ANTHROPIC_API_KEY is invalid or missing"
            elif sc == 429:
                label = "RATE LIMIT (429) — too many requests or plan limit hit"
            elif sc == 400 and ("credit" in err_str.lower() or "billing" in err_str.lower()):
                label = "OUT OF CREDITS (400) — Anthropic account needs top-up"
            elif sc == 400:
                label = f"BAD REQUEST (400) — {err_str[:200]}"
            elif sc == 529:
                label = "ANTHROPIC OVERLOADED (529) — retry later"
            else:
                label = f"HTTP {sc} — {err_str[:200]}"
        else:
            label = f"{err_type} — {err_str[:200]}"

        print(f"[AI ERROR] {label}\n{full_tb}")

        # Alert #bot-logs for auth/credit/rate issues so admins know immediately
        needs_admin_alert = (
            hasattr(e, "status_code") and e.status_code in (401, 429, 400)
            or "credit" in err_str.lower()
            or "billing" in err_str.lower()
            or "invalid" in err_str.lower()
        )
        if needs_admin_alert:
            await _alert_bot_logs(f"{label}\n\nFull error:\n{err_str}")

        return "Kitchen's busy right now, try again in a sec. 🍜"


MARKET_COMMANDS = {
    "price": lambda args: cmd_price(args) if args else "Usage: `@Jarvis price SPY`",
    "technicals": lambda args: cmd_technicals(args) if args else "Usage: `@Jarvis technicals SPY`",
    "ta": lambda args: cmd_technicals(args) if args else "Usage: `@Jarvis ta SPY`",
    "options": lambda args: cmd_options_movers() if args and args.lower() == "movers" else cmd_options(args) if args else "Usage: `@Jarvis options SPY` or `@Jarvis options movers`",
    "flow": lambda args: cmd_options_movers() if args and args.lower() == "movers" else cmd_options(args) if args else "Usage: `@Jarvis flow SPY` or `@Jarvis flow movers`",
    "levels": lambda args: cmd_levels(args) if args else "Usage: `@Jarvis levels SPY`",
    "earnings": lambda args: cmd_earnings(args) if args else "Usage: `@Jarvis earnings AAPL`",
    "news": lambda args: cmd_news(args) if args else "Usage: `@Jarvis news AAPL`",
    "info": lambda args: cmd_info(args) if args else "Usage: `@Jarvis info AAPL`",
    "crypto": lambda args: cmd_crypto(args) if args else "Usage: `@Jarvis crypto BTC`",
    "coin": lambda args: cmd_crypto(args) if args else "Usage: `@Jarvis coin BTC`",
    "fear": lambda _: cmd_fear(),
    "greed": lambda _: cmd_fear(),
    "movers": lambda _: cmd_movers(),
    "sectors": lambda _: cmd_sectors(),
    "market": lambda _: cmd_market(),
    "calendar": lambda _: cmd_calendar(),
    "econ": lambda _: cmd_calendar(),
    "prep": lambda _: build_market_prep(),
}


async def auto_create_channels(guild):
    existing = {c.name for c in guild.channels}

    # Jarvis Hub category + sub-channels
    jarvis_cat = None
    for c in guild.categories:
        if "jarvis" in c.name.lower():
            jarvis_cat = c
            break
    if jarvis_cat is None:
        jarvis_cat = await guild.create_category("🤖 Jarvis Hub")
        print("Created category: Jarvis Hub")

    jarvis_channels = {
        JARVIS_ALERTS_CHANNEL: "🚨 Breaking financial news & red folder alerts from Jarvis",
        JARVIS_DATA_CHANNEL: "📊 Market data outputs — price, technicals, options, levels, movers",
        JARVIS_CALENDAR_CHANNEL: "📅 Economic calendar, daily market prep, earnings data",
    }
    for name, topic in jarvis_channels.items():
        if name not in existing:
            await guild.create_text_channel(name, category=jarvis_cat, topic=topic)
            print(f"Created #{name}")

    # Moose Market Milad category + channels
    moose_cat = None
    for c in guild.categories:
        if "moose" in c.name.lower():
            moose_cat = c
            break
    if moose_cat is None:
        moose_cat = await guild.create_category("🫎 Moose Market Milad")
        print("Created category: Moose Market Milad")

    if "moose-stage" not in existing:
        await guild.create_voice_channel("moose-stage", category=moose_cat)
        print("Created 🎤 #moose-stage (voice)")

    moose_text_channels = {
        "moose-trade-talk": "💬 Talk through trades live with the community",
        "moose-analysis": "📈 Breakdowns, analysis, and deep dives",
    }
    for name, topic in moose_text_channels.items():
        if name not in existing:
            await guild.create_text_channel(name, category=moose_cat, topic=topic)
            print(f"Created #{name}")

    # Long-term plays (paid only)
    if "long-term-plays" not in existing:
        paid_cat = None
        for c in guild.categories:
            if "paid" in c.name.lower() or "premium" in c.name.lower() or "vip" in c.name.lower():
                paid_cat = c
                break
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
            "long-term-plays", category=paid_cat,
            topic="💎 Long-term investment plays — Paid members only",
            overwrites=overwrites,
        )
        print("Created #long-term-plays (paid only)")


@client.event
async def on_ready():
    global verification_message_id
    print(f"Logged in as {client.user} (id: {client.user.id})")
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print(f"Guild {GUILD_ID} not found")
        return
    try:
        await auto_create_channels(guild)
        print("Channel auto-creation complete")
    except Exception as e:
        print(f"Channel auto-creation error (may need Manage Channels permission): {e}")
    verification_message_id = await find_verification_message(guild)
    print(f"Watching verification message id: {verification_message_id}")
    print(f"AI responses: {'enabled' if claude_client else 'disabled (no ANTHROPIC_API_KEY)'}")
    if not daily_market_prep.is_running():
        daily_market_prep.start()
        print("Started daily 9:00 AM ET market prep task")
    if not news_scanner.is_running():
        news_scanner.start()
        print("Started breaking news scanner (every 5 min)")


@client.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return
    role = discord.utils.get(member.guild.roles, name=UNVERIFIED_ROLE)
    if role:
        await member.add_roles(role)
        print(f"Assigned {UNVERIFIED_ROLE} role to {member}")

    welcome_ch = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if welcome_ch:
        await welcome_ch.send(
            f"👑 Welcome to The Soup Kitchen, {member.mention}! "
            f"Head over to <#rules> and react with ✅ to unlock the free channels. "
            f"Good trades feed everyone. 🍜"
        )


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

    content = re.sub(r"<@!?\d+>", "", message.content).strip()
    content_lower = content.lower()

    if content_lower == "help":
        await message.reply(HELP_TEXT, mention_author=False)
        return

    # ── Test content slot: @Jarvis testpost [slot_name] ──────────────────────────
    if content_lower.startswith("testpost"):
        parts_tp = content.split(None, 1)
        slot_arg = parts_tp[1].strip().lower() if len(parts_tp) > 1 else ""
        slot_names = [s["name"] for s in _SLOTS]
        match = next((s for s in _SLOTS if s["name"] == slot_arg), None)
        if not match:
            listing = "\n".join(f"• `{s['name']}`  →  #{s['target']}" for s in _SLOTS)
            await message.reply(
                f"**Usage:** `@Jarvis testpost <slot_name>`\n\n**Available slots:**\n{listing}",
                mention_author=False,
            )
            return
        await message.reply(f"⏳ Generating test post for `{match['name']}`…", mention_author=False)
        await _fire_slot(match)
        return
    # ─────────────────────────────────────────────────────────────────────────────

    for cmd, response in STATIC_COMMANDS.items():
        if content_lower == cmd:
            await message.reply(response, mention_author=False)
            return

    parts = content_lower.split(None, 1)
    cmd_name = parts[0] if parts else ""
    cmd_args = re.sub(r"[\[\](){}]", "", parts[1]).strip().upper() if len(parts) > 1 else ""

    if cmd_name in MARKET_COMMANDS:
        try:
            async with message.channel.typing():
                result = await asyncio.to_thread(MARKET_COMMANDS[cmd_name], cmd_args)
            # build_market_prep returns a list; all other commands return a string
            msgs = result if isinstance(result, list) else [result]
            msgs = [m[:1997] + "..." if len(m) > 2000 else m for m in msgs]

            target_channel_name = COMMAND_ROUTING.get(cmd_name)
            target_channel = None
            if target_channel_name and message.channel.name != target_channel_name:
                target_channel = discord.utils.get(message.guild.text_channels, name=target_channel_name)

            if target_channel:
                for i, msg in enumerate(msgs):
                    prefix = f"*Requested by {message.author.mention} in #{message.channel.name}*\n\n" if i == 0 else ""
                    await target_channel.send(prefix + msg)
                    if len(msgs) > 1:
                        await asyncio.sleep(0.5)
                await message.reply(f"✅ Output posted to {target_channel.mention}", mention_author=False)
            else:
                for i, msg in enumerate(msgs):
                    if i == 0:
                        await message.reply(msg, mention_author=False)
                    else:
                        await message.channel.send(msg)
                    if len(msgs) > 1:
                        await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Command error: {e}")
            await message.reply(f"❌ Something went wrong running that command.", mention_author=False)
        return

    # ── Admin crown-now command ───────────────────────────────────────────────
    _CROWN_NOW_RE = re.compile(
        r"\bcrown\b.{0,30}\b(now|winner|it|week|reset|scoreboard)\b"
        r"|\b(reset|run|close|end)\b.{0,30}\b(leaderboard|scoreboard|week|pnl)\b",
        re.IGNORECASE,
    )
    _admin_roles = {"Admin", "Moderator"}
    _author_role_names = {r.name for r in message.author.roles}
    if (_author_role_names & _admin_roles or _is_cofounder(message.author)) \
            and _CROWN_NOW_RE.search(content):
        await message.reply("👑 Running the leaderboard and crowning this week's winners now…", mention_author=False)
        try:
            await _crown_top_trader()
            await message.reply("✅ Done — leaderboard posted, crowns assigned, tracker reset. 🍜", mention_author=False)
        except Exception as exc:
            import traceback as _tb
            await message.reply(f"❌ Crown job failed: `{exc}`", mention_author=False)
            print(f"[CROWN NOW] Error:\n{_tb.format_exc()}")
        return

    # ── Leaderboard question intercept — inject live PnL data ─────────────────
    _LB_RE = re.compile(
        r"\b(leaderboard|scoreboard|standing|rank|place|position|pnl|winning|winning this week|top trader|who.*winning|how.*doing)\b",
        re.IGNORECASE,
    )
    if _LB_RE.search(content):
        data    = _pnl_load()
        entries = data.get("entries", [])
        if entries:
            pnl_totals: dict = {}
            for e in entries:
                uid = e["user_id"]
                if uid not in pnl_totals:
                    pnl_totals[uid] = {"username": e["username"], "total": 0.0}
                pnl_totals[uid]["total"] += e["amount"]
            ranked = sorted(pnl_totals.values(), key=lambda x: x["total"], reverse=True)
            lb_lines = []
            for i, v in enumerate(ranked[:10]):
                s = "+" if v["total"] >= 0 else ""
                lb_lines.append(f"{i+1}. @{v['username']}  {s}${v['total']:,.0f}")
            lb_context = (
                f"CURRENT WEEK PNL LEADERBOARD (live data from pnl_tracker.json):\n"
                + "\n".join(lb_lines)
                + f"\nTotal traders this week: {len(ranked)}"
            )
            # Check if the asker is on the leaderboard
            asker_name = message.author.display_name
            asker_entry = next((v for v in ranked if v["username"] == asker_name), None)
            if asker_entry:
                asker_pos = ranked.index(asker_entry) + 1
                lb_context += f"\n{asker_name} is currently #{asker_pos} with {'+' if asker_entry['total'] >= 0 else ''}${asker_entry['total']:,.0f}"
        else:
            lb_context = "LEADERBOARD: No PnL entries logged this week yet. Members can log with /pnl."

        role_names = [r.name for r in message.author.roles if r.name != "@everyone"]
        async with message.channel.typing():
            ai_reply = await get_ai_response(
                f"{lb_context}\n\nMember question: {content}",
                message.author.display_name,
                role_names,
            )
        await message.reply(ai_reply, mention_author=False)
        return
    # ─────────────────────────────────────────────────────────────────────────

    # ── Founder poll intercept — BEFORE general AI reply ─────────────────────
    _POLL_INTENT_RE = re.compile(
        r"\b(make|create|post|run|start)\b.{0,40}\bpoll\b|\bpoll\b.{0,40}\b(make|create|post|run|start)\b",
        re.IGNORECASE,
    )
    if _is_cofounder(message.author) and _POLL_INTENT_RE.search(content):
        await _create_poll_from_request(message, content)
        return
    # ─────────────────────────────────────────────────────────────────────────

    role_names = [r.name for r in message.author.roles if r.name != "@everyone"]
    try:
        async with message.channel.typing():
            ai_reply = await get_ai_response(content, message.author.display_name, role_names)
        await message.reply(ai_reply, mention_author=False)
    except Exception as e:
        print(f"Reply error: {e}")



async def _create_poll_from_request(message: discord.Message, request_text: str):
    """
    Called when a founder asks Jarvis to make a poll.
    1. Calls Claude to extract question + options as JSON.
    2. Posts a native discord.Poll.
    3. Replies 'Poll's live 🍜' on success.
    4. On ANY exception, logs full traceback and posts the error in channel — never falls back to text.
    """
    import traceback as _tb, json as _json

    if not ANTHROPIC_API_KEY:
        await message.channel.send("❌ Poll generation unavailable — ANTHROPIC_API_KEY not set.")
        return

    async with message.channel.typing():
        try:
            import anthropic as _ant
            _ac = _ant.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            extraction_prompt = (
                "Extract a poll question and 2-4 short answer options from the following request. "
                "Return ONLY valid JSON, nothing else, in this exact shape:\n"
                "{\"question\":\"...\",\"options\":[\"...\",\"...\"]}\n\n"
                f"Request: {request_text}"
            )
            resp = await _ac.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": extraction_prompt}],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("```").strip()
            parsed = _json.loads(raw)
            question = parsed["question"]
            options  = parsed["options"]
            if not question or len(options) < 2:
                raise ValueError(f"Bad poll JSON: {parsed}")
        except Exception as exc:
            full_tb = _tb.format_exc()
            print(f"[POLL] Claude extraction error:\n{full_tb}")
            await message.channel.send(
                f"❌ Couldn't extract poll from request — AI error:\n```{exc}```"
            )
            return

        try:
            poll = discord.Poll(
                question=question,
                duration=timedelta(hours=24),
                multiple=False,
            )
            for opt in options[:10]:
                poll.add_answer(text=opt)
            sent = await message.channel.send(poll=poll)
            # Confirm poll object is attached
            if sent.poll is not None:
                print(f"[POLL] Native poll confirmed on message {sent.id} — question: '{question}'")
            else:
                print(f"[POLL] WARNING: sent.poll is None on message {sent.id}")
            await message.reply("Poll's live 🍜", mention_author=False)
        except Exception as exc:
            full_tb = _tb.format_exc()
            print(f"[POLL] discord.Poll send error:\n{full_tb}")
            await message.channel.send(
                f"❌ Poll creation failed — Discord error:\n```{exc}```\n"
                f"Full traceback in Railway logs."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ─── AI CONTENT GENERATION & APPROVAL SYSTEM ───────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

import logging
import schedule as _schedule
import threading
import pytz
import time as _time
from typing import Optional

# ── Logging ─────────────────────────────────────────────────────────────────────
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_fh = logging.FileHandler("jarvis_bot.log")
_fh.setFormatter(_log_fmt)
_sh = logging.StreamHandler()
_sh.setFormatter(_log_fmt)
jarvis_log = logging.getLogger("jarvis_content")
jarvis_log.setLevel(logging.INFO)
jarvis_log.addHandler(_fh)
jarvis_log.addHandler(_sh)

# ── Constants ────────────────────────────────────────────────────────────────────
_ET = pytz.timezone("America/New_York")
_FALLBACK = "The kitchen is open. Stay disciplined, manage your risk, and trust your levels. 🍜"
_MOD_CHANNEL = "mod-chat"
_AUTO_DELAY = 45 * 60  # seconds

_bot_loop = None
_last_fired: dict = {}  # "slot_name_YYYY-MM-DD" → True


# ── Slot definitions ─────────────────────────────────────────────────────────────
_SLOTS = [
    {
        "name": "morning_prep",
        "weekdays": [0, 1, 2, 3, 4],
        "hour": 8, "minute": 0,
        "target": "daily-levels",
        "approval": True,
        "prompt": (
            "You are Jarvis, the voice of The Soup Kitchen trading Discord. "
            "Write a pre-market preparation post. Disciplined, sharp, professional with edge. "
            "Focus on mindset and preparation before the open. Vary the angle every day — "
            "some days focus on patience, some on aggression, some on risk management. "
            "End with 🍜. Max 4 sentences."
        ),
    },
    {
        "name": "midday_checkin",
        "weekdays": [0, 1, 2, 3, 4],
        "hour": 11, "minute": 30,
        "target": "market-talk",
        "approval": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a midday market check-in post. The market has been open 2 hours. "
            "Prompt members to share how their morning trades went, what they are seeing intraday, "
            "and whether the market is trending or choppy. Vary the tone — some days energetic, "
            "some days cautious. End with 🍜. Max 4 sentences."
        ),
    },
    {
        "name": "market_close",
        "weekdays": [0, 1, 2, 3, 4],
        "hour": 16, "minute": 5,
        "target": "daily-levels",
        "approval": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a market close recap post. The trading day just ended. "
            "Prompt members to share their PnL, one thing they did well, and one thing to improve. "
            "Remind them that posting losses builds more trust than hiding them. "
            "Vary the closing energy — some days reflective, some days fired up. End with 🍜. Max 4 sentences."
        ),
    },
    {
        "name": "weekly_poll",
        "weekdays": [0],  # Monday only
        "hour": 9, "minute": 35,
        "target": "market-talk",
        "approval": False,
        "poll": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a Monday market sentiment poll question asking members their directional bias for the week. "
            "Return only the poll question text, nothing else. Keep it under 15 words."
        ),
    },
    {
        "name": "kitchen_fundamentals",
        "weekdays": [0],  # Monday only
        "hour": 10, "minute": 0,
        "target": "playbook",
        "approval": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a Kitchen Fundamentals educational post. Teach one trading or options concept in plain English. "
            "Rotate through these concepts week by week — IV rank, open interest vs volume, bull call spreads, "
            "max pain theory, theta decay, delta and gamma, support and resistance, market structure, "
            "0DTE strategy, risk management, earnings plays, sector rotation, reading options chains, "
            "tape reading, pre-market prep. 4-6 sentences max. End with 🍜 #KitchenFundamentals."
        ),
    },
    {
        "name": "midweek_engagement",
        "weekdays": [2],  # Wednesday only
        "hour": 11, "minute": 0,
        "target": "general-chat",
        "approval": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a midweek community engagement post. Rotate between these three formats — "
            "1) Would you take this trade? with a hypothetical setup, "
            "2) A trading psychology or mindset question, "
            "3) A weekly challenge for members to complete and report back on Friday. "
            "Make it conversational and engaging. End with 🍜. Max 4 sentences."
        ),
    },
    {
        "name": "friday_recap",
        "weekdays": [4],  # Friday only
        "hour": 16, "minute": 10,
        "target": "trade-recaps",
        "approval": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a Friday end of week recap post. The trading week is done. "
            "Prompt members to share their week — wins, losses, biggest lesson. "
            "Remind them the best traders document everything. "
            "Make it feel like a locker room debrief after a game. End with 🍜. Max 4 sentences."
        ),
    },
    {
        "name": "sunday_prep",
        "weekdays": [6],  # Sunday only
        "hour": 19, "minute": 0,
        "target": "daily-levels",
        "approval": True,
        "prompt": (
            "You are Jarvis for The Soup Kitchen trading Discord. "
            "Write a Sunday evening prep post. Market opens tomorrow. "
            "Prompt members to review their watchlist, set their key levels tonight, and come in with a plan. "
            "Vary the energy — some Sundays calm and methodical, some fired up. End with 🍜. Max 4 sentences."
        ),
    },
]


# ── Content generation ────────────────────────────────────────────────────────────

async def _gen_content(prompt: str) -> str:
    """Call Claude API to generate a post. Returns fallback on failure."""
    try:
        def _call():
            return claude_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                system=prompt,
                messages=[{"role": "user", "content": "Generate the post now."}],
            )
        resp = await asyncio.to_thread(_call)
        text = resp.content[0].text.strip()
        jarvis_log.info(f"Generated {len(text)} chars")
        return text
    except Exception as exc:
        jarvis_log.error(f"Anthropic API error: {exc}")
        return _FALLBACK


_DAILY_LEVELS_FALLBACK = "market-talk"

async def _send_content(channel_name: str, text: str) -> bool:
    """Post text to a channel by name, falling back to #market-talk for #daily-levels."""
    guild = client.get_guild(GUILD_ID)
    ch = guild and discord.utils.get(guild.text_channels, name=channel_name)
    if not ch and channel_name == "daily-levels":
        jarvis_log.warning(f"#daily-levels not found — falling back to #{_DAILY_LEVELS_FALLBACK}")
        channel_name = _DAILY_LEVELS_FALLBACK
        ch = guild and discord.utils.get(guild.text_channels, name=channel_name)
    if not ch:
        jarvis_log.error(f"Channel #{channel_name} not found — cannot post")
        return False
    await ch.send(text)
    jarvis_log.info(f"Posted to #{channel_name}: {text[:60]}...")
    return True


async def _send_poll_post(channel_name: str, question: str):
    """Post a Discord poll (with reaction fallback)."""
    guild = client.get_guild(GUILD_ID)
    ch = guild and discord.utils.get(guild.text_channels, name=channel_name)
    if not ch:
        jarvis_log.error(f"Poll channel #{channel_name} not found")
        return
    try:
        poll = discord.Poll(question=question, duration=timedelta(hours=24))
        poll.add_answer(text="Bullish 🟢")
        poll.add_answer(text="Bearish 🔴")
        poll.add_answer(text="Neutral ⚪")
        poll.add_answer(text="Waiting for confirmation 👀")
        await ch.send(poll=poll)
        jarvis_log.info(f"Poll posted to #{channel_name}: {question}")
    except Exception as exc:
        jarvis_log.warning(f"Native poll unavailable ({exc}), using reaction fallback")
        msg = await ch.send(
            f"🗳️ **Weekly Bias Poll**\n{question}\n\n"
            "🟢 Bullish  •  🔴 Bearish  •  ⚪ Neutral  •  👀 Waiting for confirmation"
        )
        for emoji in ["🟢", "🔴", "⚪", "👀"]:
            await msg.add_reaction(emoji)
        jarvis_log.info(f"Reaction poll posted to #{channel_name}")


# ── Approval UI ───────────────────────────────────────────────────────────────────

class _EditModal(discord.ui.Modal, title="Edit Post"):
    revised = discord.ui.TextInput(
        label="Revised Content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )

    def __init__(self, view: "ApprovalView"):
        super().__init__()
        self._view = view
        self.revised.default = view.content[:4000]

    async def on_submit(self, interaction: discord.Interaction):
        v = self._view
        if v.done:
            now = datetime.now(_ET).strftime("%I:%M %p ET")
            await interaction.response.send_message(
                f"⚠️ Already auto-posted to #{v.target} at {now}. No action taken.",
                ephemeral=True,
            )
            return
        v.done = True
        if v.timer and not v.timer.done():
            v.timer.cancel()
        await interaction.response.defer()
        edited = self.revised.value.strip()
        await _send_content(v.target, edited)
        now = datetime.now(_ET).strftime("%I:%M %p ET")
        jarvis_log.info(f"EDIT: {v.slot_name} → #{v.target} at {now}")
        if v.mod_msg:
            try:
                await v.mod_msg.edit(
                    content=v.mod_msg.content + f"\n\n✏️ Edited and posted to #{v.target} at {now}",
                    view=None,
                )
            except Exception as exc:
                jarvis_log.error(f"mod_msg edit error: {exc}")


class ApprovalView(discord.ui.View):
    def __init__(self, content: str, target: str, slot_name: str, sched_time: str):
        super().__init__(timeout=3600)
        self.content = content
        self.target = target
        self.slot_name = slot_name
        self.sched_time = sched_time
        self.done = False
        self.timer: Optional[asyncio.Task] = None
        self.mod_msg: Optional[discord.Message] = None

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        await _send_content(self.target, self.content)
        now = datetime.now(_ET).strftime("%I:%M %p ET")
        jarvis_log.info(f"VIEW TIMEOUT: {self.slot_name} → #{self.target}")
        if self.mod_msg:
            try:
                await self.mod_msg.edit(
                    content=self.mod_msg.content
                    + f"\n\n⏰ Auto-posted to #{self.target} after 60 min — view timed out",
                    view=None,
                )
            except Exception as exc:
                jarvis_log.error(f"mod_msg edit error on view timeout: {exc}")

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done:
            now = datetime.now(_ET).strftime("%I:%M %p ET")
            await interaction.response.send_message(
                f"⚠️ Already auto-posted to #{self.target} at {now}. No action taken.",
                ephemeral=True,
            )
            return
        self.done = True
        if self.timer and not self.timer.done():
            self.timer.cancel()
        await interaction.response.defer()
        await _send_content(self.target, self.content)
        now = datetime.now(_ET).strftime("%I:%M %p ET")
        jarvis_log.info(f"APPROVED: {self.slot_name} → #{self.target} at {now}")
        if self.mod_msg:
            try:
                await self.mod_msg.edit(
                    content=self.mod_msg.content + f"\n\n✅ Posted to #{self.target} at {now}",
                    view=None,
                )
            except Exception as exc:
                jarvis_log.error(f"mod_msg edit error: {exc}")

    @discord.ui.button(label="✏️ Edit", style=discord.ButtonStyle.blurple)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done:
            now = datetime.now(_ET).strftime("%I:%M %p ET")
            await interaction.response.send_message(
                f"⚠️ Already auto-posted to #{self.target} at {now}. No action taken.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(_EditModal(self))


async def _auto_post_timer(view: ApprovalView):
    """Wait 45 min then auto-post if not already handled."""
    await asyncio.sleep(_AUTO_DELAY)
    if view.done:
        return
    view.done = True
    await _send_content(view.target, view.content)
    now = datetime.now(_ET).strftime("%I:%M %p ET")
    jarvis_log.info(f"AUTO-POST: {view.slot_name} → #{view.target} (45 min timeout)")
    if view.mod_msg:
        try:
            await view.mod_msg.edit(
                content=view.mod_msg.content
                + f"\n\n⏰ Auto-posted to #{view.target} after 45 min — no approval received",
                view=None,
            )
        except Exception as exc:
            jarvis_log.error(f"mod_msg edit error after auto-post: {exc}")


async def _request_approval(content: str, slot: dict):
    """Send content to #mod-chat with Approve / Edit buttons."""
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return
    mod_ch = discord.utils.get(guild.text_channels, name=_MOD_CHANNEL)
    if not mod_ch:
        jarvis_log.error(f"#{_MOD_CHANNEL} not found — direct-posting {slot['name']}")
        await _send_content(slot["target"], content)
        return

    admin_role = discord.utils.get(guild.roles, name="Admin")
    mention = admin_role.mention if admin_role else "@Admin"
    now = datetime.now(_ET).strftime("%I:%M %p ET")

    embed = discord.Embed(
        title="📋 Pending Approval",
        description=content,
        color=discord.Color.orange(),
    )
    embed.add_field(name="Target", value=f"#{slot['target']}", inline=True)
    embed.add_field(name="Scheduled", value=now, inline=True)
    embed.add_field(name="Slot", value=slot["name"], inline=True)
    embed.set_footer(text="Auto-posts in 45 min if no action taken.")

    view = ApprovalView(content, slot["target"], slot["name"], now)
    mod_msg = await mod_ch.send(content=mention, embed=embed, view=view)
    view.mod_msg = mod_msg
    view.timer = asyncio.create_task(_auto_post_timer(view))
    jarvis_log.info(f"PENDING: {slot['name']} → #{_MOD_CHANNEL} (45 min countdown started)")


# ── Slot dispatcher ───────────────────────────────────────────────────────────────

async def _fire_slot(slot: dict):
    now_str = datetime.now(_ET).strftime("%I:%M %p ET")
    jarvis_log.info(f"SLOT: {slot['name']} firing at {now_str}")
    content = await _gen_content(slot["prompt"])
    jarvis_log.info(f"CONTENT [{slot['name']}]: {content[:80]}...")

    if slot.get("poll"):
        await _send_poll_post(slot["target"], content)
    elif slot.get("approval"):
        await _request_approval(content, slot)
    else:
        await _send_content(slot["target"], content)
        jarvis_log.info(f"DIRECT: {slot['name']} → #{slot['target']}")


# ── Schedule thread ───────────────────────────────────────────────────────────────

def _make_job(slot: dict):
    """Return a schedule-compatible job that fires only at the correct ET time/day."""
    def _job():
        now = datetime.now(_ET)
        if now.weekday() not in slot["weekdays"]:
            return
        if now.hour != slot["hour"] or now.minute != slot["minute"]:
            return
        key = f"{slot['name']}_{now.date()}"
        if _last_fired.get(key):
            return
        _last_fired[key] = True
        if _bot_loop:
            asyncio.run_coroutine_threadsafe(_fire_slot(slot), _bot_loop)
    return _job


def _start_content_scheduler():
    _schedule.clear("content")
    _DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lines = [f"{'NAME':<26} {'TIME (ET)':<10} {'DAYS':<15} {'TARGET':<20} TYPE"]
    lines.append("─" * 80)
    for slot in _SLOTS:
        _schedule.every(1).minutes.do(_make_job(slot)).tag("content")
        days = "/".join(_DAY[d] for d in slot["weekdays"])
        kind = "poll" if slot.get("poll") else ("approval" if slot.get("approval") else "direct")
        lines.append(
            f"{slot['name']:<26} "
            f"{slot['hour']:02d}:{slot['minute']:02d} ET   "
            f"{days:<15} "
            f"#{slot['target']:<19} {kind}"
        )
    for line in lines:
        jarvis_log.info(line)
        print(f"[Content] {line}")

    def _runner():
        while True:
            _schedule.run_pending()
            _time.sleep(30)

    t = threading.Thread(target=_runner, daemon=True, name="jarvis-content-scheduler")
    t.start()
    jarvis_log.info("Content scheduler thread started (polling every 30s)")
    return t


_prev_on_ready = client.on_ready  # capture existing handler


@client.event
async def on_ready():
    """Chains the original on_ready then starts the content system."""
    await _prev_on_ready()
    global _bot_loop
    _bot_loop = asyncio.get_event_loop()
    _start_content_scheduler()
    jarvis_log.info(f"═══ Content system online — {len(_SLOTS)} slots registered ═══")
    print(f"[Content] System online — {len(_SLOTS)} slots registered")



# ═══════════════════════════════════════════════════════════════════════════════
# ─── EXTENDED FEATURES 1–10 ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

import json as _json
from datetime import date as _date
import aiohttp as _aiohttp
from aiohttp import web as _aiohttp_web
from discord import app_commands as _app_commands

# ── Co-founder IDs — fill these in manually ──────────────────────────────────
_COFOUNDER_IDS: list = [
    "markyy8297",      # Marky
    "the_algo_reaper", # Milad
    "jtmfsu98",        # JT
]

def _is_cofounder(member) -> bool:
    """Match by numeric Discord user ID or by username/display_name string."""
    for entry in _COFOUNDER_IDS:
        if isinstance(entry, int):
            if member.id == entry:
                return True
        elif isinstance(entry, str):
            name = entry.lstrip("_")
            if member.name == name or member.name == entry \
               or member.display_name == name or member.display_name == entry:
                return True
    return False
_LIVE_CALLS_CHANNEL  = "live-calls"
_WATCHLIST_CHANNEL   = "watchlist"
_WINS_CHANNEL        = "wins"
_ANNOUNCEMENTS_CHANNEL = "announcements"
_PNL_FILE   = "pnl_tracker.json"
_JOINS_FILE = "member_joins.json"

_MILESTONES_ALL  = {50, 100, 250, 500, 1000}
_milestones_hit: set = set()

# ── Slash command tree ────────────────────────────────────────────────────────
_slash_tree = _app_commands.CommandTree(client)

# ── Channel helper (name-based with fallback) ─────────────────────────────────

def _ch(guild: discord.Guild, name: str, fallback: str = "market-talk"):
    ch = discord.utils.get(guild.text_channels, name=name)
    if not ch and fallback:
        ch = discord.utils.get(guild.text_channels, name=fallback)
        if ch:
            jarvis_log.warning(f"#{name} not found — using #{fallback}")
    return ch


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 1 — Live market context injected into every AI generation call
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_market_context() -> str:
    try:
        def _pull():
            spy = yf.Ticker("SPY").fast_info
            qqq = yf.Ticker("QQQ").fast_info
            vix = yf.Ticker("^VIX").fast_info
            return spy, qqq, vix

        spy_fi, qqq_fi, vix_fi = await asyncio.to_thread(_pull)

        spy_p = spy_fi.last_price
        spy_c = ((spy_p - spy_fi.previous_close) / spy_fi.previous_close) * 100
        qqq_p = qqq_fi.last_price
        qqq_c = ((qqq_p - qqq_fi.previous_close) / qqq_fi.previous_close) * 100
        vix_v = vix_fi.last_price

        if vix_v < 15:
            vix_char = "Low vol — patience pays"
        elif vix_v < 20:
            vix_char = "Moderate vol — trust your levels"
        elif vix_v < 25:
            vix_char = "Elevated vol — size down"
        else:
            vix_char = "High vol — defense wins today"

        s_spy = "+" if spy_c >= 0 else ""
        s_qqq = "+" if qqq_c >= 0 else ""
        return (
            f"Current market context: SPY ${spy_p:.2f} ({s_spy}{spy_c:.2f}%), "
            f"QQQ ${qqq_p:.2f} ({s_qqq}{qqq_c:.2f}%), "
            f"VIX {vix_v:.1f} ({vix_char}). "
            "Factor this into your post naturally — don't just list the numbers, weave them into the narrative."
        )
    except Exception as exc:
        jarvis_log.warning(f"Market context fetch failed: {exc}")
        return ""


# Monkey-patch _gen_content so every AI call gets live market context
_orig_gen_content = _gen_content

async def _gen_content(prompt: str) -> str:
    ctx = await _fetch_market_context()
    enhanced = prompt + (f"\n\n{ctx}" if ctx else "")
    return await _orig_gen_content(enhanced)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 2 — /trade slash command
# ─────────────────────────────────────────────────────────────────────────────

@_slash_tree.command(name="trade", description="Post a live trade alert to #live-calls")
@_app_commands.describe(
    ticker="Ticker symbol (e.g. MNST)",
    direction="Long or Short",
    entry="Entry price",
    stop="Stop loss price",
    target="Target price",
    notes="Trade thesis",
)
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_trade(
    interaction: discord.Interaction,
    ticker: str,
    direction: str,
    entry: float,
    stop: float,
    target: float,
    notes: str = "",
):
    if interaction.channel.name != _MOD_CHANNEL:
        await interaction.response.send_message("❌ Use /trade in #mod-chat only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    ticker = ticker.upper().strip()

    try:
        cur_price = await asyncio.to_thread(lambda: yf.Ticker(ticker).fast_info.last_price)
    except Exception:
        cur_price = None

    risk   = abs(entry - stop)
    reward = abs(target - entry)
    rr     = reward / risk if risk > 0 else 0
    pct_t  = ((target - entry) / entry) * 100
    pct_s  = ((stop - entry) / entry) * 100

    d_emoji = "📈" if direction.lower() == "long" else "📉"
    s_t = "+" if pct_t >= 0 else ""
    s_s = "+" if pct_s >= 0 else ""

    body = (
        f"🚨 **LIVE TRADE ALERT — THE SOUP KITCHEN**\n\n"
        f"{d_emoji} **${ticker} — {direction.upper()}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Entry Zone:  ${entry:.2f}\n"
        f"🎯 Target:      ${target:.2f}  ({s_t}{pct_t:.1f}%)\n"
        f"🛑 Stop Loss:   ${stop:.2f}  ({s_s}{pct_s:.1f}%)\n"
        f"📊 R:R Ratio:   {rr:.1f}:1\n"
    )
    if cur_price:
        body += f"💵 Current Price: ${cur_price:.2f}\n"
    body += "━━━━━━━━━━━━━━━━━━━━\n"
    if notes:
        body += f"💭 Thesis: {notes}\n\n"
    body += "⚠️ This is not financial advice. Manage your own risk.\nPosted by Jarvis 🍜 | The Soup Kitchen"

    live_ch = _ch(interaction.guild, _LIVE_CALLS_CHANNEL)
    if not live_ch:
        await interaction.followup.send("❌ #live-calls not found.", ephemeral=True)
        return

    alert_msg = await live_ch.send(body)
    try:
        await alert_msg.create_thread(name=f"${ticker} Trade Discussion")
    except Exception as exc:
        jarvis_log.warning(f"Trade thread creation failed: {exc}")

    jarvis_log.info(f"TRADE ALERT: {ticker} {direction} → #{_LIVE_CALLS_CHANNEL}")
    await interaction.followup.send(f"✅ Trade alert posted to {live_ch.mention}.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 3 — /watchlist slash command
# ─────────────────────────────────────────────────────────────────────────────

@_slash_tree.command(name="watchlist", description="Post today's watchlist to #watchlist")
@_app_commands.describe(tickers="Comma-separated tickers e.g. MNST,AAPL,SPY")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_watchlist(interaction: discord.Interaction, tickers: str):
    if interaction.channel.name != _MOD_CHANNEL:
        await interaction.response.send_message("❌ Use /watchlist in #mod-chat only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        await interaction.followup.send("❌ No tickers provided.", ephemeral=True)
        return

    def _fetch_wl():
        rows = []
        for sym in symbols:
            try:
                fi = yf.Ticker(sym).fast_info
                price = fi.last_price
                chg = ((price - fi.previous_close) / fi.previous_close) * 100
                rows.append((sym, price, chg, fi.year_low, fi.year_high))
            except Exception as e:
                jarvis_log.warning(f"Watchlist {sym}: {e}")
                rows.append((sym, None, None, None, None))
        return rows

    rows = await asyncio.to_thread(_fetch_wl)
    today_str = datetime.now(_ET).strftime("%B %d, %Y")
    lines = [f"👀 **TODAY'S WATCHLIST — THE SOUP KITCHEN**\n{today_str} | Market Open\n"]
    for sym, price, chg, lo52, hi52 in rows:
        if price is None:
            lines.append(f"📊 **${sym}**  ❌ Data unavailable")
            continue
        arrow = "🟢" if chg >= 0 else "🔴"
        sign = "+" if chg >= 0 else ""
        w52 = f"${lo52:.2f} — ${hi52:.2f}" if hi52 and lo52 else "N/A"
        lines.append(f"📊 **${sym}**   ${price:.2f}   {arrow} {sign}{chg:.2f}%  |  52W: {w52}")
    lines.append("\nDrop your levels and thesis below 👇\nWhat's your conviction play today? 🍜")

    wl_ch = _ch(interaction.guild, _WATCHLIST_CHANNEL)
    if not wl_ch:
        await interaction.followup.send("❌ #watchlist not found.", ephemeral=True)
        return

    await wl_ch.send("\n".join(lines))
    jarvis_log.info(f"WATCHLIST posted: {', '.join(symbols)}")
    await interaction.followup.send(f"✅ Watchlist posted to {wl_ch.mention}.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 4 — /pnl slash command + Friday leaderboard
# ─────────────────────────────────────────────────────────────────────────────

def _pnl_load() -> dict:
    try:
        with open(_PNL_FILE) as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {"entries": [], "week_start": str(_date.today())}

def _pnl_save(data: dict):
    try:
        with open(_PNL_FILE, "w") as f:
            _json.dump(data, f, indent=2)
    except Exception as exc:
        jarvis_log.error(f"PNL save error: {exc}")


@_slash_tree.command(name="pnl", description="Log your PnL for the day")
@_app_commands.describe(
    amount="Amount won or lost (e.g. +450 or -200)",
    trade="What you traded (e.g. MNST calls)",
    notes="Optional notes",
)
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_pnl(interaction: discord.Interaction, amount: str, trade: str, notes: str = ""):
    await interaction.response.defer()
    try:
        amount_val = float(amount.replace("$", "").replace(",", ""))
    except ValueError:
        await interaction.followup.send("❌ Invalid amount. Use +450 or -200.", ephemeral=True)
        return

    entry = {
        "username": interaction.user.display_name,
        "user_id": str(interaction.user.id),
        "amount": amount_val,
        "trade": trade,
        "notes": notes,
        "timestamp": datetime.now(_ET).isoformat(),
        "day": datetime.now(_ET).strftime("%A"),
    }
    data = _pnl_load()
    data["entries"].append(entry)
    _pnl_save(data)

    sign = "✅" if amount_val >= 0 else "❌"
    dollar = f"+${amount_val:.0f}" if amount_val >= 0 else f"-${abs(amount_val):.0f}"
    body = f"💰 **PNL LOGGED — {interaction.user.mention}**\n{trade}: {dollar} {sign}\n"
    if notes:
        body += f'"{notes}"\n'
    body += "🍜 Keep cooking."

    await interaction.followup.send(body)
    jarvis_log.info(f"PNL: {interaction.user.display_name} {dollar} ({trade})")


async def _post_pnl_leaderboard():
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return
    wins_ch = _ch(guild, _WINS_CHANNEL)
    if not wins_ch:
        return

    data = _pnl_load()
    entries = data.get("entries", [])
    if not entries:
        jarvis_log.info("PNL leaderboard: no entries this week — skipping")
        return

    totals: dict = {}
    for e in entries:
        uid = e["user_id"]
        if uid not in totals:
            totals[uid] = {"username": e["username"], "total": 0.0}
        totals[uid]["total"] += e["amount"]

    ranked = sorted(totals.values(), key=lambda x: x["total"], reverse=True)
    green = sum(1 for v in totals.values() if v["total"] >= 0)
    red = len(totals) - green

    week_start = data.get("week_start", str(_date.today()))
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "🏆 **WEEKLY PNL LEADERBOARD**",
        f"Week of {week_start} — {datetime.now(_ET).strftime('%B %d, %Y')}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, v in enumerate(ranked[:10]):
        medal = medals[i] if i < 3 else f"{i + 1}."
        s = "+" if v["total"] >= 0 else ""
        lines.append(f"{medal} @{v['username']}    {s}${v['total']:.0f}")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total members reporting: {len(totals)}",
        f"💚 Green on the week: {green}",
        f"🔴 Red on the week: {red}",
        "━━━━━━━━━━━━━━━━━━━━",
        "Post your trades in the server.",
        "The kitchen runs on proof. 🍜👑",
    ]
    await wins_ch.send("\n".join(lines))
    jarvis_log.info(f"PNL leaderboard posted — {len(totals)} traders")
    _pnl_save({"entries": [], "week_start": str(_date.today())})


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 5 — TradingView webhook listener on port 8080
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_tv_webhook(request: _aiohttp_web.Request) -> _aiohttp_web.Response:
    try:
        payload = await request.json()
    except Exception as exc:
        jarvis_log.error(f"Webhook: bad JSON — {exc}")
        return _aiohttp_web.Response(status=400, text="Bad JSON")

    ticker  = str(payload.get("ticker", "")).strip().upper()
    action  = str(payload.get("action", "")).strip().upper()
    price   = payload.get("price", "N/A")
    message = payload.get("message", "")

    jarvis_log.info(f"WEBHOOK IN: ticker={ticker} action={action} price={price}")

    if not ticker:
        jarvis_log.error("Webhook: missing ticker — not posting")
        return _aiohttp_web.Response(status=400, text="Missing ticker")

    now_str = datetime.now(_ET).strftime("%I:%M %p ET")
    body = (
        f"@everyone\n"
        f"📊 **CHART: UNLABELED — update TradingView webhook URL**\n"
        f"🔔 **TRADINGVIEW ALERT — ${ticker}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Action: {action} triggered at ${price}\n"
        f"Message: {message}\n"
        f"Time: {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Not financial advice. Manage your risk. 🍜"
    )

    async def _post():
        guild = client.get_guild(GUILD_ID)
        if not guild:
            return

        # Check if Jarvis has Mention Everyone permission — log warning if not
        me = guild.me
        if me and not me.guild_permissions.mention_everyone:
            jarvis_log.warning(
                "PERMISSION WARNING: Jarvis does not have 'Mention @everyone' permission. "
                "@everyone ping will not fire until this is granted in Server Settings → Roles → Jarvis."
            )

        # Find or create #marky-alerts in the paid alerts category
        ch = discord.utils.get(guild.text_channels, name="marky-alerts")
        if not ch:
            try:
                category = discord.utils.get(guild.categories, name="🔒 PAID ALERTS")
                ch = await guild.create_text_channel(
                    "marky-alerts",
                    category=category,
                    topic="Marky's live trade signals — Langston Volatility Capture. 🍜",
                )
                jarvis_log.info("Created #marky-alerts channel")
            except Exception as exc:
                jarvis_log.error(f"Could not create #marky-alerts: {exc}")
                ch = _ch(guild, _LIVE_CALLS_CHANNEL)  # fallback
        if not ch:
            return
        msg = await ch.send(
            body,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        try:
            await msg.create_thread(name=f"${ticker} Alert Discussion")
        except Exception as exc:
            jarvis_log.warning(f"Webhook thread error: {exc}")

    if _bot_loop:
        asyncio.run_coroutine_threadsafe(_post(), _bot_loop)

    return _aiohttp_web.Response(status=200, text="OK")


async def _start_webhook_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        app = _aiohttp_web.Application()
        app.router.add_post("/webhook", _handle_tv_webhook)
        # Also accept POST on / so Railway health checks and direct-root POSTs work
        app.router.add_post("/", _handle_tv_webhook)
        runner = _aiohttp_web.AppRunner(app)
        await runner.setup()
        site = _aiohttp_web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        jarvis_log.info(f"TradingView webhook server listening on 0.0.0.0:{port}")
        print(f"[Webhook] Server online — 0.0.0.0:{port}/webhook  (PORT={port})")
    except Exception as exc:
        jarvis_log.error(f"Webhook server failed to start: {exc}")
        print(f"[Webhook] Failed to start: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 6 — 3-message welcome DM sequence
# ─────────────────────────────────────────────────────────────────────────────

_DM1 = (
    "👑 Welcome to The Soup Kitchen, {name}.\n\n"
    "You just joined one of the most disciplined trading communities out there.\n\n"
    "Here's what to do first:\n"
    "1. Read #rules\n"
    "2. React ✅ to get your Free Member role\n"
    "3. Check #daily-levels every morning before the bell\n\n"
    "We feed traders daily. 🍜"
)
_DM2 = (
    "📋 Hey {name} — Jarvis checking in.\n\n"
    "Here's how to get the most out of the kitchen:\n\n"
    "• #daily-levels — key levels every morning before open\n"
    "• #watchlist — what the team is watching each day\n"
    "• #wins — drop your W's here\n"
    "• #trade-journal — log every trade, win or lose\n"
    "• #market-talk — community discussion all day\n\n"
    "The best traders in here show up every single day. 🍜"
)
_DM3 = (
    "🔒 {name} — ready for the full menu?\n\n"
    "Paid members get:\n"
    "• 🚨 Live trade alerts in real time\n"
    "• 🌊 Options flow and unusual activity\n"
    "• 📊 Full trade recaps after every call\n"
    "• 📖 The complete Soup Kitchen playbook\n"
    "• 🎥 Recorded sessions and education\n"
    "• ❓ Direct Q&A access to the team\n\n"
    "When you're ready: check #how-to-get-access\n\n"
    "Good trades feed everyone. 🍜👑"
)


def _joins_load() -> dict:
    try:
        with open(_JOINS_FILE) as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {}

def _joins_save(data: dict):
    try:
        with open(_JOINS_FILE, "w") as f:
            _json.dump(data, f, indent=2)
    except Exception as exc:
        jarvis_log.error(f"Joins save error: {exc}")


async def _check_welcome_dms():
    data = _joins_load()
    now = datetime.now(_ET)
    dirty = False
    for uid, info in list(data.items()):
        try:
            joined = datetime.fromisoformat(info["joined_at"])
            hours  = (now - joined).total_seconds() / 3600
            guild  = client.get_guild(GUILD_ID)
            member = guild.get_member(int(uid)) if guild else None
            if not member:
                del data[uid]
                dirty = True
                continue
            name = member.display_name

            if not info.get("dm2_sent") and hours >= 24:
                try:
                    await member.send(_DM2.format(name=name))
                except discord.Forbidden:
                    pass
                data[uid]["dm2_sent"] = True
                dirty = True
                jarvis_log.info(f"Welcome DM2 → {name}")

            if not info.get("dm3_sent") and hours >= 48:
                try:
                    await member.send(_DM3.format(name=name))
                except discord.Forbidden:
                    pass
                data[uid]["dm3_sent"] = True
                dirty = True
                jarvis_log.info(f"Welcome DM3 → {name}")

            if info.get("dm2_sent") and info.get("dm3_sent"):
                del data[uid]
                dirty = True
        except Exception as exc:
            jarvis_log.error(f"Welcome DM check uid={uid}: {exc}")
    if dirty:
        _joins_save(data)


# Chain on_member_join — DM1 + join tracking + milestone check
_prev_on_member_join_f6 = client.on_member_join

@client.event
async def on_member_join(member):
    try:
        await _prev_on_member_join_f6(member)
    except Exception as exc:
        jarvis_log.error(f"on_member_join chain error: {exc}")

    # DM 1 — immediate
    try:
        await member.send(_DM1.format(name=member.display_name))
        jarvis_log.info(f"Welcome DM1 → {member.display_name}")
    except discord.Forbidden:
        jarvis_log.warning(f"DM1 blocked for {member.display_name}")
    except Exception as exc:
        jarvis_log.error(f"DM1 error: {exc}")

    # Log join for DM2/DM3 scheduler
    data = _joins_load()
    data[str(member.id)] = {
        "username": member.display_name,
        "joined_at": datetime.now(_ET).isoformat(),
        "dm2_sent": False,
        "dm3_sent": False,
    }
    _joins_save(data)

    # FEATURE 9 — Milestone check
    try:
        count = member.guild.member_count
        if count in _MILESTONES_ALL and count not in _milestones_hit:
            _milestones_hit.add(count)
            ann_ch = _ch(member.guild, _ANNOUNCEMENTS_CHANNEL)
            if ann_ch:
                _milestone_msgs = {
                    50: (
                        "🎉 **50 MEMBERS IN THE KITCHEN**\n"
                        "The soup is getting thick.\n"
                        "Thank you to every single one of you for being here early.\n"
                        "The best is coming. 🍜👑"
                    ),
                    100: (
                        "👑 **100 MEMBERS — THE KITCHEN IS OFFICIAL**\n"
                        "This is where it started.\n"
                        "The founding members who were here at 100 — you'll remember this.\n"
                        "Paywall goes up soon. Get your founding rate while it's open. 🍜"
                    ),
                    250: (
                        "🔥 **250 MEMBERS DEEP**\n"
                        "The Soup Kitchen is no longer a secret.\n"
                        "Tell a trader. Send the link. Feed the people. 🍜👑"
                    ),
                    500: (
                        "⚡ **500 MEMBERS**\n"
                        "Half a thousand traders eating at the kitchen.\n"
                        "This is only the beginning. 🍜👑"
                    ),
                    1000: (
                        "👑 **ONE THOUSAND MEMBERS**\n"
                        "What started as an idea is now a movement.\n"
                        "Good trades feed everyone. 🍜👑"
                    ),
                }
                await ann_ch.send(_milestone_msgs[count])
                jarvis_log.info(f"Milestone {count} announced")
    except Exception as exc:
        jarvis_log.error(f"Milestone error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# WELCOME CHANNEL — #👋・welcome setup + join posts
# ─────────────────────────────────────────────────────────────────────────────

_WELCOME_FEED_CHANNEL = "👋・welcome"
_START_HERE_CATEGORY  = "START HERE"


async def _setup_welcome_channel(guild: discord.Guild):
    """Create #👋・welcome in START HERE, locked so only Jarvis can post."""
    existing = discord.utils.get(guild.text_channels, name=_WELCOME_FEED_CHANNEL)
    if existing:
        jarvis_log.info(f"SETUP: #{_WELCOME_FEED_CHANNEL} already exists")
        return existing

    category = discord.utils.get(guild.categories, name=_START_HERE_CATEGORY)
    everyone  = guild.default_role
    me        = guild.me

    overwrites = {
        everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        me:       discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    # Grant Admin + Moderator send access too so mods can pin/manage
    for role_name in ("Admin", "Moderator"):
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True
            )

    try:
        ch = await guild.create_text_channel(
            _WELCOME_FEED_CHANNEL,
            category=category,
            overwrites=overwrites,
            topic="Every new member who walks through the door. 🍜",
        )
        # Position it just below #rules if possible
        rules_ch = discord.utils.get(guild.text_channels, name="rules")
        if rules_ch:
            try:
                await ch.edit(position=rules_ch.position + 1)
            except Exception:
                pass
        jarvis_log.info(f"SETUP: Created #{_WELCOME_FEED_CHANNEL}")
        print(f"[Welcome] Created #{_WELCOME_FEED_CHANNEL}")
        return ch
    except Exception as exc:
        jarvis_log.error(f"SETUP: Failed to create welcome channel: {exc}")
        return None


async def _post_welcome_feed(member: discord.Member):
    """Post the join card in #👋・welcome."""
    guild = member.guild
    ch = discord.utils.get(guild.text_channels, name=_WELCOME_FEED_CHANNEL)
    if not ch:
        jarvis_log.warning(f"Welcome feed: #{_WELCOME_FEED_CHANNEL} not found")
        return
    count = guild.member_count
    try:
        await ch.send(
            f"👋 {member.mention} just walked into the kitchen!\n\n"
            f"Member **#{count}** 🍜\n\n"
            f"Say what's up in <#general-chat> and grab your seat —\n"
            f"react ✅ in <#rules> to unlock the server."
        )
        jarvis_log.info(f"Welcome feed: posted for {member.display_name} (member #{count})")
    except Exception as exc:
        jarvis_log.error(f"Welcome feed post error: {exc}")


async def _backfill_welcome_feed(guild: discord.Guild):
    """Post a catch-up card listing members who joined in the last 7 days."""
    ch = discord.utils.get(guild.text_channels, name=_WELCOME_FEED_CHANNEL)
    if not ch:
        return
    cutoff = datetime.now(_ET) - timedelta(days=7)
    recent = [
        m for m in guild.members
        if m.joined_at and m.joined_at.replace(tzinfo=None) > cutoff.replace(tzinfo=None)
        and not m.bot
    ]
    if not recent:
        jarvis_log.info("Welcome backfill: no members joined in last 7 days")
        return
    recent.sort(key=lambda m: m.joined_at)
    lines = [f"📋 **KITCHEN BACKFILL — last 7 days** ({len(recent)} members)\n"]
    for m in recent:
        joined_str = m.joined_at.strftime("%b %d") if m.joined_at else "?"
        lines.append(f"• {m.mention}  —  joined {joined_str}")
    lines.append("\nThey're all in. Welcome to the kitchen. 🍜👑")
    try:
        await ch.send("\n".join(lines))
        jarvis_log.info(f"Welcome backfill: posted {len(recent)} recent members")
    except Exception as exc:
        jarvis_log.error(f"Welcome backfill error: {exc}")


# Chain on_member_join to post welcome feed card (DM sequence stays untouched above)
_prev_on_member_join_welcome = client.on_member_join

@client.event
async def on_member_join(member):
    try:
        await _prev_on_member_join_welcome(member)
    except Exception as exc:
        jarvis_log.error(f"on_member_join welcome chain error: {exc}")
    await _post_welcome_feed(member)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 7 — Voice channel auto-announcement for co-founders
# ─────────────────────────────────────────────────────────────────────────────

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.guild.id != GUILD_ID:
        return
    if not _is_cofounder(member):
        return
    ch = _ch(member.guild, "market-talk")
    if not ch:
        return
    try:
        joined   = before.channel is None and after.channel is not None
        left     = before.channel is not None and after.channel is None
        is_stage = after.channel is not None and isinstance(after.channel, discord.StageChannel)

        if joined:
            if is_stage:
                await ch.send(
                    "🎙️ **THE KITCHEN IS LIVE**\n"
                    "Live trading session starting now. Pull up. 🍜👑"
                )
                jarvis_log.info(f"STAGE JOIN: {member.display_name} → #{after.channel.name}")
            else:
                await ch.send(
                    f"🎙️ **LIVE SESSION STARTING**\n"
                    f"{member.display_name} just joined the trading floor.\n\n"
                    f"Get in the kitchen. 🍜👑"
                )
                jarvis_log.info(f"VOICE JOIN: {member.display_name} → #{after.channel.name}")
        elif left:
            await ch.send(
                "📴 **Session ended.**\n"
                "Recap dropping in #trade-recaps shortly. 🍜"
            )
            jarvis_log.info(f"VOICE LEAVE: {member.display_name}")
    except Exception as exc:
        jarvis_log.error(f"Voice announcement error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 8 — Auto-moderator (revised rules)
# ─────────────────────────────────────────────────────────────────────────────
#
# Exempt (no automod at all):  Admin, Moderator, Paid Member
# Free Member:                 loosened rules (see below)
# Unverified:                  strictest treatment
#
# DELETE triggers:
#   • Link + banned phrase together  (classic spam combo, any account)
#   • Link posted by Unverified account
#   • Banned phrase posted by Unverified account
#   • 10+ identical chars in a row (any non-exempt account)
#
# MOD-LOG (no delete, human decides):
#   • Link alone from a Free Member
#   • Banned phrase alone from a Free Member
# ─────────────────────────────────────────────────────────────────────────────

_AUTOMOD_FULL_EXEMPT = {"Admin", "Moderator", "Paid Member"}
_AUTOMOD_UNVERIFIED  = "Unverified"
_BOT_LOGS_CHANNEL    = "bot-logs"

_BANNED_PHRASES = [
    "dm me", "check my profile", "free signals", "guaranteed profit", "100% win rate"
]
_RE_LINK = re.compile(r"https?://", re.IGNORECASE)
_RE_SPAM = re.compile(r"(.)\1{9,}")  # 10+ identical chars in a row


def _automod_tier(member: discord.Member) -> str:
    """Return 'exempt', 'unverified', or 'free'."""
    role_names = {r.name for r in member.roles}
    if role_names & _AUTOMOD_FULL_EXEMPT:
        return "exempt"
    if _AUTOMOD_UNVERIFIED in role_names:
        return "unverified"
    return "free"


async def _automod_delete(message: discord.Message, reason: str):
    try:
        await message.delete()
        jarvis_log.info(
            f"AUTOMOD DELETE [{reason}] {message.author} "
            f"in #{message.channel.name}: {message.content[:80]}"
        )
        await message.author.send(
            "🚫 Your message was removed in The Soup Kitchen.\n"
            "No unsolicited links or promotional content. Keep it clean. 🍜"
        )
    except discord.Forbidden:
        jarvis_log.warning(f"AUTOMOD: could not delete/DM {message.author}")
    except Exception as exc:
        jarvis_log.error(f"AUTOMOD delete error: {exc}")


async def _automod_flag(message: discord.Message, reason: str):
    """Post a note in #bot-logs for a human mod to review — do NOT delete."""
    guild = message.guild
    log_ch = discord.utils.get(guild.text_channels, name=_BOT_LOGS_CHANNEL)
    if not log_ch:
        log_ch = _ch(guild, "mod-chat")  # fallback if bot-logs doesn't exist
    if not log_ch:
        jarvis_log.warning(f"AUTOMOD FLAG [{reason}]: no log channel found")
        return
    try:
        mod_role = discord.utils.get(guild.roles, name="Moderator")
        mention  = mod_role.mention if mod_role else "@Moderator"
        await log_ch.send(
            f"🟡 **AUTOMOD FLAG** — {mention}\n"
            f"**Reason:** {reason}\n"
            f"**User:** {message.author.mention} ({message.author})\n"
            f"**Channel:** {message.channel.mention}\n"
            f"**Message:** {message.jump_url}\n"
            f"```{message.content[:300]}```\n"
            f"React or delete as needed — Jarvis did not remove this."
        )
        jarvis_log.info(
            f"AUTOMOD FLAG [{reason}] {message.author} "
            f"in #{message.channel.name}: {message.content[:80]}"
        )
    except Exception as exc:
        jarvis_log.error(f"AUTOMOD flag error: {exc}")


_prev_on_message_f8 = client.on_message

@client.event
async def on_message(message):
    try:
        await _prev_on_message_f8(message)
    except Exception as exc:
        jarvis_log.error(f"on_message chain error: {exc}")

    if message.author.bot or message.guild is None:
        return
    if message.guild.id != GUILD_ID:
        return

    tier = _automod_tier(message.author)
    if tier == "exempt":
        return

    content = message.content
    lower   = content.lower()

    has_link   = bool(_RE_LINK.search(content))
    has_phrase = any(p in lower for p in _BANNED_PHRASES)
    has_spam   = bool(_RE_SPAM.search(content))

    if has_spam:
        # Hard delete for everyone non-exempt
        await _automod_delete(message, "spam repeat (10+ chars)")
        return

    if tier == "unverified":
        # Stricter — delete on link OR banned phrase alone
        if has_link:
            await _automod_delete(message, "link (Unverified account)")
        elif has_phrase:
            await _automod_delete(message, "banned phrase (Unverified account)")
        return

    # Free Member — only delete when link + phrase appear together
    if has_link and has_phrase:
        await _automod_delete(message, "link + banned phrase combo")
    elif has_link:
        await _automod_flag(message, "link posted (Free Member)")
    elif has_phrase:
        await _automod_flag(message, "banned phrase (Free Member)")


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 10 — /clip slash command
# ─────────────────────────────────────────────────────────────────────────────

@_slash_tree.command(name="clip", description="Clip a message by ID and repost it in #wins")
@_app_commands.describe(message_id="Right-click the message → Copy ID, paste here")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_clip(interaction: discord.Interaction, message_id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        mid = int(message_id)
        ref_msg = await interaction.channel.fetch_message(mid)
    except Exception:
        await interaction.followup.send("❌ Message not found in this channel.", ephemeral=True)
        return

    wins_ch = _ch(interaction.guild, _WINS_CHANNEL)
    if not wins_ch:
        await interaction.followup.send("❌ #wins not found.", ephemeral=True)
        return

    body = (
        f"📸 **KITCHEN CLIP**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{ref_msg.content}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"@{ref_msg.author.display_name} | The Soup Kitchen 🍜👑\n"
        f"discord.gg/soupkitchen"
    )
    await wins_ch.send(body)
    jarvis_log.info(f"CLIP → {wins_ch.name} from {ref_msg.author.display_name}")
    await interaction.followup.send(f"✅ Clipped to {wins_ch.mention}.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Wire slash commands into the client interaction dispatcher
# ─────────────────────────────────────────────────────────────────────────────

@client.event
async def on_interaction(interaction: discord.Interaction):
    await _slash_tree.process_application_commands(interaction)


# ─────────────────────────────────────────────────────────────────────────────
# Final on_ready chain — sync slash commands, start webhook, start schedulers
# ─────────────────────────────────────────────────────────────────────────────

async def _setup_live_trading_stage(guild: discord.Guild):
    """Create 💰 LIVE TRADING 💰 category with Stage + live-chat if not already present."""

    # Step 1 — Verify Community is enabled (required for Stage channels)
    if "COMMUNITY" not in guild.features:
        jarvis_log.warning(
            "SETUP: Guild does not have COMMUNITY feature enabled. "
            "Stage channels require Community mode. "
            "Enable it in Server Settings → Enable Community, then restart the bot."
        )
        print("[Stage] ⚠️  Community not enabled — Stage channel skipped.")
        return

    # Step 2 — Find or create the category, positioned above PAID ALERTS
    cat_name   = "💰 LIVE TRADING 💰"
    stage_name = "🎙️・soup-kitchen-live"
    chat_name  = "💬・live-chat"

    category = discord.utils.get(guild.categories, name=cat_name)
    if not category:
        # Position just above 🔒 PAID ALERTS if it exists
        paid_cat = discord.utils.get(guild.categories, name="🔒 PAID ALERTS")
        position = (paid_cat.position if paid_cat else 0)
        try:
            category = await guild.create_category(cat_name, position=position)
            jarvis_log.info(f"SETUP: Created category '{cat_name}' at position {position}")
            print(f"[Stage] Created category '{cat_name}'")
        except Exception as exc:
            jarvis_log.error(f"SETUP: Failed to create category: {exc}")
            return
    else:
        jarvis_log.info(f"SETUP: Category '{cat_name}' already exists — skipping create")

    # Step 3 — Stage channel permissions
    admin_role = discord.utils.get(guild.roles, name="Admin")
    mod_role   = discord.utils.get(guild.roles, name="Moderator")
    everyone   = guild.default_role

    stage_overwrites = {
        everyone: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False),
    }
    if admin_role:
        stage_overwrites[admin_role] = discord.PermissionOverwrite(
            view_channel=True, connect=True, speak=True,
            mute_members=True, move_members=True, manage_channels=True,
        )
    if mod_role:
        stage_overwrites[mod_role] = discord.PermissionOverwrite(
            view_channel=True, connect=True, speak=True,
            mute_members=True, move_members=True,
        )

    # Create Stage channel if it doesn't exist
    existing_stage = discord.utils.get(guild.stage_channels, name=stage_name)
    if not existing_stage:
        try:
            await guild.create_stage_channel(
                stage_name,
                category=category,
                overwrites=stage_overwrites,
            )
            jarvis_log.info(f"SETUP: Created Stage channel '{stage_name}'")
            print(f"[Stage] Created Stage channel '{stage_name}'")
        except Exception as exc:
            jarvis_log.error(f"SETUP: Failed to create Stage channel: {exc}")
    else:
        jarvis_log.info(f"SETUP: Stage channel '{stage_name}' already exists")

    # Step 4 — Text channel: live-chat
    existing_chat = discord.utils.get(guild.text_channels, name=chat_name)
    if not existing_chat:
        try:
            await guild.create_text_channel(
                chat_name,
                category=category,
                topic="Chat during live trading sessions. Keep it about the trades. 🍜",
            )
            jarvis_log.info(f"SETUP: Created text channel '{chat_name}'")
            print(f"[Stage] Created text channel '{chat_name}'")
        except Exception as exc:
            jarvis_log.error(f"SETUP: Failed to create live-chat: {exc}")
    else:
        jarvis_log.info(f"SETUP: Text channel '{chat_name}' already exists")

    print("[Stage] Live trading stage setup complete.")


_prev_on_ready_f2 = client.on_ready

@client.event
async def on_ready():
    await _prev_on_ready_f2()

    # Live trading stage setup
    try:
        guild = client.get_guild(GUILD_ID)
        if guild:
            await _setup_live_trading_stage(guild)
    except Exception as exc:
        jarvis_log.error(f"Stage setup error: {exc}")

    # Welcome channel setup + backfill
    try:
        guild = client.get_guild(GUILD_ID)
        if guild:
            await _setup_welcome_channel(guild)
            await _backfill_welcome_feed(guild)
    except Exception as exc:
        jarvis_log.error(f"Welcome channel setup error: {exc}")

    # Sync slash commands to guild (instant)
    try:
        guild_obj = discord.Object(id=GUILD_ID)
        synced = await _slash_tree.sync(guild=guild_obj)
        names = [c.name for c in synced]
        jarvis_log.info(f"Slash commands synced: {names}")
        print(f"[Slash] Commands synced: {names}")
    except Exception as exc:
        jarvis_log.error(f"Slash sync failed: {exc}")
        print(f"[Slash] Sync failed: {exc}")

    # Start TradingView webhook server
    asyncio.create_task(_start_webhook_server())

    # Hourly welcome DM checker
    def _dm_job():
        if _bot_loop:
            asyncio.run_coroutine_threadsafe(_check_welcome_dms(), _bot_loop)

    _schedule.every(1).hours.do(_dm_job).tag("content")

    # Friday 5:00 PM ET PnL leaderboard
    def _pnl_job():
        now = datetime.now(_ET)
        if now.weekday() != 4 or now.hour != 17 or now.minute != 0:
            return
        key = f"pnl_lb_{now.date()}"
        if _last_fired.get(key):
            return
        _last_fired[key] = True
        if _bot_loop:
            asyncio.run_coroutine_threadsafe(_post_pnl_leaderboard(), _bot_loop)

    _schedule.every(1).minutes.do(_pnl_job).tag("content")

    _feature_summary = [
        "✅ Feature 1  — Live market context (SPY/QQQ/VIX) injected into all AI posts",
        "✅ Feature 2  — /trade slash command → #live-calls alert + thread",
        "✅ Feature 3  — /watchlist slash command → #watchlist embed",
        "✅ Feature 4  — /pnl slash command + Friday 5:00 PM leaderboard",
        "✅ Feature 5  — TradingView webhook server on port 8080",
        "✅ Feature 6  — 3-DM welcome sequence (DM1 immediate, DM2@24h, DM3@48h)",
        "✅ Feature 7  — Voice channel announcements for co-founders",
        "✅ Feature 8  — Auto-moderator (links, banned phrases, spam repeat)",
        "✅ Feature 9  — Milestone announcements (50/100/250/500/1000 members)",
        "✅ Feature 10 — /clip command → #wins",
    ]
    for line in _feature_summary:
        jarvis_log.info(line)
        print(f"[Features] {line}")



# ═══════════════════════════════════════════════════════════════════════════════
# ─── INDICATOR SYSTEM (Features A–C) ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

_INDICATOR_SETUP_TEXT = """🍜 **LANGSTON VOLATILITY CAPTURE — SETUP GUIDE**

⚙️ **RECOMMENDED SETTINGS**
• "Require 1H structure" → OFF
• All other settings → leave at default
• Chart: works on 30s, 2m, 30m, and 1H

🔔 **ALERTS — ALREADY HANDLED FOR YOU**
You don't need to set up anything. The team's signals post
automatically in #markys-alerts, 24/7, labeled by chart timeframe
(30s ⚡ / 2m 🎯 / 30m 📈 / 1H 🏛).

Just keep notifications ON for #markys-alerts. That's it.

Running the indicator on your own charts? The signal arrows,
labels, and dashboard work out of the box — no alerts needed.

🎯 **HOW WE TRADE THE SIGNALS — READ THIS TWICE**

🔴 **ENTRY:** The RED DOTTED LINE is your entry.
Not the label's entry price — the RED DOTTED LINE.
Let price come back to you. Don't chase the burst.

🛑 **STOP:** If you enter at the red line, the labeled SL is
now YOUR ENTRY — so set your own stop 9 points beyond
your fill. No stop = no trade. Ever.

💰 **PROFIT:** TP levels are guides, not homework.
In profit? Take it ANYTIME. Nobody ever went broke
taking profit. Don't let a green trade turn red waiting
for a target.

This is how the kitchen eats. 🍜

⚠️ Not financial advice. Manage your own risk. 🍜👑"""

_INDICATOR_SYSTEM_PROMPT = """You are Jarvis, the official AI for The Soup Kitchen trading Discord.
You are an expert on the Langston Volatility Capture indicator. Answer questions about it in the
confident, sharp Soup Kitchen voice — concise, practical, no fluff.

INDICATOR KNOWLEDGE BASE:
- 4 market phases: QUIET (sit out), COLLECTING (hunting season — be ready), LEG (the big move is here), STAND DOWN (blocked by structure — don't trade)
- Signals graded ⭐ to ⭐⭐⭐: more stars = signal fired at or through a key level = higher conviction trade
- Labels show: E (entry price), SL (stop loss), T1/T2/T3 (three targets)
- 🚀 LEG signals are runners with wider stops — different trade type than scalps, let them breathe
- Yellow dots = hunting conditions active (COLLECTING phase)
- Orange stepped lines = the collection range — price coiling before the move
- Recommended settings: "Require 1H structure" OFF, run on 30s/2m/30m/1H, minimum ⭐⭐ on the 30-second chart
- ENTRY RULE (emphasize this hard): The RED DOTTED LINE is the entry — NOT the label's entry price. Let price come back. Never chase the burst.
- STOP RULE (emphasize this hard): When you enter at the red dotted line, the labeled SL becomes your entry — so set your actual stop 9 points beyond your fill. No stop = no trade. Ever.
- PROFIT RULE (emphasize this hard): TP levels are guides, not requirements. In profit anytime? Take it. Nobody went broke taking profit. Don't let a green trade turn red waiting for a target.
- If anyone asks about entries, stops, the red line, or how to manage a trade, hammer these three rules clearly and directly.
- Signals post automatically in #markys-alerts labeled by timeframe — members don't set up alerts. If someone specifically asks about webhooks or how alerts are wired, tell them that's admin infrastructure and to ping @Admin.
- Access is invite-only via TradingView — members request access through the server

SETUP GUIDE (full text):
""" + _INDICATOR_SETUP_TEXT + """

Always end answers with: "Not financial advice — manage your risk 🍜"
Keep answers concise (3–6 sentences) unless a detailed walkthrough is needed."""

_INDICATOR_KEYWORDS = {
    "indicator", "langston", "volatility capture", "lvc",
    "alert", "signal", "signals", "settings", "stars",
    "phase", "phases", "quiet", "collecting", "leg", "stand down",
    "webhook", "30s", "2m", "30m", "1h", "entry", "dotted line",
    "yellow dot", "orange line", "wick",
}


async def _get_indicator_ai_response(question: str, username: str) -> str:
    """Call Claude with the indicator system prompt."""
    if not claude_client:
        return "AI is offline right now — check back soon. 🍜"
    try:
        def _call():
            return claude_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                system=_INDICATOR_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"{username} asks: {question}"}],
            )
        resp = await asyncio.to_thread(_call)
        return resp.content[0].text.strip()
    except Exception as exc:
        jarvis_log.error(f"Indicator AI error: {exc}")
        return "Something went wrong on my end — try again in a sec. 🍜"


def _is_indicator_question(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _INDICATOR_KEYWORDS)


# ─── /webhookinfo — admin-only, mod-chat only ────────────────────────────────

@_slash_tree.command(name="webhookinfo", description="Show TradingView webhook URLs (Admin only, #mod-chat only)")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_webhookinfo(interaction: discord.Interaction):
    role_names = {r.name for r in interaction.user.roles}
    if "Admin" not in role_names:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    if interaction.channel.name != _MOD_CHANNEL:
        await interaction.response.send_message("❌ Use this command in #mod-chat only.", ephemeral=True)
        return
    info = (
        "🔐 **TRADINGVIEW WEBHOOK URLS — ADMIN ONLY**\n\n"
        "```\n"
        "30s chart  →  https://jarvis-production-f7c4.up.railway.app/30s\n"
        "2m  chart  →  https://jarvis-production-f7c4.up.railway.app/2m\n"
        "30m chart  →  https://jarvis-production-f7c4.up.railway.app/30m\n"
        "1H  chart  →  https://jarvis-production-f7c4.up.railway.app/1h\n"
        "Legacy     →  https://jarvis-production-f7c4.up.railway.app/\n"
        "```\n"
        "Each URL accepts a TradingView `Any alert() function call` alert.\n"
        "All post to #marky-alerts with @everyone and the timeframe label.\n"
        "Keep these out of public channels. 🍜"
    )
    await interaction.response.send_message(info, ephemeral=True)
    jarvis_log.info(f"WEBHOOKINFO accessed by {interaction.user.display_name}")


# ─── FEATURE A: Timeframe-labeled webhook routes ──────────────────────────────

_TF_LABELS = {
    "30s": "📊 Chart: 30-Second ⚡",
    "1m":  "📊 Chart: 1-Minute ⚡",
    "2m":  "📊 Chart: 2-Minute 🎯",
    "3m":  "📊 Chart: 3-Minute 🎯",
    "30m": "📊 Chart: 30-Minute 📈",
    "1h":  "📊 Chart: 1-Hour 🏛",
}


def _make_tf_handler(tf_label: str):
    """Return an aiohttp handler that injects a timeframe label into the alert."""
    async def _handler(request: _aiohttp_web.Request) -> _aiohttp_web.Response:
        try:
            payload = await request.json()
        except Exception as exc:
            jarvis_log.error(f"Webhook [{tf_label}]: bad JSON — {exc}")
            return _aiohttp_web.Response(status=400, text="Bad JSON")

        ticker  = str(payload.get("ticker", "")).strip().upper()
        action  = str(payload.get("action", "")).strip().upper()
        price   = payload.get("price", "N/A")
        message = payload.get("message", "")

        jarvis_log.info(f"WEBHOOK [{tf_label}]: ticker={ticker} action={action} price={price}")

        if not ticker:
            jarvis_log.error(f"Webhook [{tf_label}]: missing ticker")
            return _aiohttp_web.Response(status=400, text="Missing ticker")

        now_str = datetime.now(_ET).strftime("%I:%M %p ET")

        # Map compact label → prominent header line
        _tf_header_map = {
            "📊 Chart: 30-Second ⚡": "📊 **30-SECOND ⚡ SIGNAL**",
            "📊 Chart: 1-Minute ⚡":  "📊 **1-MINUTE ⚡ SIGNAL**",
            "📊 Chart: 2-Minute 🎯":  "📊 **2-MINUTE 🎯 SIGNAL**",
            "📊 Chart: 3-Minute 🎯":  "📊 **3-MINUTE 🎯 SIGNAL**",
            "📊 Chart: 30-Minute 📈": "📊 **30-MINUTE 📈 SIGNAL**",
            "📊 Chart: 1-Hour 🏛":    "📊 **1-HOUR 🏛 SIGNAL**",
        }
        header_line = _tf_header_map.get(tf_label, f"📊 **{tf_label}**") if tf_label else ""

        body = f"@everyone\n"
        if header_line:
            body += f"{header_line}\n"
        body += (
            f"🔔 **TRADINGVIEW ALERT — ${ticker}**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Action: {action} triggered at ${price}\n"
            f"Message: {message}\n"
            f"Time: {now_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Not financial advice. Manage your risk. 🍜"
        )

        async def _post():
            guild = client.get_guild(GUILD_ID)
            if not guild:
                return
            me = guild.me
            if me and not me.guild_permissions.mention_everyone:
                jarvis_log.warning("PERMISSION WARNING: Jarvis lacks 'Mention @everyone'")
            ch = discord.utils.get(guild.text_channels, name="marky-alerts")
            if not ch:
                try:
                    category = discord.utils.get(guild.categories, name="🔒 PAID ALERTS")
                    ch = await guild.create_text_channel(
                        "marky-alerts",
                        category=category,
                        topic="Marky's live trade signals — Langston Volatility Capture. 🍜",
                    )
                    jarvis_log.info("Created #marky-alerts channel")
                except Exception as exc:
                    jarvis_log.error(f"Could not create #marky-alerts: {exc}")
                    ch = _ch(guild, _LIVE_CALLS_CHANNEL)
            if not ch:
                return
            msg = await ch.send(body, allowed_mentions=discord.AllowedMentions(everyone=True))
            try:
                thread_name = f"${ticker} {tf_label.split(':')[1].strip().split(' ')[0] if tf_label else 'Alert'} Discussion"
                await msg.create_thread(name=thread_name[:100])
            except Exception as exc:
                jarvis_log.warning(f"Webhook thread error: {exc}")

        if _bot_loop:
            asyncio.run_coroutine_threadsafe(_post(), _bot_loop)

        return _aiohttp_web.Response(status=200, text="OK")

    return _handler


# Register the new timeframe routes by patching _start_webhook_server
_orig_start_webhook_server = _start_webhook_server

async def _start_webhook_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        app = _aiohttp_web.Application()

        # Legacy routes (unchanged)
        app.router.add_post("/webhook", _handle_tv_webhook)
        app.router.add_post("/",        _handle_tv_webhook)

        # Timeframe-labeled routes
        for tf, label in _TF_LABELS.items():
            app.router.add_post(f"/{tf}", _make_tf_handler(label))
            jarvis_log.info(f"Webhook route registered: POST /{tf} → {label}")

        runner = _aiohttp_web.AppRunner(app)
        await runner.setup()
        site = _aiohttp_web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        routes = ["/", "/webhook", "/30s", "/2m", "/30m", "/1h"]
        jarvis_log.info(f"Webhook server on 0.0.0.0:{port} — routes: {routes}")
        print(f"[Webhook] Server online — port {port} — routes: {routes}")
    except Exception as exc:
        jarvis_log.error(f"Webhook server failed to start: {exc}")
        print(f"[Webhook] Failed to start: {exc}")


# ─── FEATURE B: /indicator slash command ─────────────────────────────────────

@_slash_tree.command(name="indicator", description="Langston Volatility Capture — setup guide and alert URLs")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_indicator(interaction: discord.Interaction):
    await interaction.response.send_message(_INDICATOR_SETUP_TEXT)
    jarvis_log.info(f"INDICATOR guide sent to {interaction.user.display_name} in #{interaction.channel.name}")


# ─── FEATURE C: Indicator keyword detection in @mention handler ───────────────
# Chain the existing on_message to intercept indicator questions before
# they reach the general AI, routing them to the specialist system prompt.

_prev_on_message_indicator = client.on_message

@client.event
async def on_message(message):
    try:
        await _prev_on_message_indicator(message)
    except Exception as exc:
        jarvis_log.error(f"on_message indicator chain error: {exc}")

    # Only intercept @Jarvis messages that look like indicator questions
    if message.author.bot or message.guild is None:
        return
    if message.guild.id != GUILD_ID:
        return
    if client.user not in message.mentions:
        return

    content = re.sub(r"<@!?\d+>", "", message.content).strip()
    if not content or not _is_indicator_question(content):
        return

    # Skip commands already handled upstream (help, testpost, static commands, market commands)
    content_lower = content.lower()
    skip_prefixes = ("help", "testpost", "price", "technicals", "ta", "options",
                     "flow", "levels", "info", "movers", "sectors", "market",
                     "crypto", "coin", "fear", "greed", "earnings", "news",
                     "calendar", "econ", "prep", "rules", "access", "channels",
                     "gm", "disclaimer")
    if any(content_lower == p or content_lower.startswith(p + " ") for p in skip_prefixes):
        return

    jarvis_log.info(f"INDICATOR Q: {message.author.display_name}: {content[:80]}")
    try:
        async with message.channel.typing():
            answer = await _get_indicator_ai_response(content, message.author.display_name)
        await message.reply(answer, mention_author=False)
    except Exception as exc:
        jarvis_log.error(f"Indicator AI reply error: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# BUILD 1 — TOP TRADER CROWN SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

_TOP_TRADER_ROLE_NAME  = "👑 Top Trader"
_TOP_TRADER_ROLE_COLOR = discord.Color(0xF1C40F)

# Track the pinned leaderboard message so we can unpin it next week
_crown_pinned_msg_id: int = 0


async def _get_or_create_top_trader_role(guild: discord.Guild) -> discord.Role:
    """Return the 👑 Top Trader role, creating it if it doesn't exist."""
    role = discord.utils.get(guild.roles, name=_TOP_TRADER_ROLE_NAME)
    if role:
        return role

    # Position: above Paid Member, below Moderator
    paid_role = discord.utils.get(guild.roles, name="Paid Member")
    position = (paid_role.position + 1) if paid_role else 1

    role = await guild.create_role(
        name=_TOP_TRADER_ROLE_NAME,
        color=_TOP_TRADER_ROLE_COLOR,
        hoist=True,
        reason="Top Trader Crown system initialised",
    )
    # Move to the right position
    try:
        await role.edit(position=position)
    except Exception as exc:
        jarvis_log.warning(f"CROWN: could not reposition role — {exc}")

    jarvis_log.info(f"CROWN: Created role '{_TOP_TRADER_ROLE_NAME}'")
    return role


async def _crown_top_trader():
    """Post leaderboard, then crown the week's top PnL trader."""
    global _crown_pinned_msg_id

    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    wins_ch = _ch(guild, _WINS_CHANNEL)
    if not wins_ch:
        jarvis_log.error("CROWN: #wins channel not found")
        return

    # ── Load PnL data ──
    data    = _pnl_load()
    entries = data.get("entries", [])

    if not entries:
        await wins_ch.send(
            "No PnL logged this week. The throne sits empty. "
            "Log your trades with /pnl. 👑"
        )
        jarvis_log.info("CROWN: No entries this week — throne empty message posted")
        _pnl_save({"entries": [], "week_start": str(_date.today())})
        return

    # ── Build leaderboard ──
    totals: dict = {}
    for e in entries:
        uid = e["user_id"]
        if uid not in totals:
            totals[uid] = {"username": e["username"], "total": 0.0}
        totals[uid]["total"] += e["amount"]

    ranked   = sorted(totals.items(), key=lambda x: x[1]["total"], reverse=True)
    top_uid  = ranked[0][0]
    top_data = ranked[0][1]
    green    = sum(1 for _, v in totals.items() if v["total"] >= 0)
    red      = len(totals) - green

    week_start = data.get("week_start", str(_date.today()))
    medals = ["🥇", "🥈", "🥉"]
    lines  = [
        "🏆 **WEEKLY PNL LEADERBOARD**",
        f"Week of {week_start} — {datetime.now(_ET).strftime('%B %d, %Y')}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, (uid, v) in enumerate(ranked[:10]):
        medal = medals[i] if i < 3 else f"{i + 1}."
        s = "+" if v["total"] >= 0 else ""
        lines.append(f"{medal} @{v['username']}    {s}${v['total']:.0f}")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total members reporting: {len(totals)}",
        f"💚 Green on the week: {green}",
        f"🔴 Red on the week: {red}",
        "━━━━━━━━━━━━━━━━━━━━",
        "Post your trades in the server.",
        "The kitchen runs on proof. 🍜👑",
    ]

    lb_msg = await wins_ch.send("\n".join(lines))
    jarvis_log.info(f"CROWN: Leaderboard posted — {len(totals)} traders")

    # ── Pin leaderboard, unpin last week's ──
    try:
        if _crown_pinned_msg_id:
            try:
                old_msg = await wins_ch.fetch_message(_crown_pinned_msg_id)
                await old_msg.unpin()
                jarvis_log.info(f"CROWN: Unpinned previous leaderboard {_crown_pinned_msg_id}")
            except Exception:
                pass
        await lb_msg.pin()
        _crown_pinned_msg_id = lb_msg.id
        jarvis_log.info(f"CROWN: Pinned new leaderboard {lb_msg.id}")
    except Exception as exc:
        jarvis_log.warning(f"CROWN: pin/unpin error — {exc}")

    # ── Transfer crown ──
    crown_role = await _get_or_create_top_trader_role(guild)

    # Remove from current holder(s)
    for m in guild.members:
        if crown_role in m.roles:
            try:
                await m.remove_roles(crown_role, reason="Weekly crown transfer")
                jarvis_log.info(f"CROWN: Removed from {m.display_name}")
            except Exception as exc:
                jarvis_log.warning(f"CROWN: Could not remove from {m.display_name}: {exc}")

    # Assign to new winner
    winner = guild.get_member(int(top_uid))
    if winner:
        try:
            await winner.add_roles(crown_role, reason="Top Trader of the week")
            jarvis_log.info(f"CROWN: Awarded to {winner.display_name} (${top_data['total']:.0f})")
        except Exception as exc:
            jarvis_log.warning(f"CROWN: Could not assign to {winner.display_name}: {exc}")
    else:
        jarvis_log.warning(f"CROWN: Winner UID {top_uid} not found in guild")

    # ── Crowning announcement ──
    sign   = "+" if top_data["total"] >= 0 else ""
    amount = f"{sign}${top_data['total']:.0f}"
    mention = winner.mention if winner else f"@{top_data['username']}"
    crown_msg = (
        f"👑 **NEW TOP TRADER CROWNED** 👑\n"
        f"{mention} takes the throne with {amount} on the week.\n"
        f"The crown is theirs until next Friday. Come take it. 🍜"
    )
    await wins_ch.send(crown_msg)
    jarvis_log.info("CROWN: Crowning announcement posted")

    # ── Reset PnL for next week ──
    _pnl_save({"entries": [], "week_start": str(_date.today())})


# ═════════════════════════════════════════════════════════════════════════════
# BUILD 2 — STAGE CHANNEL FOR LIVE STREAMING
# (The setup function _setup_live_trading_stage already handles Community
#  check, category, stage channel, and live-chat.  We only need to wire
#  the Build 2 variant with the correct channel name and trigger the
#  general-chat announcement when a co-founder starts a Stage instance.)
# ═════════════════════════════════════════════════════════════════════════════

# The voice-state handler already exists (Feature 7).  We extend it here
# with a chain to catch Stage-instance-started events and post to #general-chat.

_prev_on_voice_b2 = client.on_voice_state_update

@client.event
async def on_voice_state_update(member, before, after):
    try:
        await _prev_on_voice_b2(member, before, after)
    except Exception as exc:
        jarvis_log.error(f"on_voice_state_update build2 chain error: {exc}")

    if member.guild.id != GUILD_ID:
        return
    if not _is_cofounder(member):
        return

    # Co-founder joined a Stage channel (started a session)
    joined_stage = (
        before.channel != after.channel
        and after.channel is not None
        and isinstance(after.channel, discord.StageChannel)
    )
    if not joined_stage:
        return

    guild = member.guild
    general = discord.utils.get(guild.text_channels, name="general-chat")
    if not general:
        general = discord.utils.get(guild.text_channels, name="general")
    if not general:
        jarvis_log.warning("BUILD2: #general-chat not found for stage announcement")
        return

    stage_mention = after.channel.mention if after.channel else "🎙️・SOUP KITCHEN LIVE"
    await general.send(
        f"🎙️ **THE KITCHEN IS LIVE** — pull up to {stage_mention}. 🍜👑"
    )
    jarvis_log.info(f"BUILD2: Stage live announcement posted for {member.display_name}")


# ═════════════════════════════════════════════════════════════════════════════
# BUILD 3 — WIRE EVERYTHING ON READY + POST ANNOUNCEMENT
# ═════════════════════════════════════════════════════════════════════════════

_prev_on_ready_build3 = client.on_ready

@client.event
async def on_ready():
    try:
        await _prev_on_ready_build3()
    except Exception as exc:
        jarvis_log.error(f"on_ready build3 chain error: {exc}")

    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    # Ensure 👑 Top Trader role exists from the start
    try:
        await _get_or_create_top_trader_role(guild)
        jarvis_log.info("BUILD3: 👑 Top Trader role verified/created on startup")
    except Exception as exc:
        jarvis_log.error(f"BUILD3: role setup error: {exc}")

    # Replace the existing Friday leaderboard job with the crown version
    # (schedule the crown job; the plain leaderboard job still exists but
    #  _crown_top_trader does everything _post_pnl_leaderboard did + more)
    import schedule as _sched_b3
    _sched_b3.every().friday.at("17:00").do(
        lambda: asyncio.run_coroutine_threadsafe(_crown_top_trader(), _bot_loop)
    )
    jarvis_log.info("BUILD3: Crown leaderboard job scheduled — Fridays 5:00 PM ET")

    # ── Post Build 3 announcement to #general-chat ──
    general = discord.utils.get(guild.text_channels, name="general-chat")
    if not general:
        general = discord.utils.get(guild.text_channels, name="general")
    if general:
        announcement = (
            "👑 **NEW: THE TOP TRADER CROWN** 👑\n\n"
            "Every Friday at market close, the member with the best logged PnL\n"
            "of the week gets CROWNED — gold name, top of the sidebar,\n"
            "throne held for one full week.\n\n"
            "How to compete:\n"
            "📝 Log your trades all week with /pnl\n"
            "📸 Receipts in #wins make it official\n"
            "🏆 Friday 5:00 PM — the leaderboard drops and the crown moves\n\n"
            "One rule: the crown must be defended every week.\n\n"
            "🎙️ **ALSO NEW: SOUP KITCHEN LIVE**\n"
            "A real stage for live trading sessions — streams, screen shares,\n"
            "market opens, the whole show. Watch for the first session announcement.\n\n"
            "The kitchen just got louder. 🍜👑"
        )
        try:
            await general.send(announcement)
            jarvis_log.info("BUILD3: Announcement posted to #general-chat")
        except Exception as exc:
            jarvis_log.error(f"BUILD3: announcement error: {exc}")
    else:
        jarvis_log.warning("BUILD3: #general-chat not found — announcement skipped")

    print("[Build3] Top Trader Crown + Stage wiring complete.")


# ═════════════════════════════════════════════════════════════════════════════
# UPGRADE 1 — /poll slash command + AI-triggered polls
# ═════════════════════════════════════════════════════════════════════════════

_POLL_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

_poll_allowed_roles = {"Admin", "Moderator"}

def _check_poll_permission(interaction: discord.Interaction) -> bool:
    role_names = {r.name for r in interaction.user.roles}
    return bool(role_names & _poll_allowed_roles)


async def _post_poll(channel: discord.abc.Messageable, question: str, options: list, duration_hours: int = 24):
    """Post a Discord native poll; fall back to reaction embed if it fails."""
    # Clamp duration to Discord's allowed range (1–336 h)
    duration_hours = max(1, min(336, duration_hours))

    # ── Try native Discord Poll (requires discord.py ≥ 2.4) ──
    try:
        answers = [discord.PollAnswer(text=opt) for opt in options]
        poll = discord.Poll(question=question, duration=timedelta(hours=duration_hours), answers=answers)
        await channel.send(poll=poll)
        jarvis_log.info(f"POLL: Native poll posted — '{question}' ({len(options)} options, {duration_hours}h)")
        return
    except Exception as exc:
        jarvis_log.warning(f"POLL: Native poll failed ({exc}) — falling back to reaction embed")

    # ── Fallback: embed with numbered reactions ──
    lines = [f"{_POLL_EMOJI[i]}  {opt}" for i, opt in enumerate(options[:10])]
    embed = discord.Embed(
        title=f"📊 {question}",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"React to vote • Poll closes in {duration_hours}h")
    msg = await channel.send(embed=embed)
    for i in range(len(options[:10])):
        try:
            await msg.add_reaction(_POLL_EMOJI[i])
        except Exception:
            pass
    jarvis_log.info(f"POLL: Reaction fallback poll posted — '{question}'")


@_slash_tree.command(name="poll", description="Create a poll (Admin / Moderator only)")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
@_app_commands.describe(
    question="The poll question",
    options="Comma-separated options (2–10)",
    duration="Duration in hours (default 24)",
)
async def _cmd_poll(
    interaction: discord.Interaction,
    question: str,
    options: str,
    duration: int = 24,
):
    if not _check_poll_permission(interaction):
        await interaction.response.send_message(
            "❌ Only Admins and Moderators can create polls.", ephemeral=True
        )
        return

    parsed = [o.strip() for o in options.split(",") if o.strip()]
    if len(parsed) < 2:
        await interaction.response.send_message(
            "❌ Provide at least 2 comma-separated options.", ephemeral=True
        )
        return
    if len(parsed) > 10:
        await interaction.response.send_message(
            "❌ Maximum 10 options allowed.", ephemeral=True
        )
        return

    await interaction.response.send_message(f"⏳ Creating poll…", ephemeral=True)
    await _post_poll(interaction.channel, question, parsed, duration)
    jarvis_log.info(f"POLL: /poll used by {interaction.user.display_name}")


async def _ai_generate_poll(topic: str, channel: discord.abc.Messageable):
    """Ask Claude to generate a poll question + options, then post it."""
    if not ANTHROPIC_API_KEY:
        await channel.send("❌ AI poll generation is unavailable — API key not set.")
        return

    import anthropic as _ant
    _ac = _ant.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        f"You are creating a Discord poll for a trading community called The Soup Kitchen. "
        f"Generate a poll about: {topic}\n\n"
        f"Respond ONLY in this exact format (no other text):\n"
        f"QUESTION: <the poll question>\n"
        f"OPTIONS: <option1>, <option2>, <option3>\n\n"
        f"2–5 options. Keep it trading/finance focused and concise."
    )
    resp = await _ac.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    question, options_str = "", ""
    for line in text.splitlines():
        if line.startswith("QUESTION:"):
            question = line.split("QUESTION:", 1)[1].strip()
        elif line.startswith("OPTIONS:"):
            options_str = line.split("OPTIONS:", 1)[1].strip()

    if not question or not options_str:
        await channel.send("❌ Couldn't generate poll — AI response was malformed.")
        return

    parsed = [o.strip() for o in options_str.split(",") if o.strip()]
    if len(parsed) < 2:
        await channel.send("❌ AI didn't return enough options to make a poll.")
        return

    await _post_poll(channel, question, parsed, 24)


# ═════════════════════════════════════════════════════════════════════════════
# UPGRADE 2 — Live ForexFactory calendar
# ═════════════════════════════════════════════════════════════════════════════

_FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_CALENDAR_CHANNEL = "jarvis-calendar"
_FREE_ANALYSIS_CATEGORY = "FREE ANALYSIS"

# Keywords that should trigger live calendar context injection
_CALENDAR_KEYWORDS = {
    "calendar", "earnings", "red folder", "news this week", "fomc",
    "cpi", "nfp", "economic", "fed", "jobs report", "pce", "gdp",
    "unemployment", "retail sales", "ppi", "ism", "interest rate",
    "week ahead", "this week", "macro",
}


async def _fetch_ff_calendar() -> list:
    """
    Fetch ForexFactory this-week calendar. Returns list of high-impact USD events.
    Each item: {title, date, time, country, impact, forecast, previous}
    Returns empty list on failure (caller must handle).
    """
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.get(
                _FF_CALENDAR_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=_aiohttp.ClientTimeout(total=10),
                ssl=True,
            ) as resp:
                if resp.status != 200:
                    jarvis_log.warning(f"CALENDAR: Feed returned HTTP {resp.status}")
                    return []
                data = await resp.json(content_type=None)

        # Log first entry on first fetch to confirm field names in Railway logs
        if data:
            jarvis_log.info(f"CALENDAR: Feed fields sample: {list(data[0].keys())} | impact values: {set(e.get('impact','') for e in data[:20])}")

        # ForexFactory uses "High" for impact; country "USD"
        high_usd = [
            e for e in data
            if e.get("country", "").upper() == "USD"
            and e.get("impact", "").lower() in ("high", "red")
        ]
        jarvis_log.info(f"CALENDAR: {len(high_usd)} USD high-impact events fetched")
        return high_usd
    except Exception as exc:
        jarvis_log.error(f"CALENDAR: Fetch failed — {exc}")
        return []


def _format_calendar_events(events: list, week_label: str = "") -> str:
    """Format a list of FF events into the red-folder block."""
    if not week_label:
        week_label = datetime.now(_ET).strftime("%B %d, %Y")

    if not events:
        return (
            f"📅 **THIS WEEK'S RED FOLDER** — {week_label}\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "No high-impact USD events found this week — or the feed is down.\n"
            "Check ForexFactory directly. 🍜\n"
            "━━━━━━━━━━━━━━━━━━━"
        )

    lines = [
        f"📅 **THIS WEEK'S RED FOLDER** — {week_label}",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    for e in events:
        # FF date field: "2025-07-21T00:00:00-05:00" or similar ISO string
        raw_date = e.get("date", "")
        raw_time = e.get("time", "")
        title    = e.get("title", e.get("name", "Unknown Event"))
        try:
            import dateutil.parser as _dup
            dt = _dup.parse(raw_date)
            day_str  = dt.strftime("%A")
            date_str = dt.strftime("%b %d")
        except Exception:
            day_str  = raw_date[:10] if raw_date else "TBD"
            date_str = ""
        time_str = raw_time if raw_time else "All Day"
        lines.append(f"🔴 **{day_str} {date_str}** {time_str} ET — {title}")

    lines += [
        "━━━━━━━━━━━━━━━━━━━",
        "Trade around these or don't trade them at all. 🍜",
    ]
    return "\n".join(lines)


@_slash_tree.command(name="calendar", description="This week's red-folder economic events")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_calendar(interaction: discord.Interaction):
    await interaction.response.defer()
    events = await _fetch_ff_calendar()
    if events is None:
        await interaction.followup.send(
            "Calendar feed is down — check ForexFactory directly. 🍜"
        )
        return
    week_label = datetime.now(_ET).strftime("week of %B %d, %Y")
    text = _format_calendar_events(events, week_label)
    await interaction.followup.send(text)
    jarvis_log.info(f"CALENDAR: /calendar used by {interaction.user.display_name}")


async def _get_calendar_context() -> str:
    """Return a concise calendar context string to inject into AI prompts."""
    events = await _fetch_ff_calendar()
    if not events:
        return ""
    lines = ["HIGH-IMPACT USD ECONOMIC EVENTS THIS WEEK (live data):"]
    for e in events:
        raw_date = e.get("date", "")
        raw_time = e.get("time", "")
        title    = e.get("title", e.get("name", "?"))
        try:
            import dateutil.parser as _dup
            dt = _dup.parse(raw_date)
            day_str = dt.strftime("%A %b %d")
        except Exception:
            day_str = raw_date[:10]
        forecast = e.get("forecast", "")
        previous = e.get("previous", "")
        detail   = f" (forecast: {forecast}, prev: {previous})" if forecast or previous else ""
        lines.append(f"  • {day_str} {raw_time} ET — {title}{detail}")
    return "\n".join(lines)


def _is_calendar_question(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _CALENDAR_KEYWORDS)


# Chain the @mention handler to inject live calendar context for calendar questions
_prev_on_message_cal = client.on_message

@client.event
async def on_message(message):
    try:
        await _prev_on_message_cal(message)
    except Exception as exc:
        jarvis_log.error(f"on_message calendar chain error: {exc}")

    if message.author.bot or message.guild is None or message.guild.id != GUILD_ID:
        return
    if client.user not in message.mentions:
        return

    content = re.sub(r"<@!?\d+>", "", message.content).strip()
    if not content or not _is_calendar_question(content):
        return

    # Skip if it's also an indicator question (already handled upstream)
    if _is_indicator_question(content):
        return

    jarvis_log.info(f"CALENDAR Q: {message.author.display_name}: {content[:80]}")
    async with message.channel.typing():
        cal_ctx = await _get_calendar_context()
        if not cal_ctx:
            await message.reply(
                "Calendar feed is down right now — check ForexFactory directly. 🍜",
                mention_author=False,
            )
            return

        full_prompt = (
            f"{cal_ctx}\n\n"
            f"Answer this question using ONLY the live data above — never use training-data dates: "
            f"{content}"
        )
        try:
            answer = await _gen_content(full_prompt)
            await message.reply(answer, mention_author=False)
        except Exception as exc:
            jarvis_log.error(f"CALENDAR AI reply error: {exc}")


async def _post_weekly_calendar():
    """Sunday 7:30 PM ET — post red-folder rundown to #jarvis-calendar."""
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    # Find or create #jarvis-calendar in FREE ANALYSIS category
    ch = discord.utils.get(guild.text_channels, name=_CALENDAR_CHANNEL)
    if not ch:
        cat = discord.utils.get(guild.categories, name=_FREE_ANALYSIS_CATEGORY)
        try:
            ch = await guild.create_text_channel(
                _CALENDAR_CHANNEL,
                category=cat,
                topic="Weekly red-folder economic calendar — auto-posted every Sunday. 🍜",
            )
            jarvis_log.info(f"CALENDAR: Created #{_CALENDAR_CHANNEL}")
        except Exception as exc:
            jarvis_log.error(f"CALENDAR: Could not create #{_CALENDAR_CHANNEL}: {exc}")
            return

    events = await _fetch_ff_calendar()
    week_label = datetime.now(_ET).strftime("week of %B %d, %Y")
    text = _format_calendar_events(events, week_label)
    await ch.send(text)
    jarvis_log.info("CALENDAR: Weekly calendar posted")


# Wire the Sunday 7:30 PM schedule into the existing on_ready chain
_prev_on_ready_cal = client.on_ready

@client.event
async def on_ready():
    try:
        await _prev_on_ready_cal()
    except Exception as exc:
        jarvis_log.error(f"on_ready calendar chain error: {exc}")

    import schedule as _sched_cal
    _sched_cal.every().sunday.at("19:30").do(
        lambda: asyncio.run_coroutine_threadsafe(_post_weekly_calendar(), _bot_loop)
    )
    jarvis_log.info("CALENDAR: Sunday 7:30 PM ET calendar job scheduled")
    print("[Calendar] Weekly calendar job scheduled.")


# ═════════════════════════════════════════════════════════════════════════════
# SCOREBOARD — /scoreboard command + 🔥 Most Consistent role
# ═════════════════════════════════════════════════════════════════════════════

_CONSISTENT_ROLE_NAME  = "🔥 Most Consistent"
_CONSISTENT_ROLE_COLOR = discord.Color(0xE67E22)


def _build_scoreboard_data(entries: list) -> tuple:
    """
    Returns (pnl_ranked, consistency_ranked, total_traders) from raw entries.

    pnl_ranked: list of (uid, {username, total}) sorted by total desc
    consistency_ranked: list of (uid, {username, green_days, logged_days, total})
      sorted by green_days desc, then green_ratio desc, then total desc
    """
    pnl_totals: dict = {}
    consistency: dict = {}

    for e in entries:
        uid      = e["user_id"]
        username = e["username"]
        amount   = e["amount"]
        # Extract calendar date from timestamp or 'day' field
        ts = e.get("timestamp", "")
        try:
            day_key = ts[:10]  # "YYYY-MM-DD"
        except Exception:
            day_key = e.get("day", "unknown")

        # PnL totals
        if uid not in pnl_totals:
            pnl_totals[uid] = {"username": username, "total": 0.0}
        pnl_totals[uid]["total"] += amount

        # Consistency: per-day tracking
        if uid not in consistency:
            consistency[uid] = {"username": username, "green_days": set(), "all_days": set(), "total": 0.0}
        consistency[uid]["all_days"].add(day_key)
        if amount > 0:
            consistency[uid]["green_days"].add(day_key)
        consistency[uid]["total"] += amount

    pnl_ranked = sorted(pnl_totals.items(), key=lambda x: x[1]["total"], reverse=True)

    # Flatten sets to counts for sorting
    con_list = [
        (uid, {
            "username":    v["username"],
            "green_days":  len(v["green_days"]),
            "logged_days": len(v["all_days"]),
            "total":       v["total"],
            "ratio":       len(v["green_days"]) / len(v["all_days"]) if v["all_days"] else 0.0,
        })
        for uid, v in consistency.items()
    ]
    con_ranked = sorted(
        con_list,
        key=lambda x: (x[1]["green_days"], x[1]["ratio"], x[1]["total"]),
        reverse=True,
    )

    return pnl_ranked, con_ranked, len(pnl_totals)


@_slash_tree.command(name="scoreboard", description="Live kitchen scoreboard — PnL + consistency rankings")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_scoreboard(interaction: discord.Interaction):
    await interaction.response.defer()

    data    = _pnl_load()
    entries = data.get("entries", [])

    if not entries:
        await interaction.followup.send(
            "Scoreboard's empty — be the first. Log a trade with /pnl. 🍜"
        )
        return

    pnl_ranked, con_ranked, total_traders = _build_scoreboard_data(entries)
    week_start = data.get("week_start", str(_date.today()))
    medals = ["🥇", "🥈", "🥉"]

    # ── PnL section ──
    pnl_lines = ["💰 **TOP PNL (this week)**"]
    for i, (uid, v) in enumerate(pnl_ranked[:5]):
        medal = medals[i] if i < 3 else f"   {i + 1}."
        s = "+" if v["total"] >= 0 else ""
        pnl_lines.append(f"{medal} @{v['username']}    {s}${v['total']:,.0f}")

    # ── Consistency section ──
    con_lines = ["🔥 **MOST CONSISTENT (this week)**"]
    for i, (uid, v) in enumerate(con_ranked[:3]):
        medal = medals[i] if i < 3 else f"{i + 1}."
        con_lines.append(
            f"{medal} @{v['username']}    {v['green_days']} green days / {v['logged_days']} logged"
        )

    # ── Crown holder ──
    guild = interaction.guild
    crown_role = discord.utils.get(guild.roles, name=_TOP_TRADER_ROLE_NAME) if guild else None
    crown_holder = None
    if crown_role and guild:
        holders = [m for m in guild.members if crown_role in m.roles]
        crown_holder = holders[0].display_name if holders else None

    sep = "━━━━━━━━━━━━━━━━━━━━━━━"
    body = "\n".join([
        f"🏆 **THE KITCHEN SCOREBOARD — week of {week_start}**",
        sep,
        *pnl_lines,
        sep,
        *con_lines,
        sep,
        f"📊 {total_traders} trader{'s' if total_traders != 1 else ''} logged this week",
        f"👑 Current crown holder: {'@' + crown_holder if crown_holder else 'unclaimed'}",
        "⏳ Leaderboard locks Friday 5:00 PM ET",
        sep,
        "Log yours with /pnl — receipts in #wins. 🍜",
    ])

    await interaction.followup.send(body)
    jarvis_log.info(f"SCOREBOARD: /scoreboard used by {interaction.user.display_name}")


async def _get_or_create_consistent_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name=_CONSISTENT_ROLE_NAME)
    if role:
        return role
    paid_role = discord.utils.get(guild.roles, name="Paid Member")
    position  = (paid_role.position + 1) if paid_role else 1
    role = await guild.create_role(
        name=_CONSISTENT_ROLE_NAME,
        color=_CONSISTENT_ROLE_COLOR,
        hoist=True,
        reason="Most Consistent trader role initialised",
    )
    try:
        await role.edit(position=position)
    except Exception as exc:
        jarvis_log.warning(f"CONSISTENT: could not reposition role — {exc}")
    jarvis_log.info(f"CONSISTENT: Created role '{_CONSISTENT_ROLE_NAME}'")
    return role


# Extend _crown_top_trader to also award 🔥 Most Consistent
_orig_crown_top_trader = _crown_top_trader

async def _crown_top_trader():
    """Run original crown logic, then also award the consistency role."""
    # The original already handles PnL load, leaderboard post, pin, PnL reset.
    # We need the data BEFORE the reset, so we load it first.
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    data    = _pnl_load()
    entries = data.get("entries", [])

    # Run original (it resets pnl at the end)
    await _orig_crown_top_trader()

    if not entries:
        return  # original already posted "throne empty"

    wins_ch = _ch(guild, _WINS_CHANNEL)
    if not wins_ch:
        return

    _, con_ranked, _ = _build_scoreboard_data(entries)
    if not con_ranked:
        return

    con_uid, con_data = con_ranked[0]
    con_role = await _get_or_create_consistent_role(guild)

    # Strip from prior holder
    for m in guild.members:
        if con_role in m.roles:
            try:
                await m.remove_roles(con_role, reason="Weekly consistency crown transfer")
            except Exception as exc:
                jarvis_log.warning(f"CONSISTENT: remove error — {exc}")

    # Award to new winner
    con_winner = guild.get_member(int(con_uid))
    if con_winner:
        try:
            await con_winner.add_roles(con_role, reason="Most Consistent trader of the week")
        except Exception as exc:
            jarvis_log.warning(f"CONSISTENT: assign error — {exc}")
    else:
        jarvis_log.warning(f"CONSISTENT: winner UID {con_uid} not in guild")

    mention   = con_winner.mention if con_winner else f"@{con_data['username']}"
    gd        = con_data["green_days"]
    ld        = con_data["logged_days"]
    await wins_ch.send(
        f"🔥 **MOST CONSISTENT TRADER** 🔥\n"
        f"{mention} showed up {gd} green day{'s' if gd != 1 else ''} out of {ld} logged.\n"
        f"Consistency beats luck. Hold it down until next Friday. 🍜"
    )
    jarvis_log.info(f"CONSISTENT: Awarded to {con_data['username']} ({gd}/{ld} green days)")


# ── Ensure consistency role exists on startup ──
_prev_on_ready_scoreboard = client.on_ready

@client.event
async def on_ready():
    try:
        await _prev_on_ready_scoreboard()
    except Exception as exc:
        jarvis_log.error(f"on_ready scoreboard chain error: {exc}")

    guild = client.get_guild(GUILD_ID)
    if guild:
        try:
            await _get_or_create_consistent_role(guild)
            jarvis_log.info("SCOREBOARD: 🔥 Most Consistent role verified/created on startup")
        except Exception as exc:
            jarvis_log.error(f"SCOREBOARD: role setup error: {exc}")
    print("[Scoreboard] /scoreboard registered, consistency role ready.")


# ═════════════════════════════════════════════════════════════════════════════
# PAID WALL INFRASTRUCTURE
# ═════════════════════════════════════════════════════════════════════════════
#
# Two modes:
#   OPEN  — Free Member gets same access as Paid Member (current state)
#   PAID  — Free Member is explicitly denied on all paid channels/categories
#
# /paidwall on   → enforce paid wall  (Admin only)
# /paidwall off  → open mode          (Admin only)
#
# Mode persists in paidwall_mode.json and is enforced on every bot startup.
# ─────────────────────────────────────────────────────────────────────────────

_PAIDWALL_FILE = "paidwall_mode.json"

# Categories and channel name fragments considered "paid" content
_PAID_CATEGORY_NAMES = {
    "🔒 paid alerts", "paid alerts", "paid", "premium", "vip",
    "💰 live trading", "💰 live trading 💰",
}
_PAID_CHANNEL_NAMES = {"long-term-plays", "marky-alerts", "live-calls", "watchlist"}


def _paidwall_load() -> str:
    """Return 'open' or 'paid'. Defaults to 'open'."""
    try:
        with open(_PAIDWALL_FILE) as f:
            return _json.load(f).get("mode", "open")
    except (FileNotFoundError, _json.JSONDecodeError):
        return "open"


def _paidwall_save(mode: str):
    try:
        with open(_PAIDWALL_FILE, "w") as f:
            _json.dump({"mode": mode}, f)
    except Exception as exc:
        jarvis_log.error(f"PAIDWALL: save error — {exc}")


def _is_paid_channel(ch) -> bool:
    """Return True if a channel belongs to a paid category or is a known paid channel."""
    if ch.category and ch.category.name.lower() in _PAID_CATEGORY_NAMES:
        return True
    if ch.name.lower() in _PAID_CHANNEL_NAMES:
        return True
    return False


async def _apply_paidwall(guild: discord.Guild, mode: str):
    """
    Iterate every channel and set Free Member overwrite:
      mode='open' → Free Member: view_channel=True, send_messages=True  (same as Paid)
      mode='paid' → Free Member: view_channel=False (explicit deny)
    """
    free_role = discord.utils.get(guild.roles, name=FREE_MEMBER_ROLE)
    if not free_role:
        jarvis_log.error("PAIDWALL: Free Member role not found — cannot apply mode")
        return

    if mode == "open":
        overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    else:
        overwrite = discord.PermissionOverwrite(view_channel=False)

    changed = 0
    for ch in guild.channels:
        if not _is_paid_channel(ch):
            continue
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
            continue
        try:
            await ch.set_permissions(free_role, overwrite=overwrite,
                                     reason=f"Paid wall set to {mode.upper()}")
            changed += 1
            jarvis_log.info(f"PAIDWALL: #{ch.name} → Free Member {mode}")
        except Exception as exc:
            jarvis_log.warning(f"PAIDWALL: Could not update #{ch.name}: {exc}")

    _paidwall_save(mode)
    jarvis_log.info(f"PAIDWALL: Mode set to {mode.upper()} — {changed} channels updated")
    return changed


@_slash_tree.command(name="paidwall", description="Toggle paid wall — Admin only")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
@_app_commands.describe(mode="'on' to enforce paid wall, 'off' for open access")
async def _cmd_paidwall(interaction: discord.Interaction, mode: str):
    role_names = {r.name for r in interaction.user.roles}
    if "Admin" not in role_names:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    mode = mode.strip().lower()
    if mode not in ("on", "off"):
        await interaction.response.send_message(
            "❌ Use `/paidwall on` or `/paidwall off`.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    wall_mode = "paid" if mode == "on" else "open"
    changed   = await _apply_paidwall(interaction.guild, wall_mode)

    if wall_mode == "paid":
        summary = (
            f"🔒 **Paid wall is ON** — {changed} paid channels locked.\n"
            f"Free Members can no longer see paid content.\n"
            f"To reopen: `/paidwall off`"
        )
    else:
        summary = (
            f"🔓 **Paid wall is OFF** — {changed} paid channels opened.\n"
            f"Free Members now see everything (open mode).\n"
            f"To lock: `/paidwall on`"
        )

    await interaction.followup.send(summary, ephemeral=True)

    # Also log to #bot-logs so there's a record
    try:
        log_ch = discord.utils.get(interaction.guild.text_channels, name="bot-logs")
        if log_ch:
            emoji = "🔒" if wall_mode == "paid" else "🔓"
            await log_ch.send(
                f"{emoji} **Paid wall changed to `{wall_mode.upper()}`** by "
                f"{interaction.user.mention} — {changed} channels updated."
            )
    except Exception:
        pass

    jarvis_log.info(
        f"PAIDWALL: {interaction.user.display_name} set mode to {wall_mode.upper()}"
    )


# Enforce stored mode on startup
_prev_on_ready_paidwall = client.on_ready

@client.event
async def on_ready():
    try:
        await _prev_on_ready_paidwall()
    except Exception as exc:
        jarvis_log.error(f"on_ready paidwall chain error: {exc}")

    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    stored_mode = _paidwall_load()
    jarvis_log.info(f"PAIDWALL: Startup — enforcing stored mode: {stored_mode.upper()}")
    await _apply_paidwall(guild, stored_mode)
    print(f"[PaidWall] Mode on startup: {stored_mode.upper()} — permissions enforced.")


# ═════════════════════════════════════════════════════════════════════════════
# REFERRAL-GATED GIVEAWAY SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

import random as _random

_REFERRALS_FILE      = "referrals.json"
_GIVEAWAY_FILE       = "giveaway.json"
_GIVEAWAY_RESULTS_FILE = "giveaway_results.json"

# In-memory invite cache: {invite_code: use_count}
_invite_cache: dict = {}

# Per-member invite codes we created: {member_id: invite_code}
_member_invite_codes: dict = {}


# ─── JSON helpers ────────────────────────────────────────────────────────────

def _ref_load() -> dict:
    """Load referrals.json → {inviter_id: [invited_user_ids]}"""
    try:
        with open(_REFERRALS_FILE) as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {}

def _ref_save(data: dict):
    with open(_REFERRALS_FILE, "w") as f:
        _json.dump(data, f, indent=2)

def _giveaway_load() -> dict:
    try:
        with open(_GIVEAWAY_FILE) as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {}

def _giveaway_save(data: dict):
    with open(_GIVEAWAY_FILE, "w") as f:
        _json.dump(data, f, indent=2)


# ─── Invite cache helpers ─────────────────────────────────────────────────────

async def _refresh_invite_cache(guild: discord.Guild):
    """Snapshot current invite use counts into _invite_cache."""
    global _invite_cache
    try:
        invites = await guild.invites()
        _invite_cache = {inv.code: inv.uses for inv in invites}
    except discord.Forbidden:
        jarvis_log.error("GIVEAWAY: Missing 'Manage Server' permission — cannot read invites")


async def _detect_inviter(guild: discord.Guild) -> discord.Invite | None:
    """
    Compare current invite counts against cache to find which invite was just used.
    Returns the Invite object (with .inviter) or None.
    """
    try:
        current_invites = await guild.invites()
    except discord.Forbidden:
        return None

    for inv in current_invites:
        cached = _invite_cache.get(inv.code, 0)
        if inv.uses > cached:
            return inv
    return None


# ─── on_member_join chain — detect inviter ───────────────────────────────────

_prev_on_member_join_giveaway = client.on_member_join

@client.event
async def on_member_join(member: discord.Member):
    try:
        await _prev_on_member_join_giveaway(member)
    except Exception as exc:
        jarvis_log.error(f"on_member_join giveaway chain error: {exc}")

    if member.guild.id != GUILD_ID:
        return

    # Detect which invite was used BEFORE refreshing the cache
    used_invite = await _detect_inviter(member.guild)
    await _refresh_invite_cache(member.guild)   # update cache for next join

    if used_invite and used_invite.inviter and used_invite.inviter.id != member.id:
        inviter_id = str(used_invite.inviter.id)
        jarvis_log.info(
            f"GIVEAWAY: {member.display_name} joined via invite by "
            f"{used_invite.inviter.display_name} (code: {used_invite.code})"
        )
        # Store pending — only counted once they verify
        refs = _ref_load()
        pending = refs.setdefault("_pending", {})
        pending[str(member.id)] = inviter_id
        _ref_save(refs)


# ─── Verification hook — count only verified members ─────────────────────────
# Chains on_raw_reaction_add: when someone reacts ✅ on #rules, they get
# Free Member. At that point we move them from _pending → confirmed.

_prev_on_raw_reaction_add_giveaway = client.on_raw_reaction_add

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    try:
        await _prev_on_raw_reaction_add_giveaway(payload)
    except Exception as exc:
        jarvis_log.error(f"on_raw_reaction_add giveaway chain error: {exc}")

    if payload.guild_id != GUILD_ID:
        return
    if str(payload.emoji) != VERIFY_EMOJI:
        return
    if payload.message_id != verification_message_id:
        return

    member_id = str(payload.user_id)
    refs = _ref_load()
    pending = refs.get("_pending", {})

    if member_id not in pending:
        return  # didn't come from a tracked invite

    inviter_id = pending.pop(member_id)
    confirmed  = refs.setdefault(inviter_id, [])
    if member_id not in confirmed:
        confirmed.append(member_id)
        jarvis_log.info(
            f"GIVEAWAY: Member {member_id} verified — counted for inviter {inviter_id} "
            f"(total: {len(confirmed)})"
        )

    refs["_pending"] = pending
    _ref_save(refs)

    # ── Anti-abuse: flag to #mod-chat if suspicious ──────────────────────────
    guild = client.get_guild(GUILD_ID)
    if guild:
        await _check_invite_abuse(guild, inviter_id, confirmed)


async def _check_invite_abuse(guild: discord.Guild, inviter_id: str, confirmed_ids: list):
    """Flag suspicious invite patterns to #mod-chat for human review."""
    if len(confirmed_ids) < 3:
        return  # not worth flagging until there's volume

    # Check timestamps of recent joins (members in guild within last 30 min)
    recent_cutoff = datetime.now(_ET) - timedelta(minutes=30)
    recent_count  = 0
    for uid in confirmed_ids[-5:]:  # check last 5 invitees
        try:
            m = guild.get_member(int(uid))
            if m and m.joined_at and m.joined_at.replace(tzinfo=None) > recent_cutoff.replace(tzinfo=None):
                recent_count += 1
        except Exception:
            pass

    if recent_count >= 3:
        mod_ch = discord.utils.get(guild.text_channels, name=_MOD_CHANNEL)
        if mod_ch:
            inviter = guild.get_member(int(inviter_id))
            name    = inviter.mention if inviter else f"<@{inviter_id}>"
            await mod_ch.send(
                f"⚠️ **Suspicious invite pattern** — {name} had {recent_count} invitees "
                f"verify within the last 30 minutes ({len(confirmed_ids)} total). "
                f"Review before the giveaway draw. 🍜"
            )
            jarvis_log.warning(
                f"GIVEAWAY: Abuse flag — inviter {inviter_id} had {recent_count} rapid joins"
            )


# ─── /giveaway-create ────────────────────────────────────────────────────────

@_slash_tree.command(name="giveaway-create", description="Create a referral giveaway (Admin, #mod-chat only)")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
@_app_commands.describe(
    prize="What the winner receives",
    required_invites="Verified invites needed to enter (default 3)",
    duration_days="How many days the giveaway runs",
)
async def _cmd_giveaway_create(
    interaction: discord.Interaction,
    prize: str,
    duration_days: int,
    required_invites: int = 3,
):
    role_names = {r.name for r in interaction.user.roles}
    if "Admin" not in role_names:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    if interaction.channel.name != _MOD_CHANNEL:
        await interaction.response.send_message(
            f"❌ Run this in #{_MOD_CHANNEL}.", ephemeral=True
        )
        return

    end_dt   = datetime.now(_ET) + timedelta(days=duration_days)
    end_str  = end_dt.strftime("%B %d, %Y")

    giveaway = {
        "prize":            prize,
        "required_invites": required_invites,
        "end_date":         end_dt.isoformat(),
        "end_str":          end_str,
        "created_by":       str(interaction.user.id),
        "active":           True,
    }
    _giveaway_save(giveaway)

    # Post to #announcements
    guild = interaction.guild
    ann_ch = discord.utils.get(guild.text_channels, name="announcements")
    if not ann_ch:
        ann_ch = discord.utils.get(guild.text_channels, name="general-chat")

    embed = discord.Embed(
        title=f"🎁 GIVEAWAY — {prize.upper()} 🎁",
        color=discord.Color.gold(),
    )
    embed.description = (
        "━━━━━━━━━━━━━━━━━━━\n"
        f"To enter: invite **{required_invites} people** to The Soup Kitchen who verify in.\n\n"
        "📨 Get your personal invite link with `/myinvite`\n"
        "📊 Check your progress with `/mygiveaway`\n\n"
        f"Winner drawn **{end_str}**. 🍜👑"
    )
    embed.set_footer(text="Only verified members count. Bring real traders. 🍜")

    if ann_ch:
        await ann_ch.send(embed=embed)

    await interaction.response.send_message(
        f"✅ Giveaway created — posted to #{ann_ch.name if ann_ch else 'announcements'}. "
        f"Ends {end_str}. Need {required_invites} verified invites.",
        ephemeral=True,
    )
    jarvis_log.info(
        f"GIVEAWAY: Created by {interaction.user.display_name} — "
        f"prize: {prize}, invites: {required_invites}, days: {duration_days}"
    )


# ─── /myinvite ───────────────────────────────────────────────────────────────

@_slash_tree.command(name="myinvite", description="Get your personal giveaway invite link")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_myinvite(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild   = interaction.guild
    member  = interaction.user
    mid_str = str(member.id)

    # Check if we already made one for them
    existing_code = _member_invite_codes.get(mid_str)
    if existing_code:
        # Verify it still exists
        try:
            invites = await guild.invites()
            match   = next((i for i in invites if i.code == existing_code), None)
            if match:
                inv = match
            else:
                existing_code = None
        except discord.Forbidden:
            existing_code = None

    if not existing_code:
        # Create a fresh permanent invite in #general-chat or #rules
        target_ch = (
            discord.utils.get(guild.text_channels, name="general-chat")
            or discord.utils.get(guild.text_channels, name="rules")
            or guild.text_channels[0]
        )
        try:
            inv = await target_ch.create_invite(
                max_age=0,        # never expires
                max_uses=0,       # unlimited uses
                unique=True,
                reason=f"Giveaway invite for {member.display_name}",
            )
            _member_invite_codes[mid_str] = inv.code
            # Persist code so it survives Railway restarts
            refs = _ref_load()
            refs.setdefault("_invite_codes", {})[mid_str] = inv.code
            _ref_save(refs)
            jarvis_log.info(f"GIVEAWAY: Created invite {inv.code} for {member.display_name}")
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Jarvis doesn't have permission to create invites. "
                "Ask an Admin to grant **Create Invite** permission.",
                ephemeral=True,
            )
            return

    giveaway = _giveaway_load()
    needed   = giveaway.get("required_invites", 3)
    refs     = _ref_load()
    my_count = len(refs.get(mid_str, []))

    try:
        await member.send(
            f"🎁 **Your personal invite link:**\n"
            f"https://discord.gg/{inv.code}\n\n"
            f"Share this link. Every person who joins through it AND verifies "
            f"(reacts ✅ in #rules) counts toward your giveaway entry.\n\n"
            f"You've verified **{my_count}/{needed}** invites so far. 🍜"
        )
        await interaction.followup.send("✅ Invite link sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            f"✅ Your invite link: **https://discord.gg/{inv.code}**\n"
            f"(DMs are closed — sharing here instead. Keep it moving. 🍜)",
            ephemeral=True,
        )


# ─── /mygiveaway ─────────────────────────────────────────────────────────────

@_slash_tree.command(name="mygiveaway", description="Check your giveaway entry progress")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_mygiveaway(interaction: discord.Interaction):
    giveaway = _giveaway_load()
    if not giveaway or not giveaway.get("active"):
        await interaction.response.send_message(
            "No active giveaway right now. Watch #announcements. 🍜", ephemeral=True
        )
        return

    mid_str  = str(interaction.user.id)
    refs     = _ref_load()
    my_count = len(refs.get(mid_str, []))
    needed   = giveaway.get("required_invites", 3)
    prize    = giveaway.get("prize", "the prize")
    end_str  = giveaway.get("end_str", "TBD")

    if my_count >= needed:
        status = "✅ **ENTERED!** You're in the draw. Good luck. 👑"
    else:
        remaining = needed - my_count
        status = f"Invite **{remaining} more** verified member{'s' if remaining != 1 else ''} to enter."

    msg = (
        f"🎁 **Your giveaway progress**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Prize: **{prize}**\n"
        f"Verified invites: **{my_count} / {needed}**\n"
        f"{status}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Draw date: {end_str}\n"
        f"Get your link: `/myinvite` 🍜"
    )
    await interaction.response.send_message(msg, ephemeral=True)


# ─── /giveaway-draw ──────────────────────────────────────────────────────────

@_slash_tree.command(name="giveaway-draw", description="Draw the giveaway winner (Admin only)")
@_app_commands.guilds(discord.Object(id=GUILD_ID))
async def _cmd_giveaway_draw(interaction: discord.Interaction):
    role_names = {r.name for r in interaction.user.roles}
    if "Admin" not in role_names:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    giveaway = _giveaway_load()
    if not giveaway:
        await interaction.followup.send("❌ No giveaway data found.", ephemeral=True)
        return

    needed   = giveaway.get("required_invites", 3)
    prize    = giveaway.get("prize", "the prize")
    refs     = _ref_load()
    guild    = interaction.guild

    # Build qualified entrants (hit invite threshold, still in server)
    qualified = []
    for uid, invitees in refs.items():
        if uid.startswith("_"):
            continue  # skip _pending etc.
        if len(invitees) >= needed:
            member = guild.get_member(int(uid))
            if member:
                qualified.append({"user_id": uid, "username": member.display_name,
                                   "invite_count": len(invitees)})

    if not qualified:
        await interaction.followup.send(
            f"❌ No qualified entrants yet — nobody has reached {needed} verified invites.",
            ephemeral=True,
        )
        return

    winner    = _random.choice(qualified)
    winner_m  = guild.get_member(int(winner["user_id"]))
    winner_mention = winner_m.mention if winner_m else f"@{winner['username']}"

    # Announce in #announcements
    ann_ch = discord.utils.get(guild.text_channels, name="announcements")
    if not ann_ch:
        ann_ch = discord.utils.get(guild.text_channels, name="general-chat")

    if ann_ch:
        await ann_ch.send(
            f"🎁 **GIVEAWAY WINNER** 🎁\n\n"
            f"After {len(qualified)} qualified entrant{'s' if len(qualified) != 1 else ''}, "
            f"the winner of **{prize}** is…\n\n"
            f"👑 {winner_mention} 👑\n\n"
            f"**{winner['invite_count']} verified referrals** — that's how you compete. 🍜"
        )

    # Log results
    results = {
        "prize":      prize,
        "drawn_at":   datetime.now(_ET).isoformat(),
        "drawn_by":   interaction.user.display_name,
        "winner":     winner,
        "qualified":  qualified,
        "total_entrants": len(qualified),
    }
    with open(_GIVEAWAY_RESULTS_FILE, "w") as f:
        _json.dump(results, f, indent=2)

    # Mark giveaway inactive
    giveaway["active"] = False
    _giveaway_save(giveaway)

    await interaction.followup.send(
        f"✅ Winner drawn: **{winner['username']}** ({winner['invite_count']} invites). "
        f"Announced in #{ann_ch.name if ann_ch else 'announcements'}.",
        ephemeral=True,
    )
    jarvis_log.info(
        f"GIVEAWAY: Draw complete — winner {winner['username']} "
        f"({winner['invite_count']} invites), {len(qualified)} qualified"
    )


# ─── Startup: cache invites + verify permissions ──────────────────────────────

_prev_on_ready_giveaway = client.on_ready

@client.event
async def on_ready():
    try:
        await _prev_on_ready_giveaway()
    except Exception as exc:
        jarvis_log.error(f"on_ready giveaway chain error: {exc}")

    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    # Check Manage Server permission
    me = guild.me
    if me:
        if me.guild_permissions.manage_guild:
            jarvis_log.info("GIVEAWAY: ✅ Manage Server permission confirmed")
        else:
            jarvis_log.error("GIVEAWAY: ❌ Missing 'Manage Server' permission — invite tracking disabled")
            print("[Giveaway] ⚠️  Missing 'Manage Server' permission — grant it in Server Settings → Roles → Jarvis")

        if me.guild_permissions.create_instant_invite:
            jarvis_log.info("GIVEAWAY: ✅ Create Invite permission confirmed")
        else:
            jarvis_log.error("GIVEAWAY: ❌ Missing 'Create Invite' permission — /myinvite will fail")
            print("[Giveaway] ⚠️  Missing 'Create Invite' permission")

    # Load member invite codes from any existing referral data into _member_invite_codes
    # (we can't recover codes across restarts without storing them, so store them in refs)
    refs = _ref_load()
    codes = refs.get("_invite_codes", {})
    _member_invite_codes.update(codes)

    await _refresh_invite_cache(guild)
    jarvis_log.info(f"GIVEAWAY: Invite cache loaded — {len(_invite_cache)} active invites")
    print(f"[Giveaway] Invite cache ready — {len(_invite_cache)} invites tracked.")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
