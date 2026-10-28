import random
import asyncio
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from bot.helpers import format_duration, COLOR_ACTIVE, COLOR_ENDED

IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

MOTIVATIONAL_QUOTES = [
    ("“Do something today that your future self will be genuinely proud of.”", "🌱 Plant the Seeds"),
    ("“The pain of discipline weighs ounces; the pain of regret weighs tons.”", "⚖️ Choose Your Hard"),
    ("“Consistency beats intensity every single time. Show up, open your workspace, and log your hours.”", "🔥 Streak Fuel"),
    ("“Don't watch the clock; do what it does: keep moving.”", "⏱️ Momentum"),
    ("“Your mind is a muscle. The struggle you feel right now is cognitive growth taking place.”", "🧠 Neuroplasticity"),
    ("“Excellence is not an act, but a habit. Make today another day you crushed your targets.”", "👑 Daily Greatness"),
    ("“Rome wasn't built in a day, but they were laying bricks every single hour. Go lay your bricks.”", "🧱 Compounding Focus"),
    ("“Action creates motivation, not the other way around. Open the notes first; the dopamine will follow.”", "⚡ Kinetic Energy"),
    ("“There are no shortcuts to any place worth going. Put on your focus playlist and let's get to work.”", "🎧 Flow State"),
    ("“It always seems impossible until it's done. One chapter, one concept, one practice problem at a time.”", "✨ Relentless Progress"),
    ("“Your brain is an astonishing biological machine, but it will gladly convince you that organizing highlighters is more urgent than opening chapter 1. Outsmart it.”", "🧠 The Highlighter Trap"),
    ("“Momentum is strange magic: 0 minutes feels like climbing a cliff, but 10 minutes in, you wonder why you ever hesitated.”", "⚡ Quiet Momentum"),
    ("“A blank page is not an interrogation; it’s an open invitation. Put down one imperfect sentence and see what happens.”", "✍️ Permission to Begin"),
    ("“Every master once spent an entire evening staring at a problem thinking, 'I have no clue what this means.' Keep going.”", "💡 Universal Truth"),
    ("“You don't need a frantic marathon today. A focused 40-minute block done with real attention beats five hours of distracted tab-switching.”", "🎯 Depth Over Volume"),
    ("“Procrastination is just hesitation dressed up as 'I'll start after this quick video.' Call its bluff and open your workspace.”", "🎭 Unmasking Hesitation"),
    ("“The beautiful thing about learning is that nobody can take it from you. Every hour you log compounds quietly in the background.”", "📈 The Compound Effect"),
    ("“Notice how the urge to tidy your room only strikes right when you need to study? Tidy your thoughts first; the desk can wait.”", "🧹 Crafty Distractions"),
    ("“Deep focus is a rare superpower in a world engineered for fragmented attention. Protect your focus like gold today.”", "🛡️ Focus Fortress"),
    ("“Future you is resting entirely on the groundwork you lay in the next hour or two. Be a generous ancestor to yourself.”", "⏳ Time Traveler"),
    ("“Don't wait for inspiration to descend like a celestial beam. Inspiration usually clocks in five minutes after you start working.”", "🕰️ Show Up First"),
    ("“Five consistent days of modest effort will run laps around one frantic night of panic. Trust the steady rhythm.”", "🌊 Daily Rhythms"),
    ("“A tree doesn't grow by straining; it grows by absorbing light every day. Log your daily light.”", "🌿 Natural Growth"),
    ("“Your curiosity is a muscle. If a problem feels heavy, it just means you're lifting cognitive weights.”", "🏋️ Cognitive Fitness"),
    ("“Closing unnecessary tabs, silencing notifications, and learning something new is the ultimate act of quiet focus.”", "🚪 Quiet Rebellion"),
    ("“Small progress is still immense progress. A river is just raindrops that decided to stick together.”", "💧 Collective Drops"),
    ("“The joy of understanding something that baffled you yesterday is one of the purest feelings in human experience. Go find that click today.”", "🔓 The Click"),
    ("“Clarity follows execution. You don't need to see the entire staircase; you just need to take the first step on the outline.”", "🪜 Step by Step"),
    ("“Doubt loves silence and still waters. The fastest antidote to overthinking is five minutes of hands-on practice.”", "🛡️ Action Over Doubt"),
    ("“You don't have to be great to start, but you have to start to become great. Today is day one.”", "🚀 Igniting the Spark"),
    ("“Knowledge isn't acquired in sudden leaps, but in quiet, steady increments. Be proud of every page turned.”", "📚 Quiet Increment"),
    ("“When focus feels elusive, remember: even twenty minutes of honest work leaves you leagues ahead of where you woke up.”", "🕊️ The Grace of Small Steps"),
    ("“Mastery is simply persistence in disguise. Keep your head down, trust the process, and let compounding do the heavy lifting.”", "💎 The Art of Mastery"),
]

