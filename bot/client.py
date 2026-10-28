import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import discord
from discord import app_commands
from bot.config import Config
from bot.database import Database

@dataclass
class SessionState:
    user_id: int
    guild_id: int
    channel_id: int
    session_id: int
    subject: str
    topic: str | None
    planned_minutes: int | None
    start_time: datetime
    current_segment_id: int | None = None
    segment_start_time: datetime | None = None
    accumulated_seconds: int = 0
    status: str = "active"  # "active" | "paused"
    checkin_task: asyncio.Task | None = None
    latest_checkin_id: int | None = None
    thread_id: int | None = None
    control_message_id: int | None = None
    auto_paused_by_vc: bool = False
    checkin_count: int = 0
    missed_checkins: int = 0

    def get_current_elapsed_seconds(self) -> int:
        """Calculates live seconds elapsed including current active segment."""
        total = self.accumulated_seconds
        if self.status == "active" and self.segment_start_time:
            now = datetime.now(timezone.utc)
            total += max(0, int((now - self.segment_start_time).total_seconds()))
        return total

class TracgerBot(discord.Client):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.members = True
        intents.guilds = True

        super().__init__(intents=intents)
        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.db = Database(config.db_path)

        # In-memory mapping: user_id -> SessionState
        self.active_sessions: dict[int, SessionState] = {}

    async def setup_hook(self):
        # 1. Initialize DB schema
        await self.db.init_schema()

        # 2. Register Cogs / Command groups
        from bot.cogs.sessions import SessionsCog
        from bot.cogs.checkin import CheckinCog
        from bot.cogs.stats import StatsCog
        from bot.cogs.goals import GoalsCog
        from bot.cogs.dashboard import DashboardCog
        from bot.cogs.daily_report import DailyReportCog
        from bot.cogs.study_hub import StudyHubCog

        self.sessions_cog = SessionsCog(self)
        self.checkin_cog = CheckinCog(self)
        self.stats_cog = StatsCog(self)
        self.goals_cog = GoalsCog(self)
        self.dashboard_cog = DashboardCog(self)
        self.daily_report_cog = DailyReportCog(self)
        self.study_hub_cog = StudyHubCog(self)

        await self.sessions_cog.setup()
        await self.checkin_cog.setup()
        await self.stats_cog.setup()
        await self.goals_cog.setup()
        await self.dashboard_cog.setup()
        await self.daily_report_cog.setup()
        await self.study_hub_cog.setup()

        # 3. Slash command syncing
        if self.config.guild_id:
            guild_obj = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            print(f"⚡ Slash commands synced instantly to Guild ID: {self.config.guild_id}")
        else:
            await self.tree.sync()
            print("⚡ Slash commands synced globally (may take up to 1 hour to propagate across Discord).")

    async def on_ready(self):
        print(f"==================================================")
        print(f"✅ Tracger is ONLINE as {self.user} (ID: {self.user.id})")
        print(f"📦 Database connected at {self.config.db_path}")
        print(f"🎯 Ready to track study sessions!")
        print(f"==================================================")

        # Set bot presence status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="study sessions • /study"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Monitors when a user leaves or joins voice channels during a study session."""
        if member.bot:
            return

        # Check if user has an active session
        session = self.active_sessions.get(member.id)
        if not session:
            return

        is_afk_before = (before.channel is not None and member.guild.afk_channel is not None and before.channel.id == member.guild.afk_channel.id)
        is_afk_after = (after.channel is not None and member.guild.afk_channel is not None and after.channel.id == member.guild.afk_channel.id)

        left_vc = (before.channel is not None and not is_afk_before) and (after.channel is None or is_afk_after)
        joined_vc = (before.channel is None or is_afk_before) and (after.channel is not None and not is_afk_after)

        target_channel = self.get_channel(session.thread_id) if session.thread_id else self.get_channel(session.channel_id)

        if left_vc:
            if session.status == "active":
                session.auto_paused_by_vc = True
                await self.sessions_cog.pause_session_internal(member.id, reason="Left voice channel")
                if target_channel:
                    try:
                        await target_channel.send(
                            f"⏸️ **{member.display_name}** left the voice channel. "
                            f"Your study timer has been automatically **paused**! "
                            f"Hop back in and it will automatically **resume** (or click Resume below).",
                            delete_after=120
                        )
                    except Exception:
                        pass
                await self.refresh_dashboard(session.guild_id)
                await self.refresh_hub(session.guild_id)

        elif joined_vc:
            if session.status == "paused":
                session.auto_paused_by_vc = False
                await self.sessions_cog.resume_session_internal(member.id)
                if target_channel:
                    try:
                        await target_channel.send(
                            f"▶️ **{member.display_name}** rejoined voice! "
                            f"Your study timer has automatically **resumed**! Let's get focused. 💪",
                            delete_after=120
                        )
                    except Exception:
                        pass
                await self.refresh_dashboard(session.guild_id)
                await self.refresh_hub(session.guild_id)

    async def refresh_dashboard(self, guild_id: int):
        """Notifies the dashboard cog to re-render the live active study board."""
        if hasattr(self, "dashboard_cog"):
            await self.dashboard_cog.update_dashboard(guild_id)

    async def refresh_hub(self, guild_id: int):
        """Notifies the study hub cog to re-render the persistent hub panel."""
        if hasattr(self, "study_hub_cog"):
            await self.study_hub_cog.update_hub(guild_id)
