import discord
from discord.ext import commands
import match
import random

def get_or_create_sheet(spreadsheet, name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except Exception:
        sheet = spreadsheet.add_worksheet(title=name, rows="100", cols=str(len(headers)))
        sheet.append_row(headers)
    return sheet

def setup_dev_module(bot, spreadsheet, DEV_OVERRIDE_IDS):

    matches_sheet = get_or_create_sheet(spreadsheet, "Matches", ["Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Proposed Score", "Final Score", "Winner", "Loser", "Proposed By"])
    teams_sheet = get_or_create_sheet(spreadsheet, "Teams", ["Team Name", "Player 1", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])
    leaderboard_sheet = get_or_create_sheet(spreadsheet, "Leaderboard", ["Team Name", "Rating", "Wins", "Losses", "Matches Played"])

    # Helper check
    def is_dev(ctx):
        return str(ctx.author.id) in DEV_OVERRIDE_IDS

    dev_commands_list = []

    # Wrapper to make dev commands
    def dev_command(name):
        def decorator(func):
            @commands.command(name=name, hidden=True)
            async def wrapper(ctx, *args):
                if not is_dev(ctx):
                    await ctx.send("🚫 You do not have permission to use this command.")
                    return
                await func(ctx, *args)
            bot.add_command(wrapper)
            dev_commands_list.append(f"!{name}")
            return wrapper
        return decorator

    @dev_command("commands")
    async def commands_list(ctx):
        embed = discord.Embed(title="🛠️ Dev Commands", color=discord.Color.orange())
        embed.description = "\n".join(dev_commands_list)
        await ctx.send(embed=embed)

    @dev_command("force_accept_match")
    async def force_accept_match(ctx, match_id):
        match_ids = matches_sheet.col_values(1)
        if match_id not in match_ids:
            await ctx.send("Invalid Match ID.")
            return
        row = match_ids.index(match_id) + 1
        matches_sheet.update_cell(row, 6, "Accepted")
        await ctx.send(f"✅ Force accepted match {match_id}.")

    @dev_command("force_accept_score")
    async def force_accept_score(ctx, match_id, winner_team):
        match_ids = matches_sheet.col_values(1)
        if match_id not in match_ids:
            await ctx.send("Invalid Match ID.")
            return
        row = match_ids.index(match_id) + 1
        match_data = matches_sheet.row_values(row)
        loser_team = match_data[1] if match_data[1] != winner_team else match_data[2]
        matches_sheet.update_cell(row, 6, "Finished")
        matches_sheet.update_cell(row, 9, winner_team)
        matches_sheet.update_cell(row, 10, loser_team)
        await ctx.send(f"✅ Force accepted score. Winner: {winner_team}")

    @dev_command("force_disband")
    async def force_disband(ctx, team_name):
        all_teams = teams_sheet.get_all_values()
        for idx, team in enumerate(all_teams, 1):
            if team[0].lower() == team_name.lower():
                teams_sheet.delete_rows(idx)
                await ctx.send(f"✅ Team '{team_name}' disbanded.")
                return
        await ctx.send("Team not found.")

    @dev_command("force_team_create")
    async def force_team_create(ctx, team_name, player1, player2, player3, player4=None, player5=None, player6=None):
        guild = ctx.guild
        players = [player1, player2, player3] + ([player4] if player4 else []) + ([player5] if player5 else []) + ([player6] if player6 else [])

        def parse_user_id(pid):
            if pid.startswith("<@") and pid.endswith(">"):
                return int(pid.replace("<@", "").replace(">", "").replace("!", ""))
            if pid.isdigit():
                return int(pid)
            return None

        team_role = await guild.create_role(name=f"Team {team_name}")
        captain_role = await guild.create_role(name=f"Team {team_name} Captain")

        players_with_names = []
        for player_id in players:
            parsed_id = parse_user_id(player_id)
            if parsed_id:
                member = guild.get_member(parsed_id)
                if member:
                    await member.add_roles(team_role)
                    players_with_names.append(f"{member.display_name} ({parsed_id})")
                else:
                    players_with_names.append(str(parsed_id))
            else:
                players_with_names.append(player_id)

        captain_id = parse_user_id(player1)
        if captain_id:
            captain_member = guild.get_member(captain_id)
            if captain_member:
                await captain_member.add_roles(captain_role)

        teams_sheet.append_row([team_name] + players_with_names + [""] * (6 - len(players_with_names)))
        await ctx.send(f"✅ Team '{team_name}' created with {', '.join(players_with_names)}.")

    @dev_command("force_weekly_match")
    async def force_weekly_match(ctx, week_number):
        await match.generate_weekly_matches(ctx, spreadsheet, week_number, force=True)

    @dev_command("force_add_team")
    async def force_add_team(ctx, team_name, elo, wins, losses, matches_played):
        leaderboard_sheet.append_row([team_name, elo, wins, losses, matches_played])
        await ctx.send(f"✅ Added team '{team_name}' to leaderboard.")

    @dev_command("force_add_teams")
    async def force_add_teams(ctx, amount, starting_elo):
        amount = int(amount)
        starting_elo = int(starting_elo)

        for i in range(amount):
            team_name = f"TestTeam {i+1}"
            leaderboard_sheet.append_row([team_name, starting_elo + random.randint(-25, 25), 0, 0, 0])

        await ctx.send(f"✅ Added {amount} fake teams to leaderboard.")

    @dev_command("panel")
    async def panel(ctx):
        from league_panel import post_panel
        await post_panel(ctx, bot, 
            get_or_create_sheet(spreadsheet, "Players", ["User ID", "Username"]),
            teams_sheet,
            matches_sheet,
            get_or_create_sheet(spreadsheet, "Scoring", ["Team A", "Team B", "Map #", "Game Mode", "Team A Score", "Team B Score", "Winner"]),
            leaderboard_sheet,
            get_or_create_sheet(spreadsheet, "Match Proposed", ["Team A", "Team B", "Proposer ID", "Proposed Date"]),
            get_or_create_sheet(spreadsheet, "Match Scheduled", ["Team A", "Team B", "Scheduled Date"]),
            lambda cid, msg=None, embed=None: ctx.send(msg or "", embed=embed),
            lambda msg=None, embed=None: ctx.send(msg or "", embed=embed),
            DEV_OVERRIDE_IDS
        )

    @dev_command("dispute_score")
    async def dispute_score(ctx, match_id):
        match_ids = matches_sheet.col_values(1)
        if match_id not in match_ids:
            await ctx.send("Invalid Match ID.")
            return
        row = match_ids.index(match_id) + 1
        matches_sheet.update_cell(row, 6, "Disputed Score")
        await ctx.send(f"⚡ Match {match_id} score has been disputed.")

    @dev_command("dispute_match_time")
    async def dispute_match_time(ctx, match_id):
        match_ids = matches_sheet.col_values(1)
        if match_id not in match_ids:
            await ctx.send("Invalid Match ID.")
            return
        row = match_ids.index(match_id) + 1
        matches_sheet.update_cell(row, 6, "Time Dispute")
        await ctx.send(f"⏰ Match {match_id} time has been disputed.")


