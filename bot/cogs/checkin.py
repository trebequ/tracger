import asyncio
from datetime import datetime, timezone
import discord
from discord import app_commands, ui
from bot.helpers import format_duration, COLOR_CHECKIN, COLOR_ALERT


class CheckInPromptView(ui.View):
    def __init__(self, cog: "CheckinCog", user_id: int, checkin_id: int):
        super().__init__(timeout=300)  # Button stays active for 5 mins
        self.cog = cog
        self.user_id = user_id
        self.checkin_id = checkin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "⚠️ This check-in prompt is for another member.",
                ephemeral=True
            )
            return False
        return True

    @ui.button(label="✅ I'm here & focused!", style=discord.ButtonStyle.success)
    async def confirm_checkin_button(self, interaction: discord.Interaction, button: ui.Button):
        success = await self.cog.bot.db.record_checkin_response(self.checkin_id)
        button.disabled = True
        button.label = "✅ Checked In"
        button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            "🌟 Excellent! Your check-in has been logged. Keep up the great flow!",
            ephemeral=True
        )

        session = self.cog.bot.active_sessions.get(self.user_id)
        if session and session.status == "active":
            session.missed_checkins = 0  # Reset missed counter on successful check-in
            # Schedule next reminder if applicable
            self.cog.schedule_reminder(session)

    async def on_timeout(self):
        """Gracefully handle when check-in button expires without response."""
        # Disable all buttons to prevent "interaction failed" errors
        for item in self.children:
            item.disabled = True
            if hasattr(item, 'label'):
                item.label = "⏰ Expired"
                item.style = discord.ButtonStyle.secondary
        # We can't edit the message without an interaction, so this is best-effort
        # The missed check-in is handled when the next one fires


class CheckinCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        tree = self.bot.tree

        @tree.command(name="checkin", description="Perform a manual study check-in")
        async def checkin_command(interaction: discord.Interaction):
            await self.do_manual_checkin(interaction)

    def calculate_next_interval_seconds(self, session) -> int | None:
        """
        Determines the number of seconds until the next check-in.
        Returns None if no more check-ins should be scheduled.

        Timed sessions:
          ≤ 30min → single check-in at halfway, then done
          31–90min → every 30 minutes
          90+ min → every 45 minutes

        Open-ended sessions (graduated):
          1st check-in → after 30 minutes
          2nd+ → every 25 minutes (with a notice message)
        """
        if session.planned_minutes:
            # Timed session logic
            if session.planned_minutes <= 30:
                if session.checkin_count == 0:
                    # Single check-in at halfway
                    return max(5, session.planned_minutes // 2) * 60
                else:
                    return None  # No more check-ins for short sessions
            elif session.planned_minutes <= 90:
                return 30 * 60
            else:
                return 45 * 60
        else:
            # Open-ended: graduated intervals
            if session.checkin_count == 0:
                return 30 * 60  # First at 30 min
            else:
                return 25 * 60  # Then every 25 min

    def schedule_reminder(self, session):
        self.cancel_reminder(session)
        delay = self.calculate_next_interval_seconds(session)
        if delay is None:
            return  # No more check-ins to schedule
        session.checkin_task = asyncio.create_task(self._reminder_worker(session.user_id, delay))

    def cancel_reminder(self, session):
        if session.checkin_task and not session.checkin_task.done():
            session.checkin_task.cancel()
        session.checkin_task = None

    async def _get_checkin_channel(self, session):
        """Get the thread channel for check-ins, falling back to the original channel."""
        if session.thread_id:
            channel = self.bot.get_channel(session.thread_id)
            if channel:
                return channel
        return self.bot.get_channel(session.channel_id)

    async def _reminder_worker(self, user_id: int, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            session = self.bot.active_sessions.get(user_id)
            if not session or session.status != "active":
                return

            # Check for missed previous check-in
            missed_note = ""
            open_id = await self.bot.db.get_latest_open_checkin(session.session_id, user_id)
            if open_id:
                # Previous check-in was never responded to — mark it as missed
                session.missed_checkins += 1
                missed_note = f"\n\n⚠️ *You missed your last check-in (#{session.missed_checkins} consecutive miss{'es' if session.missed_checkins > 1 else ''}). Still at your desk?*"

            # Increment check-in counter
            session.checkin_count += 1

            # Log checkin entry in database
            checkin_id = await self.bot.db.log_checkin(session.session_id, user_id)
            session.latest_checkin_id = checkin_id

            channel = await self._get_checkin_channel(session)
            if not channel:
                return

            elapsed = session.get_current_elapsed_seconds()

            # Build interval notice for open-ended sessions transitioning to 25min
            interval_notice = ""
            if not session.planned_minutes and session.checkin_count == 1:
                interval_notice = "\n\n📋 *Check-ins will now happen at intervals of 25 minutes.*"

            embed = discord.Embed(
                title="🔔 Study Check-in Reminder",
                description=(
                    f"Hey <@{user_id}>, you've been working on **{session.subject}** "
                    f"for **{format_duration(elapsed)}**!\n\n"
                    f"Take a moment to check in, stretch, or hydrate. "
                    f"Tap the button below or type `/checkin` when ready."
                    f"{missed_note}{interval_notice}"
                ),
                color=COLOR_ALERT if session.missed_checkins >= 2 else COLOR_CHECKIN,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Check-in #{session.checkin_count} • Accountability check")

            view = CheckInPromptView(self, user_id, checkin_id)
            await channel.send(content=f"<@{user_id}>", embed=embed, view=view)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in checkin worker: {e}")

    async def do_manual_checkin(self, interaction: discord.Interaction):
        session = self.bot.active_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message(
                "ℹ️ You do not have an active session right now. Start one with `/study`!",
                ephemeral=True
            )
            return

        # Check if there was an open checkin
        open_id = await self.bot.db.get_latest_open_checkin(session.session_id, interaction.user.id)
        if open_id:
            await self.bot.db.record_checkin_response(open_id)
        else:
            # Log fresh check-in
            cid = await self.bot.db.log_checkin(session.session_id, interaction.user.id)
            await self.bot.db.record_checkin_response(cid)

        # Reset missed counter
        session.missed_checkins = 0

        # Reset the timer cycle for next reminder
        if session.status == "active":
            self.schedule_reminder(session)

        elapsed = session.get_current_elapsed_seconds()
        await interaction.response.send_message(
            f"✅ Check-in recorded! You are **{format_duration(elapsed)}** into your session on **{session.subject}**. Keep going! 🔥",
            ephemeral=True
        )
