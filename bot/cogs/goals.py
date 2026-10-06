from datetime import datetime, timezone
import discord
from discord import app_commands
from bot.helpers import parse_duration, format_duration, progress_bar, COLOR_ACTIVE

class GoalsCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        tree = self.bot.tree

        goal_group = app_commands.Group(name="goal", description="Manage personal daily study targets")

        @goal_group.command(name="set", description="Set your daily study goal")
        @app_commands.describe(target="Daily target duration (e.g. 3h, 2h30m, 90m)")
        async def goal_set(interaction: discord.Interaction, target: str):
            minutes = parse_duration(target)
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

        @goal_group.command(name="check", description="Check today's study progress toward your goal")
        async def goal_check(interaction: discord.Interaction):
            goal_mins = await self.bot.db.get_daily_goal(interaction.user.id)
            if goal_mins <= 0:
                await interaction.response.send_message(
                    "ℹ️ You haven't set a daily target yet! Use `/goal set 2h` to set one.",
                    ephemeral=True
                )
                return

            today_secs = await self.bot.db.get_today_total_seconds(interaction.user.id)
            goal_secs = goal_mins * 60
            bar = progress_bar(today_secs, goal_secs)

            embed = discord.Embed(
                title=f"🎯 Daily Study Progress — {interaction.user.display_name}",
                color=COLOR_ACTIVE,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.add_field(
                name="Progress",
                value=f"**{format_duration(today_secs)}** / {format_duration(goal_secs)}\n{bar}",
                inline=False
            )

            if today_secs >= goal_secs:
                embed.description = "🎉 **Target reached today!** Fantastic consistency!"
            else:
                remaining = goal_secs - today_secs
                embed.description = f"**{format_duration(remaining)}** remaining to reach your goal."

            embed.set_footer(text="Tracger Goals")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @goal_group.command(name="clear", description="Remove your daily study target")
        async def goal_clear(interaction: discord.Interaction):
            await self.bot.db.set_daily_goal(interaction.user.id, 0)
            await interaction.response.send_message("🧹 Your daily study target has been cleared.", ephemeral=True)

        tree.add_command(goal_group)
