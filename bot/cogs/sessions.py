from datetime import datetime, timezone
import discord
from discord import app_commands, ui
from bot.helpers import (
    parse_duration,
    format_duration,
    build_session_start_embed,
    build_status_embed,
    build_session_summary_embed,
)

class StudyModal(ui.Modal, title="📖 Start Study Session"):
    subject_input = ui.TextInput(
        label="Subject",
        placeholder="e.g. Mathematics, Physics, System Design",
        required=True,
        max_length=60
    )
    topic_input = ui.TextInput(
        label="Topic (Optional)",
        placeholder="e.g. Linear Algebra, Chapter 4, React Hooks",
        required=False,
        max_length=100
    )
    duration_input = ui.TextInput(
        label="Planned Duration (Optional)",
        placeholder="e.g. 2h, 1h30m, 45m (Leave empty for open-ended)",
        required=False,
        max_length=20
    )

    def __init__(self, cog: "SessionsCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.start_session_from_inputs(
            interaction=interaction,
            subject=self.subject_input.value.strip(),
            topic=self.topic_input.value.strip() or None,
            duration_raw=self.duration_input.value.strip() or None
        )

class SwitchModal(ui.Modal, title="🔄 Switch Subject / Topic"):
    subject_input = ui.TextInput(
        label="New Subject",
        placeholder="e.g. Data Structures, Chemistry",
        required=True,
        max_length=60
    )
    topic_input = ui.TextInput(
        label="New Topic (Optional)",
        placeholder="e.g. Binary Trees, Thermodynamics",
        required=False,
        max_length=100
    )

    def __init__(self, cog: "SessionsCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.switch_session_from_inputs(
            interaction=interaction,
            new_subject=self.subject_input.value.strip(),
            new_topic=self.topic_input.value.strip() or None
        )

class SessionControlView(ui.View):
    def __init__(self, cog: "SessionsCog", user_id: int):
        super().__init__(timeout=None)  # Persistent across restarts if registered
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "⚠️ This session control panel belongs to another member. Use `/study` or `/status` to manage your own timer.",
                ephemeral=True
            )
            return False
        return True

    @ui.button(label="⏸️ Pause", style=discord.ButtonStyle.secondary, custom_id="session_toggle_pause")
    async def toggle_pause_button(self, interaction: discord.Interaction, button: ui.Button):
        session = self.cog.bot.active_sessions.get(self.user_id)
        if not session:
            await interaction.response.send_message("❌ No active session found.", ephemeral=True)
            return

        if session.status == "active":
            await self.cog.pause_session_internal(self.user_id)
            button.label = "▶️ Resume"
            button.style = discord.ButtonStyle.success
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏸️ Timer paused. Take a well-deserved breather!", ephemeral=True)
        else:
            await self.cog.resume_session_internal(self.user_id)
            button.label = "⏸️ Pause"
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("▶️ Timer resumed. Let's get focused!", ephemeral=True)

        await self.cog.bot.refresh_dashboard(session.guild_id)

    @ui.button(label="🔄 Switch", style=discord.ButtonStyle.primary, custom_id="session_switch")
    async def switch_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SwitchModal(self.cog))

    @ui.button(label="✅ Check-in", style=discord.ButtonStyle.success, custom_id="session_checkin")
    async def checkin_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.bot.checkin_cog.do_manual_checkin(interaction)

    @ui.button(label="⏹️ End", style=discord.ButtonStyle.danger, custom_id="session_end")
    async def end_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.end_session_internal(interaction)

class SessionsCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        # Register slash commands
        tree = self.bot.tree

        @tree.command(name="study", description="Commence a study tracking session")
        @app_commands.describe(
            subject="Subject you are studying (e.g. Calculus)",
            topic="Specific topic or chapter (optional)",
            duration="Planned duration (e.g. 2h, 1h30m, 45m)"
        )
        async def study_command(
            interaction: discord.Interaction,
            subject: str | None = None,
            topic: str | None = None,
            duration: str | None = None
        ):
            if interaction.user.id in self.bot.active_sessions:
                await interaction.response.send_message(
                    "⚠️ You already have an active study session! Use `/status`, `/pause`, or `/end`.",
                    ephemeral=True
                )
                return

            if subject:
                await self.start_session_from_inputs(interaction, subject, topic, duration)
            else:
                # Show interactive modal
                await interaction.response.send_modal(StudyModal(self))

        @tree.command(name="pause", description="Pause your active study timer")
        async def pause_command(interaction: discord.Interaction):
            session = self.bot.active_sessions.get(interaction.user.id)
            if not session:
                await interaction.response.send_message("❌ You have no active study session to pause.", ephemeral=True)
                return
            if session.status == "paused":
                await interaction.response.send_message("ℹ️ Your study session is already paused.", ephemeral=True)
                return

            await self.pause_session_internal(interaction.user.id)
            await interaction.response.send_message("⏸️ Study timer **paused**. Use `/resume` when you are back!", ephemeral=True)
            await self.bot.refresh_dashboard(interaction.guild_id)

        @tree.command(name="resume", description="Resume your paused study timer")
        async def resume_command(interaction: discord.Interaction):
            session = self.bot.active_sessions.get(interaction.user.id)
            if not session:
                await interaction.response.send_message("❌ You have no study session in progress.", ephemeral=True)
                return
            if session.status == "active":
                await interaction.response.send_message("ℹ️ Your study session is already running!", ephemeral=True)
                return

            await self.resume_session_internal(interaction.user.id)
            await interaction.response.send_message("▶️ Study timer **resumed**! Keep up the great work.", ephemeral=True)
            await self.bot.refresh_dashboard(interaction.guild_id)

        @tree.command(name="switch", description="Change your subject or topic mid-session")
        @app_commands.describe(
            new_subject="New subject to switch to",
            new_topic="New topic (optional)"
        )
        async def switch_command(
            interaction: discord.Interaction,
            new_subject: str | None = None,
            new_topic: str | None = None
        ):
            if interaction.user.id not in self.bot.active_sessions:
                await interaction.response.send_message("❌ You do not have an active session to switch.", ephemeral=True)
                return

            if new_subject:
                await self.switch_session_from_inputs(interaction, new_subject, new_topic)
            else:
                await interaction.response.send_modal(SwitchModal(self))

        @tree.command(name="status", description="Check your current study session state")
        async def status_command(interaction: discord.Interaction):
            session = self.bot.active_sessions.get(interaction.user.id)
            if not session:
                await interaction.response.send_message("ℹ️ You are not currently in a study session. Start one with `/study`!", ephemeral=True)
                return

            elapsed = session.get_current_elapsed_seconds()
            embed = build_status_embed(
                user=interaction.user,
                subject=session.subject,
                topic=session.topic,
                status=session.status,
                elapsed_seconds=elapsed,
                planned_minutes=session.planned_minutes,
                checkins_completed=0,
                checkins_prompted=0
            )
            view = SessionControlView(self, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        @tree.command(name="end", description="End your current session and generate a study report")
        async def end_command(interaction: discord.Interaction):
            session = self.bot.active_sessions.get(interaction.user.id)
            if not session:
                await interaction.response.send_message("❌ No active session to end.", ephemeral=True)
                return

            await interaction.response.defer()
            await self.end_session_internal(interaction)

    async def start_session_from_inputs(
        self,
        interaction: discord.Interaction,
        subject: str,
        topic: str | None,
        duration_raw: str | None
    ):
        from bot.client import SessionState

        planned_mins = parse_duration(duration_raw)
        user = interaction.user
        guild_id = interaction.guild_id or 0
        channel_id = interaction.channel_id

        # Create session in DB
        session_id = await self.bot.db.create_session(
            user_id=user.id,
            guild_id=guild_id,
            display_name=user.display_name,
            subject=subject,
            topic=topic,
            planned_minutes=planned_mins
        )

        # Create first active segment
        segment_id = await self.bot.db.create_segment(session_id)
        now = datetime.now(timezone.utc)

        state = SessionState(
            user_id=user.id,
            guild_id=guild_id,
            channel_id=channel_id,
            session_id=session_id,
            subject=subject,
            topic=topic,
            planned_minutes=planned_mins,
            start_time=now,
            current_segment_id=segment_id,
            segment_start_time=now,
            accumulated_seconds=0,
            status="active"
        )
        self.bot.active_sessions[user.id] = state

        # Schedule check-in reminders
        self.bot.checkin_cog.schedule_reminder(state)

        embed = build_session_start_embed(user, subject, topic, planned_mins)
        view = SessionControlView(self, user.id)

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

        await self.bot.refresh_dashboard(guild_id)

    async def pause_session_internal(self, user_id: int, reason: str = ""):
        session = self.bot.active_sessions.get(user_id)
        if not session or session.status != "active":
            return

        # End current active segment
        if session.current_segment_id:
            elapsed = await self.bot.db.end_segment(session.current_segment_id)
            session.accumulated_seconds += elapsed
            session.current_segment_id = None
            session.segment_start_time = None

        session.status = "paused"
        await self.bot.db.update_session_meta(
            session_id=session.session_id,
            status="paused",
            add_seconds=0
        )

        # Cancel checkin reminder loop
        self.bot.checkin_cog.cancel_reminder(session)

    async def resume_session_internal(self, user_id: int):
        session = self.bot.active_sessions.get(user_id)
        if not session or session.status != "paused":
            return

        # Start new segment
        segment_id = await self.bot.db.create_segment(session.session_id)
        now = datetime.now(timezone.utc)
        session.current_segment_id = segment_id
        session.segment_start_time = now
        session.status = "active"

        await self.bot.db.update_session_meta(
            session_id=session.session_id,
            status="active"
        )

        # Re-schedule checkin reminder
        self.bot.checkin_cog.schedule_reminder(session)

    async def switch_session_from_inputs(self, interaction: discord.Interaction, new_subject: str, new_topic: str | None):
        session = self.bot.active_sessions.get(interaction.user.id)
        if not session:
            return

        old_subject = session.subject
        session.subject = new_subject
        session.topic = new_topic

        await self.bot.db.update_session_meta(
            session_id=session.session_id,
            subject=new_subject,
            topic=new_topic
        )

        msg = f"🔄 Switched focus from **{old_subject}** to **{new_subject}** ({new_topic or 'General'})!"
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)

        await self.bot.refresh_dashboard(session.guild_id)

    async def end_session_internal(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        session = self.bot.active_sessions.pop(user_id, None)
        if not session:
            return

        # Finalize running segment if active
        if session.status == "active" and session.current_segment_id:
            elapsed = await self.bot.db.end_segment(session.current_segment_id)
            session.accumulated_seconds += elapsed

        # Cancel any scheduled checkin reminder
        self.bot.checkin_cog.cancel_reminder(session)

        # Save to DB and retrieve summary metrics
        summary = await self.bot.db.end_session(session.session_id, session.accumulated_seconds)

        embed = build_session_summary_embed(
            user=interaction.user,
            subject=summary["subject"],
            topic=summary["topic"],
            total_seconds=summary["total_seconds"],
            segment_count=summary["segment_count"],
            checkins_done=summary["checkins_done"],
            checkins_total=summary["checkins_total"],
            current_streak=summary["current_streak"],
            daily_total_seconds=summary["today_total_seconds"],
            daily_goal_minutes=summary["daily_goal_minutes"]
        )

        await interaction.followup.send(embed=embed)
        await self.bot.refresh_dashboard(session.guild_id)

        # Check if user reached their daily goal in this session
        if summary["daily_goal_minutes"] > 0:
            goal_secs = summary["daily_goal_minutes"] * 60
            if summary["today_total_seconds"] >= goal_secs:
                try:
                    await interaction.channel.send(
                        f"🏆 **Goal Achieved!** <@{user_id}> reached their daily study target of "
                        f"**{format_duration(goal_secs)}** today! Outstanding commitment! 🔥"
                    )
                except Exception:
                    pass
