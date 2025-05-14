import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

CONFIG_FILE = "config.json"

with open(CONFIG_FILE) as f:
    config = json.load(f)

SHEET_NAME = config["sheet_name"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

try:
    spreadsheet = client.open(SHEET_NAME)
except gspread.SpreadsheetNotFound:
    print("Spreadsheet not found.")
    exit()

# Updated headers for all known sheets
SHEETS = {
    "Players": ["User ID", "Username",],
    "Teams": ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6", "Locked"],
    "Matches": ["Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Winner", "Loser", "Proposed By"],
    "Scoring": [
        "Match ID",
        "Team A", "Team B",
        "Map 1 Mode", "Map 1 A", "Map 1 B",
        "Map 2 Mode", "Map 2 A", "Map 2 B",
        "Map 3 Mode", "Map 3 A", "Map 3 B",
        "Total A", "Total B", "Maps Won A", "Maps Won B", "Winner"
    ],
    "Match Propose": ["Team A", "Team B", "Proposer ID", "Proposed Date"],
    "Match Scheduled": ["Match ID", "Team A", "Team B", "Scheduled Date"],
    "Leaderboard": ["Team Name", "Rating", "Wins", "Losses", "Matches Played"],
    "Weekly Matches": ["Week", "Team A", "Team B", "Match ID", "Scheduled Date"],
    "Challenge Matches": ["Week", "Team A", "Team B", "Proposer ID", "Proposed Date", "Completion Date"],
    "Match History": [
        "Week", "Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date",
        "Map 1 Mode", "Map 1 A", "Map 1 B",
        "Map 2 Mode", "Map 2 A", "Map 2 B",
        "Map 3 Mode", "Map 3 A", "Map 3 B",
        "Total A", "Total B", "Maps Won A", "Maps Won B", "Winner"
    ],
    "LeagueWeek": ["League Week"]
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
        clean_sheet(sheet, headers, fake_team_check_columns=[0])

    elif sheet_name in ["Weekly Matches", "Matches"]:
        clean_sheet(sheet, headers, fake_team_check_columns=[1, 2])

    elif sheet_name == "Scoring":
        clean_sheet(sheet, headers, fake_team_check_columns=[1, 2, 17])  # Team A/B/Winner

    elif sheet_name in ["Match Propose", "Match Scheduled", "Challenge Matches", "Match History"]:
        clean_sheet(sheet, headers, fake_team_check_columns=[1, 2])

    else:
        clean_sheet(sheet, headers)

print("✅ All sheets fixed and cleaned up smartly.")

