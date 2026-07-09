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
Only redirect Free Members or Unverified users there."""

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
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

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


async def get_ai_response(user_message, username, role_names=None):
    if claude_client is None:
        return "🍜 AI responses aren't configured yet. Try `@Jarvis help` for available commands."
    role_context = ""
    if role_names:
        role_context = f" (roles: {', '.join(role_names)})"
    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"{username}{role_context} says: {user_message}"}
            ],
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude API error: {e}")
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

    role_names = [r.name for r in message.author.roles if r.name != "@everyone"]
    try:
        async with message.channel.typing():
            ai_reply = await get_ai_response(content, message.author.display_name, role_names)
        await message.reply(ai_reply, mention_author=False)
    except Exception as e:
        print(f"Reply error: {e}")


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


async def _send_content(channel_name: str, text: str) -> bool:
    """Post text to a channel by name."""
    guild = client.get_guild(GUILD_ID)
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
        super().__init__(timeout=None)
        self.content = content
        self.target = target
        self.slot_name = slot_name
        self.sched_time = sched_time
        self.done = False
        self.timer: Optional[asyncio.Task] = None
        self.mod_msg: Optional[discord.Message] = None

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

    view = ApprovalView(content, slot["target"], slot["name"], now)
    body = (
        f"{mention}\n"
        f"📋 **PENDING APPROVAL**\n"
        f"Target channel: #{slot['target']}\n"
        f"Scheduled time: {now}\n\n"
        f"{content}"
    )
    mod_msg = await mod_ch.send(body, view=view)
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
    print("[Content] Scheduled slots:")
    for slot in _SLOTS:
        _schedule.every(1).minutes.do(_make_job(slot)).tag("content")
        days = "/".join(_DAY[d] for d in slot["weekdays"])
        kind = "poll" if slot.get("poll") else ("approval" if slot.get("approval") else "direct")
        line = (
            f"  ⏰ {slot['name']:<26} "
            f"{slot['hour']:02d}:{slot['minute']:02d} ET  "
            f"({days:<15})  "
            f"→ #{slot['target']:<20}  [{kind}]"
        )
        jarvis_log.info(line)
        print(f"[Content]{line}")

    def _runner():
        while True:
            _schedule.run_pending()
            _time.sleep(30)

    t = threading.Thread(target=_runner, daemon=True, name="jarvis-content-scheduler")
    t.start()
    jarvis_log.info("Content scheduler thread started (polling every 30s)")


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


if __name__ == "__main__":
    client.run(BOT_TOKEN)
