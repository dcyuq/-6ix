import discord
from discord.ext import commands

SEND_MODES = [
    ("text", "Plain text", "A normal message. No embed."),
    ("embed_title", "Embed with header", "Embed with a title at the top."),
    ("embed_plain", "Embed without header", "Embed with no title. Slimmer."),
]

MODE_KEYS = {m[0] for m in SEND_MODES}


def can_send(member):
    perms = member.guild_permissions
    return perms.administrator or perms.manage_messages


def mode_label(mode):
    for key, label, _ in SEND_MODES:
        if key == mode:
            return label
    return "Plain text"


def parse_color(text, fallback=0x2B2D31):
    if not text:
        return fallback
    text = text.strip().lstrip("#")
    try:
        value = int(text, 16)
    except ValueError:
        return fallback
    return value if 0 <= value <= 0xFFFFFF else fallback


def clean_url(text):
    if not text:
        return None
    text = text.strip()
    if text.lower().startswith(("http://", "https://")):
        return text
    return None


def new_draft():
    return {
        "channel_id": None,
        "mode": "text",
        "content": "",
        "title": "",
        "description": "",
        "color": 0x2B2D31,
        "image_url": None,
        "thumbnail_url": None,
        "pings": False,
    }


def build_payload(draft):
    """Return (content, embed) for the message this draft describes."""
    if draft["mode"] == "text":
        return draft["content"][:2000], None

    embed = discord.Embed(
        description=draft["description"][:4096],
        color=draft["color"],
    )
    if draft["mode"] == "embed_title" and draft["title"]:
        embed.title = draft["title"][:256]
    if draft.get("image_url"):
        embed.set_image(url=draft["image_url"])
    if draft.get("thumbnail_url"):
        embed.set_thumbnail(url=draft["thumbnail_url"])

    return None, embed


def draft_problems(draft, guild, author):
    problems = []

    if not draft["channel_id"]:
        problems.append("a target channel")

    if draft["mode"] == "text":
        if not draft["content"].strip():
            problems.append("some message text")
    elif not draft["description"].strip():
        problems.append("an embed description")

    channel = guild.get_channel(draft["channel_id"]) if draft["channel_id"] else None
    if channel is not None:
        if not channel.permissions_for(author).send_messages:
            problems.append("permission for you to post there")
        if not channel.permissions_for(guild.me).send_messages:
            problems.append("permission for me to post there")

    return problems


class TextComposeModal(discord.ui.Modal, title="Message Text"):
    def __init__(self, builder):
        super().__init__()
        self.builder = builder
        self.f_content = discord.ui.TextInput(
            label="Message",
            default=builder.draft["content"],
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True,
        )
        self.add_item(self.f_content)

    async def on_submit(self, interaction):
        await interaction.response.defer()
        self.builder.draft["content"] = self.f_content.value
        await self.builder.refresh()


class EmbedComposeModal(discord.ui.Modal, title="Embed Content"):
    def __init__(self, builder):
        super().__init__()
        self.builder = builder
        draft = builder.draft

        self.f_title = discord.ui.TextInput(
            label="Title",
            default=draft["title"],
            placeholder="Ignored if you picked the no header style",
            max_length=256,
            required=False,
        )
        self.f_desc = discord.ui.TextInput(
            label="Description",
            default=draft["description"],
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True,
        )
        self.f_color = discord.ui.TextInput(
            label="Colour hex",
            default=f"{draft['color']:06X}",
            placeholder="5865F2",
            max_length=7,
            required=False,
        )
        self.f_image = discord.ui.TextInput(
            label="Large image URL",
            default=draft.get("image_url") or "",
            placeholder="https://...",
            required=False,
        )
        self.f_thumb = discord.ui.TextInput(
            label="Thumbnail URL",
            default=draft.get("thumbnail_url") or "",
            placeholder="https://...",
            required=False,
        )

        for item in (
            self.f_title,
            self.f_desc,
            self.f_color,
            self.f_image,
            self.f_thumb,
        ):
            self.add_item(item)

    async def on_submit(self, interaction):
        await interaction.response.defer()
        draft = self.builder.draft
        draft["title"] = self.f_title.value
        draft["description"] = self.f_desc.value
        draft["color"] = parse_color(self.f_color.value, draft["color"])
        draft["image_url"] = clean_url(self.f_image.value)
        draft["thumbnail_url"] = clean_url(self.f_thumb.value)
        await self.builder.refresh()


class ModeSelect(discord.ui.Select):
    def __init__(self, builder):
        self.builder = builder
        current = builder.draft["mode"]
        options = [
            discord.SelectOption(
                label=label, value=key, description=blurb, default=(key == current)
            )
            for key, label, blurb in SEND_MODES
        ]
        super().__init__(placeholder="Message style", options=options, row=1)

    async def callback(self, interaction):
        await interaction.response.defer()
        self.builder.draft["mode"] = self.values[0]
        await self.builder.refresh()


