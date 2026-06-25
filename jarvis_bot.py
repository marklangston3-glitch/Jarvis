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
from datetime import datetime, timedelta

import anthropic
import discord
import requests as http_requests
import yfinance as yf

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

Jarvis has built-in market data commands: price, options, technicals, news, earnings, crypto,
fear, movers, sectors, levels. If a user asks for market data, tell them to use the specific
command (e.g. @Jarvis price SPY) rather than trying to answer from memory.

Never give financial advice. If asked for a specific trade, say the kitchen serves levels and
frameworks, not financial advice. Direct them to the appropriate channel instead.

IMPORTANT: Users have roles. If a user has the Admin, Moderator, or Paid Member role, they already
have access to all paid channels — DO NOT tell them to upgrade or check #how-to-get-access. Treat
them as insiders. If an Admin asks you to do something, comply — they run the server. Only redirect
Free Member or Unverified users to #how-to-get-access."""

HELP_TEXT = (
    "👑 **Jarvis Commands**\n\n"
    "**📊 Market Data:**\n"
    "• `@Jarvis price SPY` — live quote + daily change\n"
    "• `@Jarvis technicals SPY` — RSI, MACD, SMAs, VWAP\n"
    "• `@Jarvis options SPY` — options chain snapshot\n"
    "• `@Jarvis options movers` — top 10 most active contracts market-wide\n"
    "• `@Jarvis levels SPY` — key support/resistance levels\n"
    "• `@Jarvis earnings AAPL` — next earnings + recent EPS\n"
    "• `@Jarvis news AAPL` — latest headlines\n"
    "• `@Jarvis info AAPL` — company overview\n"
    "• `@Jarvis movers` — top gainers & losers today\n"
    "• `@Jarvis sectors` — sector performance\n"
    "• `@Jarvis crypto BTC` — crypto price\n"
    "• `@Jarvis fear` — Fear & Greed Index\n"
    "• `@Jarvis market` — market overview (SPY, QQQ, VIX)\n\n"
    "**🛠️ Server:**\n"
    "• `@Jarvis rules` — server rules\n"
    "• `@Jarvis access` — how to get paid access\n"
    "• `@Jarvis channels` — channel guide\n"
    "• `@Jarvis gm` — morning check-in\n\n"
    "Or just talk to me — I'm powered by AI. 🍜"
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
            title = item.get("title", "Untitled")
            link = item.get("link", "")
            publisher = item.get("publisher", "")
            pub_time = item.get("providerPublishTime")
            time_str = ""
            if pub_time:
                dt = datetime.fromtimestamp(pub_time)
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
}


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
            if len(result) > 2000:
                result = result[:1997] + "..."
            await message.reply(result, mention_author=False)
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


if __name__ == "__main__":
    client.run(BOT_TOKEN)
