import discord
from discord import app_commands, ui
import aiosqlite
import asyncio
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

intents = discord.Intents.default()
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DB_FILE = "ramp_rally.db"
scheduler = AsyncIOScheduler(timezone="UTC")

# ====================== PERMISSIONS ======================
ALLOWED_ROLES = ["RAMP-Admin", "RAMP-Create", "RAMP-Event", "RAMP-ORG", "Officer", "Leader", "Admin"]

def has_permission():
    async def predicate(interaction: discord.Interaction):
        role_names = [role.name.lower() for role in interaction.user.roles]
        return any(allowed.lower() in role_names for allowed in ALLOWED_ROLES)
    return app_commands.check(predicate)

# ====================== DATABASE ======================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS recurring_events (
            template_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            title TEXT,
            description TEXT,
            event_time TEXT,
            recurring TEXT,
            last_created INTEGER
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS events (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            title TEXT,
            description TEXT,
            event_time TEXT,
            template_id INTEGER
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS rsvps (
            message_id INTEGER, user_id INTEGER, status TEXT, PRIMARY KEY (message_id, user_id)
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS ships (
            message_id INTEGER, user_id INTEGER, ship_name TEXT, PRIMARY KEY (message_id, user_id)
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS items (
            message_id INTEGER, item_name TEXT, claimed_by INTEGER, PRIMARY KEY (message_id, item_name)
        )''')
        await db.commit()

# ====================== UPDATE EMBED ======================
async def update_event_embed(message: discord.Message):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM rsvps WHERE message_id = ? AND status = 'Attending'", (message.id,)) as cursor:
            attending = (await cursor.fetchone() or (0,))[0]
        async with db.execute("SELECT user_id, ship_name FROM ships WHERE message_id = ?", (message.id,)) as cursor:
            ships = await cursor.fetchall()
        async with db.execute("SELECT item_name, claimed_by FROM items WHERE message_id = ?", (message.id,)) as cursor:
            items = await cursor.fetchall()

    embed = message.embeds[0].copy()
    for field in embed.fields:
        if "Attending" in field.name:
            field.value = f"{attending} players" if attending > 0 else "No one yet"
        elif "Ships" in field.name:
            field.value = "\n".join([f"• **{ship}** ← <@{user}>" for user, ship in ships]) if ships else "No ships signed up yet"
        elif "Items" in field.name:
            field.value = "\n".join([f"• {name} ← <@{user}>" for name, user in items]) if items else "None claimed yet"
    await message.edit(embed=embed)

# ====================== MODALS ======================
class EventCreateModal(ui.Modal, title="Create Recurring Event"):
    title_input = ui.TextInput(label="Event Title", placeholder="Weekly Cap Ships Monday", required=True)
    description_input = ui.TextInput(label="Description", placeholder="Bring your capital ships...", style=discord.TextStyle.paragraph, required=True)
    time_input = ui.TextInput(label="Time", placeholder="Monday at 8:00 PM EST", required=True)
    recurring_input = ui.TextInput(label="Recurring", placeholder="Weekly / Bi-weekly / Monthly / No", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = discord.Embed(title=f"🌌 {self.title_input.value}", description=self.description_input.value, color=0x00ff88)
        embed.add_field(name="🕒 Time", value=self.time_input.value, inline=False)
        embed.add_field(name="🔄 Recurring", value=self.recurring_input.value, inline=False)
        embed.add_field(name="✅ Attending", value="No one yet", inline=True)
        embed.add_field(name="🚀 Ships", value="No ships signed up yet", inline=False)
        embed.add_field(name="🍔 Items", value="None claimed yet", inline=False)

        view = RampEventView()
        message = await interaction.channel.send(embed=embed, view=view)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT INTO recurring_events (channel_id, title, description, event_time, recurring, last_created) VALUES (?, ?, ?, ?, ?, ?)",
                            (message.channel.id, self.title_input.value, self.description_input.value, self.time_input.value, self.recurring_input.value, int(datetime.now().timestamp())))
            await db.commit()

        await interaction.followup.send("✅ Recurring event template created! o7", ephemeral=True)

class ShipClaimModal(ui.Modal, title="What ship are you bringing?"):
    ship_name = ui.TextInput(label="Ship Name", placeholder="Polaris, Carrack...", required=True)

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

# ====================== EVENT VIEW ======================
class RampEventView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Attending", style=discord.ButtonStyle.green)
    async def attending(self, interaction: discord.Interaction, button):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO rsvps VALUES (?, ?, ?)", (interaction.message.id, interaction.user.id, "Attending"))
            await db.commit()
        await update_event_embed(interaction.message)
        await interaction.response.send_message("You're signed up! o7", ephemeral=True)

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
        await interaction.response.send_message("What are you bringing?", ephemeral=True)

# ====================== COMMANDS ======================
@tree.command(name="rampcreate", description="Create a recurring Star Citizen event")
@has_permission()
async def ramp_create(interaction: discord.Interaction):
    await interaction.response.send_modal(EventCreateModal())

@bot.event
async def on_ready():
    await init_db()
    bot.add_view(RampEventView())
    await tree.sync()
    print(f"✅ RAMPRally with recurring events is online as {bot.user}")

# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ DISCORD_TOKEN not found!")
