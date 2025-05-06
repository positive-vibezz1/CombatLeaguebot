import discord
from discord.ui import View, Button, Modal, TextInput
import json
import re

# Helper function to extract user ID from "Name (ID)"
def extract_user_id(text):
    match = re.search(r"\((\d{15,})\)", text)
    if match:
        return int(match.group(1))
    return None

class LeaguePanel(View):
    def __init__(self, bot, players_sheet, teams_sheet, matches_sheet, scoring_sheet, leaderboard_sheet, proposed_sheet, scheduled_sheet, send_to_channel, send_notification, DEV_OVERRIDE_IDS):
        super().__init__(timeout=None)
        self.bot = bot
        self.players_sheet = players_sheet
        self.teams_sheet = teams_sheet
        self.matches_sheet = matches_sheet
        self.scoring_sheet = scoring_sheet
        self.leaderboard_sheet = leaderboard_sheet
        self.proposed_sheet = proposed_sheet
        self.scheduled_sheet = scheduled_sheet
        self.send_to_channel = send_to_channel
        self.send_notification = send_notification
        self.DEV_OVERRIDE_IDS = DEV_OVERRIDE_IDS

        with open("config.json") as f:
            self.config = json.load(f)

    def player_signed_up(self, user_id):
        user_id = str(user_id)
        for row in self.players_sheet.get_all_values():
            extracted_id = extract_user_id(row[0])
            if extracted_id and str(extracted_id) == user_id:
                return True
        return False

    def team_exists(self, team_name):
        return any(team[0].lower() == team_name.lower() for team in self.teams_sheet.get_all_values())

