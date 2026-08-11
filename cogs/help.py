import discord
from discord.ext import commands

PREFIX = ","
ACCENT = discord.Color.dark_theme()

CATEGORY_META = {
    "Moderation": "Kick, ban and timeout members.",
    "Music": "Play audio in a voice channel.",
    "Scrims": "Generate scrim threads for team matches.",
    "StickyNotes": "Keep a message pinned to the bottom of a channel.",
    "AutoResponder": "Auto-reply to trigger words.",
    "GamePass": "Look up Roblox gamepass prices.",
    "Vanity": "Award a role for a keyword in someone's status.",
}

COMMAND_HELP = {
    "kick": "Remove a member from the server.",
    "ban": "Ban a member from the server.",
    "unban": "Lift a ban by user ID.",
    "timeout": "Mute a member for a number of minutes.",
    "untimeout": "End a member's timeout early.",
    "join": "Bring the bot into your voice channel.",
    "play": "Queue a track by search term or URL.",
    "skip": "Skip the current track.",
    "queue": "Show what's queued up.",
    "loop": "Toggle repeating the current track.",
    "pause": "Pause playback.",
    "resume": "Resume playback.",
    "stop": "Stop playback and clear the queue.",
    "leave": "Disconnect from voice.",
    "scrim": "Open the scrim thread generator.",
    "stickynote": "Open the sticky note panel.",
    "unsticky": "Remove the active sticky in this channel.",
    "autoresponder": "Open the autoresponder panel.",
    "gamepass": "Look up a Roblox gamepass and its payout.",
    "vanity": "Configure the vanity status role.",
    "unvanity": "Disable the vanity status role.",
}


def describe(command) -> str:
    return command.help or COMMAND_HELP.get(command.name, "No description yet.")


def usage(command) -> str:
    sig = command.signature
    return f"{PREFIX}{command.qualified_name} {sig}".strip()


async def visible_commands(cog, ctx):
    """Commands in this cog the invoker is actually allowed to run."""
    out = []
    for command in cog.get_commands():
        if command.hidden:
            continue
        try:
            if not await command.can_run(ctx):
                continue
        except commands.CommandError:
            continue
        out.append(command)
    return sorted(out, key=lambda c: c.name)


def home_embed(bot, ctx, categories):
    embed = discord.Embed(
        title="Command Help",
        description=(
            f"Prefix is `{PREFIX}`\n"
            f"Use the menu below to browse a category, or "
            f"`{PREFIX}help <command>` for details on one command."
        ),
        color=ACCENT,
    )

    for cog_name, cmds in categories.items():
        blurb = CATEGORY_META.get(cog_name, "")
        names = " ".join(f"`{c.name}`" for c in cmds)
        value = f"{blurb}\n{names}" if blurb else names
        embed.add_field(name=cog_name, value=value, inline=False)

    if not categories:
        embed.description = "You don't have access to any commands here."

    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    return embed


def category_embed(cog_name, cmds):
    blurb = CATEGORY_META.get(cog_name, "")
    embed = discord.Embed(
        title=cog_name,
        description=blurb,
        color=ACCENT,
    )

    for command in cmds:
        aliases = ""
        if command.aliases:
            aliases = " | " + " ".join(f"`{a}`" for a in command.aliases)
        embed.add_field(
            name=f"`{usage(command)}`{aliases}",
            value=describe(command),
            inline=False,
        )

    embed.set_footer(text=f"{len(cmds)} command{'s' if len(cmds) != 1 else ''}")
    return embed


def command_embed(command):
    embed = discord.Embed(
        title=f"{PREFIX}{command.qualified_name}",
        description=describe(command),
        color=ACCENT,
    )
    embed.add_field(name="Usage", value=f"`{usage(command)}`", inline=False)

    if command.aliases:
        embed.add_field(
            name="Aliases",
            value=" ".join(f"`{PREFIX}{a}`" for a in command.aliases),
            inline=False,
        )

    if command.cog:
        embed.set_footer(text=command.cog.qualified_name)
    return embed


class HelpSelect(discord.ui.Select):
    def __init__(self, categories):
        self.categories = categories

        options = [
            discord.SelectOption(
                label="Overview",
                value="__home__",
                description="Back to the main list",
            )
        ]
        for cog_name, cmds in categories.items():
            blurb = CATEGORY_META.get(cog_name, "")
            options.append(
                discord.SelectOption(
                    label=cog_name,
                    value=cog_name,
                    description=(blurb[:100] if blurb else None),
                )
            )

        super().__init__(placeholder="Pick a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__home__":
            embed = home_embed(
                interaction.client, self.view.ctx, self.categories
            )
        else:
            name = self.values[0]
            embed = category_embed(name, self.categories[name])

        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, ctx, categories):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message = None
        self.add_item(HelpSelect(categories))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                f"Run `{PREFIX}help` yourself to use this menu.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Help(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx: commands.Context, *, query: str = None):
        if query:
            command = self.bot.get_command(query.lstrip(PREFIX).strip())
            if command is None or command.hidden:
                await ctx.send(
                    f"No command called `{query}`. Try `{PREFIX}help`."
                )
                return
            await ctx.send(embed=command_embed(command))
            return

        categories = {}
        for cog_name, cog in self.bot.cogs.items():
            if cog_name == "Help":
                continue
            cmds = await visible_commands(cog, ctx)
            if cmds:
                categories[cog_name] = cmds

        categories = dict(sorted(categories.items()))

        view = HelpView(ctx, categories)
        message = await ctx.send(
            embed=home_embed(self.bot, ctx, categories),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = message


async def setup(bot):
    bot.remove_command("help")
    await bot.add_cog(Help(bot))