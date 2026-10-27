import os
import shlex
import sqlite3
import threading
from datetime import datetime
from functools import wraps
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

DB_PATH = os.environ.get("DB_PATH", "step_prep.db")
# Set this to your own numeric Telegram user id so no one else can use the bot.
# Leave empty while testing to allow anyone (not recommended once deployed).
OWNER_ID = os.environ.get("OWNER_ID", "")


def owner_only(handler):
    @wraps(handler)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if OWNER_ID and str(update.effective_user.id) != str(OWNER_ID):
            await update.message.reply_text("This bot is private.")
            return
        return await handler(update, context)
    return wrapped


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            topic TEXT,
            total INTEGER,
            correct INTEGER,
            wrong INTEGER,
            accuracy REAL,
            notes TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            url TEXT,
            added_date TEXT
        )"""
    )
    return conn


HELP_TEXT = (
    "📚 *Step Prep Bot*\n\n"
    "*Logging QBank sessions*\n"
    "/log <topic> <total> <correct> [notes]\n"
    "  e.g. `/log Thyroid 20 15 missed hyperthyroid labs qs`\n"
    "  Use quotes for multi-word topics: `/log \"Diabetic foot\" 15 10`\n\n"
    "*Physeo videos*\n"
    "/addvideo <topic> <url>\n"
    "  e.g. `/addvideo Thyroid https://physeo.com/...`\n"
    "/videos <topic> — list saved videos for a topic\n\n"
    "*Reviewing progress*\n"
    "/stats — overall accuracy + weakest topics\n"
    "/weak [n] — n weakest topics with any linked videos (default 5)\n"
    "/topics — all topics logged so far, with accuracy\n"
    "/history [n] — last n sessions (default 10)\n"
    "/delete <id> — delete a logged session by id (see /history for ids)\n"
)


def parse_command_args(text: str):
    """Strip the leading /command (and @botname) and shlex-split the rest,
    so quoted multi-word topics work."""
    parts = text.split(maxsplit=1)
    rest = parts[1] if len(parts) > 1 else ""
    return shlex.split(rest)


@owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


@owner_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


@owner_only
async def log_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = parse_command_args(update.message.text)
    if len(args) < 3:
        await update.message.reply_text(
            "Format: /log <topic> <total> <correct> [notes]\n"
            "e.g. /log Thyroid 20 15 missed hyperthyroid labs qs"
        )
        return
    topic = args[0]
    try:
        total = int(args[1])
        correct = int(args[2])
    except ValueError:
        await update.message.reply_text("total and correct must be numbers.")
        return
    if correct > total or total <= 0 or correct < 0:
        await update.message.reply_text("Check your numbers — correct can't exceed total.")
        return
    notes = " ".join(args[3:]) if len(args) > 3 else ""
    wrong = total - correct
    accuracy = round(correct / total * 100, 1)
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (date, topic, total, correct, wrong, accuracy, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (date, topic, total, correct, wrong, accuracy, notes),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Logged *{topic}*: {correct}/{total} correct ({accuracy}%), {wrong} wrong.",
        parse_mode="Markdown",
    )


@owner_only
async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = parse_command_args(update.message.text)
    if len(args) < 2:
        await update.message.reply_text("Format: /addvideo <topic> <url>")
        return
    topic = args[0]
    url = args[1]
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_conn()
    conn.execute(
        "INSERT INTO videos (topic, url, added_date) VALUES (?, ?, ?)",
        (topic, url, date),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🎥 Saved a video for *{topic}*.", parse_mode="Markdown")


@owner_only
async def list_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = parse_command_args(update.message.text)
    if not args:
        await update.message.reply_text("Format: /videos <topic>")
        return
    topic = args[0]

    conn = get_conn()
    rows = conn.execute(
        "SELECT url, added_date FROM videos WHERE topic = ? COLLATE NOCASE ORDER BY id DESC",
        (topic,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"No videos saved for {topic} yet.")
        return
    lines = [f"🎥 Videos for *{topic}*:"]
    for url, added_date in rows:
        lines.append(f"- {url} ({added_date})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@owner_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    overall = conn.execute(
        "SELECT COUNT(*), SUM(total), SUM(correct) FROM sessions"
    ).fetchone()
    sessions_count, total_q, total_correct = overall
    if not sessions_count:
        conn.close()
        await update.message.reply_text("No sessions logged yet. Try /log to start.")
        return
    overall_acc = round((total_correct or 0) / (total_q or 1) * 100, 1)

    weak = conn.execute(
        """SELECT topic, SUM(total) AS t, SUM(correct) AS c,
                  ROUND(SUM(correct) * 100.0 / SUM(total), 1) AS acc
           FROM sessions GROUP BY topic COLLATE NOCASE
           ORDER BY acc ASC LIMIT 5"""
    ).fetchall()
    conn.close()

    lines = [
        f"📊 *Overall*: {total_correct}/{total_q} ({overall_acc}%) across {sessions_count} sessions.",
        "",
        "*Weakest topics:*",
    ]
    for topic, t, c, acc in weak:
        lines.append(f"- {topic}: {c}/{t} ({acc}%)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@owner_only
async def weak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = parse_command_args(update.message.text)
    n = int(args[0]) if args and args[0].isdigit() else 5

    conn = get_conn()
    weak_topics = conn.execute(
        """SELECT topic, SUM(total) AS t, SUM(correct) AS c,
                  ROUND(SUM(correct) * 100.0 / SUM(total), 1) AS acc
           FROM sessions GROUP BY topic COLLATE NOCASE
           ORDER BY acc ASC LIMIT ?""",
        (n,),
    ).fetchall()

    if not weak_topics:
        conn.close()
        await update.message.reply_text("No sessions logged yet.")
        return

    lines = ["🧩 *Weakest topics:*", ""]
    for topic, t, c, acc in weak_topics:
        lines.append(f"*{topic}* — {c}/{t} ({acc}%)")
        vids = conn.execute(
            "SELECT url FROM videos WHERE topic = ? COLLATE NOCASE ORDER BY id DESC LIMIT 2",
            (topic,),
        ).fetchall()
        for (url,) in vids:
            lines.append(f"   🎥 {url}")
        lines.append("")
    conn.close()
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@owner_only
async def topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    rows = conn.execute(
        """SELECT topic, SUM(total) AS t, SUM(correct) AS c,
                  ROUND(SUM(correct) * 100.0 / SUM(total), 1) AS acc
           FROM sessions GROUP BY topic COLLATE NOCASE ORDER BY topic ASC"""
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No sessions logged yet.")
        return
    lines = ["📋 *All topics:*"]
    for topic, t, c, acc in rows:
        lines.append(f"- {topic}: {c}/{t} ({acc}%)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@owner_only
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = parse_command_args(update.message.text)
    n = int(args[0]) if args and args[0].isdigit() else 10

    conn = get_conn()
    rows = conn.execute(
        "SELECT id, date, topic, total, correct, wrong, accuracy, notes FROM sessions ORDER BY id DESC LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No sessions logged yet.")
        return
    lines = ["🕓 *Recent sessions:*"]
    for sid, date, topic, total, correct, wrong, acc, notes in rows:
        line = f"#{sid} [{date}] {topic}: {correct}/{total} ({acc}%)"
        if notes:
            line += f" — {notes}"
        lines.append(line)
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@owner_only
async def delete_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = parse_command_args(update.message.text)
    if not args or not args[0].isdigit():
        await update.message.reply_text("Format: /delete <id> (see /history for ids)")
        return
    sid = int(args[0])

    conn = get_conn()
    cur = conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted:
        await update.message.reply_text(f"🗑 Deleted session #{sid}.")
    else:
        await update.message.reply_text(f"No session with id {sid}.")


class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass  # keep the console quiet


def start_ping_server():
    """Render's free Web Service tier requires something listening on a
    port, and an external pinger hitting it keeps the service awake. This
    does nothing else — the real bot runs separately via polling."""
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    server.serve_forever()


def main():
    threading.Thread(target=start_ping_server, daemon=True).start()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("log", log_session))
    app.add_handler(CommandHandler("addvideo", add_video))
    app.add_handler(CommandHandler("videos", list_videos))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("weak", weak))
    app.add_handler(CommandHandler("topics", topics))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("delete", delete_session))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
