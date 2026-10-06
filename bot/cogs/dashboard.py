from datetime import datetime, timezone
import discord
from discord import app_commands
from bot.helpers import format_duration, COLOR_ACTIVE, COLOR_PAUSED

class DashboardCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        tree = self.bot.tree

        @tree.command(name="dashboard", description="Pin or display a live study overview board in this channel")
        async def dashboard_command(interaction: discord.Interaction):
            guild_id = interaction.guild_id or 0
            embed = self.generate_dashboard_embed(guild_id)
            await interaction.response.send_message(embed=embed)
            msg = await interaction.original_response()

            # Store the message info for live automatic edits
            await self.bot.db.set_dashboard_message(guild_id, msg.channel.id, msg.id)

    def generate_dashboard_embed(self, guild_id: int) -> discord.Embed:
        # Find active sessions in this guild
        guild_sessions = [
            s for s in self.bot.active_sessions.values()
            if s.guild_id == guild_id
        ]

        embed = discord.Embed(
            title="📋 Tracger — Live Study Dashboard",
            color=COLOR_ACTIVE if guild_sessions else discord.Color.dark_grey(),
            timestamp=datetime.now(timezone.utc)
        )

        if not guild_sessions:
            embed.description = (
                "☕ *No active study sessions right now.*\n\n"
                "Hop into a voice channel and type `/study` to begin tracking!"
            )
            embed.set_footer(text="Tracger • Updates automatically as members study")
            return embed

        for s in guild_sessions:
            user = self.bot.get_user(s.user_id)
            name = user.display_name if user else f"User {s.user_id}"
            elapsed = s.get_current_elapsed_seconds()
            dur_str = format_duration(elapsed)

            status_bullet = "🟢 **Running**" if s.status == "active" else "🟡 **Paused**"
            topic_str = f" ({s.topic})" if s.topic else ""
            planned_str = f" / {format_duration(s.planned_minutes * 60)}" if s.planned_minutes else ""

            embed.add_field(
                name=f"{name} — {s.subject}{topic_str}",
                value=f"{status_bullet} • ⏱️ **{dur_str}**{planned_str}",
                inline=False
            )

        embed.set_footer(text="Updates automatically when sessions start, pause, or end")
        return embed

    async def update_dashboard(self, guild_id: int):
        """Attempts to edit the existing live dashboard embed."""
        record = await self.bot.db.get_dashboard_message(guild_id)
        if not record:
            return

        channel_id, message_id = record
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(message_id)
            new_embed = self.generate_dashboard_embed(guild_id)
            await msg.edit(embed=new_embed)
        except Exception:
            # Message might have been deleted or permissions changed
            pass
