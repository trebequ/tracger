from datetime import datetime, timezone
import discord
from discord import app_commands, ui
from bot.helpers import format_duration, COLOR_ACTIVE, COLOR_ENDED


class HubStudyModal(ui.Modal, title="📖 Start Study Session"):
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

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.sessions_cog.start_session_from_inputs(
            interaction=interaction,
            subject=self.subject_input.value.strip(),
            topic=self.topic_input.value.strip() or None,
            duration_raw=self.duration_input.value.strip() or None
        )


class HubGoalModal(ui.Modal, title="🎯 Set Daily Study Goal"):
    goal_input = ui.TextInput(
        label="Daily Target",
        placeholder="e.g. 3h, 2h30m, 90m",
        required=True,
        max_length=20
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        from bot.helpers import parse_duration
        minutes = parse_duration(self.goal_input.value.strip())
        if not minutes or minutes <= 0:
            await interaction.response.send_message(
                "❌ Invalid format. Please specify e.g. `2h`, `1h30m`, or `90m`.",
                ephemeral=True
            )
            return
        await self.bot.db.set_daily_goal(interaction.user.id, minutes)
        await interaction.response.send_message(
            f"🎯 Daily study target set to **{format_duration(minutes * 60)}**! Go crush it! 💪",
            ephemeral=True
        )


class StudyHubView(ui.View):
    """Persistent view attached to the Study Hub embed. Survives bot restarts."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="📖 Start Studying", style=discord.ButtonStyle.success, custom_id="hub_start_study", row=0)
    async def start_study_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id in self.bot.active_sessions:
            session = self.bot.active_sessions[interaction.user.id]
            thread_mention = f"<#{session.thread_id}>" if session.thread_id else "your current session"
            await interaction.response.send_message(
                f"⚠️ You already have an active study session! Check {thread_mention} or use the buttons below to pause/end.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(HubStudyModal(self.bot))

    @ui.button(label="⏸️ Pause / ▶️ Resume", style=discord.ButtonStyle.secondary, custom_id="hub_toggle_pause", row=0)
    async def toggle_pause_button(self, interaction: discord.Interaction, button: ui.Button):
        session = self.bot.active_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message(
                "❌ You do not have an active study session. Click **Start Studying** to begin!",
                ephemeral=True
            )
            return

        if session.status == "active":
            await self.bot.sessions_cog.pause_session_internal(interaction.user.id)
            await interaction.response.send_message("⏸️ Your study timer has been **paused**! Take a breather.", ephemeral=True)
        else:
            await self.bot.sessions_cog.resume_session_internal(interaction.user.id)
            await interaction.response.send_message("▶️ Your study timer has been **resumed**! Let's get focused.", ephemeral=True)

        await self.bot.refresh_dashboard(session.guild_id)
        await self.bot.refresh_hub(session.guild_id)

    @ui.button(label="⏹️ End Session", style=discord.ButtonStyle.danger, custom_id="hub_end_session", row=0)
    async def end_session_button(self, interaction: discord.Interaction, button: ui.Button):
        session = self.bot.active_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message(
                "❌ You do not have an active study session to end.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self.bot.sessions_cog.end_session_internal(interaction)

    @ui.button(label="🎯 Set Daily Goal", style=discord.ButtonStyle.primary, custom_id="hub_set_goal", row=1)
    async def set_goal_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(HubGoalModal(self.bot))

    @ui.button(label="📊 My Stats", style=discord.ButtonStyle.secondary, custom_id="hub_my_stats", row=1)
    async def my_stats_button(self, interaction: discord.Interaction, button: ui.Button):
        from bot.helpers import progress_bar
        stats = await self.bot.db.get_user_stats(interaction.user.id)

        if stats["session_count"] == 0:
            await interaction.response.send_message(
                "ℹ️ You haven't studied yet! Click **Start Studying** to begin.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📊 Quick Stats — {interaction.user.display_name}",
            color=COLOR_ACTIVE,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="📅 Today", value=f"**{format_duration(stats['today_seconds'])}**", inline=True)
        embed.add_field(name="📆 This Week", value=f"**{format_duration(stats['week_seconds'])}**", inline=True)
        embed.add_field(name="📈 All-Time", value=f"**{format_duration(stats['all_time_seconds'])}**", inline=True)

        streak_val = f"🔥 **{stats['current_streak']}** day{'s' if stats['current_streak'] != 1 else ''}"
        embed.add_field(name="Streak", value=streak_val, inline=True)
        embed.add_field(name="Sessions", value=str(stats["session_count"]), inline=True)

        goal_mins = stats["daily_goal_minutes"]
        if goal_mins > 0:
            goal_secs = goal_mins * 60
            bar = progress_bar(stats["today_seconds"], goal_secs)
            embed.add_field(
                name="🎯 Today's Goal",
                value=f"{format_duration(stats['today_seconds'])} / {format_duration(goal_secs)}\n{bar}",
                inline=False
            )

        embed.set_footer(text="Use /stats for full analytics")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class StudyHubCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        tree = self.bot.tree

        # Register the persistent view so it works after restarts
        self.bot.add_view(StudyHubView(self.bot))

        @tree.command(name="hub", description="Set up the persistent Study Hub panel in this channel")
        async def hub_command(interaction: discord.Interaction):
            guild_id = interaction.guild_id or 0
            embed = self.generate_hub_embed(guild_id)
            view = StudyHubView(self.bot)
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()
            await self.bot.db.set_hub_message(guild_id, msg.channel.id, msg.id)

    def generate_hub_embed(self, guild_id: int) -> discord.Embed:
        """Builds the Study Hub embed showing active sessions and instructions."""
        guild_sessions = [
            s for s in self.bot.active_sessions.values()
            if s.guild_id == guild_id
        ]

        embed = discord.Embed(
            title="📖 Tracger — Study Hub",
            color=COLOR_ACTIVE if guild_sessions else discord.Color.from_rgb(47, 49, 54),
            timestamp=datetime.now(timezone.utc)
        )

        if not guild_sessions:
            embed.description = (
                "Ready to focus? Hit the button below to start tracking your study session.\n\n"
                "Each session gets its own thread for check-ins and controls — "
                "keeping this channel clean and your progress organized."
            )
        else:
            active_count = sum(1 for s in guild_sessions if s.status == "active")
            paused_count = sum(1 for s in guild_sessions if s.status == "paused")

            status_parts = []
            if active_count:
                status_parts.append(f"🟢 {active_count} active")
            if paused_count:
                status_parts.append(f"🟡 {paused_count} paused")

            embed.description = (
                f"**{len(guild_sessions)}** study session{'s' if len(guild_sessions) != 1 else ''} "
                f"in progress ({', '.join(status_parts)})\n"
            )

            for s in guild_sessions:
                user = self.bot.get_user(s.user_id)
                name = user.display_name if user else f"User {s.user_id}"
                elapsed = s.get_current_elapsed_seconds()
                dur_str = format_duration(elapsed)
                status_icon = "▶️" if s.status == "active" else "⏸️"
                topic_str = f" ({s.topic})" if s.topic else ""
                thread_str = f" • <#{s.thread_id}>" if s.thread_id else ""

                embed.add_field(
                    name=f"{status_icon} {name} — {s.subject}{topic_str}",
                    value=f"⏱️ **{dur_str}**{thread_str}",
                    inline=False
                )

        embed.set_footer(text="Tracger • Click a button below to get started")
        return embed

    async def update_hub(self, guild_id: int):
        """Re-renders the persistent hub embed in-place."""
        record = await self.bot.db.get_hub_message(guild_id)
        if not record:
            return

        channel_id, message_id = record
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(message_id)
            new_embed = self.generate_hub_embed(guild_id)
            await msg.edit(embed=new_embed)
        except Exception:
            pass