DAILY_CHALLENGES = [
    "Do a 3-minute brain-dump on paper before starting: write down any mental clutter so your head is clear for deep work.",
    "Set a modest target today (e.g. 35m or 45m) and honor it with zero tab-switching or multi-tasking.",
    "Hop into a study thread, log your first check-in, and notice how effortless the momentum becomes.",
    "Leave your study desk 10% neater than you found it when your timer rings.",
    "Teach a concept you learned today to an imaginary friend in your head (the Feynman technique).",
    "Take a genuine 10-minute stretch or walk away from all screens right after your session ends.",
    "Tackle that one topic you've been putting off for the past two days for just 20 minutes.",
    "Write a single-sentence summary of your main takeaway at the very end of today's study block.",
    "Keep a 'distraction scratchpad' nearby: whenever a random urge pops up, jot it down to check later instead of switching tabs.",
    "Drink a full glass of water before starting your timer to keep mental fatigue at bay.",
    "Identify the single most confusing concept from today's material and write down three specific questions about it.",
    "Close every single browser tab and app that has nothing to do with what you are about to study.",
    "Do an active recall check: close your notes and spend 2 minutes sketching or summarizing what you just read.",
    "Split a daunting chapter or assignment into three bite-sized sub-tasks before clicking Start.",
    "Take three slow, deep breaths to signal to your nervous system that it is time to slow down and focus.",
    "Put your phone across the room or face down on silent mode for the entire duration of your session.",
    "Re-read the hardest paragraph from yesterday's study notes and see how much clearer it looks with fresh eyes.",
    "Explain a key formula, rule, or mechanism out loud in your own plain words without looking at the textbook.",
    "Review your notes using clean color coding: one accent for core definitions, another for examples.",
    "Write down your top priority topic on a sticky note and stick it right below your monitor before you begin.",
    "Turn today's most difficult section into two flashcards or quiz questions for your future review.",
    "Take a 5-minute eye-rest break looking out a window at distance after finishing your first 45 minutes.",
    "Notice when your mind starts drifting and gently guide your attention back without judging yourself.",
    "Try the 5-Minute Rule: commit to focusing on your hardest problem for just 5 minutes before deciding whether to stop.",
    "Outline the skeleton of your topic (headings and subheadings) before diving into the fine details.",
    "Celebrate a small win: when you finish your planned block, take 30 seconds to acknowledge your discipline.",
    "Find one real-world example or practical application of the concept you are reviewing today.",
    "Do a quick 2-minute posture check: adjust your screen height and relax your shoulders before hitting Start.",
    "Replace passive re-reading with active practice questions or end-of-chapter problems for at least half your session.",
    "Pick one diagram or summary from earlier this week and spend 3 minutes refining or clarifying it.",
    "Reflect on your streak: celebrate showing up today, regardless of how easy or difficult the material felt.",
    "End your session by writing down the very first action item for tomorrow, so future you can start without friction.",
]

