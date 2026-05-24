import discord
from discord import app_commands
import aiosqlite
import asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DB_FILE = "ramp_rally.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER,
                title TEXT,
                description TEXT,
                event_time TEXT
            )
        ''')
        await db.commit()

@bot.event
async def on_ready():
    await init_db()
    await tree.sync()
    print(f"✅ RAMPRally is online as {bot.user}")

# ==================== CREATE EVENT ====================
@tree.command(name="rampcreate", description="Create a new RAMPRally event")
@app_commands.describe(
    title="Event title",
    description="Short description",
    time="When is it? (e.g. Monday 8PM)"
)
async def ramp_create(interaction: discord.Interaction, title: str, description: str, time: str):
    await interaction.response.defer()

    embed = discord.Embed(
        title=f"🎉 {title}",
        description=description,
        color=0x00ff88
    )
    embed.add_field(name="🕒 Time", value=time, inline=False)
    embed.add_field(name="✅ Attending", value="No one yet", inline=True)

    view = RampEventView()
    message = await interaction.channel.send(embed=embed, view=view)

    await interaction.followup.send("✅ Event created successfully!", ephemeral=True)

# ==================== EVENT VIEW ====================
class RampEventView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Attending", style=discord.ButtonStyle.green)
    async def attending(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You're in! 🎉", ephemeral=True)

    @discord.ui.button(label="🤔 Maybe", style=discord.ButtonStyle.gray)
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Noted as Maybe!", ephemeral=True)

    @discord.ui.button(label="🍔 Bring Item", style=discord.ButtonStyle.blurple)
    async def bring_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("What item are you bringing? (Reply in next message)", ephemeral=True)

# Run the bot
if __name__ == "__main__":
    import os
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ DISCORD_TOKEN not found!")
