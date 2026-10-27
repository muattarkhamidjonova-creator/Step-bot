# Step Prep Bot

A private Telegram bot for your own USMLE Step prep: logs Coursology QBank
sessions (topic, score, wrong answers) and stores Physeo video links per
topic, so you can pull up the weakest topics and the videos for them in one
place. First Aid stays as your hard copy — not part of the bot.

## 1. Create the bot (2 minutes)
1. In Telegram, message **@BotFather**.
2. Send `/newbot`, give it a name and a username (must end in `bot`).
3. BotFather gives you a **token** like `123456:ABC-DEF...`. Save it.

## 2. Find your own Telegram user id
1. Message **@userinfobot** (or **@getmyid_bot**) — it replies with your
   numeric id.
2. This locks the bot so only you can use it, even if someone else finds it.

## 3. Run it locally first (optional but recommended)
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your-token-here"
export OWNER_ID="your-numeric-id-here"
python bot.py
```
Then message your bot on Telegram — try `/start`.

## 4. Deploy for free so it runs 24/7
**Railway** is the simplest free option:
1. Create a free account at railway.app.
2. "New Project" → "Deploy from GitHub repo" (push these 3 files — `bot.py`,
   `requirements.txt`, this README — to a new GitHub repo first), or use
   Railway's CLI to deploy a local folder directly.
3. In the project's **Variables** tab, add:
   - `TELEGRAM_BOT_TOKEN` = your token
   - `OWNER_ID` = your numeric id
4. Railway auto-detects Python and runs `python bot.py`. Done — it stays
   online even when your phone/laptop is off.

(Render.com works the same way if you'd rather use that — "Background
Worker" service type, same environment variables, start command `python
bot.py`.)

**Note on the database**: `step_prep.db` (SQLite) is created in the app's
own folder. On Railway's free tier the filesystem resets on redeploy, so if
you want your logged sessions to survive redeploys long-term, say so and
I'll switch it to Railway's free Postgres add-on instead — for now it's
simplest to leave as SQLite and just not redeploy often.

## 5. Using it
- `/log Thyroid 20 15 missed hyperthyroid labs qs` — log a QBank session
- `/addvideo Thyroid https://t.me/physeo_channel/123` — save a Physeo video
  link under a topic
- `/videos Thyroid` — see saved videos for that topic
- `/weak` — your 5 weakest topics, each with its saved videos
- `/stats` — overall accuracy and weakest topics
- `/topics` — every topic logged, with accuracy
- `/history` — recent sessions
- `/delete <id>` — remove a wrongly logged session

Multi-word topics need quotes: `/log "Diabetic foot" 15 10`.
