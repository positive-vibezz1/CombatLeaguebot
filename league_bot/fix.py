import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

CONFIG_FILE = "config.json"

with open(CONFIG_FILE) as f:
    config = json.load(f)

SHEET_NAME = config["sheet_name"]

scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

try:
    spreadsheet = client.open(SHEET_NAME)
except gspread.SpreadsheetNotFound:
    print("Spreadsheet not found.")
    exit()

# Sheet definitions
SHEETS = {
    "Players": ["User ID", "Username", "Sign-up Date"],
    "Teams": ["Team Name", "Player 1 ID", "Player 2 ID", "Player 3 ID", "Player 4 ID", "Player 5 ID", "Player 6 ID"],
    "Matches": ["Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Proposed Score", "Final Score", "Winner", "Loser", "Proposed By"],
    "Scoring": ["Match ID", "Map #", "Game Mode", "Team A Score", "Team B Score", "Winner"],
    "Match Proposed": ["Match ID", "Proposer ID", "Proposed Date"],
    "Match Scheduled": ["Match ID", "Scheduled Date"],
    "Leaderboard": ["Team Name", "Rating", "Wins", "Losses", "Matches Played"],
    "Weekly Matches": ["Week", "Team A", "Team B", "Match ID", "Scheduled Date"]
}

def get_or_create_sheet(name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        print(f"Sheet '{name}' not found. Creating...")
        sheet = spreadsheet.add_worksheet(title=name, rows="100", cols=str(len(headers)))
        sheet.append_row(headers)
        return sheet

    all_rows = sheet.get_all_values()
    if len(all_rows) == 0 or all_rows[0] != headers:
        print(f"Fixing headers for '{name}'")
        sheet.clear()
        sheet.append_row(headers)
    return sheet

def is_fake_team(name):
    return name.lower().startswith("testteam") or name.lower().startswith("faketeam")

def clean_sheet(sheet, headers, fake_team_check_columns=[]):
    all_rows = sheet.get_all_values()
    new_rows = []

    for row in all_rows[1:]:
        # Check if row should be removed
        if len(row) == 0 or row[0].strip() == "":
            continue

        remove = False
        for col in fake_team_check_columns:
            if len(row) > col and is_fake_team(row[col]):
                remove = True
                break

        if remove:
            continue

        new_rows.append(row)

    sheet.clear()
    sheet.append_row(headers)

    for row in new_rows:
        sheet.append_row(row)

# Start fixing

print("✅ Starting smart fix...")

for sheet_name, headers in SHEETS.items():
    sheet = get_or_create_sheet(sheet_name, headers)

    if sheet_name == "Leaderboard":
        # Remove fake teams from leaderboard
        clean_sheet(sheet, headers, fake_team_check_columns=[0])

    elif sheet_name == "Weekly Matches":
        # Remove matches with fake teams
        clean_sheet(sheet, headers, fake_team_check_columns=[1, 2])

    elif sheet_name == "Matches":
        # Remove matches with fake teams
        clean_sheet(sheet, headers, fake_team_check_columns=[1, 2])

    elif sheet_name == "Scoring":
        # Remove scores with fake team winner
        clean_sheet(sheet, headers, fake_team_check_columns=[5])

    elif sheet_name == "Match Proposed":
        # Clean normally (no fake team check, only empty row removal)
        clean_sheet(sheet, headers)

    else:
        # Clean normally (Players, Teams, Match Scheduled)
        clean_sheet(sheet, headers)

print("✅ All sheets fixed and cleaned up smartly.")

