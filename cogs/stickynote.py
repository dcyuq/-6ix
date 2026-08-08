import discord
from discord.ext import commands
import json
import os

# ==========================
# PERSISTENT STORAGE
# ==========================
# Notes are stored per-guild in a JSON file so they survive bot restarts.
# Structure on disk / in memory:
# {
#   "<guild_id>": {
#       "<trigger>": {"message": "...", "creator": "<mention>"},
#       ...
#   },
#   ...
# }

DATA_FILE = "stickynotes.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


sticky_notes = load_data()

# Which note is "bumping" in a given channel right now.
# Not persisted to disk on purpose - a restart just means bumping
# pauses in that channel until someone triggers a sticky note again.
# {channel_id: {"trigger": "<name>", "message_id": <int>}}
active_stickies = {}


def get_guild_notes(guild_id):
    gid = str(guild_id)
    if gid not in sticky_notes:
        sticky_notes[gid] = {}
    return sticky_notes[gid]


def normalize_name(name: str) -> str:
    return name.lower().strip().replace(",", "")


def can_manage(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or perms.manage_messages


# ==========================
# CREATE MODAL
# ==========================

class StickyCreateModal(discord.ui.Modal, title="Create Sticky Note"):

    call = discord.ui.TextInput(
        label="Call Prefix",
        placeholder="Example: rules",
        required=True,
        max_length=50
    )

    message = discord.ui.TextInput(
        label="Bot Message",
        placeholder="What should the bot say?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        notes = get_guild_notes(interaction.guild_id)
        name = normalize_name(self.call.value)

        if not name:
            await interaction.response.send_message(
                "That trigger isn't valid.", ephemeral=True
            )
            return

        if name in notes:
            await interaction.response.send_message(
                f"A sticky note called `{name}` already exists.",
                ephemeral=True
            )
            return

        notes[name] = {
            "message": self.message.value,
            "creator": interaction.user.mention
        }
        save_data(sticky_notes)

        await interaction.response.send_message(
            f"Sticky note `{name}` created.", ephemeral=True
        )


# ==========================
# EDIT MODAL
# ==========================

class StickyEditModal(discord.ui.Modal):

    def __init__(self, name: str):
        super().__init__(title=f"Edit '{name}'")
        self.original_name = name

        self.call = discord.ui.TextInput(
            label="Call Prefix",
            default=name,
            required=True,
            max_length=50
        )
        self.add_item(self.call)

        self.message = discord.ui.TextInput(
            label="Bot Message",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        notes = get_guild_notes(interaction.guild_id)

        if self.original_name not in notes:
            await interaction.response.send_message(
                "That sticky note no longer exists.", ephemeral=True
            )
            return

        new_name = normalize_name(self.call.value)
        if not new_name:
            await interaction.response.send_message(
                "That trigger isn't valid.", ephemeral=True
            )
            return

        if new_name != self.original_name and new_name in notes:
            await interaction.response.send_message(
                f"A sticky note called `{new_name}` already exists.",
                ephemeral=True
            )
            return

        data = notes.pop(self.original_name)
        data["message"] = self.message.value
        notes[new_name] = data
        save_data(sticky_notes)

        await interaction.response.send_message(
            f"Updated `{self.original_name}` → `{new_name}`.",
            ephemeral=True
        )


# ==========================
# VIEW DROPDOWN (browse notes)
# ==========================

class StickyViewSelect(discord.ui.Select):

    def __init__(self, guild_id):
        self.guild_id = guild_id
        notes = get_guild_notes(guild_id)

        options = [
            discord.SelectOption(label=note, value=note)
            for note in notes
        ][:25]

        super().__init__(
            placeholder="Select a sticky note to view",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        notes = get_guild_notes(self.guild_id)
        note = notes.get(self.values[0])

        if note is None:
            await interaction.response.edit_message(
                content="That sticky note no longer exists.",
                embed=None, view=None
            )
            return

        embed = discord.Embed(
            title=f"{self.values[0]}",
            description=note["message"],
            color=discord.Color.dark_theme()
        )
        embed.set_footer(text=f"Created by {note['creator']}")

        await interaction.response.edit_message(embed=embed, view=None)


class StickyViewSelectView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=120)
        self.add_item(StickyViewSelect(guild_id))


# ==========================
# EDIT DROPDOWN (pick note -> modal)
# ==========================

class StickyEditSelect(discord.ui.Select):

    def __init__(self, guild_id):
        self.guild_id = guild_id
        notes = get_guild_notes(guild_id)

        options = [
            discord.SelectOption(label=note, value=note)
            for note in notes
        ][:25]

        super().__init__(
            placeholder="Select a sticky note to edit",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        notes = get_guild_notes(self.guild_id)
        name = self.values[0]

        if name not in notes:
            await interaction.response.edit_message(
                content="That sticky note no longer exists.",
                embed=None, view=None
            )
            return

        modal = StickyEditModal(name)
        modal.message.default = notes[name]["message"]
        await interaction.response.send_modal(modal)


class StickyEditSelectView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=120)
        self.add_item(StickyEditSelect(guild_id))


# ==========================
# DELETE DROPDOWN
# ==========================

class StickyDeleteSelect(discord.ui.Select):

    def __init__(self, guild_id):
        self.guild_id = guild_id
        notes = get_guild_notes(guild_id)

        options = [
            discord.SelectOption(label=note, value=note)
            for note in notes
        ][:25]

        super().__init__(
            placeholder="Select a sticky note to delete",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        notes = get_guild_notes(self.guild_id)
        name = self.values[0]

        if name not in notes:
            await interaction.response.edit_message(
                content="That sticky note no longer exists.",
                embed=None, view=None
            )
            return

        del notes[name]
        save_data(sticky_notes)

        await interaction.response.edit_message(
            content=f"Deleted `{name}`.", embed=None, view=None
        )


class StickyDeleteSelectView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=120)
        self.add_item(StickyDeleteSelect(guild_id))


# ==========================
# MAIN PANEL (View / Create / Edit / Delete buttons)
# ==========================

class StickyPanelView(discord.ui.View):

    def __init__(self, guild_id):
        super().__init__(timeout=120)
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Re-check permissions on every click, in case roles changed after
        # the panel was posted (e.g. someone else's panel message).
        if not can_manage(interaction.user):
            await interaction.response.send_message(
                "You need Administrator or Manage Messages permission.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="View", style=discord.ButtonStyle.secondary)
    async def view_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        notes = get_guild_notes(self.guild_id)

        if not notes:
            await interaction.response.send_message(
                "No sticky notes created yet.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Sticky Notes",
            description=f"Total Notes: **{len(notes)}**\n\nSelect one below.",
            color=discord.Color.dark_theme()
        )
        await interaction.response.edit_message(
            embed=embed, view=StickyViewSelectView(self.guild_id)
        )

    @discord.ui.button(label="Create", style=discord.ButtonStyle.success)
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StickyCreateModal())

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        notes = get_guild_notes(self.guild_id)
        if not notes:
            await interaction.response.send_message(
                "No sticky notes to edit.", ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="Select a sticky note to edit:",
            embed=None,
            view=StickyEditSelectView(self.guild_id)
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        notes = get_guild_notes(self.guild_id)
        if not notes:
            await interaction.response.send_message(
                "No sticky notes to delete.", ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="Select a sticky note to delete:",
            embed=None,
            view=StickyDeleteSelectView(self.guild_id)
        )


# ==========================
# MAIN COG
# ==========================

class StickyNotes(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="stickynote", aliases=["sn"])
    @commands.guild_only()
    async def stickynote(self, ctx: commands.Context):
        if not can_manage(ctx.author):
            await ctx.send(
                "You need Administrator or Manage Messages permission to use this."
            )
            return

        notes = get_guild_notes(ctx.guild.id)

        embed = discord.Embed(
            title="Sticky Notes",
            description=(
                f"Total Notes: **{len(notes)}**\n\n"
                "**View** — browse existing sticky notes\n"
                "**Create** — add a new sticky note\n"
                "**Edit** — change a note's trigger or message\n"
                "**Delete** — remove a sticky note"
            ),
            color=discord.Color.dark_theme()
        )

        await ctx.send(embed=embed, view=StickyPanelView(ctx.guild.id))

    @commands.command(name="unsticky", aliases=["unsn"])
    @commands.guild_only()
    async def unsticky(self, ctx: commands.Context):
        if not can_manage(ctx.author):
            await ctx.send(
                "You need Administrator or Manage Messages permission to use this."
            )
            return

        if ctx.channel.id not in active_stickies:
            await ctx.send("There's no active sticky note in this channel.")
            return

        await self._clear_active(ctx.channel)
        await ctx.send("Sticky note removed from this channel.")

    # ==========================
    # STICKY NOTE TRIGGER
    # ==========================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        notes = get_guild_notes(message.guild.id)
        channel_id = message.channel.id

        # Is this message a ,(trigger) call that starts/replaces a sticky?
        if message.content.startswith(","):
            command = normalize_name(message.content[1:])

            if command in notes:
                if not can_manage(message.author):
                    return

                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass

                # A previous sticky may already be bumping in this channel -
                # clear it out before posting the new one.
                await self._clear_active(message.channel)

                sent = await message.channel.send(notes[command]["message"])
                active_stickies[channel_id] = {
                    "trigger": command,
                    "message_id": sent.id
                }
                return

        # Otherwise: if this channel has an active sticky, bump it -
        # delete the old sticky post and repost it at the bottom.
        active = active_stickies.get(channel_id)
        if active is None:
            return

        note = notes.get(active["trigger"])
        if note is None:
            # The note itself was deleted/renamed elsewhere - stop bumping.
            del active_stickies[channel_id]
            return

        old_message_id = active["message_id"]
        try:
            old_message = await message.channel.fetch_message(old_message_id)
            await old_message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        sent = await message.channel.send(note["message"])
        active_stickies[channel_id]["message_id"] = sent.id

    async def _clear_active(self, channel: discord.TextChannel):
        active = active_stickies.pop(channel.id, None)
        if active is None:
            return

        try:
            old_message = await channel.fetch_message(active["message_id"])
            await old_message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass


# ==========================
# SETUP
# ==========================

async def setup(bot):
    await bot.add_cog(StickyNotes(bot))