import io
import json
import asyncio
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from bot.helpers import format_duration, progress_bar, COLOR_ACTIVE, COLOR_ENDED

# IST is UTC + 5:30
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

class DailyReportCog:
    def __init__(self, bot):
        self.bot = bot
        self.report_task: asyncio.Task | None = None

    async def setup(self):
        tree = self.bot.tree

        @tree.command(name="dailyreport", description="Trigger or preview today's study report and backup manually")
        async def manual_report_command(interaction: discord.Interaction):
            await interaction.response.defer()
            success = await self.send_daily_report(channel_override=interaction.channel)
            if success:
                await interaction.followup.send("✅ Daily study report & backup dispatched!", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ Could not generate report. Check bot permissions.", ephemeral=True)

        @tree.command(name="dailylogchannel", description="Set or view the channel where the daily 11:00 PM IST report & backup are sent")
        @app_commands.describe(channel="Text channel to receive daily reports and backups (leave empty to view current)")
        async def dailylogchannel_command(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
            guild_id = interaction.guild_id or 0
            if channel:
                await self.bot.db.set_daily_log_channel(guild_id, channel.id)
                await interaction.response.send_message(
                    f"✅ Daily 11:00 PM IST study recaps and automated database backups will now be posted to {channel.mention}!",
                    ephemeral=True
                )
            else:
                ch_id = await self.bot.db.get_daily_log_channel(guild_id) or self.bot.config.daily_log_channel_id
                if ch_id:
                    await interaction.response.send_message(
                        f"📢 Current daily log channel for this server: <#{ch_id}>",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "ℹ️ No daily log channel set yet for this server. Use `/dailylogchannel #channel` to configure one!",
                        ephemeral=True
                    )

        # Start the 11:00 PM IST background loop
        self.report_task = asyncio.create_task(self._daily_schedule_loop())

    async def _daily_schedule_loop(self):
        """Runs indefinitely, firing every day at 11:00 PM IST (17:30 UTC)."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now_utc = datetime.now(timezone.utc)
            # 11:00 PM IST is 17:30 UTC
            target_utc = now_utc.replace(hour=17, minute=30, second=0, microsecond=0)

            if target_utc <= now_utc:
                target_utc += timedelta(days=1)

            sleep_seconds = (target_utc - now_utc).total_seconds()
            print(f"⏰ Daily report scheduled in {sleep_seconds / 3600:.2f} hours (at 11:00 PM IST)")

            try:
                await asyncio.sleep(sleep_seconds)
                await self.dispatch_all_daily_reports()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in daily report loop: {e}")
                # Wait 60s before retrying to prevent tight crash loop
                await asyncio.sleep(60)

    async def dispatch_all_daily_reports(self):
        """Dispatches daily report & backup to all configured guild channels."""
        sent_channel_ids = set()

        # 1. Dispatch to all channels stored in database across guilds
        try:
            configured = await self.bot.db.get_all_daily_log_channels()
            for guild_id, channel_id in configured:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await self.send_daily_report(channel_override=channel)
                    sent_channel_ids.add(channel_id)
        except Exception as e:
            print(f"Error dispatching db daily reports: {e}")

        # 2. Fallback to env-configured daily_log_channel_id if not already sent
        if self.bot.config.daily_log_channel_id and self.bot.config.daily_log_channel_id not in sent_channel_ids:
            channel = self.bot.get_channel(self.bot.config.daily_log_channel_id)
            if channel:
                await self.send_daily_report(channel_override=channel)

    async def send_daily_report(self, channel_override: discord.TextChannel | None = None) -> bool:
        channel = channel_override
        if not channel:
            target_id = self.bot.config.daily_log_channel_id
            if not target_id:
                return False
            channel = self.bot.get_channel(target_id)
            if not channel:
                return False

        guild_id = channel.guild.id if hasattr(channel, "guild") else (self.bot.config.guild_id or 0)
        now_ist = datetime.now(IST_OFFSET)
        date_str = now_ist.strftime("%B %d, %Y")
        iso_date = now_ist.strftime("%Y-%m-%d")

        # 1. Fetch today's leaderboard
        leaderboard = await self.bot.db.get_leaderboard(guild_id, "today")

        # 2. Compute total server study seconds today
        total_today_secs = sum(row["total_seconds"] for row in leaderboard)

        embed = discord.Embed(
            title=f"🌙 Daily Study Recap — {date_str}",
            description=f"Compounding focus data for today. Total group focus: **{format_duration(total_today_secs)}**",
            color=COLOR_ACTIVE if total_today_secs > 0 else COLOR_ENDED,
            timestamp=datetime.now(timezone.utc)
        )

        if leaderboard:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for idx, row in enumerate(leaderboard, start=1):
                badge = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
                streak = f"🔥{row['current_streak']}" if row['current_streak'] > 0 else ""
                lines.append(f"{badge} **{row['display_name']}** — **{format_duration(row['total_seconds'])}** {streak}")
            embed.add_field(name="🏆 Today's Standings", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="🏆 Today's Standings", value="*No study sessions logged today.*", inline=False)

        embed.set_footer(text="Tracger Daily Digest • 11:00 PM IST • Automated Backup Attached")

        # 3. Create JSON backup attachment
        data = await self.bot.db.export_all()
        json_bytes = json.dumps(data, indent=2).encode("utf-8")
        backup_file = discord.File(
            io.BytesIO(json_bytes),
            filename=f"tracger_backup_{iso_date}.json"
        )

        try:
            await channel.send(embed=embed, file=backup_file)
            return True
        except Exception as e:
            print(f"Failed to send daily report: {e}")
            return False
