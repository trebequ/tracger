import random
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

# Rotating pairs with exactly 2 subjects and 2 topics
MODAL_EXAMPLES = [
    ("Law, World History", "Constitutional Rights, Cold War"),
    ("Graphic Design, Economics", "Figma Layouts, Monetary Policy"),
    ("Psychology, Literature", "Cognitive Biases, Poetry Analysis"),
    ("Biochemistry, Linear Algebra", "Enzyme Kinetics, Vector Spaces"),
    ("Philosophy, Sociology", "Stoic Ethics, Social Mobility"),
    ("Architecture, Data Structures", "Urban Planning, Binary Trees"),
]

class StudyModal(ui.Modal, title="📖 Start Study Session"):
    def __init__(self, cog: "SessionsCog"):
        super().__init__()
        self.cog = cog
        subjects, topics = random.choice(MODAL_EXAMPLES)

        self.subject_input = ui.TextInput(
            label="Subject",
            placeholder=f"e.g. {subjects}",
            required=True,
            max_length=60
        )
        self.topic_input = ui.TextInput(
            label="Topic (Optional)",
            placeholder=f"e.g. {topics}",
            required=False,
            max_length=100
        )
        self.duration_input = ui.TextInput(
            label="Planned Duration (Optional)",
            placeholder="e.g. 2h, 1h30m, 45m (Leave empty for open-ended)",
            required=False,
            max_length=20
        )
        self.add_item(self.subject_input)
        self.add_item(self.topic_input)
        self.add_item(self.duration_input)

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
        placeholder="e.g. Psychology, Macroeconomics, Literature",
        required=True,
        max_length=60
    )
    topic_input = ui.TextInput(
        label="New Topic (Optional)",
        placeholder="e.g. Cognitive Biases, Monetary Policy, Poetry Analysis",
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

class ThreadControlView(ui.View):
    """Session controls displayed inside the user's session thread."""
    def __init__(self, cog: "SessionsCog", user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "⚠️ This session belongs to another member.",
                ephemeral=True
            )
            return False
        return True

    @ui.button(label="⏸️ Pause", style=discord.ButtonStyle.secondary, custom_id="thread_pause")
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
        await self.cog.bot.refresh_hub(session.guild_id)

    @ui.button(label="🔄 Switch", style=discord.ButtonStyle.primary, custom_id="thread_switch")
    async def switch_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SwitchModal(self.cog))

    @ui.button(label="✅ Check-in", style=discord.ButtonStyle.success, custom_id="thread_checkin")
    async def checkin_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.bot.checkin_cog.do_manual_checkin(interaction)

    @ui.button(label="⏹️ End Session", style=discord.ButtonStyle.danger, custom_id="thread_end")
    async def end_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.end_session_internal(interaction)


