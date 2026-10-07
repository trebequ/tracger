import os
import json
from datetime import datetime, timezone, timedelta
import aiosqlite

class Database:
    def __init__(self, db_path: str = "data/tracger.db"):
        self.db_path = db_path

    async def init_schema(self):
        """Initializes tables and indexes if they do not exist."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")

            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id            INTEGER PRIMARY KEY,
                    display_name       TEXT NOT NULL,
                    daily_goal_minutes INTEGER DEFAULT 0,
                    current_streak     INTEGER DEFAULT 0,
                    longest_streak     INTEGER DEFAULT 0,
                    last_study_date    TEXT,
                    created_at         TEXT DEFAULT (datetime('now'))
                );
            """)

            # Study sessions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         INTEGER NOT NULL,
                    guild_id        INTEGER NOT NULL,
                    subject         TEXT NOT NULL,
                    topic           TEXT,
                    planned_minutes INTEGER,
                    start_time      TEXT NOT NULL,
                    end_time        TEXT,
                    total_seconds   INTEGER DEFAULT 0,
                    status          TEXT DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

            # Segments within a session (handles pause / resume)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    segment_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  INTEGER NOT NULL,
                    start_time  TEXT NOT NULL,
                    end_time    TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)

            # Check-ins table for accountability logs
            await db.execute("""
                CREATE TABLE IF NOT EXISTS checkins (
                    checkin_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   INTEGER NOT NULL,
                    user_id      INTEGER NOT NULL,
                    prompted_at  TEXT NOT NULL,
                    responded_at TEXT,
                    responded    INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)

            # Live dashboard message trackers
            await db.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_messages (
                    guild_id   INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL
                );
            """)

            # Persistent Study Hub message trackers
            await db.execute("""
                CREATE TABLE IF NOT EXISTS hub_messages (
                    guild_id   INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL
                );
            """)

            # Dedicated session summary channel
            await db.execute("""
                CREATE TABLE IF NOT EXISTS summary_channels (
                    guild_id   INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                );
            """)

            await db.commit()

    async def upsert_user(self, user_id: int, display_name: str):
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO users (user_id, display_name, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET display_name = excluded.display_name;
            """, (user_id, display_name, now_str))
            await db.commit()

    async def create_session(
        self,
        user_id: int,
        guild_id: int,
        display_name: str,
        subject: str,
        topic: str | None,
        planned_minutes: int | None
    ) -> int:
        await self.upsert_user(user_id, display_name)
        now_str = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO sessions (user_id, guild_id, subject, topic, planned_minutes, start_time, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active');
            """, (user_id, guild_id, subject.strip(), topic.strip() if topic else None, planned_minutes, now_str))
            session_id = cursor.lastrowid
            await db.commit()
            return session_id

    async def create_segment(self, session_id: int) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO segments (session_id, start_time)
                VALUES (?, ?);
            """, (session_id, now_str))
            segment_id = cursor.lastrowid
            await db.commit()
            return segment_id

    async def end_segment(self, segment_id: int) -> int:
        """Ends the segment, returns the seconds elapsed in that segment."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT start_time FROM segments WHERE segment_id = ?;", (segment_id,))
            row = await cursor.fetchone()
            if not row or not row["start_time"]:
                return 0

            start_dt = datetime.fromisoformat(row["start_time"])
            elapsed = max(0, int((now - start_dt).total_seconds()))

            await db.execute("""
                UPDATE segments SET end_time = ? WHERE segment_id = ?;
            """, (now_str, segment_id))
            await db.commit()
            return elapsed

    async def update_session_meta(
        self,
        session_id: int,
        status: str | None = None,
        subject: str | None = None,
        topic: str | None = None,
        add_seconds: int = 0
    ):
        async with aiosqlite.connect(self.db_path) as db:
            updates = []
            params = []
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if subject is not None:
                updates.append("subject = ?")
                params.append(subject.strip())
            if topic is not None:
                updates.append("topic = ?")
                params.append(topic.strip() if topic else None)
            if add_seconds > 0:
                updates.append("total_seconds = total_seconds + ?")
                params.append(add_seconds)

            if updates:
                params.append(session_id)
                query = f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?;"
                await db.execute(query, params)
                await db.commit()

    async def end_session(self, session_id: int, final_total_seconds: int) -> dict:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            await db.execute("""
                UPDATE sessions
                SET end_time = ?, total_seconds = ?, status = 'completed'
                WHERE session_id = ?;
            """, (now_str, final_total_seconds, session_id))

            # Fetch session info
            cursor = await db.execute("""
                SELECT user_id, guild_id, subject, topic, start_time, total_seconds
                FROM sessions WHERE session_id = ?;
            """, (session_id,))
            session_row = await cursor.fetchone()

            # Count segments
            cursor = await db.execute("""
                SELECT COUNT(*) as seg_count FROM segments WHERE session_id = ?;
            """, (session_id,))
            seg_row = await cursor.fetchone()
            segment_count = seg_row["seg_count"] if seg_row else 1

            # Count check-ins
            cursor = await db.execute("""
                SELECT
                    COUNT(*) as total_checkins,
                    SUM(CASE WHEN responded = 1 THEN 1 ELSE 0 END) as done_checkins
                FROM checkins WHERE session_id = ?;
            """, (session_id,))
            check_row = await cursor.fetchone()
            total_checkins = check_row["total_checkins"] if check_row else 0
            done_checkins = check_row["done_checkins"] if (check_row and check_row["done_checkins"]) else 0

            await db.commit()

        user_id = session_row["user_id"]
        streak, longest = await self.update_streak(user_id)
        today_total = await self.get_today_total_seconds(user_id)
        goal = await self.get_daily_goal(user_id)

        return {
            "user_id": user_id,
            "guild_id": session_row["guild_id"],
            "subject": session_row["subject"],
            "topic": session_row["topic"],
            "total_seconds": final_total_seconds,
            "segment_count": segment_count,
            "checkins_done": done_checkins,
            "checkins_total": total_checkins,
            "current_streak": streak,
            "longest_streak": longest,
            "today_total_seconds": today_total,
            "daily_goal_minutes": goal
        }

    async def log_checkin(self, session_id: int, user_id: int) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO checkins (session_id, user_id, prompted_at, responded)
                VALUES (?, ?, ?, 0);
            """, (session_id, user_id, now_str))
            checkin_id = cursor.lastrowid
            await db.commit()
            return checkin_id

    async def record_checkin_response(self, checkin_id: int) -> bool:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE checkins
                SET responded_at = ?, responded = 1
                WHERE checkin_id = ? AND responded = 0;
            """, (now_str, checkin_id))
            await db.commit()
            return cursor.rowcount > 0

    async def get_latest_open_checkin(self, session_id: int, user_id: int) -> int | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT checkin_id FROM checkins
                WHERE session_id = ? AND user_id = ? AND responded = 0
                ORDER BY checkin_id DESC LIMIT 1;
            """, (session_id, user_id))
            row = await cursor.fetchone()
            return row["checkin_id"] if row else None

    async def update_streak(self, user_id: int) -> tuple[int, int]:
        """Calculates and updates consecutive day streak for a user."""
        today = datetime.now(timezone.utc).date()
        today_str = today.isoformat()
        yesterday_str = (today - timedelta(days=1)).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT current_streak, longest_streak, last_study_date
                FROM users WHERE user_id = ?;
            """, (user_id,))
            user = await cursor.fetchone()
            if not user:
                return 1, 1

            current = user["current_streak"] or 0
            longest = user["longest_streak"] or 0
            last_date = user["last_study_date"]

            if last_date == today_str:
                # Already studied today, streak stays the same
                return current, longest
            elif last_date == yesterday_str:
                # Studied yesterday: increment streak
                current += 1
            else:
                # Streak broken or first study day
                current = 1

            longest = max(longest, current)

            await db.execute("""
                UPDATE users
                SET current_streak = ?, longest_streak = ?, last_study_date = ?
                WHERE user_id = ?;
            """, (current, longest, today_str, user_id))
            await db.commit()
            return current, longest

    async def set_daily_goal(self, user_id: int, minutes: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET daily_goal_minutes = ? WHERE user_id = ?;
            """, (max(0, minutes), user_id))
            await db.commit()

    async def get_daily_goal(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT daily_goal_minutes FROM users WHERE user_id = ?;", (user_id,))
            row = await cursor.fetchone()
            return row["daily_goal_minutes"] if row and row["daily_goal_minutes"] else 0

    async def get_today_total_seconds(self, user_id: int) -> int:
        today_start = datetime.now(timezone.utc).date().isoformat() + "T00:00:00"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT SUM(total_seconds) as total
                FROM sessions
                WHERE user_id = ? AND start_time >= ?;
            """, (user_id, today_start))
            row = await cursor.fetchone()
            return row["total"] if row and row["total"] else 0

    async def get_user_stats(self, user_id: int) -> dict:
        now = datetime.now(timezone.utc)
        today_start = now.date().isoformat() + "T00:00:00"
        # Start of this week (Monday)
        week_start = (now.date() - timedelta(days=now.weekday())).isoformat() + "T00:00:00"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # User record
            cursor = await db.execute("""
                SELECT display_name, daily_goal_minutes, current_streak, longest_streak
                FROM users WHERE user_id = ?;
            """, (user_id,))
            user_row = await cursor.fetchone()

            # Today total
            cursor = await db.execute("""
                SELECT SUM(total_seconds) as total FROM sessions
                WHERE user_id = ? AND start_time >= ?;
            """, (user_id, today_start))
            today_row = await cursor.fetchone()
            today_sec = today_row["total"] if today_row and today_row["total"] else 0

            # Week total
            cursor = await db.execute("""
                SELECT SUM(total_seconds) as total FROM sessions
                WHERE user_id = ? AND start_time >= ?;
            """, (user_id, week_start))
            week_row = await cursor.fetchone()
            week_sec = week_row["total"] if week_row and week_row["total"] else 0

            # All-time total & session count
            cursor = await db.execute("""
                SELECT COUNT(*) as sess_count, SUM(total_seconds) as total
                FROM sessions WHERE user_id = ?;
            """, (user_id,))
            all_row = await cursor.fetchone()
            all_time_sec = all_row["total"] if all_row and all_row["total"] else 0
            session_count = all_row["sess_count"] if all_row else 0

            # Top subjects
            cursor = await db.execute("""
                SELECT subject, SUM(total_seconds) as sub_total
                FROM sessions WHERE user_id = ?
                GROUP BY subject
                ORDER BY sub_total DESC LIMIT 5;
            """, (user_id,))
            subject_rows = await cursor.fetchall()
            subjects = [{"subject": r["subject"], "seconds": r["sub_total"]} for r in subject_rows]

            # Checkin rate
            cursor = await db.execute("""
                SELECT
                    COUNT(*) as total_prompted,
                    SUM(CASE WHEN responded = 1 THEN 1 ELSE 0 END) as total_done
                FROM checkins WHERE user_id = ?;
            """, (user_id,))
            check_row = await cursor.fetchone()
            check_prompted = check_row["total_prompted"] if check_row else 0
            check_done = check_row["total_done"] if check_row and check_row["total_done"] else 0

        return {
            "display_name": user_row["display_name"] if user_row else "Unknown",
            "daily_goal_minutes": user_row["daily_goal_minutes"] if user_row else 0,
            "current_streak": user_row["current_streak"] if user_row else 0,
            "longest_streak": user_row["longest_streak"] if user_row else 0,
            "today_seconds": today_sec,
            "week_seconds": week_sec,
            "all_time_seconds": all_time_sec,
            "session_count": session_count,
            "top_subjects": subjects,
            "checkins_prompted": check_prompted,
            "checkins_done": check_done
        }

    async def get_leaderboard(self, guild_id: int, period: str = "week") -> list[dict]:
        now = datetime.now(timezone.utc)
        if period == "today":
            start_iso = now.date().isoformat() + "T00:00:00"
        elif period == "week":
            start_iso = (now.date() - timedelta(days=now.weekday())).isoformat() + "T00:00:00"
        else: # all-time
            start_iso = "1970-01-01T00:00:00"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT
                    u.user_id,
                    u.display_name,
                    u.current_streak,
                    SUM(s.total_seconds) as total_time
                FROM sessions s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.guild_id = ? AND s.start_time >= ?
                GROUP BY s.user_id
                ORDER BY total_time DESC LIMIT 15;
            """, (guild_id, start_iso))
            rows = await cursor.fetchall()

            return [
                {
                    "user_id": r["user_id"],
                    "display_name": r["display_name"],
                    "current_streak": r["current_streak"],
                    "total_seconds": r["total_time"] or 0
                }
                for r in rows
            ]

    async def get_history(self, user_id: int, limit: int = 5, offset: int = 0) -> tuple[list[dict], int]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            count_cursor = await db.execute("SELECT COUNT(*) as total FROM sessions WHERE user_id = ?;", (user_id,))
            total_count = (await count_cursor.fetchone())["total"]

            cursor = await db.execute("""
                SELECT session_id, subject, topic, start_time, end_time, total_seconds, status
                FROM sessions
                WHERE user_id = ?
                ORDER BY session_id DESC
                LIMIT ? OFFSET ?;
            """, (user_id, limit, offset))
            rows = await cursor.fetchall()

            sessions = [
                {
                    "session_id": r["session_id"],
                    "subject": r["subject"],
                    "topic": r["topic"],
                    "start_time": r["start_time"],
                    "end_time": r["end_time"],
                    "total_seconds": r["total_seconds"],
                    "status": r["status"]
                }
                for r in rows
            ]
            return sessions, total_count

    async def set_dashboard_message(self, guild_id: int, channel_id: int, message_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO dashboard_messages (guild_id, channel_id, message_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id;
            """, (guild_id, channel_id, message_id))
            await db.commit()

    async def get_dashboard_message(self, guild_id: int) -> tuple[int, int] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT channel_id, message_id FROM dashboard_messages WHERE guild_id = ?;
            """, (guild_id,))
            row = await cursor.fetchone()
            return (row["channel_id"], row["message_id"]) if row else None

    async def set_hub_message(self, guild_id: int, channel_id: int, message_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO hub_messages (guild_id, channel_id, message_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id;
            """, (guild_id, channel_id, message_id))
            await db.commit()

    async def get_hub_message(self, guild_id: int) -> tuple[int, int] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT channel_id, message_id FROM hub_messages WHERE guild_id = ?;
            """, (guild_id,))
            row = await cursor.fetchone()
            return (row["channel_id"], row["message_id"]) if row else None

    async def set_summary_channel(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO summary_channels (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id;
            """, (guild_id, channel_id))
            await db.commit()

    async def get_summary_channel(self, guild_id: int) -> int | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT channel_id FROM summary_channels WHERE guild_id = ?;
            """, (guild_id,))
            row = await cursor.fetchone()
            return row["channel_id"] if row else None

    async def get_latest_completed_session(self, user_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT session_id, user_id, guild_id, subject, topic, total_seconds, start_time, end_time
                FROM sessions
                WHERE user_id = ? AND status = 'completed'
                ORDER BY session_id DESC LIMIT 1;
            """, (user_id,))
            session_row = await cursor.fetchone()
            if not session_row:
                return None

            session_id = session_row["session_id"]

            cursor = await db.execute("""
                SELECT COUNT(*) as seg_count FROM segments WHERE session_id = ?;
            """, (session_id,))
            seg_row = await cursor.fetchone()
            segment_count = seg_row["seg_count"] if seg_row else 1

            cursor = await db.execute("""
                SELECT
                    COUNT(*) as total_checkins,
                    SUM(CASE WHEN responded = 1 THEN 1 ELSE 0 END) as done_checkins
                FROM checkins WHERE session_id = ?;
            """, (session_id,))
            check_row = await cursor.fetchone()
            total_checkins = check_row["total_checkins"] if check_row else 0
            done_checkins = check_row["done_checkins"] if (check_row and check_row["done_checkins"]) else 0

        streak, longest = await self.update_streak(user_id)
        today_total = await self.get_today_total_seconds(user_id)
        goal = await self.get_daily_goal(user_id)

        return {
            "session_id": session_id,
            "user_id": user_id,
            "guild_id": session_row["guild_id"],
            "subject": session_row["subject"],
            "topic": session_row["topic"],
            "total_seconds": session_row["total_seconds"],
            "segment_count": segment_count,
            "checkins_done": done_checkins,
            "checkins_total": total_checkins,
            "current_streak": streak,
            "longest_streak": longest,
            "today_total_seconds": today_total,
            "daily_goal_minutes": goal
        }

    async def export_all(self) -> dict:
        """Exports entire database as JSON dictionary for easy backup."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            data = {}
            for table in ["users", "sessions", "segments", "checkins"]:
                cur = await db.execute(f"SELECT * FROM {table};")
                rows = await cur.fetchall()
                data[table] = [dict(r) for r in rows]
            return data

    async def import_all(self, data: dict):
        """Imports dataset into database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = OFF;")
            for table in ["users", "sessions", "segments", "checkins"]:
                rows = data.get(table, [])
                if not rows:
                    continue
                for row in rows:
                    cols = list(row.keys())
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    query = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders});"
                    await db.execute(query, list(row.values()))
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.commit()
