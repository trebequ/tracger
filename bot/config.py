import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

@dataclass
class Config:
    token: str
    guild_id: int | None = None
    study_channel_ids: list[int] = field(default_factory=list)
    daily_log_channel_id: int | None = None
    summary_channel_id: int | None = None
    checkin_interval_minutes: int = 60
    db_path: str = "data/tracger.db"

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_TOKEN is missing or empty in .env file.")

        raw_guild = os.getenv("GUILD_ID", "").strip()
        guild_id = int(raw_guild) if raw_guild.isdigit() else None

        raw_channels = os.getenv("STUDY_CHANNEL_IDS", "").strip()
        study_channels = [
            int(c.strip()) for c in raw_channels.split(",") if c.strip().isdigit()
        ]

        raw_daily = os.getenv("DAILY_LOG_CHANNEL_ID", "").strip()
        daily_log_channel = int(raw_daily) if raw_daily.isdigit() else None

        raw_summary = os.getenv("SUMMARY_CHANNEL_ID", os.getenv("SESSION_LOG_CHANNEL_ID", "")).strip()
        summary_channel = int(raw_summary) if raw_summary.isdigit() else None

        raw_interval = os.getenv("CHECKIN_INTERVAL_MINUTES", "60").strip()
        checkin_interval = int(raw_interval) if raw_interval.isdigit() else 60

        db_path = os.getenv("DB_PATH", "data/tracger.db").strip()
        # Ensure parent directory for database exists
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        return cls(
            token=token,
            guild_id=guild_id,
            study_channel_ids=study_channels,
            daily_log_channel_id=daily_log_channel,
            summary_channel_id=summary_channel,
            checkin_interval_minutes=max(5, checkin_interval),
            db_path=db_path,
        )
