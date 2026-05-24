import discord
from discord import app_commands
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DB_FILE = "ramp_rally.db"

# ====================== DATABASE SETUP ======================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER,
                title TEXT,
                description TEXT,
                event_time TEXT,
                recurring TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id INTEGER,
                user_id INTEGER,
                status TEXT,
                PRIMARY KEY (event_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS items (
                event_id INTEGER,
                item_name TEXT,
                claimed_by INTEGER,
                PRIMARY KEY (event_id, item_name)
            )
        ''')
        await db.commit()

# ====================== BOT READY ======================
@bot.event
async def on_ready():
    await init_db()
    print(f"🚀 RAMPRally is online as {bot.user}")
    await tree.sync()
    scheduler.start()

# ====================== CREATE EVENT ======================
@tree.command(name="rampcreate", description="Create a new RAMPRally event")
@app_commands.describe(title="Event title", description="Description", time="When? (e.g. next monday 8pm)")
async def ramp_create(interaction: discord.Interaction, title: str, description: str, time: str):
    await interaction.response.defer()

    # For now we'll use simple next Monday logic - we can improve later
    channel = interaction.channel

    embed = discord.Embed(title=f"🎉 {title}", description=description, color=0x00ff00)
    embed.add_field(name="🕒 When", value=time, inline=False)
    embed.add_field(name="👥 Attending", value="No one yet", inline=True)

    view = RampView(title, description, time)
    msg = await channel.send(embed=embed, view=view)

    await interaction.followup.send("✅ RAMPRally event created!", ephemeral=True)

# ====================== VIEW WITH BUTTONS ======================
class RampView(discord.ui.View):
    def __init__(self, title, description, time):
        super().__init__(timeout=None)
        self.title = title
        self.description = description
        self.time = time

    @discord.ui.button(label="✅ Attending", style=discord.ButtonStyle.green)
    async def attending(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_rsvp(interaction, "Attending")

    @discord.ui.button(label="🤔 Maybe", style=discord.ButtonStyle.gray)
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_rsvp(interaction, "Maybe")

    @discord.ui.button(label="❌ Not Going", style=discord.ButtonStyle.red)
    async def not_going(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_rsvp(interaction, "Not Going")

    async def update_rsvp(self, interaction, status):
        await interaction.response.send_message(f"You are now **{status}**!", ephemeral=True)
        # In full version we would update DB + refresh embed

# Run the bot
if __name__ == "__main__":
    import os
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ Please add your Discord Token in Railway Variables!")
    else:
        bot.run(TOKEN)
