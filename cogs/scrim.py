import discord
from discord.ext import commands

class ScrimModal(discord.ui.Modal, title="Scrim Setup"):
    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    description = discord.ui.TextInput(
        label="Description",
        placeholder="e.g. cezu scrims!",
        style=discord.TextStyle.paragraph,
        required=True,
    )
    team_count = discord.ui.TextInput(
        label="Team count",
        placeholder="e.g. 4",
        required=True,
        max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.team_count.value)
        except ValueError:
            await interaction.response.send_message("Team count must be a number.", ephemeral=True)
            return

        if count < 1 or count > 20:
            await interaction.response.send_message("Team count must be between 1 and 20.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        await self.channel.send(
            self.description.value,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )

        for i in range(1, count + 1):
            team_message = await self.channel.send(f"``team {i}``")
            await team_message.create_thread(name=f"team {i}")

        await interaction.followup.send(
            f"Created {count} scrim thread(s) in {self.channel.mention}.", ephemeral=True
        )

class ScrimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.selected_channel = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Pick a channel for the scrim",
        min_values=1,
        max_values=1,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.selected_channel = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Create Scrim", style=discord.ButtonStyle.primary)
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_channel is None:
            await interaction.response.send_message("Pick a channel first.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.selected_channel.id)
        await interaction.response.send_modal(ScrimModal(channel))

class Scrims(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def scrim(self, ctx):
        await ctx.send(
            "To create a scrim, pick a channel and click the button below",
            view=ScrimView(),
        )

async def setup(bot):
    await bot.add_cog(Scrims(bot))