import re
from datetime import datetime, timezone
import discord

def parse_duration(text: str | None) -> int | None:
    """
    Parses human-friendly durations into minutes.
    Examples:
        '2h' -> 120
        '1h30m' or '1h 30m' -> 90
        '45m' -> 45
        '90' -> 90
        '1.5h' -> 90
    Returns None if text cannot be parsed.
    """
    if not text:
        return None
    raw = text.strip().lower()
    if not raw:
        return None

    # Plain digits assume minutes
    if raw.isdigit():
        val = int(raw)
        return val if val > 0 else None

    # Decimal hours e.g. 1.5h
    dec_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*h(?:ours?)?", raw)
    if dec_match:
        val = int(float(dec_match.group(1)) * 60)
        return val if val > 0 else None

    # Pattern like 1h30m or 45m or 2h
    total_minutes = 0
    matched = False

    hours_match = re.search(r"(\d+)\s*h(?:ours?)?", raw)
    if hours_match:
        total_minutes += int(hours_match.group(1)) * 60
        matched = True

    mins_match = re.search(r"(\d+)\s*m(?:in(?:ute)?s?)?", raw)
    if mins_match:
        total_minutes += int(mins_match.group(1))
        matched = True

    return total_minutes if (matched and total_minutes > 0) else None

def format_duration(seconds: int, compact: bool = False) -> str:
    """
    Formats seconds into clean readable strings.
    E.g., 3665 -> '1h 01m' or '1h 1m 5s'
    """
    if seconds <= 0:
        return "0m"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if compact:
        if hours > 0:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes:02d}m" if hours > 0 else f"{minutes}m")
    if hours == 0 and secs > 0 and len(parts) == 0:
        parts.append(f"{secs}s")

    return " ".join(parts) if parts else "0m"

def progress_bar(current: float, total: float, length: int = 12) -> str:
    """
    Generates a Unicode progress bar.
    Example: '[████████░░░░] 67%'
    """
    if total <= 0:
        ratio = 0.0
    else:
        ratio = min(max(current / total, 0.0), 1.0)

    filled = int(round(length * ratio))
    bar = "█" * filled + "░" * (length - filled)
    percent = int(ratio * 100)
    return f"`[{bar}]` {percent}%"

# Styling constants
COLOR_ACTIVE = discord.Color.from_rgb(46, 204, 113)    # Emerald green
COLOR_PAUSED = discord.Color.from_rgb(241, 196, 15)   # Amber yellow
COLOR_ENDED = discord.Color.from_rgb(52, 152, 219)     # Soft blue
COLOR_CHECKIN = discord.Color.from_rgb(155, 89, 182)   # Purple
COLOR_ALERT = discord.Color.from_rgb(231, 76, 60)      # Red

def build_session_start_embed(
    user: discord.User | discord.Member,
    subject: str,
    topic: str | None,
    planned_minutes: int | None
) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Study Session Commenced",
        description=f"**{user.display_name}** has started focusing.",
        color=COLOR_ACTIVE,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="📚 Subject", value=subject, inline=True)
    embed.add_field(name="📝 Topic", value=topic or "*General*", inline=True)
    if planned_minutes:
        embed.add_field(name="🎯 Planned Duration", value=f"{format_duration(planned_minutes * 60)}", inline=True)
    embed.add_field(name="⏱️ Status", value="🟢 **Running**", inline=False)
    embed.set_footer(text="Tracger • Use the buttons below or slash commands to control your timer")
    return embed

def build_status_embed(
    user: discord.User | discord.Member,
    subject: str,
    topic: str | None,
    status: str,
    elapsed_seconds: int,
    planned_minutes: int | None,
    checkins_completed: int,
    checkins_prompted: int
) -> discord.Embed:
    color = COLOR_ACTIVE if status == "active" else COLOR_PAUSED
    status_icon = "🟢 **Active**" if status == "active" else "🟡 **Paused**"

    embed = discord.Embed(
        title=f"⏱️ Active Session — {user.display_name}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="📚 Subject", value=subject, inline=True)
    embed.add_field(name="📝 Topic", value=topic or "*General*", inline=True)
    embed.add_field(name="State", value=status_icon, inline=True)

    elapsed_str = format_duration(elapsed_seconds)
    if planned_minutes:
        planned_secs = planned_minutes * 60
        bar = progress_bar(elapsed_seconds, planned_secs)
        embed.add_field(
            name="⏱️ Time Tracked",
            value=f"**{elapsed_str}** / {format_duration(planned_secs)}\n{bar}",
            inline=False
        )
    else:
        embed.add_field(name="⏱️ Time Tracked", value=f"**{elapsed_str}**", inline=False)

    checkin_str = f"{checkins_completed}/{checkins_prompted}" if checkins_prompted > 0 else "None yet"
    embed.add_field(name="✅ Check-ins", value=checkin_str, inline=True)
    embed.set_footer(text="Tracger Study Companion")
    return embed

def build_session_summary_embed(
    user: discord.User | discord.Member,
    subject: str,
    topic: str | None,
    total_seconds: int,
    segment_count: int,
    checkins_done: int,
    checkins_total: int,
    current_streak: int,
    daily_total_seconds: int,
    daily_goal_minutes: int
) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 Session Finished!",
        description=f"Outstanding work, **{user.display_name}**! Here is your session summary.",
        color=COLOR_ENDED,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="📚 Subject & Topic", value=f"**{subject}** — {topic or 'General'}", inline=False)
    embed.add_field(name="⏱️ Focused Time", value=f"**{format_duration(total_seconds)}**", inline=True)
    embed.add_field(name="📊 Segments", value=f"{segment_count} part{'s' if segment_count != 1 else ''}", inline=True)

    if checkins_total > 0:
        pct = int((checkins_done / checkins_total) * 100)
        embed.add_field(name="✅ Check-in Rate", value=f"{checkins_done}/{checkins_total} ({pct}%)", inline=True)
    else:
        embed.add_field(name="✅ Check-ins", value="None needed", inline=True)

    streak_str = f"🔥 **{current_streak}** day{'s' if current_streak != 1 else ''}"
    embed.add_field(name="Streak", value=streak_str, inline=True)

    if daily_goal_minutes > 0:
        goal_secs = daily_goal_minutes * 60
        bar = progress_bar(daily_total_seconds, goal_secs)
        embed.add_field(
            name="🎯 Today's Goal Progress",
            value=f"{format_duration(daily_total_seconds)} / {format_duration(goal_secs)}\n{bar}",
            inline=False
        )
    else:
        embed.add_field(name="📅 Today Total", value=f"{format_duration(daily_total_seconds)}", inline=True)

    embed.set_footer(text="Keep the momentum going! • Tracger")
    return embed