class MotivationCog:
    def __init__(self, bot):
        self.bot = bot
        self.daily_task: asyncio.Task | None = None

    async def setup(self):
        tree = self.bot.tree

        @tree.command(name="motivationchannel", description="Set or view the channel where daily quirky quotes and stats are posted")
        @app_commands.describe(channel="Text channel for daily quotes and community motivation (leave blank to check current)")
        async def motivationchannel_command(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild_id or 0

            if channel:
                await self.bot.db.set_motivation_channel(guild_id, channel.id)
                await interaction.followup.send(
                    f"✅ Daily morning quotes and community motivation highlights will now be posted to {channel.mention}!",
                    ephemeral=True
                )
            else:
                ch_id = await self.bot.db.get_motivation_channel(guild_id)
                if ch_id:
                    await interaction.followup.send(f"📢 Current motivation channel is <#{ch_id}>.", ephemeral=True)
                else:
                    await interaction.followup.send("ℹ️ No motivation channel set yet. Use `/motivationchannel #channel` to configure one!", ephemeral=True)

        @tree.command(name="motivate", description="Post or preview today's quirky motivational quote and study stats")
        async def motivate_command(interaction: discord.Interaction):
            await interaction.response.defer()
            guild_id = interaction.guild_id or 0
            embed = await self.build_motivation_embed(guild_id)
            await interaction.followup.send(embed=embed)

        # Start 8:00 AM IST daily motivation schedule loop
        if not self.daily_task or self.daily_task.done():
            self.daily_task = asyncio.create_task(self._daily_motivation_loop())

    async def build_motivation_embed(self, guild_id: int) -> discord.Embed:
        """Builds a quirky, wholesome, community-oriented daily motivation card."""
        now_ist = datetime.now(IST_OFFSET)
        date_str = now_ist.strftime("%A, %B %d")

        # Pick quote based on calendar date so the entire server shares the same daily thought
        day_seed = int(now_ist.strftime("%Y%m%d"))
        quote, theme = MOTIVATIONAL_QUOTES[day_seed % len(MOTIVATIONAL_QUOTES)]
        challenge = DAILY_CHALLENGES[day_seed % len(DAILY_CHALLENGES)]

        embed = discord.Embed(
            title=f"☀️ Morning Momentum — {date_str}",
            description=f"### {quote}\n*Perspective: **{theme}***",
            color=COLOR_ACTIVE,
            timestamp=datetime.now(timezone.utc)
        )

        # Fetch collaborative community stats (no individual competition)
        try:
            leaderboard_week = await self.bot.db.get_leaderboard(guild_id, "week")
            total_week_seconds = sum(r["total_seconds"] for r in leaderboard_week)
            active_streakers = sum(1 for r in leaderboard_week if r.get("current_streak", 0) > 0)
            total_students = len(leaderboard_week)

            if total_week_seconds > 0:
                embed.add_field(
                    name="📈 Community Focus This Week",
                    value=f"**{format_duration(total_week_seconds)}** compounded together",
                    inline=True
                )

            if active_streakers > 0:
                embed.add_field(
                    name="🔥 Collective Momentum",
                    value=f"**{active_streakers}** member{'s' if active_streakers != 1 else ''} holding active study streaks!",
                    inline=True
                )
            elif total_students > 0:
                embed.add_field(
                    name="🌱 Active Learners",
                    value=f"**{total_students}** member{'s' if total_students != 1 else ''} focusing this week",
                    inline=True
                )
        except Exception:
            pass

        embed.add_field(
            name="🎯 Daily Micro-Challenge",
            value=f"💡 *{challenge}*",
            inline=False
        )

        embed.set_footer(text="Tracger • Friendly accountability and mutual focus")
        return embed

    async def _daily_motivation_loop(self):
        """Runs indefinitely, firing every morning at 8:00 AM IST (02:30 UTC)."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now_utc = datetime.now(timezone.utc)
            # 8:00 AM IST is 02:30 UTC
            target_utc = now_utc.replace(hour=2, minute=30, second=0, microsecond=0)

            if target_utc <= now_utc:
                target_utc += timedelta(days=1)

            sleep_seconds = (target_utc - now_utc).total_seconds()
            print(f"⏰ Morning motivation scheduled in {sleep_seconds / 3600:.2f} hours (at 8:00 AM IST)")

            try:
                await asyncio.sleep(sleep_seconds)
                await self.dispatch_all_morning_motivations()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in motivation schedule loop: {e}")
                await asyncio.sleep(60)

    async def dispatch_all_morning_motivations(self):
        """Dispatches daily morning motivation embeds to all configured motivation channels."""
        try:
            channels = await self.bot.db.get_all_motivation_channels()
            for guild_id, channel_id in channels:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        embed = await self.build_motivation_embed(guild_id)
                        await channel.send(embed=embed)
                    except Exception as e:
                        print(f"Failed to post motivation in channel {channel_id}: {e}")
        except Exception as e:
            print(f"Error dispatching morning motivations: {e}")
