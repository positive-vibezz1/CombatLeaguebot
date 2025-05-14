import discord
import gspread
import json
import os
from discord.ext import commands
from oauth2client.service_account import ServiceAccountCredentials
from discord.ext import tasks


# === Load config ===
with open("config.json") as f:
    config = json.load(f)

SHEET_NAME = config["sheet_name"]
CHANNEL_ID = int(config["leaderboard_channel_id"])
MESSAGE_ID_FILE = "leaderboard_msg_id.txt"

# === Google Sheets setup ===
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open(SHEET_NAME)
leaderboard_sheet = spreadsheet.worksheet("Leaderboard")

# === Bot setup ===
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def get_tier_label(rating):
    r = int(rating)
    if r >= 1400:
        return "🟪 **Master**"
    elif r >= 1200:
        return "🟦 **Platinum**"
    elif r >= 1050:
        return "💎 **Diamond**"
    elif r >= 900:
        return "🟨 **Gold**"
    elif r >= 750:
        return "⚪ **Silver**"
    else:
        return "🟫 **Bronze**"

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await post_or_update_leaderboard_embed()

    @tasks.loop(minutes=3600)               # Update leaderboard timer here
    async def update_leaderboard_loop():
        await post_or_update_leaderboard_embed()

    @bot.event
    async def on_ready():
        print(f"✅ Logged in as {bot.user}")
        update_leaderboard_loop.start()


async def post_or_update_leaderboard_embed():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("❗ Score channel not found.")
        return

    data = leaderboard_sheet.get_all_values()
    headers, rows = data[0], data[1:]

    # Filter out inactive teams
    filtered = [row for row in rows if row[4].isdigit() and int(row[4]) > 0]

    if not filtered:
        await channel.send("📊 Leaderboard is currently empty or all teams are inactive.")
        return

    # Sort by rating descending
    sorted_rows = sorted(filtered, key=lambda r: int(r[1]), reverse=True)

    # Group by tiers
    tiers = {
        "🟪 **Master**": [],
        "🟦 **Platinum**": [],
        "💎 **Diamond**": [],
        "🟨 **Gold**": [],
        "⚪ **Silver**": [],
        "🟫 **Bronze**": []
    }

    for row in sorted_rows:
        team, rating, wins, losses, matches = row[:5]
        label = get_tier_label(rating)
        entry = f"**{team}** — {rating}  |  W: {wins} L: {losses} GP: {matches}"
        tiers[label].append(entry)

    embed = discord.Embed(title="🏆 League Leaderboard", color=discord.Color.purple())
    embed.set_footer(text="Tiered by Rating")

    for tier_label, team_entries in tiers.items():
        if team_entries:
            embed.add_field(
                name=tier_label,
                value="\n".join(team_entries),
                inline=False
            )

    # Load saved message ID
    message_id = None
    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            try:
                message_id = int(f.read().strip())
            except:
                pass

    if message_id:
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=embed)
            print("✅ Leaderboard message updated.")
            return
        except discord.NotFound:
            print("⚠️ Old message not found. Creating a new one.")

    new_msg = await channel.send(embed=embed)
    with open(MESSAGE_ID_FILE, "w") as f:
        f.write(str(new_msg.id))
    print("✅ Leaderboard message created and saved.")

# === Run bot ===
bot.run(config["bot_token"])
