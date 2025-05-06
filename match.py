import discord
from discord import app_commands

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

async def create_matchup_channel(interaction, team_a, team_b, captain_a_id, captain_b_id, week_number):
    config = interaction.client.config
    category_id = config.get("matchups_category_id")
    category = interaction.guild.get_channel(int(category_id))

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
    }

    captain_a = interaction.guild.get_member(int(captain_a_id)) if captain_a_id else None
    captain_b = interaction.guild.get_member(int(captain_b_id)) if captain_b_id else None

    if captain_a:
        overwrites[captain_a] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    if captain_b:
        overwrites[captain_b] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel_name = f"week{week_number}-match-{team_a.lower()}-vs-{team_b.lower()}"
    channel = await interaction.guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

    mention_a = f"<@{captain_a_id}>" if captain_a_id else team_a
    mention_b = f"<@{captain_b_id}>" if captain_b_id else team_b

    desc = f"📢 **Matchup for Week {week_number}**\n\n**{mention_a}** vs **{mention_b}**\n\n📅 Scheduled: TBD\n\nGood luck!"
    await channel.send(desc)

    return channel

async def generate_weekly_matches(interaction, spreadsheet, week_number, force=False):
    await interaction.response.defer()

    matches_sheet = get_or_create_sheet(spreadsheet, "Matches", ["Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Proposed Score", "Final Score", "Winner", "Loser", "Proposed By"])
    leaderboard_sheet = get_or_create_sheet(spreadsheet, "Leaderboard", ["Team Name", "Rating", "Wins", "Losses", "Matches Played"])
    weekly_matches_sheet = get_or_create_sheet(spreadsheet, "Weekly Matches", ["Week", "Team A", "Team B", "Match ID", "Scheduled Date"])
    teams_sheet = get_or_create_sheet(spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])

    all_teams = leaderboard_sheet.get_all_values()[1:]
    if len(all_teams) < 2:
        await interaction.followup.send("❗ Not enough teams to generate matchups.", ephemeral=True)
        return

    # Filter teams with enough players
    valid_teams = []
    team_player_counts = {}

    for team_row in teams_sheet.get_all_values()[1:]:
        team_name = team_row[0]
        players = [p for p in team_row[1:] if p.strip()]
        team_player_counts[team_name] = len(players)

        if len(players) >= 3:
            valid_teams.append(team_name)

    if len(valid_teams) < 2:
        await interaction.followup.send("❗ Not enough valid teams (3+ players required) to generate matchups.", ephemeral=True)
        return

    # Sort by ELO
    valid_teams.sort(key=lambda x: int(next((row[1] for row in all_teams if row[0] == x), 0)), reverse=True)
    matchups = []
    used_pairs = set()

    for idx, team in enumerate(valid_teams):
        opponents = []

        for opponent in valid_teams:
            if team == opponent:
                continue

            pair = tuple(sorted([team, opponent]))
            if pair in used_pairs:
                continue

            if opponent not in opponents:
                opponents.append(opponent)

            if len(opponents) == 2:
                break

        if len(opponents) < 2 and not force:
            await interaction.followup.send(f"❗ Not enough available opponents for **{team}** to schedule 2 matches.", ephemeral=True)
            return

        for opp in opponents:
            pair = tuple(sorted([team, opp]))
            if pair not in used_pairs:
                used_pairs.add(pair)
                matchups.append((team, opp))

    for team_a, team_b in matchups:
        match_id = get_next_match_id(matches_sheet)
        weekly_matches_sheet.append_row([week_number, team_a, team_b, match_id, "TBD"])
        matches_sheet.append_row([match_id, team_a, team_b, "TBD", "", "Auto Proposed", "", "", "", "", "System"])

        team_a_row = [row for row in teams_sheet.get_all_values() if row[0] == team_a]
        team_b_row = [row for row in teams_sheet.get_all_values() if row[0] == team_b]

        captain_a_id = extract_user_id(team_a_row[0][1]) if team_a_row else None
        captain_b_id = extract_user_id(team_b_row[0][1]) if team_b_row else None

        await create_matchup_channel(interaction, team_a, team_b, captain_a_id, captain_b_id, week_number)

    embed = discord.Embed(title=f"✅ Week {week_number} Matches Generated", color=discord.Color.red() if force else discord.Color.blue())
    for match_pair in matchups:
        embed.add_field(name=f"{match_pair[0]} vs {match_pair[1]}", value="Scheduled: TBD", inline=False)

    await interaction.followup.send(embed=embed)

def setup_match_module(bot, spreadsheet):
    class WeeklyMatchGenerator(app_commands.Group):
        def __init__(self):
            super().__init__(name="weekly", description="Weekly match generation commands.")

        @app_commands.command(name="generate", description="Generate weekly matchups based on ELO.")
        @app_commands.describe(week_number="Enter the week number")
        async def generate(self, interaction: discord.Interaction, week_number: int):
            await generate_weekly_matches(interaction, spreadsheet, week_number)

    bot.tree.add_command(WeeklyMatchGenerator())

