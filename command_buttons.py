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

    @discord.ui.button(label="✅ Player Signup", style=discord.ButtonStyle.blurple)
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
        user_id = f"{interaction.user.display_name} ({interaction.user.id})"

        # Check if user is already on a team
        for team in self.teams_sheet.get_all_values():
            if user_id in team:
                await interaction.response.send_message("❗ You are already on a team. Leave your team first.", ephemeral=True)
                return

        class TeamNameModal(discord.ui.Modal, title="Create Team"):
            team_name = discord.ui.TextInput(label="Team Name", required=True)

            def __init__(self, parent_view):
                super().__init__()
                self.parent = parent_view

            async def on_submit(self, modal_interaction: discord.Interaction):
                team_name = self.team_name.value.strip()

                # Check for duplicate team names
                existing_teams = [row[0].lower() for row in self.parent.teams_sheet.get_all_values()]
                if team_name.lower() in existing_teams:
                    await modal_interaction.response.send_message("❗ Team already exists.", ephemeral=True)
                    return

                guild = modal_interaction.guild

                # Create team roles
                team_role = await guild.create_role(name=f"Team {team_name}")
                captain_role = await guild.create_role(name=f"Team {team_name} Captain")

                # Assign roles to captain
                await modal_interaction.user.add_roles(team_role, captain_role)

                # Add team to sheet with captain only
                self.parent.teams_sheet.append_row([team_name, f"{modal_interaction.user.display_name} ({modal_interaction.user.id})"] + [""] * 5)

                await modal_interaction.response.send_message(f"✅ Team **{team_name}** created! Invite players to join your team.", ephemeral=True)
                await self.parent.send_notification(f"🎉 **Team Created:** `{team_name}` by {modal_interaction.user.mention}")

        await interaction.response.send_modal(TeamNameModal(self))

    # -------------------- PROPOSE MATCH --------------------

    @discord.ui.button(label="📅 Propose Match", style=discord.ButtonStyle.blurple)
    async def propose_match(self, interaction: discord.Interaction, button: discord.ui.Button):

        async def create_private_channel(guild, category_id, channel_name, members):
            category = discord.utils.get(guild.categories, id=category_id)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            for member in members:
                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            return channel

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
                self.parent.proposed_sheet.append_row([self.selected_team, self.opponent_team, str(interaction.user.id), proposed_date])

                guild = interaction.guild
                opponent_role = discord.utils.get(guild.roles, name=f"Team {self.opponent_team}")

                if opponent_role and opponent_role.members:
                    captain = opponent_role.members[0]
                    try:
                        await captain.send(f"📨 Proposed Match from **{self.selected_team}** on `{proposed_date}`. Accept?",
                                        view=AcceptDenyMatchView(self.parent, self.selected_team, self.opponent_team, proposed_date))
                    except discord.Forbidden:
                        # Fallback to private channel
                        category_id = self.parent.config.get("matchups_category_id")
                        channel = await create_private_channel(guild, int(category_id),
                                                            f"proposed-match-{self.selected_team}-vs-{self.opponent_team}",
                                                            [interaction.user, captain])
                        await channel.send(f"{captain.mention} 📨 Proposed Match from **{self.selected_team}** on `{proposed_date}`. Accept?",
                                        view=AcceptDenyMatchView(self.parent, self.selected_team, self.opponent_team, proposed_date))

                await interaction.response.send_message(f"✅ Proposed match sent to {self.opponent_team}!", ephemeral=True)

        teams = [row[0] for row in self.teams_sheet.get_all_values() if row[0]]
        await interaction.response.send_message("Propose a match:", view=ProposeMatchView(self, teams), ephemeral=True)

    # -------------------- PROPOSE SCORE --------------------

    @discord.ui.button(label="🏆 Propose Score", style=discord.ButtonStyle.blurple)
    async def propose_score(self, interaction: discord.Interaction, button: discord.ui.Button):

        async def create_private_channel(guild, category_id, channel_name, members):
            category = discord.utils.get(guild.categories, id=category_id)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            for member in members:
                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            return channel

        scheduled_matches = self.scheduled_sheet.get_all_values()[1:]
        user_id = str(interaction.user.id)

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

                opponent_team = self.match["team2"] if interaction.user in [m for m in discord.utils.get(interaction.guild.roles, name=f"Team {self.match['team1']} Captain").members] else self.match["team1"]
                opponent_role = discord.utils.get(interaction.guild.roles, name=f"Team {opponent_team} Captain")
                opponent_captain = opponent_role.members[0] if opponent_role and opponent_role.members else None

                embed = discord.Embed(title="Proposed Match Scores", description=f"**{self.match['team1']}** vs **{self.match['team2']}** on {self.match['date']}")
                for i, s in enumerate(self.map_scores, 1):
                    embed.add_field(name=f"Map {i} ({s['gamemode']})", value=f"{self.match['team1']} {s['team1_score']} - {s['team2_score']} {self.match['team2']}", inline=False)

                if opponent_captain:
                    try:
                        await opponent_captain.send(embed=embed, view=ConfirmScoreView(self.parent, self.match, self.map_scores, interaction.user))
                    except discord.Forbidden:
                        category_id = self.parent.config.get("matchups_category_id")
                        private_channel = await create_private_channel(interaction.guild, int(category_id),
                                                                    f"proposed-score-{self.match['team1']}-vs-{self.match['team2']}",
                                                                    [interaction.user, opponent_captain])

                        await private_channel.send(f"{opponent_captain.mention} 📥 Proposed Scores:", embed=embed, view=ConfirmScoreView(self.parent, self.match, self.map_scores, interaction.user))
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
                        "TBD"
                    ])

                await interaction.response.send_message("✅ Scores accepted and saved.", ephemeral=True)
                await self.proposer.send("✅ Your proposed match scores have been accepted and finalized.")

            @discord.ui.button(label="❌ Deny Scores", style=discord.ButtonStyle.red)
            async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("❌ Scores denied.", ephemeral=True)
                await self.proposer.send("❌ Your proposed match scores were denied by the opponent captain.")

        await interaction.response.send_message("Select your match to propose score:", view=MatchSelectView(self, matches), ephemeral=True)

    # -------------------- JOIN TEAM --------------------

    @discord.ui.button(label="👥 Join Team", style=discord.ButtonStyle.blurple)
    async def join_team(self, interaction: discord.Interaction, button: discord.ui.Button):

        class TeamSearchModal(discord.ui.Modal, title="Search Team Name"):
            query = discord.ui.TextInput(label="Enter Team Name", required=True)

            def __init__(self, parent_view):
                super().__init__()
                self.parent_view = parent_view

            async def on_submit(self, interaction: discord.Interaction):
                search = self.query.value.lower()
                all_teams = [row[0] for row in self.parent_view.teams_sheet.get_all_values() if row[0]]

                matches = [team for team in all_teams if search in team.lower()]
                if not matches:
                    matches = all_teams[:25]

                view = TeamSelectView(self.parent_view, matches, interaction.user)
                await interaction.response.send_message("Select the team you want to join:", view=view, ephemeral=True)

        class TeamSelectView(discord.ui.View):
            def __init__(self, parent_view, teams, user):
                super().__init__(timeout=300)
                self.parent_view = parent_view
                self.teams = teams
                self.user = user

                options = [discord.SelectOption(label=team, value=team) for team in self.teams]
                select = discord.ui.Select(placeholder="Select Team", options=options)
                select.callback = self.select_team
                self.add_item(select)

            async def select_team(self, interaction: discord.Interaction):
                selected_team = self.children[0].values[0]

                for row in self.parent_view.teams_sheet.get_all_values():
                    for cell in row[1:7]:
                        if cell.strip() == f"{self.user.display_name} ({self.user.id})":
                            await interaction.response.send_message("❗ You are already on a team.", ephemeral=True)
                            return

                guild = interaction.guild
                team_role = discord.utils.get(guild.roles, name=f"Team {selected_team}")

                if not team_role:
                    await interaction.response.send_message("❗ Team role does not exist.", ephemeral=True)
                    return

                captain = None
                for member in team_role.members:
                    cap_role = discord.utils.get(guild.roles, name=f"Team {selected_team} Captain")
                    if cap_role and cap_role in member.roles:
                        captain = member
                        break

                if not captain:
                    await interaction.response.send_message("❗ Could not find team captain.", ephemeral=True)
                    return

                try:
                    await captain.send(
                        f"📥 **{self.user.display_name}** wants to join **{selected_team}**. Approve?",
                        view=AcceptDenyJoinRequestView(self.parent_view, selected_team, self.user, guild.id)
                    )
                    await interaction.response.send_message("✅ Request sent to team captain via DM.", ephemeral=True)

                except discord.Forbidden:
                    fallback_channel = discord.utils.get(guild.text_channels, name="team-requests")
                    if fallback_channel is None:
                        overwrites = {
                            guild.default_role: discord.PermissionOverwrite(read_messages=False),
                            captain: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        }
                        fallback_channel = await guild.create_text_channel("team-requests", overwrites=overwrites)
                    else:
                        await fallback_channel.set_permissions(captain, read_messages=True, send_messages=True)

                    await fallback_channel.send(
                        f"📥 {captain.mention} **{self.user.display_name}** wants to join **{selected_team}**. Approve?",
                        view=AcceptDenyJoinRequestView(self.parent_view, selected_team, self.user, guild.id)
                    )
                    await interaction.response.send_message("✅ Captain's DMs closed, sent request to private channel.", ephemeral=True)

                    async def auto_delete(channel):
                        await discord.utils.sleep_until(discord.utils.utcnow() + discord.timedelta(minutes=5))
                        if len([m async for m in channel.history(limit=1)]) > 0:
                            await channel.delete()

                    self.parent_view.bot.loop.create_task(auto_delete(fallback_channel))

        class AcceptDenyJoinRequestView(discord.ui.View):
            def __init__(self, parent_view, team_name, invitee, guild_id):
                super().__init__(timeout=300)
                self.parent_view = parent_view
                self.team_name = team_name
                self.invitee = invitee
                self.guild_id = guild_id

            @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
            async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                guild = self.parent_view.bot.get_guild(self.guild_id)
                team_role = discord.utils.get(guild.roles, name=f"Team {self.team_name}")

                if not team_role:
                    await interaction.response.send_message("❗ Team role no longer exists.", ephemeral=True)
                    return

                already_on_team = False
                for row in self.parent_view.teams_sheet.get_all_values():
                    for cell in row[1:7]:
                        if cell.strip() == f"{self.invitee.display_name} ({self.invitee.id})":
                            already_on_team = True
                            break
                    if already_on_team:
                        break

                if already_on_team:
                    await interaction.response.send_message("❗ Player is already on another team.", ephemeral=True)
                    return

                await self.invitee.add_roles(team_role)

                for idx, row in enumerate(self.parent_view.teams_sheet.get_all_values(), 1):
                    if row[0].lower() == self.team_name.lower():
                        for i in range(1, 7):
                            if row[i] == "":
                                self.parent_view.teams_sheet.update_cell(idx, i + 1, f"{self.invitee.display_name} ({self.invitee.id})")
                                break
                        break

                await interaction.response.send_message("✅ Player added to team.", ephemeral=True)

                await interaction.message.delete()

                if interaction.channel and interaction.channel.name == "team-requests":
                    await interaction.channel.delete()

            @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.danger)
            async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("❌ Request denied.", ephemeral=True)

                await interaction.message.delete()

                if interaction.channel and interaction.channel.name == "team-requests":
                    await interaction.channel.delete()

        await interaction.response.send_modal(TeamSearchModal(self))

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

        # Check if on a team first
        for team in self.teams_sheet.get_all_values():
            if username_id in team:
                await interaction.response.send_message("❗ You are currently on a team. Leave your team before unsigning.", ephemeral=True)
                return

        # Check if signed up
        for idx, row in enumerate(self.players_sheet.get_all_values(), 1):
            if row[0] == username_id:
                self.players_sheet.delete_rows(idx)
                await interaction.response.send_message("✅ You have been removed from the league.", ephemeral=True)
                await self.send_notification(f"❌ {interaction.user.mention} has left the league.")
                return

        await interaction.response.send_message("❗ You are not signed up.", ephemeral=True)

    # -------------------- PROMOTE PLAYER ------------------

    @discord.ui.button(label="⭐ Promote Player", style=discord.ButtonStyle.green)
    async def promote_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        username_id = f"{interaction.user.display_name} ({interaction.user.id})"

        # Find team and check if user is captain
        for idx, team in enumerate(self.teams_sheet.get_all_values(), 1):
            if team[1] == username_id:
                team_name = team[0]
                members = [player for player in team[1:] if player]

                # Build dropdown options (skip self / captain)
                options = [
                    discord.SelectOption(label=p.split(" (")[0], value=p)
                    for p in members if p != username_id
                ]

                if not options:
                    await interaction.response.send_message("❗ No players available to promote.", ephemeral=True)
                    return

                class PromoteSelect(discord.ui.View):
                    def __init__(self, parent, team_name, old_captain, team_idx):
                        super().__init__(timeout=300)
                        self.parent = parent
                        self.team_name = team_name
                        self.old_captain = old_captain
                        self.team_idx = team_idx

                        select = discord.ui.Select(placeholder="Select player to promote", options=options)
                        select.callback = self.promote
                        self.add_item(select)

                    async def promote(self, select_interaction):
                        new_captain_user_id = extract_user_id(select_interaction.data['values'][0])
                        guild = select_interaction.guild

                        old_captain_member = guild.get_member(int(extract_user_id(self.old_captain)))
                        new_captain_member = guild.get_member(int(new_captain_user_id))

                        captain_role = discord.utils.get(guild.roles, name=f"Team {self.team_name} Captain")
                        if captain_role:
                            await old_captain_member.remove_roles(captain_role)
                            await new_captain_member.add_roles(captain_role)

                        # Update sheet: move old captain to player spot and new captain to spot 2
                        row = self.parent.teams_sheet.row_values(self.team_idx)
                        new_row = [self.team_name, f"{new_captain_member.display_name} ({new_captain_member.id})"]
                        added = False

                        for val in row[1:]:
                            if val == self.old_captain:
                                continue
                            if not added and len(new_row) < 7:
                                new_row.append(self.old_captain)
                                added = True
                            if val and val != self.old_captain:
                                new_row.append(val)

                        while len(new_row) < 7:
                            new_row.append("")

                        self.parent.teams_sheet.update(f"A{self.team_idx}:G{self.team_idx}", [new_row])

                        await select_interaction.response.send_message(f"✅ {new_captain_member.mention} is now the captain of **{self.team_name}**!", ephemeral=True)
                        await self.parent.send_notification(f"⭐ {new_captain_member.mention} has been promoted to **Captain of {self.team_name}**.")

                await interaction.response.send_message("Select player to promote to captain:", view=PromoteSelect(self, team_name, username_id, idx), ephemeral=True)
                return

        await interaction.response.send_message("❗ You are not a captain or on a team.", ephemeral=True)

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








