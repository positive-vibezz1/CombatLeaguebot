import discord
from discord import app_commands
import json

def setup_commands(bot, players_sheet, teams_sheet, matches_sheet, scoring_sheet, leaderboard_sheet, proposed_sheet, scheduled_sheet, send_to_channel, send_notification, DEV_OVERRIDE_IDS):

    with open("config.json") as f:
        config = json.load(f)

    MATCH_CHANNEL_ID = config.get("match_channel_id")
    SCORE_CHANNEL_ID = config.get("score_channel_id")
    RESULTS_CHANNEL_ID = config.get("results_channel_id")

    # -------------------- Helper --------------------

    def get_team_limits():
        with open("config.json") as f:
            config = json.load(f)
        return config.get("team_min_players", 3), config.get("team_max_players", 6)

    def get_team_rating(team_name):
        for idx, row in enumerate(leaderboard_sheet.get_all_values(), 1):
            if row[0] == team_name:
                return idx, int(row[1]), int(row[2]), int(row[3]), int(row[4])
        return None

    def update_team_rating(team_name, won):
        ELO_WIN_POINTS = config.get("elo_win_points", 25)
        ELO_LOSS_POINTS = config.get("elo_loss_points", -25)

        team = get_team_rating(team_name)
        if team:
            idx, rating, wins, losses, matches = team
            new_rating = rating + ELO_WIN_POINTS if won else rating + ELO_LOSS_POINTS
            leaderboard_sheet.update(f"B{idx}", [[new_rating, wins + (1 if won else 0), losses + (0 if won else 1), matches + 1]])
        else:
            starting = 1025 if won else 975
            leaderboard_sheet.append_row([team_name, starting, 1 if won else 0, 0 if won else 1, 1])

    # -------------------- PLAYER --------------------
    
    player_group = app_commands.Group(name="player", description="Player commands")

    @player_group.command(name="signup")
    async def signup(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        if user_id in players_sheet.col_values(1):
            await interaction.followup.send("You are already signed up.")
            return

        players_sheet.append_row([user_id, username])
        await interaction.followup.send("You have been signed up!")
        await send_notification(f"📌 {interaction.user.mention} has signed up for the league!")

    @player_group.command(name="unsignup")
    async def unsignup(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        for idx, row in enumerate(players_sheet.get_all_values(), 1):
            if row[0] == user_id:
                for team in teams_sheet.get_all_values():
                    if user_id in team:
                        await interaction.followup.send("You must leave your team first.")
                        return
                players_sheet.delete_rows(idx)
                await interaction.followup.send("You have been removed from the player list.")
                return

        await interaction.followup.send("You are not signed up.")

    bot.tree.add_command(player_group)

    # -------------------- TEAM --------------------

    team_group = app_commands.Group(name="team", description="Team commands")

    @team_group.command(name="signup")
    async def team_signup(interaction: discord.Interaction, team_name: str, player1: discord.Member, player2: discord.Member, player3: discord.Member, player4: discord.Member = None, player5: discord.Member = None, player6: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        players = [player1, player2, player3] + ([player4] if player4 else []) + ([player5] if player5 else []) + ([player6] if player6 else [])
        min_players, max_players = get_team_limits()

        signed_up_ids = players_sheet.col_values(1)
        not_signed_up = [p.display_name for p in players if str(p.id) not in signed_up_ids]
        if not_signed_up:
            await interaction.followup.send("Some players are not signed up: " + ", ".join(not_signed_up))
            return

        for team in teams_sheet.get_all_values():
            for p in players:
                if p.display_name in team:
                    await interaction.followup.send(f"{p.display_name} is already in a team!")
                    return

        if str(interaction.user.id) not in DEV_OVERRIDE_IDS and (len(players) < min_players or len(players) > max_players):
            await interaction.followup.send(f"Teams must have between {min_players} and {max_players} players.")
            return

        if discord.utils.get(interaction.guild.roles, name=f"Team {team_name}"):
            await interaction.followup.send("Team already exists.")
            return

        team_role = await interaction.guild.create_role(name=f"Team {team_name}")
        captain_role = await interaction.guild.create_role(name=f"Team {team_name} Captain")

        for member in players:
            await member.add_roles(team_role)
        await player1.add_roles(captain_role)

        player_names = [p.display_name for p in players]
        teams_sheet.append_row([team_name] + player_names + [""] * (6 - len(player_names)))

        await interaction.followup.send(f"✅ Team **{team_name}** created successfully!")
        embed = discord.Embed(title=f"📢 Team Created: {team_name}", color=discord.Color.green())
        embed.add_field(name="Players", value=", ".join([p.mention for p in players]), inline=False)
        await send_notification(None, embed)

    @team_group.command(name="leave")
    async def team_leave(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        username = interaction.user.display_name

        for idx, team in enumerate(teams_sheet.get_all_values(), 1):
            if username in team:
                team_name = team[0]
                if username == team[1]:
                    await interaction.followup.send("You are the captain. Disband or promote before leaving.")
                    return

                row = teams_sheet.row_values(idx)
                for i in range(1, 7):
                    if row[i] == username:
                        teams_sheet.update_cell(idx, i + 1, "")
                        break

                team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name}")
                if team_role:
                    await interaction.user.remove_roles(team_role)

                await interaction.followup.send(f"You have left **{team_name}**.")
                embed = discord.Embed(title=f"🚪 Player Left: {username}", description=f"{username} has left **{team_name}**.", color=discord.Color.orange())
                await send_notification(None, embed)
                return

        await interaction.followup.send("You are not in any team.")

    @team_group.command(name="promote")
    async def team_promote(interaction: discord.Interaction, new_captain: discord.Member):
        await interaction.response.defer(ephemeral=True)
        username = interaction.user.display_name
        new_name = new_captain.display_name

        for idx, team in enumerate(teams_sheet.get_all_values(), 1):
            if username == team[1]:
                team_name = team[0]
                if new_name not in team:
                    await interaction.followup.send("That user is not in your team.")
                    return

                teams_sheet.update_cell(idx, 2, new_name)
                old_captain_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name} Captain")

                if old_captain_role:
                    await interaction.user.remove_roles(old_captain_role)
                    await new_captain.add_roles(old_captain_role)

                await interaction.followup.send(f"{new_captain.mention} is now the captain of **{team_name}**.")
                embed = discord.Embed(title=f"👑 New Captain: {team_name}", description=f"{new_captain.mention} is now the captain.", color=discord.Color.gold())
                await send_notification(None, embed)
                return

        await interaction.followup.send("You are not the captain or in a team.")

    @team_group.command(name="disband")
    async def team_disband(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        username = interaction.user.display_name

        for idx, team in enumerate(teams_sheet.get_all_values(), 1):
            if len(team) < 2:
                continue

            if username == team[1] or str(interaction.user.id) in DEV_OVERRIDE_IDS:
                team_name = team[0]

                team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name}")
                captain_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name} Captain")

                if team_role:
                    await team_role.delete()
                if captain_role:
                    await captain_role.delete()

                teams_sheet.delete_rows(idx)

                await interaction.followup.send(f"✅ Team **{team_name}** has been disbanded.")
                embed = discord.Embed(title=f"❗ Team Disbanded", description=f"**{team_name}** has been disbanded.", color=discord.Color.red())
                await send_notification(None, embed)
                return

        await interaction.followup.send("You are not the captain or dev.")
        
    bot.tree.add_command(team_group)

        # -------------------- MATCH --------------------

    match_group = app_commands.Group(name="match", description="Match commands")

    @match_group.command(name="propose")
    async def propose_match(interaction: discord.Interaction, my_team: str, opponent_team: str, proposed_date: str):
        await interaction.response.defer(ephemeral=True)

        if my_team == opponent_team:
            await interaction.followup.send("Cannot propose against yourself.")
            return

        if str(interaction.user.id) not in DEV_OVERRIDE_IDS and discord.utils.get(interaction.user.roles, name=f"Team {my_team} Captain") is None:
            await interaction.followup.send("Only captains can propose.")
            return

        all_teams = [row[0] for row in teams_sheet.get_all_values()]
        if my_team not in all_teams or opponent_team not in all_teams:
            await interaction.followup.send("One or both teams do not exist.")
            return

        matches_sheet.append_row([my_team, opponent_team, proposed_date, "", "Proposed", "", "", str(interaction.user.id)])
        proposed_sheet.append_row([my_team, opponent_team, str(interaction.user.id), proposed_date])

        embed = discord.Embed(title="📌 Match Proposed", color=discord.Color.blue())
        embed.add_field(name="Teams", value=f"{my_team} vs {opponent_team}")
        embed.add_field(name="Proposed Date", value=proposed_date)

        await send_to_channel(MATCH_CHANNEL_ID, f"📢 Match Proposed: **{my_team} vs {opponent_team}** → `{proposed_date}`", embed=embed)
        await interaction.followup.send("Match proposal sent!")

    bot.tree.add_command(match_group)

    # -------------------- SCORE --------------------

    score_group = app_commands.Group(name="score", description="Score commands")

    @score_group.command(name="propose")
    async def propose_score(interaction: discord.Interaction, my_team: str, opponent_team: str,
                            map1_mode: str, map1_my: int, map1_opp: int,
                            map2_mode: str, map2_my: int, map2_opp: int,
                            map3_mode: str, map3_my: int, map3_opp: int):
        await interaction.response.defer(ephemeral=True)

        if str(interaction.user.id) not in DEV_OVERRIDE_IDS and discord.utils.get(interaction.user.roles, name=f"Team {my_team} Captain") is None:
            await interaction.followup.send("Only captains can propose scores.")
            return

        all_teams = [row[0] for row in teams_sheet.get_all_values()]
        if my_team not in all_teams or opponent_team not in all_teams:
            await interaction.followup.send("Teams do not exist.")
            return

        maps = [(map1_mode, map1_my, map1_opp), (map2_mode, map2_my, map2_opp), (map3_mode, map3_my, map3_opp)]
        my_wins, opp_wins = 0, 0
        embed = discord.Embed(title="📊 Score Proposal", color=discord.Color.gold())

        for idx, (mode, my_score, opp_score) in enumerate(maps, 1):
            winner = my_team if my_score > opp_score else opponent_team
            if winner == my_team:
                my_wins += 1
            else:
                opp_wins += 1

            scoring_sheet.append_row([my_team, opponent_team, idx, mode, my_score, opp_score, winner])
            embed.add_field(name=f"Map {idx} [{mode}]", value=f"{my_team}: {my_score} - {opponent_team}: {opp_score} → Winner: {winner}", inline=False)

        final_winner = my_team if my_wins >= 2 else opponent_team
        embed.add_field(name="Overall Winner", value=f"🏆 {final_winner}")

        matches_sheet.append_row([my_team, opponent_team, "", "", "Score Proposed", final_winner, opponent_team if final_winner == my_team else my_team, str(interaction.user.id)])

        await send_to_channel(SCORE_CHANNEL_ID, f"📊 **Score Proposed:** {my_team} vs {opponent_team}", embed=embed)
        await interaction.followup.send("Score proposal sent.")

    @score_group.command(name="accept")
    async def accept_score(interaction: discord.Interaction, my_team: str, opponent_team: str):
        await interaction.response.defer(ephemeral=True)

        for idx, row in enumerate(matches_sheet.get_all_values()[::-1], 1):
            if row[0] == opponent_team and row[1] == my_team and row[4] == "Score Proposed":
                real_row = len(matches_sheet.get_all_values()) - idx + 1
                winner = row[5]
                loser = row[6]

                matches_sheet.update_cell(real_row, 5, "Finished")
                update_team_rating(winner, True)
                update_team_rating(loser, False)

                await interaction.followup.send("✅ Score accepted and finalized!")
                await send_to_channel(RESULTS_CHANNEL_ID, f"🏆 **Finalized:** {winner} defeated {loser}")
                return

        await interaction.followup.send("No proposed score found.")

    bot.tree.add_command(score_group)

    # -------------------- LEADERBOARD --------------------

    @bot.tree.command(name="leaderboard", description="View the current leaderboard.")
    async def leaderboard(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        all_teams = leaderboard_sheet.get_all_values()[1:]
        if not all_teams:
            await interaction.followup.send("Leaderboard is empty.")
            return

        all_teams.sort(key=lambda x: int(x[1]), reverse=True)
        embed = discord.Embed(title="🏆 League Leaderboard", color=discord.Color.purple())

        for idx, team in enumerate(all_teams[:10], 1):
            embed.add_field(name=f"#{idx} - {team[0]}", value=f"ELO: {team[1]} | Wins: {team[2]} | Losses: {team[3]} | Matches: {team[4]}", inline=False)

        await interaction.followup.send(embed=embed)

# -------------------- LEAVE TEAM --------------------

@discord.ui.button(label="🚪 Leave Team", style=discord.ButtonStyle.red)
async def leave_team(self, interaction: discord.Interaction, button: discord.ui.Button):
    username = interaction.user.display_name

    for idx, team in enumerate(self.teams_sheet.get_all_values(), 1):
        if username in team:
            team_name = team[0]
            if username == team[1]:
                await interaction.response.send_message("You are the captain. Promote or disband first.", ephemeral=True)
                return

            self.teams_sheet.update_cell(idx, team.index(username)+1, "")
            team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name}")
            if team_role:
                await interaction.user.remove_roles(team_role)

            await interaction.response.send_message(f"You left {team_name}.", ephemeral=True)
            return

    await interaction.response.send_message("You are not in a team.", ephemeral=True)

# -------------------- UNSIGNUP --------------------

@discord.ui.button(label="❌ Unsignup", style=discord.ButtonStyle.red)
async def unsignup(self, interaction: discord.Interaction, button: discord.ui.Button):
    user_id = str(interaction.user.id)

    for idx, row in enumerate(self.players_sheet.get_all_values(), 1):
        if row[0] == user_id:
            for team in self.teams_sheet.get_all_values():
                if row[0] in team:
                    await interaction.response.send_message("You must leave your team first.", ephemeral=True)
                    return
            self.players_sheet.delete_rows(idx)
            await interaction.response.send_message("You have been removed from the player list.", ephemeral=True)
            return

    await interaction.response.send_message("You are not signed up.", ephemeral=True)

# -------------------- JOIN TEAM (Request/Approve System) --------------------

@discord.ui.button(label="➕ Request to Join Team", style=discord.ButtonStyle.blurple)
async def join_team(self, interaction: discord.Interaction, button: discord.ui.Button):

    class JoinModal(Modal, title="Request to Join Team"):
        team_name = TextInput(label="Team Name")

        async def on_submit(modal_self, modal_interaction: discord.Interaction):
            team_name = modal_self.team_name.value
            for team in self.teams_sheet.get_all_values():
                if team[0].lower() == team_name.lower():
                    captain_name = team[1]
                    captain = discord.utils.get(interaction.guild.members, display_name=captain_name)
                    if captain:
                        async def approve_callback(inter2: discord.Interaction):
                            self.teams_sheet.append_row([team_name, interaction.user.display_name])
                            await interaction.user.add_roles(discord.utils.get(interaction.guild.roles, name=f"Team {team_name}"))
                            await inter2.response.send_message("✅ Request accepted.", ephemeral=True)

                        async def deny_callback(inter2: discord.Interaction):
                            await inter2.response.send_message("❌ Request denied.", ephemeral=True)

                        view = View(timeout=600)
                        view.add_item(Button(label="✅ Accept", style=discord.ButtonStyle.green, custom_id="accept"))
                        view.add_item(Button(label="❌ Deny", style=discord.ButtonStyle.red, custom_id="deny"))

                        async def interaction_check(inter3: discord.Interaction):
                            return inter3.user == captain

                        view.interaction_check = interaction_check

                        await captain.send(f"{interaction.user.display_name} requested to join {team_name}.", view=view)
                        await modal_interaction.response.send_message("Join request sent to captain!", ephemeral=True)
                        return

            await modal_interaction.response.send_message("Team not found or no captain.", ephemeral=True)

    await interaction.response.send_modal(JoinModal())

# -------------------- ACCEPT MATCH --------------------

@discord.ui.button(label="📌 Accept Proposed Match", style=discord.ButtonStyle.green)
async def accept_match(self, interaction: discord.Interaction, button: discord.ui.Button):

    class MatchAcceptModal(Modal, title="Accept Proposed Match"):
        match_id = TextInput(label="Match ID (row number)")

        async def on_submit(modal_self, modal_interaction: discord.Interaction):
            row = int(modal_self.match_id.value)
            self.matches_sheet.update_cell(row, 5, "Scheduled")
            await modal_interaction.response.send_message("✅ Match accepted and scheduled!", ephemeral=True)

    await interaction.response.send_modal(MatchAcceptModal())

# -------------------- ACCEPT SCORE --------------------

@discord.ui.button(label="🏆 Accept Proposed Score", style=discord.ButtonStyle.green)
async def accept_score(self, interaction: discord.Interaction, button: discord.ui.Button):

    class ScoreAcceptModal(Modal, title="Accept Proposed Score"):
        match_id = TextInput(label="Match ID (row number)")

        async def on_submit(modal_self, modal_interaction: discord.Interaction):
            row = int(modal_self.match_id.value)
            winner = self.matches_sheet.cell(row, 6).value
            loser = self.matches_sheet.cell(row, 7).value

            self.matches_sheet.update_cell(row, 5, "Finished")
            self.update_team_rating(winner, True)
            self.update_team_rating(loser, False)

            await modal_interaction.response.send_message("✅ Score finalized!", ephemeral=True)

    await interaction.response.send_modal(ScoreAcceptModal())

# -------------------- DISBAND TEAM --------------------

@discord.ui.button(label="❗ Disband Team", style=discord.ButtonStyle.red)
async def disband_team(self, interaction: discord.Interaction, button: discord.ui.Button):

    class DisbandModal(Modal, title="Disband Team"):
        team_name = TextInput(label="Team Name")

        async def on_submit(modal_self, modal_interaction: discord.Interaction):
            team_name = modal_self.team_name.value
            for idx, team in enumerate(self.teams_sheet.get_all_values(), 1):
                if team[0].lower() == team_name.lower():
                    if team[1] != interaction.user.display_name and str(interaction.user.id) not in self.DEV_OVERRIDE_IDS:
                        await modal_interaction.response.send_message("Only captain or dev can disband.", ephemeral=True)
                        return

                    team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name}")
                    captain_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name} Captain")
                    if team_role:
                        await team_role.delete()
                    if captain_role:
                        await captain_role.delete()

                    self.teams_sheet.delete_rows(idx)
                    await modal_interaction.response.send_message("✅ Team disbanded.", ephemeral=True)
                    return

            await modal_interaction.response.send_message("Team not found.", ephemeral=True)

    await interaction.response.send_modal(DisbandModal())
