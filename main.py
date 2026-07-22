import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=',', intents=intents)

# test

@bot.event
async def on_ready():
    print(f"I am online!")

async def main():
    async with bot:
        discord.utils.setup_logging(handler=handler, level=logging.DEBUG)
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await bot.load_extension(f'cogs.{filename[:-3]}')
        await bot.start(token)

asyncio.run(main())