# Keep the old SessionControlView for /status and /study fallback (non-hub usage)
class SessionControlView(ui.View):
    def __init__(self, cog: "SessionsCog", user_id: int):
        super().__init__(timeout=None)
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
        await self.cog.bot.refresh_hub(session.guild_id)

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
            await self.bot.refresh_hub(interaction.guild_id)

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
            await self.bot.refresh_hub(interaction.guild_id)

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

            # If inside the session thread, respond publicly within the thread; otherwise keep ephemeral
            is_inside_thread = (session.thread_id is not None and interaction.channel_id == session.thread_id)
            await interaction.response.defer(ephemeral=not is_inside_thread)
            await self.end_session_internal(interaction)

        @tree.command(name="summary", description="View your latest completed study session summary in this channel")
        @app_commands.describe(member="Member to view summary for (leave blank for yourself)")
        async def summary_command(interaction: discord.Interaction, member: discord.Member | None = None):
            target = member or interaction.user
            summary = await self.bot.db.get_latest_completed_session(target.id)
            if not summary:
                await interaction.response.send_message(
                    f"ℹ️ No completed study sessions found for **{target.display_name}**.",
                    ephemeral=True
                )
                return

            embed = build_session_summary_embed(
                user=target,
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
            await interaction.response.send_message(embed=embed)

        @tree.command(name="summarychannel", description="Set or view the channel where all completed session summaries are posted")
        @app_commands.describe(channel="Text channel to receive session summaries (leave empty to view current)")
        async def summarychannel_command(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
            guild_id = interaction.guild_id or 0
            if channel:
                await self.bot.db.set_summary_channel(guild_id, channel.id)
                await interaction.response.send_message(
                    f"✅ Session summaries will now automatically be posted to {channel.mention} whenever members finish studying!",
                    ephemeral=True
                )
            else:
                ch_id = await self.bot.db.get_summary_channel(guild_id) or self.bot.config.summary_channel_id
                if ch_id:
                    await interaction.response.send_message(
                        f"📢 Current session summary channel: <#{ch_id}>",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "ℹ️ No summary channel set yet. Use `/summarychannel #channel` to configure one!",
                        ephemeral=True
                    )

    async def _create_session_thread(self, interaction: discord.Interaction, user: discord.User | discord.Member, subject: str, topic: str | None) -> discord.Thread | None:
        """
        Creates a thread for the session in the hub channel (preferred) or the interaction channel.
        Returns the thread or None if creation fails.
        """
        guild_id = interaction.guild_id or 0

        # Try to use the hub channel if one exists
        hub_record = await self.bot.db.get_hub_message(guild_id)
        if hub_record:
            target_channel = self.bot.get_channel(hub_record[0])
        else:
            target_channel = interaction.channel

        if not target_channel:
            return None

        # If current target is already a thread, use its parent channel
        if isinstance(target_channel, discord.Thread):
            target_channel = target_channel.parent

        if not target_channel or not hasattr(target_channel, 'create_thread'):
            return None

        topic_str = f" — {topic}" if topic else ""
        thread_name = f"📖 {user.display_name} — {subject}{topic_str}"
        # Truncate to Discord's 100-char thread name limit
        if len(thread_name) > 100:
            thread_name = thread_name[:97] + "..."

        try:
            # 1. Try private thread first (Discord NEVER posts an announcement in the channel for private threads!)
            thread = await target_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=60
            )
            return thread
        except discord.Forbidden:
            print("⚠️ Private thread forbidden: Tracger needs 'Create Private Threads' permission in Discord to prevent channel announcement cards.")
        except Exception as e:
            print(f"⚠️ Private thread failed: {e}")

        try:
            # 2. Fallback to public thread if server/permissions disallow private threads
            thread = await target_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60
            )
            return thread
        except discord.Forbidden:
            print("⚠️ Public thread forbidden: Tracger needs 'Create Public Threads' and 'Send Messages in Threads'. Falling back to channel messages.")
            return None
        except Exception as e:
            print(f"Failed to create session thread: {e}")
            return None

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

        # Create a session thread
        thread = await self._create_session_thread(interaction, user, subject, topic)
        if thread:
            state.thread_id = thread.id

        # Schedule check-in reminders
        self.bot.checkin_cog.schedule_reminder(state)

        # Send start confirmation
        embed = build_session_start_embed(user, subject, topic, planned_mins)

        if thread:
            # Acknowledge the interaction with a pointer to the thread
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"✅ Session started! Head to your session thread: {thread.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Session started! Head to your session thread: {thread.mention}",
                    ephemeral=True
                )

            # Post the full session embed + controls inside the thread, mentioning user to auto-join
            thread_view = ThreadControlView(self, user.id)
            await thread.send(content=f"<@{user.id}>", embed=embed, view=thread_view)

            # Add duration info for check-in context
            if planned_mins:
                checkin_info = f"⏱️ Planned: **{format_duration(planned_mins * 60)}** • Check-ins based on session length"
            else:
                checkin_info = "⏱️ Open-ended session • First check-in in **30 minutes**, then every **25 minutes**"
            await thread.send(checkin_info)
        else:
            # No thread — fall back to inline response
            view = SessionControlView(self, user.id)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)

        await self.bot.refresh_dashboard(guild_id)
        await self.bot.refresh_hub(guild_id)

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

        # Also update the thread name if we have one
        if session.thread_id:
            thread = self.bot.get_channel(session.thread_id)
            if thread:
                topic_str = f" — {new_topic}" if new_topic else ""
                new_name = f"📖 {interaction.user.display_name} — {new_subject}{topic_str}"
                if len(new_name) > 100:
                    new_name = new_name[:97] + "..."
                try:
                    await thread.edit(name=new_name)
                except Exception:
                    pass

        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)

        await self.bot.refresh_dashboard(session.guild_id)
        await self.bot.refresh_hub(session.guild_id)

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

        # Handle thread cleanup and summary delivery
        if session.thread_id:
            thread = self.bot.get_channel(session.thread_id)
            if thread:
                if interaction.channel_id == session.thread_id:
                    # User clicked End inside the thread: post summary, then delete thread to clear channel clutter
                    try:
                        await interaction.followup.send(embed=embed)
                        await thread.send("🗑️ *Session complete! This throwaway thread will self-destruct in 30 seconds to keep the server clean.*")
                    except Exception:
                        pass

                    async def _delayed_thread_delete(th):
                        import asyncio
                        await asyncio.sleep(30)
                        try:
                            await th.delete(reason="Tracger study session ended - throwaway cleanup")
                        except Exception:
                            pass

                    import asyncio
                    asyncio.create_task(_delayed_thread_delete(thread))
                else:
                    # User clicked End from the Hub panel or slash command outside the thread
                    try:
                        if interaction.response.is_done():
                            # Send summary and auto-dissolve after 15s to leave the hub spotless
                            msg = await interaction.followup.send(embed=embed, wait=True)
                            if msg:
                                async def _auto_dissolve_msg(m):
                                    import asyncio
                                    await asyncio.sleep(15)
                                    try:
                                        await m.delete()
                                    except Exception:
                                        pass
                                import asyncio
                                asyncio.create_task(_auto_dissolve_msg(msg))
                        else:
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                    except Exception:
                        pass

                    # Immediately delete throwaway thread so the starter card dissolves from the channel
                    try:
                        await thread.delete(reason="Tracger study session ended - throwaway cleanup")
                    except Exception:
                        pass
        else:
            # Fallback if thread creation failed: send embed ephemerally
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception:
                pass

        await self.bot.refresh_dashboard(session.guild_id)
        await self.bot.refresh_hub(session.guild_id)

        # Post summary to the dedicated summary channel if configured
        try:
            summary_ch_id = await self.bot.db.get_summary_channel(session.guild_id)
            if not summary_ch_id and self.bot.config.summary_channel_id:
                summary_ch_id = self.bot.config.summary_channel_id

            if summary_ch_id:
                summary_ch = self.bot.get_channel(summary_ch_id)
                if summary_ch and summary_ch.id != (session.thread_id or 0):
                    await summary_ch.send(embed=embed)
        except Exception as e:
            print(f"Error posting to summary channel: {e}")

        # Check if user reached their daily goal in this session
        if summary["daily_goal_minutes"] > 0:
            goal_secs = summary["daily_goal_minutes"] * 60
            if summary["today_total_seconds"] >= goal_secs:
                try:
                    channel = self.bot.get_channel(session.channel_id)
                    if channel:
                        await channel.send(
                            f"🏆 **Goal Achieved!** <@{user_id}> reached their daily study target of "
                            f"**{format_duration(goal_secs)}** today! Outstanding commitment! 🔥"
                        )
                except Exception:
                    pass
