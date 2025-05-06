import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import commands as league_commands
import match
import dev
import command_buttons  # <-- League Command Panel buttons

# -------------------- Load config --------------------

with open("config.json") as f:
    config = json.load(f)

BOT_TOKEN = config["bot_token"]
SHEET_NAME = config["sheet_name"]
DEV_OVERRIDE_IDS = config.get("dev_override_ids", [])
NOTIFICATIONS_CHANNEL_ID = config.get("notifications_channel_id")
MATCH_CHANNEL_ID = config.get("match_channel_id")
SCORE_CHANNEL_ID = config.get("score_channel_id")
RESULTS_CHANNEL_ID = config.get("results_channel_id")
PANEL_CHANNEL_ID = config.get("panel_channel_id")
TEAM_MIN_PLAYERS = int(config.get("team_min_players", 3))
TEAM_MAX_PLAYERS = int(config.get("team_max_players", 6))
ELO_WIN_POINTS = config.get("elo_win_points", 25)
ELO_LOSS_POINTS = config.get("elo_loss_points", -25)

# -------------------- Google Sheets Setup --------------------

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

try:
    spreadsheet = client.open(SHEET_NAME)
except gspread.SpreadsheetNotFound:
    spreadsheet = client.create(SHEET_NAME)

def get_or_create_sheet(name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=name, rows="100", cols=str(len(headers)))
        sheet.append_row(headers)
    return spreadsheet.worksheet(name)

players_sheet = get_or_create_sheet("Players", ["User ID", "Username"])
teams_sheet = get_or_create_sheet("Teams", ["Team Name", "Player 1", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])
matches_sheet = get_or_create_sheet("Matches", ["Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Winner", "Loser", "Proposed By"])
scoring_sheet = get_or_create_sheet("Scoring", ["Team A", "Team B", "Map #", "Game Mode", "Team A Score", "Team B Score", "Winner"])
leaderboard_sheet = get_or_create_sheet("Leaderboard", ["Team Name", "Rating", "Wins", "Losses", "Matches Played"])
proposed_sheet = get_or_create_sheet("Match Proposed", ["Team A", "Team B", "Proposer ID", "Proposed Date"])
scheduled_sheet = get_or_create_sheet("Match Scheduled", ["Team A", "Team B", "Scheduled Date"])

# -------------------- Bot Setup --------------------

intents = discord.Intents.default()
intents.members = True  # ✅ FIXED: Required to use fetch_members and see all members

bot = commands.Bot(command_prefix="!", intents=intents)
bot.config = config  # ✅ Very important → allows match.py and others to access config

match.setup_match_module(bot, spreadsheet)
dev.setup_dev_module(bot, spreadsheet, DEV_OVERRIDE_IDS)

# -------------------- Helper Functions --------------------

async def send_to_channel(channel_id, message=None, embed=None):
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(content=message, embed=embed)

async def send_notification(message=None, embed=None):
    await send_to_channel(NOTIFICATIONS_CHANNEL_ID, message, embed)

def get_team_rating(team_name):
    for idx, row in enumerate(leaderboard_sheet.get_all_values(), 1):
        if row[0] == team_name:
            return idx, int(row[1]), int(row[2]), int(row[3]), int(row[4])
    return None

def update_team_rating(team_name, won):
    team = get_team_rating(team_name)
    if team:
        idx, rating, wins, losses, matches = team
        new_rating = rating + ELO_WIN_POINTS if won else rating + ELO_LOSS_POINTS
        leaderboard_sheet.update(f"B{idx}", [[new_rating, wins + (1 if won else 0), losses + (0 if won else 1), matches + 1]])
    else:
        starting = 1025 if won else 975
        leaderboard_sheet.append_row([team_name, starting, 1 if won else 0, 0 if won else 1, 1])

# -------------------- Load Commands --------------------

league_commands.setup_commands(
    bot,
    players_sheet,
    teams_sheet,
    matches_sheet,
    scoring_sheet,
    leaderboard_sheet,
    proposed_sheet,
    scheduled_sheet,
    send_to_channel,
    send_notification,
    DEV_OVERRIDE_IDS
)

# -------------------- Bot Ready Event --------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot ready as {bot.user}")

    # League panel (Command panel)
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    if panel_channel:
        view = command_buttons.LeaguePanel(
            bot,
            players_sheet,
            teams_sheet,
            matches_sheet,
            scoring_sheet,
            leaderboard_sheet,
            proposed_sheet,
            scheduled_sheet,
            send_to_channel,
            send_notification,
            DEV_OVERRIDE_IDS
        )

        embed = discord.Embed(
            title="📋 League Command Panel",
            description="Use the buttons below to manage your league registration, teams, and matches!",
            color=discord.Color.blue()
        )

        embed.add_field(name="✅ Player Signup", value="Sign up to participate in the league and become eligible to join or create teams.", inline=False)
        embed.add_field(name="🏷️ Create Team", value="Register a new team. Captains can form teams and receive matches once minimum players are reached.", inline=False)
        embed.add_field(name="➕ Request to Join Team", value="Request to join a team. The captain must approve your request to join.", inline=False)
        embed.add_field(name="⭐ Promote Player", value="Team captains can promote another player to captain to take over the team.", inline=False)
        embed.add_field(name="🚪 Leave Team", value="Leave your current team (if not a captain).", inline=False)
        embed.add_field(name="❌ Unsignup", value="Remove yourself from the league. You must leave your team first to unsign.", inline=False)
        embed.add_field(name="❗ Disband Team", value="Disband your team permanently (Captain or Dev Only).", inline=False)
        embed.add_field(name="📅 Propose Match", value="Propose a match against another team. Opponent captain must confirm. Fallback channel if needed.", inline=False)
        embed.add_field(name="📊 Propose Score", value="Submit game scores map-by-map after a match. Opponent captain must confirm. Fallback channel if needed.", inline=False)

        embed.set_footer(text="⚡ Some actions require being a captain or developer. Captains manage teams and approve requests.")

        await panel_channel.send(embed=embed, view=view)
        print("Posted League Command Panel!")

    # ✅ POST DEV PANEL TOO (make sure dev_channel_id exists in config.json)
    await dev.post_dev_panel(bot, spreadsheet, DEV_OVERRIDE_IDS)
    print("Posted Dev Panel!")

bot.run(BOT_TOKEN)