# -------------------- PLAYER SIGNUP --------------------

    @discord.ui.button(label="✅ Player Signup", style=discord.ButtonStyle.green)
    async def player_signup(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        username = f"{interaction.user.display_name} ({user_id})"

        if self.player_signed_up(user_id):
            await interaction.response.send_message("You are already signed up.", ephemeral=True)
            return

        self.players_sheet.append_row([username])
        await interaction.response.send_message("You have been signed up!", ephemeral=True)
        await self.send_notification(f"📌 {interaction.user.mention} has signed up for the league!")

# -------------------- CREATE TEAM --------------------

    @discord.ui.button(label="🏷️ Create Team", style=discord.ButtonStyle.blurple)
    async def create_team(self, interaction: discord.Interaction, button: discord.ui.Button):

        # Check if captain already on a team
        user_id = f"{interaction.user.display_name} ({interaction.user.id})"
        for row in self.teams_sheet.get_all_values():
            if user_id in row:
                await interaction.response.send_message("❗ You are already on a team. Leave your team before creating a new one.", ephemeral=True)
                return

        # --- Team Name Modal ---
        class TeamNameModal(discord.ui.Modal, title="Enter Team Name"):
            team_name = discord.ui.TextInput(label="Team Name", required=True)

            def __init__(self, parent_view):
                super().__init__()
                self.parent = parent_view

            async def on_submit(self, modal_interaction: discord.Interaction):
                team_name = self.team_name.value.strip()

                # Check if team already exists
                existing_teams = [row[0].strip().lower() for row in self.parent.teams_sheet.get_all_values()]
                if team_name.lower() in existing_teams:
                    await modal_interaction.response.send_message("❗ Team already exists. Choose another name.", ephemeral=True)
                    return

                await modal_interaction.response.send_message(f"✅ Team name **{team_name}** selected! Now select players.", ephemeral=True)

                await modal_interaction.followup.send(view=SelectPlayersView(self.parent, team_name, modal_interaction.user, modal_interaction.guild.id), ephemeral=True)

        # --- Player Select View ---
        class SelectPlayersView(discord.ui.View):
            def __init__(self, parent, team_name, captain, guild_id):
                super().__init__(timeout=600)
                self.parent = parent
                self.team_name = team_name
                self.captain = captain
                self.guild_id = guild_id
                self.selected_players = []
                self.min_starters = self.parent.config.get("team_min_players", 3)
                self.max_total = self.parent.config.get("team_max_players", 6)

            @discord.ui.button(label="➕ Add Starter", style=discord.ButtonStyle.green)
            async def add_starter(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.select_player(interaction, starter=True)

            @discord.ui.button(label="➕ Add Sub", style=discord.ButtonStyle.blurple)
            async def add_sub(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.select_player(interaction, starter=False)

            @discord.ui.button(label="📩 Send Invites", style=discord.ButtonStyle.green)
            async def send_invites(self, interaction: discord.Interaction, button: discord.ui.Button):
                if len([p for p, role in self.selected_players if role == "Starter"]) < self.min_starters:
                    await interaction.response.send_message(f"❗ You must select at least {self.min_starters} starters.", ephemeral=True)
                    return

                if len(self.selected_players) > self.max_total:
                    await interaction.response.send_message(f"❗ Maximum team size is {self.max_total}.", ephemeral=True)
                    return

                success, fail = [], []

                for player, role in self.selected_players:
                    try:
                        view = AcceptDenyInviteView(self.parent, self.captain, self.team_name, player, role, self.guild_id)
                        await player.send(f"You are invited to join **{self.team_name}** as a **{role}**.", view=view)
                        success.append(player.display_name)
                    except:
                        fail.append(player.display_name)

                await interaction.response.send_message(f"✅ Invites sent to: {', '.join(success)}" + (f"\n❗ Could not DM: {', '.join(fail)}" if fail else ""), ephemeral=True)

            async def select_player(self, interaction: discord.Interaction, starter=True):
                members = [m async for m in interaction.guild.fetch_members(limit=None)]

                existing_members = set()
                for team in self.parent.teams_sheet.get_all_values():
                    existing_members.update(team[1:7])

                players = [
                    m for m in members
                    if self.parent.player_signed_up(m.id)
                    and f"{m.display_name} ({m.id})" not in existing_members
                    and m != self.captain
                    and m not in [p for p, _ in self.selected_players]
                ]

                if not players:
                    await interaction.response.send_message("❗ No available players to select.", ephemeral=True)
                    return

                options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in players[:25]]
                select = discord.ui.Select(placeholder="Pick Player", options=options)

                async def callback(select_interaction):
                    player_id = int(select.values[0])
                    player = interaction.guild.get_member(player_id)

                    self.selected_players.append((player, "Starter" if starter else "Sub"))
                    await select_interaction.response.send_message(f"✅ Added {player.mention} as {'Starter' if starter else 'Sub'}.", ephemeral=True)

                select.callback = callback
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await interaction.response.send_message("Select player:", view=view, ephemeral=True)

        # --- Accept / Deny Invite View ---
        class AcceptDenyInviteView(discord.ui.View):
            def __init__(self, parent, captain, team_name, invitee, role, guild_id):
                super().__init__(timeout=300)
                self.parent = parent
                self.captain = captain
                self.team_name = team_name
                self.invitee = invitee
                self.role = role
                self.guild_id = guild_id

            @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
            async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                guild = self.parent.bot.get_guild(self.guild_id)
                if guild is None:
                    await interaction.response.send_message("❗ Guild not available or invite expired.", ephemeral=True)
                    return

                for idx, team in enumerate(self.parent.teams_sheet.get_all_values(), 1):
                    if team[0].lower() == self.team_name.lower():
                        for i in range(1, 7):
                            if team[i] == "":
                                self.parent.teams_sheet.update_cell(idx, i+1, f"{self.invitee.display_name} ({self.invitee.id})")
                                break
                        break
                else:
                    self.parent.teams_sheet.append_row([self.team_name, f"{self.captain.display_name} ({self.captain.id})", f"{self.invitee.display_name} ({self.invitee.id})"] + [""]*4)

                team_role = discord.utils.get(guild.roles, name=f"Team {self.team_name}")
                if not team_role:
                    team_role = await guild.create_role(name=f"Team {self.team_name}")

                member = guild.get_member(self.invitee.id)
                if member:
                    await member.add_roles(team_role)
                    await interaction.response.send_message(f"✅ You joined **{self.team_name}**!", ephemeral=True)
                else:
                    await interaction.response.send_message("❗ You are not in the server.", ephemeral=True)

            @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
            async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message(f"❌ You declined the invite to **{self.team_name}**.", ephemeral=True)

        # Start with team name modal
        await interaction.response.send_modal(TeamNameModal(self))

    # -------------------- PROPOSE MATCH --------------------

    @discord.ui.button(label="📅 Propose Match", style=discord.ButtonStyle.green)
    async def propose_match(self, interaction: discord.Interaction, button: discord.ui.Button):

        class DateSelectView(discord.ui.View):
            def __init__(self, parent):
                super().__init__(timeout=300)
                self.parent = parent

            @discord.ui.button(label="📅 Select Day 1-15", style=discord.ButtonStyle.primary)
            async def select_day_1_15(self, interaction: discord.Interaction, button: discord.ui.Button):
                days = [discord.SelectOption(label=str(day), value=str(day)) for day in range(1, 16)]
                select = discord.ui.Select(placeholder="Select Day (1-15)", options=days)

                async def callback(select_interaction):
                    self.parent.date_time["day"] = select.values[0]
                    await select_interaction.response.send_message(f"✅ Day set to {select.values[0]}", ephemeral=True)

                select.callback = callback
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await interaction.response.send_message("Select day (1-15):", view=view, ephemeral=True)

            @discord.ui.button(label="📅 Select Day 16-31", style=discord.ButtonStyle.primary)
            async def select_day_16_31(self, interaction: discord.Interaction, button: discord.ui.Button):
                days = [discord.SelectOption(label=str(day), value=str(day)) for day in range(16, 32)]
                select = discord.ui.Select(placeholder="Select Day (16-31)", options=days)

                async def callback(select_interaction):
                    self.parent.date_time["day"] = select.values[0]
                    await select_interaction.response.send_message(f"✅ Day set to {select.values[0]}", ephemeral=True)

                select.callback = callback
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await interaction.response.send_message("Select day (16-31):", view=view, ephemeral=True)

            @discord.ui.button(label="📅 Select Month", style=discord.ButtonStyle.primary)
            async def select_month(self, interaction: discord.Interaction, button: discord.ui.Button):
                months = [discord.SelectOption(label=month, value=str(i + 1)) for i, month in enumerate(
                    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])]
                select = discord.ui.Select(placeholder="Select Month", options=months)

                async def callback(select_interaction):
                    self.parent.date_time["month"] = select.values[0]
                    await select_interaction.response.send_message(f"✅ Month set to {select.values[0]}", ephemeral=True)

                select.callback = callback
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await interaction.response.send_message("Select month:", view=view, ephemeral=True)

        class TimeSelectView(discord.ui.View):
            def __init__(self, parent):
                super().__init__(timeout=300)
                self.parent = parent

                hours = [discord.SelectOption(label=str(h), value=str(h)) for h in range(1, 13)]
                self.hour_select = discord.ui.Select(placeholder="Select Hour", options=hours)
                self.hour_select.callback = self.set_hour
                self.add_item(self.hour_select)

                minutes = [discord.SelectOption(label=f"{m:02}", value=str(m)) for m in range(0, 60, 5)]
                self.minute_select = discord.ui.Select(placeholder="Select Minute", options=minutes)
                self.minute_select.callback = self.set_minute
                self.add_item(self.minute_select)

                am_pm = [discord.SelectOption(label="AM", value="AM"), discord.SelectOption(label="PM", value="PM")]
                self.am_pm_select = discord.ui.Select(placeholder="Select AM or PM", options=am_pm)
                self.am_pm_select.callback = self.set_am_pm
                self.add_item(self.am_pm_select)

                timezones = [discord.SelectOption(label=tz, value=tz) for tz in ["UTC", "EST", "CST", "MST", "PST"]]
                self.timezone_select = discord.ui.Select(placeholder="Select Timezone", options=timezones)
                self.timezone_select.callback = self.set_timezone
                self.add_item(self.timezone_select)

            async def set_hour(self, interaction: discord.Interaction):
                self.parent.date_time["hour"] = self.hour_select.values[0]
                await interaction.response.send_message(f"✅ Hour set to {self.hour_select.values[0]}", ephemeral=True)

            async def set_minute(self, interaction: discord.Interaction):
                self.parent.date_time["minute"] = self.minute_select.values[0]
                await interaction.response.send_message(f"✅ Minute set to {self.minute_select.values[0]}", ephemeral=True)

            async def set_am_pm(self, interaction: discord.Interaction):
                self.parent.date_time["am_pm"] = self.am_pm_select.values[0]
                await interaction.response.send_message(f"✅ AM/PM set to {self.am_pm_select.values[0]}", ephemeral=True)

            async def set_timezone(self, interaction: discord.Interaction):
                self.parent.date_time["timezone"] = self.timezone_select.values[0]
                await interaction.response.send_message(f"✅ Timezone set to {self.timezone_select.values[0]}", ephemeral=True)

        class ProposeMatchView(discord.ui.View):
            def __init__(self, parent, teams):
                super().__init__(timeout=600)
                self.parent = parent
                self.teams = teams
                self.selected_team = None
                self.opponent_team = None
                self.date_time = {}

            @discord.ui.button(label="Select Your Team", style=discord.ButtonStyle.blurple)
            async def select_team(self, interaction: discord.Interaction, button: discord.ui.Button):
                options = [discord.SelectOption(label=team, value=team) for team in self.teams]
                select = discord.ui.Select(placeholder="Your Team", options=options)

                async def callback(select_interaction):
                    self.selected_team = select.values[0]
                    await select_interaction.response.send_message(f"✅ Selected your team: {self.selected_team}", ephemeral=True)

                select.callback = callback
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await interaction.response.send_message("Select your team:", view=view, ephemeral=True)

            @discord.ui.button(label="Select Opponent Team", style=discord.ButtonStyle.blurple)
            async def select_opponent(self, interaction: discord.Interaction, button: discord.ui.Button):
                options = [discord.SelectOption(label=team, value=team) for team in self.teams if team != self.selected_team]
                select = discord.ui.Select(placeholder="Opponent Team", options=options)

                async def callback(select_interaction):
                    self.opponent_team = select.values[0]
                    await select_interaction.response.send_message(f"✅ Selected opponent: {self.opponent_team}", ephemeral=True)

                select.callback = callback
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await interaction.response.send_message("Select opponent team:", view=view, ephemeral=True)

            @discord.ui.button(label="📅 Select Date (Month/Day)", style=discord.ButtonStyle.primary)
            async def open_date_selector(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("Select month and day:", view=DateSelectView(self), ephemeral=True)

            @discord.ui.button(label="⏰ Select Time (Hour, Minute, AM/PM, Timezone)", style=discord.ButtonStyle.primary)
            async def open_time_selector(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("Select time:", view=TimeSelectView(self), ephemeral=True)

            @discord.ui.button(label="✅ Finalize and Send Proposal", style=discord.ButtonStyle.green)
            async def finalize(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not self.selected_team or not self.opponent_team or any(k not in self.date_time for k in ["month", "day", "hour", "minute", "am_pm", "timezone"]):
                    await interaction.response.send_message("❗ Complete all fields first.", ephemeral=True)
                    return

                proposed_date = f"{self.date_time['month']}/{self.date_time['day']} at {self.date_time['hour']}:{self.date_time['minute']} {self.date_time['am_pm']} {self.date_time['timezone']}"

                self.parent.proposed_sheet.append_row([
                    self.selected_team,
                    self.opponent_team,
                    str(interaction.user.id),
                    proposed_date
                ])

                await interaction.response.send_message(f"✅ Proposed match sent to {self.opponent_team}!", ephemeral=True)

                guild = interaction.guild
                opponent_role = discord.utils.get(guild.roles, name=f"Team {self.opponent_team}")
                if opponent_role and opponent_role.members:
                    captain = opponent_role.members[0]
                    try:
                        await captain.send(
                            f"📨 Proposed Match from **{self.selected_team}** on `{proposed_date}`. Accept?",
                            view=AcceptDenyMatchView(self.parent, self.selected_team, self.opponent_team, proposed_date)
                        )
                    except discord.Forbidden:
                        await interaction.followup.send("Opponent captain's DMs are closed.", ephemeral=True)

        class AcceptDenyMatchView(discord.ui.View):
            def __init__(self, parent, team_a, team_b, proposed_date):
                super().__init__(timeout=300)
                self.parent = parent
                self.team_a = team_a
                self.team_b = team_b
                self.proposed_date = proposed_date

            @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
            async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.parent.scheduled_sheet.append_row([
                    self.team_a, self.team_b, self.proposed_date
                ])

                await interaction.response.send_message("✅ Match accepted and scheduled!", ephemeral=True)

                match_channel = self.parent.bot.get_channel(self.parent.match_channel_id)
                if match_channel:
                    embed = discord.Embed(
                        title="📅 Match Scheduled",
                        description=f"**{self.team_a}** vs **{self.team_b}**\n📆 {self.proposed_date}",
                        color=discord.Color.green()
                    )
                    await match_channel.send(embed=embed)

            @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
            async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("❌ Match proposal declined.", ephemeral=True)

        teams = [row[0] for row in self.teams_sheet.get_all_values() if row[0]]
        await interaction.response.send_message("Propose a match:", view=ProposeMatchView(self, teams), ephemeral=True)

    # -------------------- PROPOSE SCORE --------------------

    @discord.ui.button(label="🏆 Propose Score", style=discord.ButtonStyle.blurple)
    async def propose_score(self, interaction: discord.Interaction, button: discord.ui.Button):

        # Helper to get matches scheduled
        scheduled_matches = self.scheduled_sheet.get_all_values()[1:]  # skip header
        user_id = str(interaction.user.id)

        # Find matches where user is captain (either team A or team B captain role exists)
        matches = []
        for match in scheduled_matches:
            team1, team2, date = match[0], match[1], match[2]
            team1_role = discord.utils.get(interaction.guild.roles, name=f"Team {team1} Captain")
            team2_role = discord.utils.get(interaction.guild.roles, name=f"Team {team2} Captain")

            if (team1_role and user_id in [str(m.id) for m in team1_role.members]) or (team2_role and user_id in [str(m.id) for m in team2_role.members]):
                matches.append({"team1": team1, "team2": team2, "date": date})

        if not matches:
            await interaction.response.send_message("❗ No scheduled matches found or you are not a captain.", ephemeral=True)
            return

        # Step 1: Select match
        class MatchSelectView(discord.ui.View):
            def __init__(self, parent, matches):
                super().__init__(timeout=600)
                self.parent = parent
                self.matches = matches

                options = [discord.SelectOption(label=f"{m['team1']} vs {m['team2']} on {m['date']}", value=str(i)) for i, m in enumerate(matches)]
                select = discord.ui.Select(placeholder="Select Match", options=options)
                select.callback = self.match_selected
                self.add_item(select)

            async def match_selected(self, interaction: discord.Interaction):
                match = self.matches[int(interaction.data['values'][0])]
                await interaction.response.send_message("Now enter scores for Map 1", view=MapScoreView(self.parent, match, [], map_number=1), ephemeral=True)

        # Step 2: Enter map scores
        class MapScoreView(discord.ui.View):
            def __init__(self, parent, match, map_scores, map_number):
                super().__init__(timeout=600)
                self.parent = parent
                self.match = match
                self.map_scores = map_scores
                self.map_number = map_number

                self.add_item(discord.ui.Button(label=f"Enter Map {map_number} Score", style=discord.ButtonStyle.green, custom_id="map_score"))

            @discord.ui.button(label="✅ Submit", style=discord.ButtonStyle.success, row=1)
            async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.map_number < 2:
                    await interaction.response.send_message(f"❗ Map {self.map_number} is required.", ephemeral=True)
                    return

                await interaction.response.send_message("Proposed scores submitted. Waiting for opponent confirmation...", ephemeral=True)

                # Get opponent captain
                opponent_team = self.match["team2"] if interaction.user in [m for m in discord.utils.get(interaction.guild.roles, name=f"Team {self.match['team1']} Captain").members] else self.match["team1"]
                opponent_role = discord.utils.get(interaction.guild.roles, name=f"Team {opponent_team} Captain")
                opponent_captain = opponent_role.members[0] if opponent_role and opponent_role.members else None

                if opponent_captain:
                    embed = discord.Embed(title="Proposed Match Scores", description=f"**{self.match['team1']}** vs **{self.match['team2']}** on {self.match['date']}")
                    for i, s in enumerate(self.map_scores, 1):
                        embed.add_field(name=f"Map {i} ({s['gamemode']})", value=f"{self.match['team1']} {s['team1_score']} - {s['team2_score']} {self.match['team2']}", inline=False)

                    await opponent_captain.send(embed=embed, view=ConfirmScoreView(self.parent, self.match, self.map_scores, interaction.user))
                else:
                    await interaction.followup.send("❗ Could not find opponent captain.", ephemeral=True)

            @discord.ui.button(label="Add Next Map", style=discord.ButtonStyle.blurple, row=1)
            async def next_map(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.map_number >= 3:
                    await interaction.response.send_message("❗ You can only add up to 3 maps.", ephemeral=True)
                    return

                await interaction.response.send_modal(MapScoreModal(self.parent, self.match, self.map_scores, self.map_number + 1))

            @discord.ui.button(label="Add Map Score", style=discord.ButtonStyle.green)
            async def map_score_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_modal(MapScoreModal(self.parent, self.match, self.map_scores, self.map_number))

        # Step 3: Enter gamemode and scores for map
        class MapScoreModal(discord.ui.Modal, title="Enter Map Score"):
            gamemode = discord.ui.TextInput(label="Gamemode", required=True)
            team1_score = discord.ui.TextInput(label="Team 1 Score", required=True)
            team2_score = discord.ui.TextInput(label="Team 2 Score", required=True)

            def __init__(self, parent, match, map_scores, map_number):
                super().__init__()
                self.parent = parent
                self.match = match
                self.map_scores = map_scores
                self.map_number = map_number

            async def on_submit(self, interaction: discord.Interaction):
                self.map_scores.append({
                    "gamemode": self.gamemode.value,
                    "team1_score": self.team1_score.value,
                    "team2_score": self.team2_score.value
                })
                await interaction.response.send_message(f"✅ Map {self.map_number} score saved.", view=MapScoreView(self.parent, self.match, self.map_scores, self.map_number), ephemeral=True)

        # Step 4: Confirmation view for opponent
        class ConfirmScoreView(discord.ui.View):
            def __init__(self, parent, match, map_scores, proposer):
                super().__init__(timeout=600)
                self.parent = parent
                self.match = match
                self.map_scores = map_scores
                self.proposer = proposer

            @discord.ui.button(label="✅ Accept Scores", style=discord.ButtonStyle.green)
            async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                for m in self.map_scores:
                    self.parent.scoring_sheet.append_row([
                        self.match["team1"],
                        self.match["team2"],
                        m["gamemode"],
                        m["team1_score"],
                        m["team2_score"],
                        "TBD"  # Winner could be calculated
                    ])

                await interaction.response.send_message("✅ Scores accepted and saved.", ephemeral=True)
                await self.proposer.send("Your proposed match scores have been accepted and finalized.")

            @discord.ui.button(label="❌ Deny Scores", style=discord.ButtonStyle.red)
            async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("❌ Scores denied.", ephemeral=True)
                await self.proposer.send("Your proposed match scores were denied by the opponent captain.")

        await interaction.response.send_message("Select your match to propose score:", view=MatchSelectView(self, matches), ephemeral=True)

    # -------------------- JOIN TEAM --------------------

    @discord.ui.button(label="👥 Join Team", style=discord.ButtonStyle.blurple)
    async def join_team(self, interaction: discord.Interaction, button: discord.ui.Button):

        class JoinTeamView(View):
            def __init__(self, parent, teams):
                super().__init__(timeout=300)
                self.parent = parent
                self.teams = teams
                self.selected_team = None

                options = [discord.SelectOption(label=team, value=team) for team in self.teams]
                self.team_select = discord.ui.Select(placeholder="Select Team to Join", options=options)
                self.team_select.callback = self.select_team
                self.add_item(self.team_select)

                self.join_button = discord.ui.Button(label="✅ Join Selected Team", style=discord.ButtonStyle.green)
                self.join_button.callback = self.join_team_confirm
                self.add_item(self.join_button)

            async def select_team(self, interaction):
                self.selected_team = self.team_select.values[0]
                await interaction.response.defer()

            async def join_team_confirm(self, interaction):
                if not self.selected_team:
                    await interaction.response.send_message("Please select a team first.", ephemeral=True)
                    return

                team_role = discord.utils.get(interaction.guild.roles, name=f"Team {self.selected_team}")
                if team_role:
                    await interaction.user.add_roles(team_role)
                    await interaction.response.send_message(f"✅ You joined **{self.selected_team}**.", ephemeral=True)
                else:
                    await interaction.response.send_message("Team role does not exist.", ephemeral=True)

        teams = [row[0] for row in self.teams_sheet.get_all_values() if row[0]]
        await interaction.response.send_message("Join a team:", view=JoinTeamView(self, teams), ephemeral=True)

    # -------------------- LEAVE TEAM --------------------

    @discord.ui.button(label="🚪 Leave Team", style=discord.ButtonStyle.red)
    async def leave_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        username_id = f"{interaction.user.display_name} ({interaction.user.id})"

        for idx, team in enumerate(self.teams_sheet.get_all_values(), 1):
            if username_id in team:
                team_name = team[0]

                if username_id == team[1]:
                    await interaction.response.send_message("❗ You are the captain. Promote or disband first.", ephemeral=True)
                    return

                self.teams_sheet.update_cell(idx, team.index(username_id) + 1, "")
                team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_name}")

                if team_role:
                    await interaction.user.remove_roles(team_role)

                await interaction.response.send_message(f"✅ You left **{team_name}**.", ephemeral=True)
                await self.send_notification(f"🚪 {interaction.user.mention} has left **{team_name}**.")
                return

        await interaction.response.send_message("You are not on a team.", ephemeral=True)

    # -------------------- UNSIGNUP --------------------

    @discord.ui.button(label="❌ Unsignup", style=discord.ButtonStyle.red)
    async def unsignup(self, interaction: discord.Interaction, button: discord.ui.Button):
        username_id = f"{interaction.user.display_name} ({interaction.user.id})"

        for idx, row in enumerate(self.players_sheet.get_all_values(), 1):
            if row[0] == username_id:
                self.players_sheet.delete_rows(idx)
                await interaction.response.send_message("✅ You have been removed from the league.", ephemeral=True)
                await self.send_notification(f"❌ {interaction.user.mention} has left the league.")
                return

        await interaction.response.send_message("You are not signed up.", ephemeral=True)

    # -------------------- DISBAND TEAM --------------------

    @discord.ui.button(label="❗ Disband Team", style=discord.ButtonStyle.red)
    async def disband_team(self, interaction: discord.Interaction, button: discord.ui.Button):

        class DisbandModal(Modal, title="Disband Team"):
            team_name = TextInput(label="Team Name")

            def __init__(self, parent_view):
                super().__init__()
                self.parent_view = parent_view

            async def on_submit(self, modal_interaction: discord.Interaction):
                team_name = self.team_name.value

                for idx, team in enumerate(self.parent_view.teams_sheet.get_all_values(), 1):
                    if team[0].lower() == team_name.lower():
                        captain_id = extract_user_id(team[1])

                        if str(modal_interaction.user.id) != str(captain_id) and str(modal_interaction.user.id) not in self.parent_view.DEV_OVERRIDE_IDS:
                            await modal_interaction.response.send_message("❗ Only the captain or a developer can disband this team.", ephemeral=True)
                            return

                        team_role = discord.utils.get(modal_interaction.guild.roles, name=f"Team {team_name}")
                        captain_role = discord.utils.get(modal_interaction.guild.roles, name=f"Team {team_name} Captain")

                        if team_role:
                            await team_role.delete()
                        if captain_role:
                            await captain_role.delete()

                        self.parent_view.teams_sheet.delete_rows(idx)
                        await modal_interaction.response.send_message("✅ Team disbanded successfully.", ephemeral=True)
                        await self.parent_view.send_notification(f"💥 **{team_name}** has been disbanded.")
                        return

                await modal_interaction.response.send_message("Team not found.", ephemeral=True)

        modal = DisbandModal(self)
        await interaction.response.send_modal(modal)