class SendBuilderView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.draft = new_draft()
        self.message = None
        self.add_item(ModeSelect(self))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This composer isn't yours.", ephemeral=True
            )
            return False
        if not can_send(interaction.user):
            await interaction.response.send_message(
                "You need Administrator or Manage Messages permission.", ephemeral=True
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

    def status_embed(self):
        draft = self.draft
        channel = (
            self.ctx.guild.get_channel(draft["channel_id"])
            if draft["channel_id"]
            else None
        )

        if draft["mode"] == "text":
            body = draft["content"] or "nothing written yet"
        else:
            body = draft["description"] or "nothing written yet"

        preview = body if len(body) <= 200 else body[:200] + "..."

        lines = [
            f"**Sending to** - {channel.mention if channel else 'not set'}",
            f"**Style** - {mode_label(draft['mode'])}",
            f"**Pings** - {'allowed' if draft['pings'] else 'blocked'}",
            "",
            "**Content**",
            preview,
        ]

        return discord.Embed(
            title="Compose Message",
            description="\n".join(lines),
            color=draft["color"],
        )

    async def refresh(self):
        if self.message is None:
            return
        try:
            await self.message.edit(embed=self.status_embed(), view=self)
        except discord.HTTPException:
            pass

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Which channel?",
        row=0,
    )
    async def pick_channel(self, interaction, select):
        await interaction.response.defer()
        self.draft["channel_id"] = select.values[0].id
        await self.refresh()

    @discord.ui.button(label="Write", style=discord.ButtonStyle.primary, row=2)
    async def write(self, interaction, button):
        if self.draft["mode"] == "text":
            await interaction.response.send_modal(TextComposeModal(self))
        else:
            await interaction.response.send_modal(EmbedComposeModal(self))

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.secondary, row=2)
    async def preview(self, interaction, button):
        content, embed = build_payload(self.draft)

        if not content and embed is None:
            await interaction.response.send_message(
                "Nothing written yet.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            content=content,
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Allow Pings", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_pings(self, interaction, button):
        if not interaction.user.guild_permissions.mention_everyone:
            await interaction.response.send_message(
                "You need the Mention Everyone permission to enable pings.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        self.draft["pings"] = not self.draft["pings"]
        button.label = "Block Pings" if self.draft["pings"] else "Allow Pings"
        button.style = (
            discord.ButtonStyle.danger
            if self.draft["pings"]
            else discord.ButtonStyle.secondary
        )
        await self.refresh()

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, row=2)
    async def send(self, interaction, button):
        problems = draft_problems(self.draft, interaction.guild, interaction.user)
        if problems:
            await interaction.response.send_message(
                "Still need: " + ", ".join(problems), ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(self.draft["channel_id"])
        content, embed = build_payload(self.draft)

        if self.draft["pings"]:
            mentions = discord.AllowedMentions(everyone=True, roles=True, users=True)
        else:
            mentions = discord.AllowedMentions.none()

        await interaction.response.defer()

        try:
            sent = await channel.send(
                content=content, embed=embed, allowed_mentions=mentions
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I can't post in that channel.", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Discord rejected the message: {exc}", ephemeral=True
            )
            return

        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(
                    content=f"Sent to {channel.mention}: {sent.jump_url}",
                    embed=self.status_embed(),
                    view=self,
                )
            except discord.HTTPException:
                pass

        self.stop()


class Send(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if can_send(ctx.author):
            return True
        raise commands.MissingPermissions(["manage_messages"])

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need Administrator or Manage Messages permission.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command only works in a server.")
        else:
            await ctx.send(f"Something went wrong: {error}")

    @commands.command(name="send", aliases=["say"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def send(self, ctx, channel: discord.TextChannel = None, *, text: str = None):
        if channel is not None and text:
            if not channel.permissions_for(ctx.author).send_messages:
                await ctx.send("You can't post in that channel.")
                return
            if not channel.permissions_for(ctx.guild.me).send_messages:
                await ctx.send("I can't post in that channel.")
                return

            try:
                sent = await channel.send(
                    text[:2000], allowed_mentions=discord.AllowedMentions.none()
                )
            except discord.Forbidden:
                await ctx.send("I can't post in that channel.")
                return

            await ctx.send(f"Sent to {channel.mention}: {sent.jump_url}")
            return

        view = SendBuilderView(ctx)
        if channel is not None:
            view.draft["channel_id"] = channel.id

        message = await ctx.send(
            embed=view.status_embed(),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = message


async def setup(bot):
    await bot.add_cog(Send(bot))