import io
import json
from datetime import datetime, timezone
import discord
from discord import app_commands, ui
from bot.helpers import format_duration, progress_bar, COLOR_ENDED, COLOR_ACTIVE

class LeaderboardView(ui.View):
    def __init__(self, cog: "StatsCog", guild_id: int, current_period: str = "week"):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.current_period = current_period
        self._update_button_styles()

    def _update_button_styles(self):
        self.today_button.style = discord.ButtonStyle.primary if self.current_period == "today" else discord.ButtonStyle.secondary
        self.week_button.style = discord.ButtonStyle.primary if self.current_period == "week" else discord.ButtonStyle.secondary
        self.all_button.style = discord.ButtonStyle.primary if self.current_period == "all" else discord.ButtonStyle.secondary

    @ui.button(label="📅 Today", style=discord.ButtonStyle.secondary, custom_id="lb_today")
    async def today_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_period = "today"
        self._update_button_styles()
        embed = await self.cog.build_leaderboard_embed(self.guild_id, "today")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="📆 This Week", style=discord.ButtonStyle.primary, custom_id="lb_week")
    async def week_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_period = "week"
        self._update_button_styles()
        embed = await self.cog.build_leaderboard_embed(self.guild_id, "week")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="📈 All-Time", style=discord.ButtonStyle.secondary, custom_id="lb_all")
    async def all_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_period = "all"
        self._update_button_styles()
        embed = await self.cog.build_leaderboard_embed(self.guild_id, "all")
        await interaction.response.edit_message(embed=embed, view=self)

class HistoryPaginationView(ui.View):
    def __init__(self, cog: "StatsCog", user: discord.User | discord.Member, limit: int = 5):
        super().__init__(timeout=180)
        self.cog = cog
        self.user = user
        self.limit = limit
        self.offset = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("⚠️ Use `/history` to view your own session history.", ephemeral=True)
            return False
        return True

    @ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.offset >= self.limit:
            self.offset -= self.limit
        embed, total = await self.cog.build_history_embed(self.user, self.limit, self.offset)
        self.prev_button.disabled = (self.offset == 0)
        self.next_button.disabled = (self.offset + self.limit >= total)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        self.offset += self.limit
        embed, total = await self.cog.build_history_embed(self.user, self.limit, self.offset)
        self.prev_button.disabled = (self.offset == 0)
        self.next_button.disabled = (self.offset + self.limit >= total)
        await interaction.response.edit_message(embed=embed, view=self)

