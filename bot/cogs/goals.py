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

        @goal_group.command(name="set", description="Set or extend your daily study goal (e.g. 3h, 90m, or +1h)")
        @app_commands.describe(target="Daily target duration (e.g. 3h, 2h30m, 90m, +1h, or 'clear')")
        async def goal_set(interaction: discord.Interaction, target: str):
            val = target.strip().lower()
            if val in ("0", "clear", "reset", "off", "none", "remove", "0m", "0h"):
                await self.bot.db.set_daily_goal(interaction.user.id, 0)
                if hasattr(self.bot, "sessions_cog"):
                    await self.bot.sessions_cog.update_thread_control_panel(interaction.user.id)
                await interaction.response.send_message("🧹 Today's study target has been cleared.", ephemeral=True)
                return

            if val.startswith("+"):
                delta_mins = parse_duration(val[1:])
                if not delta_mins or delta_mins <= 0:
                    await interaction.response.send_message("❌ Invalid extension format. Please specify e.g. `+1h` or `+30m`.", ephemeral=True)
                    return
                current_goal = await self.bot.db.get_daily_goal(interaction.user.id)
                if current_goal <= 0:
                    today_secs = await self.bot.db.get_today_total_seconds(interaction.user.id)
                    current_goal = max(0, today_secs // 60)
                minutes = current_goal + delta_mins
            else:
                minutes = parse_duration(val)

            if not minutes or minutes <= 0:
                await interaction.response.send_message(
                    "❌ Invalid format. Please specify e.g. `2h`, `1h30m`, `+1h` (or type `clear`).",
                    ephemeral=True
                )
                return

            await self.bot.db.set_daily_goal(interaction.user.id, minutes)
            if hasattr(self.bot, "sessions_cog"):
                await self.bot.sessions_cog.update_thread_control_panel(interaction.user.id)
            await interaction.response.send_message(
                f"🎯 Today's study target set to **{format_duration(minutes * 60)}**! Go crush it! 💪",
                ephemeral=True
            )

        @goal_group.command(name="check", description="Check today's study progress toward your goal")
        async def goal_check(interaction: discord.Interaction):
            goal_mins = await self.bot.db.get_daily_goal(interaction.user.id)
            if goal_mins <= 0:
                today_secs = await self.bot.db.get_today_total_seconds(interaction.user.id)
                today_dur = format_duration(today_secs)
                await interaction.response.send_message(
                    f"ℹ️ You haven't set a goal for today yet! You've focused for **{today_dur}** so far today. Use `/goal set 2h` or the Hub to set a target.",
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
                overtime = today_secs - goal_secs
                bonus_str = f" (+{format_duration(overtime)} bonus focus!)" if overtime > 0 else ""
                embed.description = f"🎉 **Target reached today!** Fantastic consistency!{bonus_str}"
            else:
                remaining = goal_secs - today_secs
                embed.description = f"**{format_duration(remaining)}** remaining to reach your goal."

            embed.set_footer(text="Tracger Goals")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @goal_group.command(name="clear", description="Remove your daily study target")
        async def goal_clear(interaction: discord.Interaction):
            await self.bot.db.set_daily_goal(interaction.user.id, 0)
            if hasattr(self.bot, "sessions_cog"):
                await self.bot.sessions_cog.update_thread_control_panel(interaction.user.id)
            await interaction.response.send_message("🧹 Your daily study target has been cleared.", ephemeral=True)

        tree.add_command(goal_group)
