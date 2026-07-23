import discord 
from discord.ext import commands 
import yt_dlp
import asyncio 

FFMPEG_PATH= r"D:\projects (code)\!6\bin\ffmpeg.exe"

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

async def search(query, loop):
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    if 'entries' in data:
        data = data['entries'][0]
    return {
        'title': data.get('title'),
        'stream': data['url'],
        'webpage': data.get('webpage_url'),
    }

class GuildMusicState:
    def __init__(self):
        self.queue = []
        self.current = None
        self.loop = False
        self.skipping = False

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = {}

    def get_state(self, guild_id):
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    async def ensure_voice(self, ctx):
        if ctx.author.voice is None:
            await ctx.send("You need to be in a voice channel.")
            return None
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            return await channel.connect()
        await ctx.voice_client.move_to(channel)
        return ctx.voice_client

    async def play_next(self, ctx):
        state = self.get_state(ctx.guild.id)
        vc = ctx.voice_client
        if vc is None:
            return

        if state.loop and state.current and not state.skipping:
            track = state.current
        elif state.queue:
            track = state.queue.pop(0)
            state.current = track
        else:
            state.current = None
            return
        state.skipping = False

        source = discord.FFmpegPCMAudio(track['stream'], executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source, volume=0.5)

        def after(error):
            if error:
                print(f"Player error: {error}")
            asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

        vc.play(source, after=after)
        await ctx.send(f"Now playing: **{track['title']}**")

    @commands.command()
    async def play(self, ctx, *, query):
        vc = await self.ensure_voice(ctx)
        if vc is None:
            return
        state = self.get_state(ctx.guild.id)
        async with ctx.typing():
            track = await search(query, self.bot.loop)
        state.queue.append(track)
        if not vc.is_playing() and not vc.is_paused():
            await self.play_next(ctx)
        else:
            await ctx.send(f"Added to queue: **{track['title']}**")

    @commands.command()
    async def skip(self, ctx):
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.get_state(ctx.guild.id).skipping = True
            vc.stop()
            await ctx.send("Skipped.")
        else:
            await ctx.send("Nothing is playing.")

    @commands.command()
    async def queue(self, ctx):
        state = self.get_state(ctx.guild.id)
        if not state.queue and not state.current:
            await ctx.send("Queue is empty.")
            return
        lines = []
        if state.current:
            lines.append(f"**Now playing:** {state.current['title']}")
        for i, track in enumerate(state.queue, 1):
            lines.append(f"{i}. {track['title']}")
        await ctx.send("\n".join(lines))

    @commands.command()
    async def loop(self, ctx):
        state = self.get_state(ctx.guild.id)
        state.loop = not state.loop
        await ctx.send(f"Loop {'enabled' if state.loop else 'disabled'}.")

    @commands.command()
    async def pause(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("Paused.")

    @commands.command()
    async def resume(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("Resumed.")

    @commands.command()
    async def stop(self, ctx):
        state = self.get_state(ctx.guild.id)
        state.queue.clear()
        state.loop = False
        state.current = None
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.send("Stopped and cleared the queue.")

    @commands.command()
    async def leave(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            self.states.pop(ctx.guild.id, None)
            await ctx.send("Left the voice channel.")


async def setup(bot):
    await bot.add_cog(Music(bot))