class StatsCog:
    def __init__(self, bot):
        self.bot = bot

    async def setup(self):
        tree = self.bot.tree

        @tree.command(name="stats", description="View personal or another member's study analytics")
        @app_commands.describe(member="Member to view stats for (leave blank for yourself)")
        async def stats_command(interaction: discord.Interaction, member: discord.Member | None = None):
            target = member or interaction.user
            stats = await self.bot.db.get_user_stats(target.id)

            embed = discord.Embed(
                title=f"📊 Study Analytics — {target.display_name}",
                color=COLOR_ENDED,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)

            # Overview row
            embed.add_field(name="📅 Today", value=f"**{format_duration(stats['today_seconds'])}**", inline=True)
            embed.add_field(name="📆 This Week", value=f"**{format_duration(stats['week_seconds'])}**", inline=True)
            embed.add_field(name="📈 All-Time", value=f"**{format_duration(stats['all_time_seconds'])}**", inline=True)

            # Streak & Accountability
            streak_val = f"🔥 **{stats['current_streak']}** days (Best: {stats['longest_streak']})"
            embed.add_field(name="Streak", value=streak_val, inline=True)

            prompted = stats["checkins_prompted"]
            done = stats["checkins_done"]
            if prompted > 0:
                pct = int((done / prompted) * 100)
                check_str = f"✅ {done}/{prompted} ({pct}%)"
            else:
                check_str = "None logged"
            embed.add_field(name="Check-in Rate", value=check_str, inline=True)
            embed.add_field(name="Sessions Completed", value=str(stats["session_count"]), inline=True)

            # Daily Goal progress
            goal_mins = stats["daily_goal_minutes"]
            if goal_mins > 0:
                goal_secs = goal_mins * 60
                bar = progress_bar(stats["today_seconds"], goal_secs)
                embed.add_field(
                    name="🎯 Today's Goal",
                    value=f"{format_duration(stats['today_seconds'])} / {format_duration(goal_secs)}\n{bar}",
                    inline=False
                )

            # Top Subjects
            if stats["top_subjects"]:
                sub_lines = []
                total_sub_secs = sum(s["seconds"] for s in stats["top_subjects"]) or 1
                for s in stats["top_subjects"]:
                    bar = progress_bar(s["seconds"], total_sub_secs, length=8)
                    sub_lines.append(f"• **{s['subject']}**: {format_duration(s['seconds'])} {bar}")
                embed.add_field(name="📚 Top Focus Areas", value="\n".join(sub_lines), inline=False)
            else:
                embed.add_field(name="📚 Top Focus Areas", value="*No recorded subjects yet.*", inline=False)

            embed.set_footer(text="Tracger Study Insights")
            await interaction.response.send_message(embed=embed)

        @tree.command(name="leaderboard", description="View ranked study leaderboards across the server")
        async def leaderboard_command(interaction: discord.Interaction):
            guild_id = interaction.guild_id or 0
            embed = await self.build_leaderboard_embed(guild_id, "week")
            view = LeaderboardView(self, guild_id, "week")
            await interaction.response.send_message(embed=embed, view=view)

        @tree.command(name="history", description="Browse recent study session records")
        async def history_command(interaction: discord.Interaction):
            embed, total = await self.build_history_embed(interaction.user, limit=5, offset=0)
            if total == 0:
                await interaction.response.send_message("ℹ️ No completed sessions found yet. Start one with `/study`!", ephemeral=True)
                return

            view = HistoryPaginationView(self, interaction.user, limit=5)
            view.prev_button.disabled = True
            view.next_button.disabled = (total <= 5)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        @tree.command(name="export", description="Export database session data as a downloadable JSON file")
        async def export_command(interaction: discord.Interaction):
            data = await self.bot.db.export_all()
            json_bytes = json.dumps(data, indent=2).encode("utf-8")
            file = discord.File(io.BytesIO(json_bytes), filename="tracger_backup.json")
            await interaction.response.send_message(
                "📦 Here is your Tracger database backup. Keep this file safe!",
                file=file,
                ephemeral=True
            )

        @tree.command(name="import", description="Import session records from a JSON file backup")
        @app_commands.describe(backup_file="JSON file exported from Tracger")
        async def import_command(interaction: discord.Interaction, backup_file: discord.Attachment):
            if not backup_file.filename.endswith(".json"):
                await interaction.response.send_message("❌ Please upload a valid `.json` backup file.", ephemeral=True)
                return

            try:
                content = await backup_file.read()
                data = json.loads(content.decode("utf-8"))
                await self.bot.db.import_all(data)
                await interaction.response.send_message("✅ Database imported and restored successfully!", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to import backup: `{e}`", ephemeral=True)

    async def build_leaderboard_embed(self, guild_id: int, period: str) -> discord.Embed:
        period_titles = {
            "today": "📅 Today's Study Rankings",
            "week": "📆 This Week's Study Rankings",
            "all": "📈 All-Time Study Rankings"
        }

        data = await self.bot.db.get_leaderboard(guild_id, period)

        embed = discord.Embed(
            title=f"🏆 {period_titles.get(period, 'Study Leaderboard')}",
            color=COLOR_ACTIVE,
            timestamp=datetime.now(timezone.utc)
        )

        if not data:
            embed.description = "*No study sessions logged for this timeframe yet.*"
            return embed

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for idx, row in enumerate(data, start=1):
            badge = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            streak_str = f"🔥{row['current_streak']}" if row['current_streak'] > 0 else ""
            lines.append(
                f"{badge} **{row['display_name']}** — **{format_duration(row['total_seconds'])}** {streak_str}"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text="Tracger • Friendly accountability")
        return embed

    async def build_history_embed(self, user: discord.User | discord.Member, limit: int, offset: int) -> tuple[discord.Embed, int]:
        sessions, total = await self.bot.db.get_history(user.id, limit=limit, offset=offset)

        page = (offset // limit) + 1
        max_page = max(1, (total + limit - 1) // limit)

        embed = discord.Embed(
            title=f"📜 Session History — {user.display_name}",
            description=f"Showing **{len(sessions)}** of **{total}** recorded sessions (Page {page}/{max_page}):\n",
            color=COLOR_ENDED,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

        for s in sessions:
            dt = s["start_time"][:10] if s["start_time"] else "Unknown date"
            dur = format_duration(s["total_seconds"])
            topic_str = f" ({s['topic']})" if s["topic"] else ""
            status_emoji = "✅" if s["status"] == "completed" else "⏸️"
            embed.add_field(
                name=f"{status_emoji} {s['subject']}{topic_str}",
                value=f"📅 {dt} • ⏱️ {dur}",
                inline=False
            )

        return embed, total
