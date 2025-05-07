import discord
import json

def get_or_create_sheet(spreadsheet, name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except Exception:
        sheet = spreadsheet.add_worksheet(title=name, rows="100", cols=str(len(headers)))
        sheet.append_row(headers)
    return sheet

def get_next_match_id(matches_sheet):
    match_ids = matches_sheet.col_values(1)[1:]
    return str(len(match_ids) + 1)

def extract_user_id(user_string):
    if "(" in user_string and ")" in user_string:
        return user_string.split("(")[-1].split(")")[0]
    return None

def get_team_mentions(interaction, team_name, teams_sheet, ping_full_team):
    team_row = next((row for row in teams_sheet.get_all_values() if row[0] == team_name), None)
    if not team_row:
        return team_name

    mentions = []
    for player in team_row[1:]:
        if "(" in player and ")" in player:
            user_id = player.split("(")[-1].split(")")[0]
            member = interaction.guild.get_member(int(user_id))
            if member and ping_full_team:
                mentions.append(member.mention)
        elif player.strip():
            mentions.append(player)

    return " ".join(mentions) if mentions else team_name

def update_team_rating(leaderboard_sheet, team_name, won, elo_win, elo_loss):
    for idx, row in enumerate(leaderboard_sheet.get_all_values(), 1):
        if row[0] == team_name:
            rating = int(row[1])
            wins = int(row[2])
            losses = int(row[3])
            matches = int(row[4])

            new_rating = rating + elo_win if won else rating + elo_loss
            leaderboard_sheet.update(f"B{idx}", [[new_rating, wins + (1 if won else 0), losses + (0 if won else 1), matches + 1]])
            return

    starting_elo = 1025 if won else 975
    leaderboard_sheet.append_row([team_name, starting_elo, 1 if won else 0, 0 if won else 1, 1])

async def generate_weekly_matches(interaction, spreadsheet, week_number, force=False):
    if not interaction.response.is_done():
        await interaction.response.defer()

    with open("config.json") as f:
        config_data = json.load(f)

    min_teams_required = config_data.get("minimum_teams_start", 4)
    team_min_players = config_data.get("team_min_players", 3)
    match_channel_id = config_data.get("weekly_channel_id")
    elo_win = config_data.get("elo_win_points", 25)
    elo_loss = config_data.get("elo_loss_points", -25)
    affect_elo = config_data.get("forfeit_affects_elo", True)
    ping_full_team = config_data.get("match_ping_full_team", True)

    matches_sheet = get_or_create_sheet(spreadsheet, "Matches", ["Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Winner", "Loser", "Proposed By"])
    leaderboard_sheet = get_or_create_sheet(spreadsheet, "Leaderboard", ["Team Name", "Rating", "Wins", "Losses", "Matches Played"])
    weekly_sheet = get_or_create_sheet(spreadsheet, "Weekly Matches", ["Week", "Team A", "Team B", "Match ID", "Scheduled Date"])
    teams_sheet = get_or_create_sheet(spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])

    all_teams = leaderboard_sheet.get_all_values()[1:]
    if len(all_teams) < min_teams_required:
        await interaction.followup.send("❗ Not enough teams to generate matchups.", ephemeral=True)
        return

    valid_teams = []
    team_players = {}

    for team_row in teams_sheet.get_all_values()[1:]:
        team_name = team_row[0]
        players = [p for p in team_row[1:] if p.strip()]
        team_players[team_name] = len(players)

        if len(players) >= team_min_players:
            valid_teams.append(team_name)

    if len(valid_teams) < min_teams_required:
        await interaction.followup.send("❗ Not enough valid teams to generate matchups.", ephemeral=True)
        return

    if force:
        existing = matches_sheet.get_all_values()[1:]
        for idx, row in enumerate(existing, start=2):
            match_id, team_a, team_b, _, _, status, _, _, winner, loser, _ = row

            if status.strip() not in ["Finished", "Cancelled", "Forfeited"]:
                team_a_valid = team_players.get(team_a, 0) >= team_min_players
                team_b_valid = team_players.get(team_b, 0) >= team_min_players

                if team_a_valid and team_b_valid:
                    matches_sheet.update_cell(idx, 6, "Double Forfeit")
                elif team_a_valid:
                    matches_sheet.update_cell(idx, 6, "Forfeited")
                    matches_sheet.update_cell(idx, 7, team_a)
                    matches_sheet.update_cell(idx, 8, team_b)
                    if affect_elo:
                        update_team_rating(leaderboard_sheet, team_a, True, elo_win, elo_loss)
                        update_team_rating(leaderboard_sheet, team_b, False, elo_win, elo_loss)
                elif team_b_valid:
                    matches_sheet.update_cell(idx, 6, "Forfeited")
                    matches_sheet.update_cell(idx, 7, team_b)
                    matches_sheet.update_cell(idx, 8, team_a)
                    if affect_elo:
                        update_team_rating(leaderboard_sheet, team_b, True, elo_win, elo_loss)
                        update_team_rating(leaderboard_sheet, team_a, False, elo_win, elo_loss)
                else:
                    matches_sheet.update_cell(idx, 6, "Double Forfeit")

    valid_teams.sort(key=lambda x: int(next((row[1] for row in all_teams if row[0] == x), 1000)), reverse=True)

    matchups = []
    used = set()

    for i, team in enumerate(valid_teams):
        for opponent in valid_teams[i+1:]:
            pair = tuple(sorted([team, opponent]))
            if pair not in used:
                used.add(pair)
                matchups.append((team, opponent))
                break

    match_channel = interaction.guild.get_channel(int(match_channel_id))
    message_lines = [f"📢 **Week {week_number} Matchups:**\n"]

    for team_a, team_b in matchups:
        match_id = get_next_match_id(matches_sheet)
        weekly_sheet.append_row([week_number, team_a, team_b, match_id, "TBD"])
        matches_sheet.append_row([match_id, team_a, team_b, "TBD", "", "Auto Proposed", "", "", "", "System"])

        mentions_a = get_team_mentions(interaction, team_a, teams_sheet, ping_full_team)
        mentions_b = get_team_mentions(interaction, team_b, teams_sheet, ping_full_team)

        message_lines.append(f"🔹 {team_a} vs {team_b}\n{mentions_a} vs {mentions_b}\n")

    if match_channel:
        await match_channel.send("\n".join(message_lines))

    await interaction.followup.send(f"✅ Week {week_number} matchups generated and posted in <#{match_channel_id}>.", ephemeral=True)

def setup_match_module(bot, spreadsheet):
    from discord import app_commands

    class WeeklyMatchGenerator(app_commands.Group):
        def __init__(self):
            super().__init__(name="weekly", description="Weekly match generation commands.")

        @app_commands.command(name="generate", description="Generate weekly matchups")
        @app_commands.describe(week_number="Week number")
        async def generate(self, interaction: discord.Interaction, week_number: int):
            await generate_weekly_matches(interaction, spreadsheet, week_number)

    bot.tree.add_command(WeeklyMatchGenerator())


