import asyncio
from datetime import datetime, timezone
import discord
from discord import app_commands, ui
from bot.helpers import format_duration, COLOR_CHECKIN

class CheckInPromptView(ui.View):
    def __init__(self, cog: "CheckinCog", user_id: int, checkin_id: int):
        super().__init__(timeout=300) # Button stays active for 5 mins
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
            # Schedule next reminder interval
            self.cog.schedule_reminder(session)

class CheckinCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        tree = self.bot.tree

        @tree.command(name="checkin", description="Perform a manual study check-in")
        async def checkin_command(interaction: discord.Interaction):
            await self.do_manual_checkin(interaction)

    def calculate_next_interval_seconds(self, session) -> int:
        """Determines the number of seconds until the next check-in."""
        if session.planned_minutes and session.planned_minutes <= 60:
            # For short sessions, prompt at halfway
            halfway = max(5, session.planned_minutes // 2)
            return halfway * 60
        else:
            # Hourly or configured interval
            return self.bot.config.checkin_interval_minutes * 60

    def schedule_reminder(self, session):
        self.cancel_reminder(session)
        delay = self.calculate_next_interval_seconds(session)
        session.checkin_task = asyncio.create_task(self._reminder_worker(session.user_id, delay))

    def cancel_reminder(self, session):
        if session.checkin_task and not session.checkin_task.done():
            session.checkin_task.cancel()
        session.checkin_task = None

    async def _reminder_worker(self, user_id: int, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            session = self.bot.active_sessions.get(user_id)
            if not session or session.status != "active":
                return

            # Log checkin entry in database
            checkin_id = await self.bot.db.log_checkin(session.session_id, user_id)
            session.latest_checkin_id = checkin_id

            channel = self.bot.get_channel(session.channel_id)
            if not channel:
                return

            elapsed = session.get_current_elapsed_seconds()
            embed = discord.Embed(
                title="🔔 Study Check-in Reminder",
                description=(
                    f"Hey <@{user_id}>, you've been working on **{session.subject}** "
                    f"for **{format_duration(elapsed)}**!\n\n"
                    f"Take a moment to check in, stretch, or hydrate. "
                    f"Tap the button below or type `/checkin` when ready."
                ),
                color=COLOR_CHECKIN,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text="Accountability check-in • Freeflow study")

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

        # Reset the timer cycle for next reminder
        if session.status == "active":
            self.schedule_reminder(session)

        elapsed = session.get_current_elapsed_seconds()
        await interaction.response.send_message(
            f"✅ Check-in recorded! You are **{format_duration(elapsed)}** into your session on **{session.subject}**. Keep going! 🔥",
            ephemeral=True
        )
