import discord
from discord import app_commands
from discord.ui import Button, View, Select, Modal, TextInput
import asyncio
import json

def setup_dev_module(bot, spreadsheet, dev_ids):

    @bot.event
    async def on_ready():
        bot.add_view(DevPanel(bot, spreadsheet, dev_ids))
        print("✅ DevPanel loaded!")

# -------------------- Sheet Helper --------------------

def get_or_create_sheet(spreadsheet, name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except Exception:
        sheet = spreadsheet.add_worksheet(title=name, rows="100", cols=str(len(headers)))
        sheet.append_row(headers)
    return sheet

# -------------------- Dev Panel --------------------

class DevPanel(View):
    def __init__(self, bot, spreadsheet, dev_ids):
        super().__init__(timeout=None)
        self.bot = bot
        self.spreadsheet = spreadsheet
        self.dev_ids = dev_ids

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not any(role.id in allowed_role_ids for role in interaction.user.roles):
            await interaction.response.send_message("❗ You do not have permission to use this.", ephemeral=True)
            return False
        return True

    # 📥 Force Weekly Matchups
    @discord.ui.button(label="📥 Force Weekly Matchups", style=discord.ButtonStyle.red)
    async def force_matchups(self, interaction: discord.Interaction, button: discord.ui.Button):

        class WeekModal(Modal, title="Force Weekly Matchups"):
            week_number = TextInput(label="Week Number", required=True)

            def __init__(self, parent_view):
                super().__init__()
                self.parent_view = parent_view

            async def on_submit(self, modal_interaction: discord.Interaction):
                week_num = int(self.week_number.value)

                await modal_interaction.response.send_message(f"✅ Forcing weekly matchups for Week {week_num}...", ephemeral=True)

                import match  # import here or put on top of file
                await match.generate_weekly_matches(modal_interaction, self.parent_view.spreadsheet, week_num, force=True)

        await interaction.response.send_modal(WeekModal(self))

        # 📢 Announce scheduled matchups
    @discord.ui.button(label="📢 Announce Unscheduled Matches", style=discord.ButtonStyle.green)
    async def announce_unscheduled(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        import json

        # Load config to get match_channel_id
        with open("config.json") as f:
            config = json.load(f)

        channel_id = config.get("match_channel_id")
        if not channel_id:
            await interaction.followup.send("❗ match_channel_id not found in config.json.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(int(channel_id))
        if not channel:
            await interaction.followup.send("❗ Could not find the match channel.", ephemeral=True)
            return

        matches_sheet = get_or_create_sheet(self.spreadsheet, "Matches", ["Match ID", "Team A", "Team B", "Proposed Date", "Scheduled Date", "Status", "Winner", "Loser", "Proposed By"])
        teams_sheet = get_or_create_sheet(self.spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])

        unscheduled = []
        for row in matches_sheet.get_all_values()[1:]:
            if row[4] in ["", "TBD"] and row[5] not in ["Finished", "Cancelled", "Forfeited"]:
                unscheduled.append((row[1], row[2]))

        if not unscheduled:
            await interaction.followup.send("✅ No unscheduled matches found.", ephemeral=True)
            return

        for team_a, team_b in unscheduled:

            def get_team_mentions(team_name):
                team_row = next((row for row in teams_sheet.get_all_values() if row[0] == team_name), None)
                if not team_row:
                    return team_name

                mentions = []
                for player in team_row[1:]:
                    if "(" in player and ")" in player:
                        user_id = player.split("(")[-1].split(")")[0]
                        mentions.append(f"<@{user_id}>")
                    elif player.strip():
                        mentions.append(player)
                return " ".join(mentions) if mentions else team_name

            team_a_mentions = get_team_mentions(team_a)
            team_b_mentions = get_team_mentions(team_b)

            # Load config
        with open("config.json") as f:
            config_data = json.load(f)

        TEAM_PING_MODE = config_data.get("team_ping_mode", "all").lower()

        def get_team_mentions(team_name):
            team_row = next((row for row in teams_sheet.get_all_values() if row[0] == team_name), None)
            if not team_row:
                return team_name

            captain_player = team_row[1]
            players = [p for p in team_row[1:] if p.strip()]

            mentions = []

            if TEAM_PING_MODE == "captain":
                # Only ping captain
                if "(" in captain_player and ")" in captain_player:
                    user_id = captain_player.split("(")[-1].split(")")[0]
                    mentions.append(f"<@{user_id}>")
                elif captain_player:
                    mentions.append(captain_player)

            elif TEAM_PING_MODE == "role":
                # Ping team role only (assuming role exists named exactly Team {team_name})
                mentions.append(f"@Team {team_name}")

            elif TEAM_PING_MODE == "all":
                # Ping all players
                for player in players:
                    if "(" in player and ")" in player:
                        user_id = player.split("(")[-1].split(")")[0]
                        mentions.append(f"<@{user_id}>")
                    elif player.strip():
                        mentions.append(player)

            return " ".join(mentions) if mentions else team_name

        # Send normal text message with pings
        message = f"📢 **Unscheduled Match Alert!**\n\n" \
                f"**{team_a}** vs **{team_b}**\n\n" \
                f"**{team_a} Members:** {team_a_mentions}\n" \
                f"**{team_b} Members:** {team_b_mentions}\n\n" \
                f"Please coordinate and schedule this match as soon as possible."

        await channel.send(message)

        await interaction.followup.send("✅ Announced all unscheduled matches.", ephemeral=True)

    # ❌ Clear Proposed Match
    @discord.ui.button(label="❌ Clear Proposed Match", style=discord.ButtonStyle.primary)
    async def clear_proposed_match(self, interaction: discord.Interaction, button: discord.ui.Button):

        class ProposedMatchSearchModal(Modal, title="Search Proposed Match"):
            search = TextInput(label="Search Team Name (partial allowed)", required=True)

            def __init__(self, parent, proposed_sheet):
                super().__init__()
                self.parent = parent
                self.proposed_sheet = proposed_sheet

            async def on_submit(self, modal_interaction: discord.Interaction):
                query = self.search.value.lower()
                proposed = self.proposed_sheet.get_all_values()[1:]
                options = []

                for idx, row in enumerate(proposed):
                    if query in row[0].lower() or query in row[1].lower():
                        label = f"{row[0]} vs {row[1]} (Proposed Date: {row[3]})"
                        options.append(discord.SelectOption(label=label, value=str(idx)))

                if not options:
                    await modal_interaction.response.send_message("❗ No matches found.", ephemeral=True)
                    return

                class SelectToDeleteView(View):
                    @discord.ui.select(placeholder="Select a proposed match to delete", options=options)
                    async def select_delete(self, select_interaction: discord.Interaction, select: discord.ui.Select):
                        index = int(select.values[0])
                        self.proposed_sheet.delete_rows(index + 2)
                        await select_interaction.response.send_message("✅ Proposed match deleted.", ephemeral=True)

                await modal_interaction.response.send_message("Select proposed match to delete:", view=SelectToDeleteView(), ephemeral=True)

        modal = ProposedMatchSearchModal(self, get_or_create_sheet(self.spreadsheet, "Match Proposed", ["Team A", "Team B", "Proposer ID", "Proposed Date"]))
        await interaction.response.send_modal(modal)

    # ❌ Clear Proposed Score
    @discord.ui.button(label="❌ Clear Proposed Score", style=discord.ButtonStyle.blurple)
    async def clear_proposed_score(self, interaction: discord.Interaction, button: discord.ui.Button):

        class ProposedScoreSearchModal(Modal, title="Search Proposed Score"):
            search = TextInput(label="Search Team Name (partial allowed)", required=True)

            def __init__(self, parent, scoring_sheet):
                super().__init__()
                self.parent = parent
                self.scoring_sheet = scoring_sheet

            async def on_submit(self, modal_interaction: discord.Interaction):
                query = self.search.value.lower()
                scores = self.scoring_sheet.get_all_values()[1:]
                options = []

                for idx, row in enumerate(scores):
                    if query in row[0].lower() or query in row[1].lower():
                        label = f"{row[0]} vs {row[1]} (Mode: {row[3]})"
                        options.append(discord.SelectOption(label=label, value=str(idx)))

                if not options:
                    await modal_interaction.response.send_message("❗ No scores found.", ephemeral=True)
                    return

                class SelectToDeleteView(View):
                    @discord.ui.select(placeholder="Select a proposed score to delete", options=options)
                    async def select_delete(self, select_interaction: discord.Interaction, select: discord.ui.Select):
                        index = int(select.values[0])
                        self.scoring_sheet.delete_rows(index + 2)
                        await select_interaction.response.send_message("✅ Proposed score deleted.", ephemeral=True)

                await modal_interaction.response.send_message("Select proposed score to delete:", view=SelectToDeleteView(), ephemeral=True)

        modal = ProposedScoreSearchModal(self, get_or_create_sheet(self.spreadsheet, "Scoring", ["Team A", "Team B", "Map #", "Game Mode", "Team A Score", "Team B Score", "Winner"]))
        await interaction.response.send_modal(modal)  # ✅ Valid because no defer above

    # ♻️ Reload Views
    @discord.ui.button(label="♻️ Reload Views", style=discord.ButtonStyle.green)
    async def reload_views(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        await interaction.followup.send("✅ Views reloaded and commands synced.", ephemeral=True)

        # 🚫 Kick Player
    @discord.ui.button(label="🚫 Kick Player", style=discord.ButtonStyle.danger)
    async def kick_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        class KickPlayerModal(Modal, title="Kick Player from League"):
            user_id = TextInput(label="Enter User ID to Kick", required=True)

            def __init__(self, parent):
                super().__init__()
                self.parent = parent

            async def on_submit(self, modal_interaction: discord.Interaction):
                players_sheet = get_or_create_sheet(self.parent.spreadsheet, "Players", ["User ID", "Username"])
                teams_sheet = get_or_create_sheet(self.parent.spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])
                user_id_input = self.user_id.value.strip()

                values = players_sheet.get_all_values()
                found = False
                username = None

                for idx, row in enumerate(values[1:], start=2):
                    if user_id_input in row[0] or user_id_input in row[1]:
                        username = row[1]
                        players_sheet.delete_rows(idx)
                        found = True
                        break

                if not found:
                    await modal_interaction.response.send_message("❗ Player not found in Players sheet.", ephemeral=True)
                    return

                team_values = teams_sheet.get_all_values()
                for row_idx, row in enumerate(team_values[1:], start=2):
                    for col_idx in range(1, len(row)):
                        if user_id_input in row[col_idx] or (username and username == row[col_idx]):
                            
                            # If captain (col_idx == 1), promote player 2
                            if col_idx == 1:
                                player_2 = row[2]
                                if player_2.strip():
                                    teams_sheet.update_cell(row_idx, 2, player_2)  # Promote to captain
                                    teams_sheet.update_cell(row_idx, 3, "")       # Clear Player 2 slot
                                else:
                                    teams_sheet.update_cell(row_idx, 2, "")  # No player 2, leave captain blank
                            else:
                                teams_sheet.update_cell(row_idx, col_idx + 1, "")

                await modal_interaction.response.send_message(f"✅ Player `{username}` has been kicked and removed from all teams.", ephemeral=True)

        await interaction.response.send_modal(KickPlayerModal(self))

    # 🚫 Ban Player
    @discord.ui.button(label="🚫 Ban Player", style=discord.ButtonStyle.red)
    async def ban_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        class BanPlayerModal(Modal, title="Ban Player from League"):
            user_id = TextInput(label="Enter User ID to Ban", required=True)

            def __init__(self, parent):
                super().__init__()
                self.parent = parent

            async def on_submit(self, modal_interaction: discord.Interaction):
                players_sheet = get_or_create_sheet(self.parent.spreadsheet, "Players", ["User ID", "Username"])
                banned_sheet = get_or_create_sheet(self.parent.spreadsheet, "Banned", ["User ID", "Username"])
                teams_sheet = get_or_create_sheet(self.parent.spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])

                user_id_input = self.user_id.value.strip()

                values = players_sheet.get_all_values()
                found = False
                username = None

                for idx, row in enumerate(values[1:], start=2):
                    if user_id_input in row[0] or user_id_input in row[1]:
                        username = row[1]
                        banned_sheet.append_row(row)
                        players_sheet.delete_rows(idx)
                        found = True
                        break

                if not found:
                    await modal_interaction.response.send_message("❗ Player not found in Players sheet.", ephemeral=True)
                    return

                team_values = teams_sheet.get_all_values()
                for row_idx, row in enumerate(team_values[1:], start=2):
                    for col_idx in range(1, len(row)):
                        if user_id_input in row[col_idx] or (username and username == row[col_idx]):

                            # If captain (col_idx == 1), promote player 2
                            if col_idx == 1:
                                player_2 = row[2]
                                if player_2.strip():
                                    teams_sheet.update_cell(row_idx, 2, player_2)  # Promote to captain
                                    teams_sheet.update_cell(row_idx, 3, "")       # Clear Player 2 slot
                                else:
                                    teams_sheet.update_cell(row_idx, 2, "")  # No player 2, leave captain blank
                            else:
                                teams_sheet.update_cell(row_idx, col_idx + 1, "")

                await modal_interaction.response.send_message(f"✅ Player `{username}` has been banned, removed from all teams, and added to Banned list.", ephemeral=True)

        await interaction.response.send_modal(BanPlayerModal(self))

    # 🔒 Lock All Rosters
    @discord.ui.button(label="🔒 Lock All Rosters", style=discord.ButtonStyle.red)
    async def lock_rosters(self, interaction: discord.Interaction, button: discord.ui.Button):
        rosters_sheet = get_or_create_sheet(self.spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])
        values = rosters_sheet.get_all_values()

        if values and values[0][-1] != "Locked":
            rosters_sheet.resize(rows=len(values), cols=len(values[0]) + 1)
            rosters_sheet.update_cell(1, len(values[0]) + 1, "Locked")

        for idx in range(2, len(values) + 1):
            rosters_sheet.update_cell(idx, len(values[0]) + 1, "Yes")

        await interaction.response.send_message("✅ All rosters have been locked.", ephemeral=True)

    # 🔓 Unlock All Rosters
    @discord.ui.button(label="🔓 Unlock All Rosters", style=discord.ButtonStyle.green)
    async def unlock_rosters(self, interaction: discord.Interaction, button: discord.ui.Button):
        rosters_sheet = get_or_create_sheet(self.spreadsheet, "Teams", ["Team Name", "Captain", "Player 2", "Player 3", "Player 4", "Player 5", "Player 6"])
        values = rosters_sheet.get_all_values()

        if values and values[0][-1] == "Locked":
            for idx in range(2, len(values) + 1):
                rosters_sheet.update_cell(idx, len(values[0]), "")
            await interaction.response.send_message("✅ All rosters have been unlocked.", ephemeral=True)
        else:
            await interaction.response.send_message("❗ Rosters are not locked.", ephemeral=True)

