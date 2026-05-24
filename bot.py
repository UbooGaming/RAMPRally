import discord
from discord import app_commands, ui
import aiosqlite
import asyncio
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

intents = discord.Intents.default()
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DB_FILE = "ramp_rally.db"
scheduler = AsyncIOScheduler(timezone="UTC")

# ====================== CONFIG ======================
ALLOWED_ROLES = ["Officer", "Event Organizer", "Leader", "Admin"]  # Change these to match your server roles

def has_permission():
    async def predicate(interaction: discord.Interaction):
        if not interaction.user.roles:
            return False
        role_names = [role.name.lower() for role in interaction.user.roles]
        return any(allowed.lower() in role_names for allowed in ALLOWED_ROLES)
    return app_commands.check(predicate)

# ====================== DATABASE ======================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                title TEXT,
                description TEXT,
                event_time TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rsvps (
                message_id INTEGER,
                user_id INTEGER,
                status TEXT,
                PRIMARY KEY (message_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ships (
                message_id INTEGER,
                user_id INTEGER,
                ship_name TEXT,
                PRIMARY KEY (message_id, user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS items (
                message_id INTEGER,
                item_name TEXT,
                claimed_by INTEGER,
                PRIMARY KEY (message_id, item_name)
            )
        ''')
        await db.commit()

# ====================== UPDATE EMBED ======================
async def update_event_embed(message: discord.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM rsvps WHERE message_id = ? AND status = 'Attending'", (message.id,)) as cursor:
            attending = (await cursor.fetchone())[0]
        async with db.execute("SELECT user_id, ship_name FROM ships WHERE message_id = ?", (message.id,)) as cursor:
            ships = await cursor.fetchall()
        async with db.execute("SELECT item_name, claimed_by FROM items WHERE message_id = ?", (message.id,)) as cursor:
            items = await cursor.fetchall()

    embed = message.embeds[0]
    for field in embed.fields:
        if "Attending" in field.name:
            field.value = f"{attending} players" if attending > 0 else "No one yet"
        elif "Ships" in field.name:
            field.value = "\n".join([f"• **{ship}** ← <@{user}>" for user, ship in ships]) if ships else "No ships signed up yet"
        elif "Items" in field.name:
            field.value = "\n".join([f"• {name} ← <@{user}>" for name, user in items]) if items else "None claimed yet"

    await message.edit(embed=embed)

# ====================== MODALS ======================
class ShipClaimModal(ui.Modal, title="What ship are you bringing?"):
    ship_name = ui.TextInput(label="Ship Name", placeholder="Constellation Andromeda, Cutlass Black...", required=True)

    def __init__(self, message_id):
        super().__init__()
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        ship = self.ship_name.value.strip()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO ships VALUES (?, ?, ?)", (self.message_id, interaction.user.id, ship))
            await db.commit()
        message = await interaction.channel.fetch_message(self.message_id)
        await update_event_embed(message)
        await interaction.response.send_message(f"✅ Bringing the **{ship}**! o7", ephemeral=True)

# ====================== VIEW ======================
class RampEventView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Attending", style=discord.ButtonStyle.green)
    async def attending(self, interaction: discord.Interaction, button):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO rsvps VALUES (?, ?, ?)", (interaction.message.id, interaction.user.id, "Attending"))
            await db.commit()
        await update_event_embed(interaction.message)
        await interaction.response.send_message("You're signed up for the event! o7", ephemeral=True)

    @discord.ui.button(label="🤔 Maybe", style=discord.ButtonStyle.gray)
    async def maybe(self, interaction: discord.Interaction, button):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO rsvps VALUES (?, ?, ?)", (interaction.message.id, interaction.user.id, "Maybe"))
            await db.commit()
        await interaction.response.send_message("Marked as Maybe!", ephemeral=True)

    @discord.ui.button(label="🚀 Bring Ship", style=discord.ButtonStyle.blurple)
    async def bring_ship(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(ShipClaimModal(interaction.message.id))

    @discord.ui.button(label="🍔 Claim Item", style=discord.ButtonStyle.gray)
    async def claim_item(self, interaction: discord.Interaction, button):
        await interaction.response.send_message("What item are you bringing?", ephemeral=True)

# ====================== CREATE COMMAND (Role Restricted) ======================
@tree.command(name="rampcreate", description="Create a Star Citizen Org Event (Org Leaders only)")
@app_commands.describe(title="Event title", description="Description", time="When is it? (e.g. Next Monday 8PM)")
@has_permission()   # ← Role check here
async def ramp_create(interaction: discord.Interaction, title: str, description: str, time: str):
    await interaction.response.defer()

    embed = discord.Embed(title=f"🌌 {title}", description=description, color=0x00ff88)
    embed.add_field(name="🕒 Time", value=time, inline=False)
    embed.add_field(name="✅ Attending", value="No one yet", inline=True)
    embed.add_field(name="🚀 Ships", value="No ships signed up yet", inline=False)
    embed.add_field(name="🍔 Items", value="None claimed yet", inline=False)

    view = RampEventView()
    message = await interaction.channel.send(embed=embed, view=view)

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                        (message.id, message.channel.id, title, description, time))
        await db.commit()

    await interaction.followup.send("✅ Event created successfully! o7", ephemeral=True)

# Error handler for permission checks
@ramp_create.error
async def ramp_create_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.CheckFailure):
        await interaction.response.send_message("❌ You don't have permission to create events.\nOnly **Officer / Leader / Event Organizer** roles can use this command.", ephemeral=True)
    else:
        await interaction.response.send_message("An error occurred.", ephemeral=True)

@bot.event
async def on_ready():
    await init_db()
    await tree.sync()
    print(f"✅ RAMPRally Star Citizen Org Bot is online as {bot.user}")

# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ DISCORD_TOKEN not found!")