# -------------------- Dev Panel Poster --------------------

async def post_dev_panel(bot, spreadsheet, dev_ids):
    channel_id = bot.config.get("dev_channel_id")
    if not channel_id:
        print("No dev_channel_id in config.")
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        print("Dev channel not found.")
        return

    # ✅ Delete old dev panels first
    try:
        async for msg in channel.history(limit=50):
            if msg.author == bot.user and msg.embeds:
                if msg.embeds[0].title == "🛠️ Developer Panel":
                    await msg.delete()
                    print("Deleted old Developer Panel.")
    except Exception as e:
        print(f"Failed to delete old Developer Panel: {e}")

        # ✅ Post new Dev panel
    embed = discord.Embed(title="🛠️ Developer Panel", description="Developer & Admin Tools", color=discord.Color.red())
    embed.add_field(name="📥 Force Weekly Matchups", value="Force generate weekly matches (Forfeits any unfinished).", inline=False)
    embed.add_field(name="📢 Announce Unscheduled Matches", value="Announce matches that are not yet scheduled.", inline=False)
    embed.add_field(name="❌ Clear Proposed Match", value="Remove proposed match requests.", inline=False)
    embed.add_field(name="❌ Clear Proposed Score", value="Remove proposed score requests.", inline=False)
    embed.add_field(name="🚫 Kick Player", value="Kick a player from league and remove them from any team they are in.", inline=False)
    embed.add_field(name="🚫 Ban Player", value="Ban a player from league and remove them from all teams, adding to banned list.", inline=False)
    embed.add_field(name="♻️ Reload Views", value="Reload bot views and slash commands.", inline=False)
    embed.add_field(name="🔒 Lock All Rosters", value="Lock all rosters (disable player joins).", inline=False)
    embed.add_field(name="🔓 Unlock All Rosters", value="Unlock rosters (allow player joins).", inline=False)

    await channel.send(embed=embed, view=DevPanel(bot, spreadsheet, dev_ids))
    print("Posted new Developer Panel!")





