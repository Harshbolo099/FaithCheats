import asyncio
from math import perm
import sys

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import discord
from io import BytesIO
import qrcode
import json
import os
import requests
import re
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp  # Added for music feature
import chat_exporter
import io

from keep_alive import keep_alive

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.guild_messages = True
intents.guilds = True
intents.members = True  # Needed to read roles

# bot = commands.Bot(command_prefix='!', intents=intents)
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# colours hain laadleee

THEME = {
    "payment": discord.Color.gold(),
    "moderation": discord.Color.red(),
    "info": discord.Color.blue(),
    "music": discord.Color.purple(),
    "utility": discord.Color.green(),
    "system": discord.Color.dark_gray()
}




# Directory for storing templates
TEMPLATE_DIR = "templates"
if not os.path.exists(TEMPLATE_DIR):
    os.makedirs(TEMPLATE_DIR)




# Load environment variables
load_dotenv()  # It auto-loads from ".env" in the same directory

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No bot token found in .env file.")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True  # Required for music feature and giveroleall
intents.voice_states = True  # Required for music feature
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# File for storing UPI IDs
UPI_DATA_FILE = "user_upi_ids.json"
user_upi_ids = {}

def load_upi_data():
    try:
        with open(UPI_DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_upi_data(data):
    with open(UPI_DATA_FILE, "w") as f:
        json.dump(data, f)

user_upi_ids = load_upi_data()

# LTC validation
def is_valid_ltc_address(address):
    pattern = re.compile(r"^[LM3][a-km-zA-HJ-NP-Z1-9]{26,33}$")
    return bool(pattern.match(address))

# 🔧 Ensure required roles exist
async def ensure_roles_exist(guild: discord.Guild, role_names: list[str]):
    existing_roles = [role.name for role in guild.roles]
    for role_name in role_names:
        if role_name not in existing_roles:
            await guild.create_role(name=role_name)
            print(f"Created missing role: {role_name}")

# --------------------------
# 📦 LTC ADDRESS COMMAND
# --------------------------
@bot.command(name="setltc")
@commands.has_role("Team Faith")
async def set_ltc(ctx, *, address: str):
    force = "--force" in address
    if force:
        address = address.replace("--force", "").strip()

    if not is_valid_ltc_address(address) and not force:
        return await ctx.send("❌ Invalid LTC address. Use --force to override.")

    # Save directly to the database
    await users_collection.update_one(
        {"_id": str(ctx.author.id)}, 
        {"$set": {"ltc": address}}, 
        upsert=True
    )
    await ctx.send(f"✅ Your LTC address has been saved:\n`{address}`")

@bot.command(name="ltc2")
async def show_ltc(ctx, member: discord.Member = None):
    target = member or ctx.author
    
    if member and not discord.utils.get(ctx.author.roles, name="Team Faith"):
        return await ctx.send("🚫 You need the Team Faith role to view others' LTC.")

    # Fetch from database
    user_data = await users_collection.find_one({"_id": str(target.id)})
    
    if not user_data or "ltc" not in user_data:
        return await ctx.send(f"❌ {target.mention} has not set an LTC address yet.")

    await ctx.send(f"💰 {target.mention}'s LTC address:\n`{user_data['ltc']}`")

# --------------------------
# ⚠️ FORCE CONFIRM VIEW
# --------------------------
class ConfirmForceView(discord.ui.View):
    def __init__(self, user_id, address):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.address = address

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your action.", ephemeral=True)

        user_ltc_addresses[str(self.user_id)] = self.address
        save_ltc_data(user_ltc_addresses)

        await interaction.response.edit_message(
            content=f"⚠️ Forced LTC saved:\n`{self.address}`",
            view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your action.", ephemeral=True)

        await interaction.response.edit_message(
            content="❌ Operation cancelled.",
            view=None
        )


# SAVE LTC YAYYY
# --------------------------
# 💾 LTC STORAGE
# --------------------------
LTC_DATA_FILE = "user_ltc_addresses.json"

def load_ltc_data():
    try:
        with open(LTC_DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_ltc_data(data):
    with open(LTC_DATA_FILE, "w") as f:
        json.dump(data, f)

user_ltc_addresses = load_ltc_data()

@set_ltc.error
async def set_ltc_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You must have the 'Team Faith' role to use this command.")


# LTC ese ayga ywrr

@bot.command(name="ltc")
async def show_ltc(ctx, member: discord.Member = None):
    # If no member → show own
    if member is None:
        address = user_ltc_addresses.get(str(ctx.author.id))

        if not address:
            await ctx.send("❌ You haven't set any LTC address yet.")
            return

        await ctx.send(f"💰 Your LTC address:\n`{address}`")
        return

    # If trying to view others → require Team Faith
    if not discord.utils.get(ctx.author.roles, name="Team Faith"):
        await ctx.send("🚫 You need Team Faith role to view others' LTC.")
        return

    address = user_ltc_addresses.get(str(member.id))

    if not address:
        await ctx.send(f"❌ {member.mention} has no LTC set.")
        return

    await ctx.send(f"💰 {member.mention}'s LTC:\n`{address}`")

# SABKA LTC DEKHO BC
@bot.command(name="ltclist")
@commands.has_role("Team Faith")
async def ltc_list(ctx):
    if not user_ltc_addresses:
        await ctx.send("No LTC addresses saved.")
        return

    text = ""
    for user_id, address in user_ltc_addresses.items():
        user = ctx.guild.get_member(int(user_id))
        name = user.mention if user else f"Unknown ({user_id})"
        text += f"{name} → `{address}`\n"

    # prevent message overflow
    if len(text) > 1900:
        text = text[:1900] + "\n..."

    await ctx.send(f"📋 **All LTC Addresses:**\n{text}")

# STATS LELO DALAAALO
@bot.command(name="ltcstats")
@commands.has_role("Team Faith")
async def ltc_stats(ctx):
    total = len(user_ltc_addresses)

    if total == 0:
        await ctx.send("No LTC data available.")
        return

    await ctx.send(f"📊 **LTC Stats**\nTotal users with LTC: `{total}`")

# LTC DHUNDHOO
@bot.command(name="ltcsearch")
@commands.has_role("Team Faith")
async def ltc_search(ctx, query: str):
    results = []

    for user_id, address in user_ltc_addresses.items():
        if query.lower() in address.lower():
            user = ctx.guild.get_member(int(user_id))
            name = user.mention if user else f"Unknown ({user_id})"
            results.append(f"{name} → `{address}`")

    if not results:
        await ctx.send("❌ No matching LTC addresses found.")
        return

    text = "\n".join(results)

    if len(text) > 1900:
        text = text[:1900] + "\n..."

    await ctx.send(f"🔍 **Search Results:**\n{text}")


# --------------------------
# 💳 UPI SETUP & QR COMMAND
# --------------------------
@bot.command(name="setupi")
@commands.has_role("Team Faith")
async def setupi(ctx, upi_id: str):
    # upsert=True means "update if it exists, create if it doesn't"
    await users_collection.update_one(
        {"_id": str(ctx.author.id)}, 
        {"$set": {"upi": upi_id}}, 
        upsert=True
    )
    await ctx.send(f"✅ Your UPI ID has been stored safely in the database: `{upi_id}`")

@bot.command(name="myqr")
@commands.has_role("Team Faith")
async def generate_qr(ctx, amount: float):
    # Fetch from database
    user_data = await users_collection.find_one({"_id": str(ctx.author.id)})
    
    if not user_data or "upi" not in user_data:
        return await ctx.send("❌ Set your UPI ID first with `.setupi [upi_id]`")

    upi_id = user_data["upi"]
    note = "I have authorised this payment"
    payment_url = f"upi://pay?pa={upi_id}&pn={ctx.author.display_name}&am={amount}&cu=INR&tn={note}"
    
    qr = qrcode.make(payment_url)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)

    file = discord.File(fp=buffer, filename="payment_qr.png")
    await ctx.send(f"Here is your payment QR code for INR {amount}:", file=file)

@generate_qr.error
async def generate_qr_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You are not allowed to generate a QR code, Please ask the owner.")

# --------------------------
# 💰 LTC BALANCE CHECKER
# --------------------------
@bot.tree.command(name="bal", description="Check LTC balance.")
async def balance(interaction: discord.Interaction, ltc_address: str):
    if not is_valid_ltc_address(ltc_address):
        await interaction.response.send_message(
            embed=discord.Embed(title="Invalid LTC Address", description="Loda sahi dal na addy", color=THEME["moderation"])
        )
        return

    try:
        url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{ltc_address}/balance"
        data = requests.get(url).json()

        confirmed_ltc = data.get("final_balance", 0) / 1e8
        unconfirmed_ltc = data.get("unconfirmed_balance", 0) / 1e8

        confirmed_usd = await get_ltc_to_usd(confirmed_ltc)
        unconfirmed_usd = await get_ltc_to_usd(unconfirmed_ltc)

        embed = discord.Embed(title=":money_with_wings: LTC BALANCE", color=THEME["payment"])
        embed.add_field(name="Address", value=ltc_address, inline=False)
        embed.add_field(name="Confirmed", value=f"${confirmed_usd:.2f} / {confirmed_ltc:.8f} LTC", inline=False)
        embed.add_field(name="Unconfirmed", value=f"${unconfirmed_usd:.2f} / {unconfirmed_ltc:.8f} LTC", inline=False)
        embed.set_footer(text="POWERED BY FAITH MM | .gg/faithmm")

        await interaction.response.send_message(embed=embed)

    except Exception:
        await interaction.response.send_message("Failed to retrieve LTC balance. Try again later.")

async def get_ltc_to_usd(ltc_amount):
    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd")
        usd_price = res.json().get("litecoin", {}).get("usd", 0)
        return ltc_amount * usd_price
    except:
        return 0

# --------------------------
# 🎭 ROLE COMMANDS
# --------------------------
@bot.tree.command(name="client", description="Give ~ Clients role.")
async def client_command(interaction: discord.Interaction, member: discord.Member):
    team_faith = discord.utils.get(interaction.guild.roles, name="Team Faith")
    if team_faith not in interaction.user.roles:
        await interaction.response.send_message("You don't have permission to do this.")
        return

    client_role = discord.utils.get(interaction.guild.roles, name="~ Clients") or await interaction.guild.create_role(name="~ Clients")
    await member.add_roles(client_role)
    await interaction.response.send_message(f"{member.mention} has been given the ~ Clients role.")

@bot.tree.command(name="giveroleall", description="Give a role to everyone.")
async def giveroleall(interaction: discord.Interaction, role_name: str):
    team_faith = discord.utils.get(interaction.guild.roles, name="Team Faith")
    if team_faith not in interaction.user.roles:
        await interaction.response.send_message("You don't have permission to do this.")
        return

    role = discord.utils.get(interaction.guild.roles, name=role_name) or await interaction.guild.create_role(name=role_name)
    for member in interaction.guild.members:
        if role not in member.roles:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"Could not assign role to {member.name}: {e}")
    
    await interaction.response.send_message(f"Everyone has been given the '{role_name}' role.")
# --------------------------
# 💥 NUKE COMMAND
# --------------------------
@bot.command(name="nuke")
@commands.has_role("CHEETAH")
async def nuke(ctx):
    original_channel = ctx.channel
    
    # 1. Save both the exact position AND the category
    original_position = original_channel.position
    original_category = original_channel.category
    
    # 2. Clone the current channel (this natively copies name, perms, and topic)
    new_channel = await original_channel.clone(reason=f"Nuked by {ctx.author.name}")
    
    # 3. Delete the original channel to free up that specific spot in the list
    await original_channel.delete(reason=f"Nuked by {ctx.author.name}")
    
    # 4. Edit the cloned channel to lock it into the exact spot and category
    await new_channel.edit(position=original_position, category=original_category)
    
    # 5. Send the confirmation
    await new_channel.send(f"💥 Channel has been nuked and recreated by {ctx.author.mention}!")

@nuke.error
async def nuke_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You need to be the Raja of this server :moyai: !")
    elif isinstance(error, discord.Forbidden):
        await ctx.send("I don't have permission to delete or create channels. Please check my permissions.")
#===========================
# COMEBACK TIMEEEEEEEE
#==============================

@bot.command(name="comeback")
@commands.has_role("Raja")
async def comeback(ctx):
    embed = discord.Embed(
        title="⚠️ PROMPTED DEALER — WE ARE BACK ⚠️",
        description="Something happened… and not everything was under our control.",
        color=THEME["info"]
    )

    embed.add_field(
        name="What Happened?",
        value="Our previous server didn’t just disappear randomly.\nThere was **internal betrayal** — people we trusted were secretly working with rivals.",
        inline=False
    )

    embed.add_field(
        name="The Result",
        value="Because of that, the server got taken down.\nEverything we built — gone overnight.",
        inline=False
    )

    embed.add_field(
        name="But We Didn’t Stop",
        value="We rebuilt everything from scratch.\nStronger systems, tighter control, no weak links this time.",
        inline=False
    )

    embed.add_field(
        name="What’s New?",
        value="We’ve expanded way beyond before…\n||we were dealing in multiple things and built a much larger collection now||",
        inline=False
    )

    embed.add_field(
        name="This Time",
        value="No trust without verification.\nNo shortcuts.\nNo repeats of the past.",
        inline=False
    )

    embed.add_field(
        name="Final Note",
        value="**Prompted Dealer isn’t done.**\nWe’re just getting started again.",
        inline=False
    )

    embed.set_footer(text="POWERED BY PROMPTED DEALER")

    await ctx.send(embed=embed)

# --------------------------
# 📜 TERMS OF SERVICE COMMAND
# --------------------------
@bot.command(name="tos")
async def tos(ctx):
    embed = discord.Embed(
        title="FAITH MM TERMS OF SERVICE",
        description="By using Faith MM services, you agree to be bound by these terms. If you disagree with any part, please don't proceed.",
        color=THEME["info"]
    )
    
    embed.add_field(
        name="Service Scope",
        value="We provide middleman services for cryptocurrency trades and UPI payments for deals between $1 and $1000.",
        inline=False
    )
    
    embed.add_field(
        name="No Currency/Server Ownership",
        value="The middleman does not hold bot currency or server ownership.",
        inline=False
    )
    
    embed.add_field(
        name="Response Time",
        value="If the person requesting the deal is away for more than 24 hours and requests their belongings back, the middleman will return them within 24 hours. The middleman is not responsible for any consequences thereafter.",
        inline=False
    )
    
    embed.add_field(
        name="Server Deals Only",
        value="Middleman services only occur within the specified server. Deals made outside the server or with staff members directly are not eligible for refunds or responsibility from the middleman.",
        inline=False
    )
    
    embed.add_field(
        name="Cryptocurrency Trades",
        value="For cryptocurrency trades, clients must wait for blockchain confirmation, and the middleman must also wait. The client is responsible for network fees for deposit and withdrawal; the middleman won't cover these fees.",
        inline=False
    )
    
    embed.add_field(
        name="Deal Limits",
        value="Clients should check the maximum deal limit of the middleman. Any issues arising from paying more than the limit are the client's responsibility.",
        inline=False
    )
    
    embed.add_field(
        name="No Accountability for Events",
        value="The middleman is not held accountable for any events before, during, or after the deal, nor responsible for compensating for events beyond their control, such as account terminations, locks, skipped confirmations, chargebacks, or technical issues.",
        inline=False
    )
    
    embed.add_field(
        name="Offline Middleman",
        value="If a middleman goes offline after notifying the client, they will complete the deal upon their return and are not responsible for any consequences thereafter.",
        inline=False
    )
    
    embed.add_field(
        name="Market Fluctuations",
        value="The middleman is not responsible for any losses if the market goes down during the deal.",
        inline=False
    )
    
    embed.add_field(
        name="INR Transactions",
        value="For INR transactions, clients are required to pay GST and other charges. Adding a Paynote is mandatory while paying staff; failure to do so will result in a penalty fee of ₹10.",
        inline=False
    )
    
    embed.add_field(
        name="Refunds",
        value="Refunds are only provided if the client is scammed by the deals are to be avoided.",
        inline=False
    )
    
    embed.add_field(
        name="Cancellation Fee",
        value="If a deal is cancelled for any reason, the client will be charged a cancellation fee of $0.20.",
        inline=False
    )
    
    embed.add_field(
        name="Client Responsibility",
        value="Clients must stay active and responsive during the deal. Swearing is not allowed in the ticket.",
        inline=False
    )
    
    embed.add_field(
        name="Terms Subject to Change",
        value="Rules and terms of service are subject to change without notice. Abusive language is prohibited.",
        inline=False
    )
    
    embed.add_field(
        name="Chat Logs",
        value="Chat logs will be saved and archived for security reasons after the deal finishes.",
        inline=False
    )
    
    embed.add_field(
        name="No Refunds for Voucher Abuse",
        value="Clients are not allowed to refuse to vouch for the middleman after a successful trade. Refusal to vouch may result in being blacklisted from using the service.",
        inline=False
    )
    
    embed.add_field(
        name="MM Deal ToS",
        value="When using our middleman services: If the buyer fails to return within 24 hours after making payment, we will release the funds to the seller. Conversely, if the seller fails to return within 24 hours after receiving payment from the buyer through the middleman, we will issue a refund to the buyer. If you charge back the funds after a successful trade and then create a ticket again for exchange in the future, we will permanently freeze your funds to provide compensation to our exchanger for the loss incurred by the client. If payment is sent through a third party without informing the exchanger or MM, they have the right to freeze funds. You will have to give the ID of the third-party user so we can confirm with them that they are sending payment.",
        inline=False
    )
    
    embed.add_field(
        name="Fees and Charges",
        value="• Delay charges: 5% of your deal amount if MM holds funds for more than 6 hours\n• Cancellation charges:\n  Below 10$/<₹900 deal: 0% fee\n  Above 10$/>₹900 deal: 0.20$/₹20 INR fee\n• Penalty charges: ₹10.00\n\n*INR MM Fee:* 5% of the deal amount.",
        inline=False
    )
    
    embed.set_footer(text="POWERED BY FAITH MM ")
    
    await ctx.send(embed=embed)

# --------------------------
# 📜 RULES
# --------------------------
@bot.command(name="rules")
async def rules(ctx):
    embed = discord.Embed(
        title="📜 SERVER RULES",
        description="Welcome to our awesome server! Here are some cool rules that will ensure a positive and enjoyable experience for everyone:",
        color=THEME["info"]
    )

    embed.add_field(name="➤ Show Respect", value="Treat your fellow members with kindness, respect, and inclusivity. Harassment or any form of bullying will not be tolerated.", inline=False)
    embed.add_field(name="➤ Privacy Matters", value="Safeguard the privacy of our members. Avoid invading personal boundaries or causing embarrassment to others.", inline=False)
    embed.add_field(name="➤ Spread Positivity", value="Refrain from engaging in hate speech towards any religion, society, or country. Let’s foster a supportive and accepting community.", inline=False)
    embed.add_field(name="➤ Keep it Clean", value="Do not share abusive, indecent, or explicit images or content. Let’s maintain a server that’s safe for all ages.", inline=False)
    embed.add_field(name="➤ No Promotion Zone", value="Avoid promoting other servers, publicly or privately. Let’s focus on our amazing community.", inline=False)
    embed.add_field(name="➤ Personal Matters", value="The server isn't responsible for personal issues. Please resolve them outside the server.", inline=False)
    embed.add_field(name="➤ Mind Your Appearance", value="Do not join with inappropriate profile pictures or usernames. Keep it cool and classy.", inline=False)
    embed.add_field(name="➤ Uphold Morals and Ethics", value="Do not share links or images that depict murder, obscenity, or other public moral violations. Instant ban applies.", inline=False)
    embed.add_field(name="➤ Mind Your Language", value="Avoid offensive language or excessive slang. Maintain a respectful and inclusive tone.", inline=False)

    embed.add_field(
        name="📌 Follow Official Discord Rules",
        value="We abide by [Discord's Terms of Service](https://discord.com/terms), [Community Guidelines](https://discord.com/guidelines), and [Privacy Policy](https://discord.com/privacy). Please follow them.",
        inline=False
    )
    
    embed.set_footer(text="POWERED BY FAITH MM ")
    
    await ctx.send(embed=embed)

# --------------------------
# 📋 TEMPLATE COMMANDS
# --------------------------
import time

# Retry mechanism for rate limits (no manual delays)
async def retry_on_rate_limit(func, *args, **kwargs):
    retries = 5
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limit error
                retry_after = e.retry_after if e.retry_after else 1
                print(f"Rate limit hit, retrying after {retry_after} seconds...")
                await asyncio.sleep(retry_after)
            else:
                raise e
        except Exception as e:
            print(f"Unexpected error during operation: {str(e)}")
            raise e
    raise Exception(f"Failed after {retries} retries due to rate limits")

@bot.command(name="savetemplate")
@commands.has_role("Raja")
async def savetemplate(ctx, template_name: str):
    """Save the server's categories, channels, and roles to a template."""
    print(f"Received .savetemplate command from {ctx.author} with template_name: {template_name}")
    guild = ctx.guild
    print(f"Processing guild: {guild.name}")
    template = {
        'name': guild.name,
        'categories': [],
        'channels': [],
        'roles': []
        
    }

    # Save roles
    print("Saving roles...")
    for role in guild.roles:
        if role.name != '@everyone':
            template['roles'].append({
                'name': role.name,
                'color': role.color.to_rgb(),
                'permissions': role.permissions.value,
                'hoist': role.hoist,
                'mentionable': role.mentionable
            })

    # Save categories and their channels
    print("Saving categories...")
    for category in guild.categories:
        category_data = {
            'name': category.name,
            'position': category.position,
            'permission_overwrites': {
                str(target.id): {
                    'allow': overwrite.pair()[0].value,
                    'deny': overwrite.pair()[1].value
                } for target, overwrite in category.overwrites.items()
            },
            'channels': []
        }
        for channel in category.channels:
            channel_data = {
                'name': channel.name,
                'type': str(channel.type),
                'position': channel.position,
                'topic': getattr(channel, 'topic', None),
                'permission_overwrites': {
                    str(target.id): {
                        'allow': overwrite.pair()[0].value,
                        'deny': overwrite.pair()[1].value
                    } for target, overwrite in channel.overwrites.items()
                }
            }
            category_data['channels'].append(channel_data)
        template['categories'].append(category_data)

    # Save standalone channels
    print("Saving standalone channels...")
    for channel in guild.channels:
        if not channel.category:
            channel_data = {
                'name': channel.name,
                'type': str(channel.type),
                'position': channel.position,
                'topic': getattr(channel, 'topic', None),
                'permission_overwrites': {
                    str(target.id): {
                        'allow': overwrite.pair()[0].value,
                        'deny': overwrite.pair()[1].value
                    } for target, overwrite in channel.overwrites.items()
                }
            }
            template['channels'].append(channel_data)

    # Save to JSON file
    print(f"Saving template to {TEMPLATE_DIR}/{template_name}.json...")
    try:
        with open(f'{TEMPLATE_DIR}/{template_name}.json', 'w') as f:
            json.dump(template, f, indent=4)
        await ctx.send(f'Template "{template_name}" saved successfully!')
        print("Template saved successfully!")
    except Exception as e:
        await ctx.send(f'Failed to save template: {str(e)}')
        print(f"Failed to save template: {str(e)}")

@savetemplate.error
async def savetemplate_error(ctx, error):
    print(f"Error in savetemplate: {str(error)}")
    if isinstance(error, commands.MissingRole):
        await ctx.send("You need to be the Raja of this server :moyai: !")
    elif isinstance(error, discord.Forbidden):
        await ctx.send("I don't have permission to read server settings. Please check my permissions.")
    else:
        await ctx.send(f"An unexpected error occurred: {str(error)}")
        print(f"Unexpected error in savetemplate: {str(error)}")

async def nuke_server(guild: discord.Guild, bot_user: discord.User, temp_channel: discord.TextChannel):
    """Delete all channels, categories, and roles (except @everyone, bot's role, and temp_channel) in parallel."""
    try:
        # Protect bot's role
        bot_role = guild.me.top_role
        print(f"Bot's role: {bot_role.name} (ID: {bot_role.id}) - preserving during nuke")

        # Delete all channels in parallel (except temp_channel)
        print("Deleting channels...")
        channel_deletions = [
            retry_on_rate_limit(channel.delete, reason="Nuking server for template application")
            for channel in guild.channels
            if channel != temp_channel
        ]
        await asyncio.gather(*channel_deletions)

        # Delete all roles in parallel (except @everyone and bot's role)
        print("Deleting roles...")
        role_deletions = []

        for role in guild.roles:
            if role.name == "@everyone":
                continue

            if role >= guild.me.top_role:
                continue  # cannot delete roles above bot

            if role.managed:
                continue  # skip bot/integration roles

            role_deletions.append(
                retry_on_rate_limit(role.delete, reason="Nuking server for template application")
            )

        await asyncio.gather(*role_deletions)

        print(f"Server {guild.name} has been nuked (except {temp_channel.name}).")
    except Exception as e:
        print(f"Error during server nuke: {str(e)}")
        raise e  # Re-raise to catch in applytemplate

@bot.command(name="applytemplate")
@commands.has_role("CHEETAH")
async def applytemplate(ctx, template_name: str, nuke: str = None):
    """Apply a saved template. Use --nuke to clear server first."""
    guild = ctx.guild

    temp_channel = None
    # Handle nuke option
    if nuke == "--nuke":
        # Create the temporary "applying-template" channel
        print("Creating temporary applying-template channel...")
        try:
            temp_channel = await retry_on_rate_limit(
                guild.create_text_channel,
                name="applying-template",
                reason="Temporary channel for applying template"
            )
            await temp_channel.send("⚠️ Nuking server... This will delete all channels, categories, and roles (except @everyone, bot's role, and this channel).")
        except Exception as e:
            await ctx.send(f"Failed to create temporary channel: {str(e)}")
            return

        # Nuke the server (excluding temp_channel)
        try:
            await nuke_server(guild, bot.user, temp_channel)
            await temp_channel.send("💥 Server nuked! Applying template...")
            await asyncio.sleep(2)  # brief pause before applying template
        except Exception as e:
            await temp_channel.send(f"Failed during nuke operation: {str(e)}")
            return

    # Load template
    print(f"Loading template {template_name}...")
    try:
        with open(f'{TEMPLATE_DIR}/{template_name}.json', 'r', encoding='utf-8') as f:
            template = json.load(f)
        print("Template loaded successfully")
    except FileNotFoundError:
        if temp_channel:
            await temp_channel.send(f'Template "{template_name}" not found!')
        else:
            await ctx.send(f'Template "{template_name}" not found!')
        return
    except Exception as e:
        if temp_channel:
            await temp_channel.send(f'Failed to load template: {str(e)}')
        else:
            await ctx.send(f'Failed to load template: {str(e)}')
        return

    # Validate template data
    print("Validating template data...")
    required_keys = ['name', 'categories', 'channels', 'roles']
    for key in required_keys:
        if key not in template:
            if temp_channel:
                await temp_channel.send(f"Invalid template: missing '{key}' key")
            else:
                await ctx.send(f"Invalid template: missing '{key}' key")
            return

#====================================================================

# ===============================
# 🔥 FIXED ROLE CREATION (NO DUPES)
# ===============================

    print("Creating roles...")
    role_map = {}

    for role_data in template['roles']:
        role_name = role_data['name']

        # 🔍 Check if role already exists
        existing_role = discord.utils.get(guild.roles, name=role_name)

        if existing_role:
            print(f"Role '{role_name}' already exists → using existing")
            role_map[role_name] = existing_role
            continue

        try:
            print(f"Creating role {role_name}...")

            new_role = await retry_on_rate_limit(
                guild.create_role,
                name=role_name,
                color=discord.Color.from_rgb(*role_data.get('color', (0, 0, 0))),
            permissions=discord.Permissions(role_data.get('permissions', 0)),
                hoist=role_data.get('hoist', False),
                mentionable=role_data.get('mentionable', False)
            )

            role_map[role_name] = new_role
            print(f"Role {role_name} created successfully")

        except Exception as e:
            print(f"Failed to create role {role_name}: {e}")
    
#====================================================================

    # Create categories and channels
    print("Creating categories and channels...")
    for category_data in template['categories']:
        overwrites = {}

        for role_id, perms in category_data.get('permission_overwrites', {}).items():
            try:
                role = guild.get_role(int(role_id)) or role_map.get(role_id)
            except:
                role = None

            if role is None:
                continue  # skip invalid/deleted roles

            overwrites[role] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(perms['allow']),
                discord.Permissions(perms['deny'])
            )

        try:
            print(f"Creating category {category_data['name']}...")
            new_category = await retry_on_rate_limit(
                guild.create_category,
                name=category_data['name'],
                position=category_data['position'],
                overwrites=overwrites
            )
            print(f"Category {category_data['name']} created successfully")
        except Exception as e:
            print(f"Failed to create category {category_data['name']}: {e}")
            continue

        # Create channels in parallel within the category
        channel_creations = []
        for channel_data in category_data['channels']:
            async def create_channel(channel_data):
                try:
                    print(f"Creating channel {channel_data['name']} in category {category_data['name']}...")
                    overwrites = {}

                    for role_id, perms in channel_data.get('permission_overwrites', {}).items():
                        try:
                            role = guild.get_role(int(role_id)) or role_map.get(role_id)
                        except:
                            role = None

                        if role is None:
                            continue  # skip invalid/deleted roles

                        overwrites[role] = discord.PermissionOverwrite.from_pair(
                            discord.Permissions(perms['allow']),
                            discord.Permissions(perms['deny'])
                        )

                    if channel_data['type'] == 'text':
                        await retry_on_rate_limit(
                            new_category.create_text_channel,
                            name=channel_data['name'],
                            position=channel_data['position'],
                            topic=channel_data.get('topic'),
                            overwrites=overwrites
                        )
                    elif channel_data['type'] == 'voice':
                        await retry_on_rate_limit(
                            new_category.create_voice_channel,
                            name=channel_data['name'],
                            position=channel_data['position'],
                            overwrites=overwrites
                        )
                    print(f"Channel {channel_data['name']} created successfully")
                except Exception as e:
                    print(f"Failed to create channel {channel_data['name']}: {e}")

            channel_creations.append(create_channel(channel_data))
        await asyncio.gather(*channel_creations)

    # Create standalone channels in parallel
    print("Creating standalone channels...")
    standalone_creations = []
    for channel_data in template['channels']:
        async def create_standalone_channel(channel_data):
            try:
                print(f"Creating standalone channel {channel_data['name']}...")
                overwrites = {}

                for role_id, perms in channel_data.get('permission_overwrites', {}).items():
                    try:
                        role = guild.get_role(int(role_id)) or role_map.get(role_id)
                    except:
                        role = None

                    if role is None:
                        continue  # skip invalid/deleted roles

                    overwrites[role] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(perms['allow']),
                        discord.Permissions(perms['deny'])
                    )

                if channel_data['type'] == 'text':
                    await retry_on_rate_limit(
                        guild.create_text_channel,
                        name=channel_data['name'],
                        position=channel_data['position'],
                        topic=channel_data.get('topic'),
                        overwrites=overwrites
                    )
                elif channel_data['type'] == 'voice':
                    await retry_on_rate_limit(
                        guild.create_voice_channel,
                        name=channel_data['name'],
                        position=channel_data['position'],
                        overwrites=overwrites
                    )
                print(f"Standalone channel {channel_data['name']} created successfully")
            except Exception as e:
                print(f"Failed to create standalone channel {channel_data['name']}: {e}")

        standalone_creations.append(create_standalone_channel(channel_data))
    await asyncio.gather(*standalone_creations)

    # Delete the temporary channel and send final message
    if temp_channel:
        try:
            # Find the first text channel from the template to send the final message
            new_channel = None
            for channel in guild.text_channels:
                if channel.name != "applying-template":
                    new_channel = channel
                    break

            # Delete the temporary channel
            await retry_on_rate_limit(temp_channel.delete, reason="Template application complete")
            print("Temporary applying-template channel deleted")

            # Send final message to the new channel (or ctx if no new channel)
            if new_channel:
                await new_channel.send(f'Template "{template_name}" applied successfully!')
            else:
                try:
                    await ctx.author.send(f'✅ Template "{template_name}" applied successfully!')
                except:
                    print("Could not DM user")
        except Exception as e:
            print(f"Failed to delete temporary channel: {str(e)}")
            await ctx.send(f'Template "{template_name}" applied successfully, but failed to delete temporary channel: {str(e)}')
    else:
        try:
            await ctx.author.send(f'✅ Template "{template_name}" applied successfully!')
        except:
            print("Could not DM user")

    print(f"Template {template_name} applied successfully!")

@applytemplate.error
async def applytemplate_error(ctx, error):
    print(f"Error in applytemplate: {str(error)}")
    if isinstance(error, commands.MissingRole):
        await ctx.send("You need to be the Raja of this server :moyai: !")
    elif isinstance(error, discord.Forbidden):
        await ctx.send("I don't have permission to create/delete channels or roles. Please check my permissions.")
    else:
        await ctx.send(f"An unexpected error occurred: {str(error)}")
        print(f"Unexpected error in applytemplate: {str(error)}")

# --------------------------
# 🎵 MUSIC COMMANDS
# --------------------------
# yt-dlp configuration
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'executable': r'D:\ffmpeg-2026-02-04-git-627da111c-essentials_build\bin\ffmpeg.exe'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Music queue
queues = {}

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):  # stream=False is more reliable
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def check_queue(ctx, guild_id):
    if queues.get(guild_id):
        player = queues[guild_id].pop(0)

        def after_playing(error):
            if error:
                print(f"Playback error: {error}")
            future = asyncio.run_coroutine_threadsafe(check_queue(ctx, guild_id), bot.loop)
            try:
                future.result()
            except Exception as e:
                print(f"Error continuing queue: {e}")

        ctx.voice_client.play(player, after=after_playing)
        asyncio.run_coroutine_threadsafe(ctx.send(f'Now playing: {player.title}'), bot.loop)

@bot.command(name="play")
async def play(ctx, *, url):
    """Play a song from a YouTube URL."""
    if not ctx.author.voice:
        return await ctx.send('You need to be in a voice channel to play music!')

    channel = ctx.author.voice.channel
    if not ctx.voice_client:
        await channel.connect()

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)  # Use stream=False
        guild_id = ctx.guild.id

        if guild_id not in queues:
            queues[guild_id] = []

        if ctx.voice_client.is_playing():
            queues[guild_id].append(player)
            await ctx.send(f'Added to queue: {player.title}')
        else:
            ctx.voice_client.play(player, after=lambda e: check_queue(ctx, guild_id))
            await ctx.send(f'Now playing: {player.title}')

@play.error
async def play_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide a YouTube URL to play.")
    else:
        await ctx.send(f"An error occurred: {str(error)}")

@bot.command(name="skip")
async def skip(ctx):
    """Skip the current song."""
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        return await ctx.send('No music is playing!')
    ctx.voice_client.stop()
    await ctx.send('Skipped song.')

@skip.error
async def skip_error(ctx, error):
    await ctx.send(f"An error occurred: {str(error)}")

@bot.command(name="stop")
async def stop(ctx):
    """Stop music and disconnect the bot from the voice channel."""
    if not ctx.voice_client:
        return await ctx.send('Not connected to a voice channel!')
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    await ctx.voice_client.disconnect()
    queues.pop(ctx.guild.id, None)
    await ctx.send('Stopped music and disconnected.')

@stop.error
async def stop_error(ctx, error):
    await ctx.send(f"An error occurred: {str(error)}")

# --------------------------
# 🔢 CALCULATOR COMMAND
# --------------------------
@bot.command(name="calc", aliases=['calculate'])
async def calculate(ctx, *, expression: str):
    """Calculates a simple mathematical expression."""
    
    # 1. Clean and validate the expression
    # Allows numbers, basic operators (+-*/), parentheses, and spaces.
    # Replaces 'x' or 'X' with '*' for multiplication.
    safe_expression = expression.replace('x', '*').replace('X', '*')
    
    # Check for disallowed characters (protects against code injection)
    # The pattern checks if the expression contains anything OTHER than
    # numbers, +, -, *, /, ., and spaces.
    if re.search(r'[^\d+\-*/.()\s]', safe_expression):
        await ctx.send(
            embed=discord.Embed(
                title=":x: Invalid Input",
                description="Please use only numbers and basic operators (+, -, *, /).",
                color=THEME["moderation"]
            )
        )
        return

    # 2. Safely evaluate the expression
    try:
        # The eval() function is generally dangerous, but restricted use with 
        # minimal input validation is often used for simple calculators.
        # For a truly safe implementation, you'd use a parser/AST.
        result = eval(safe_expression)
        
        # Format the result to two decimal places
        output_str = f"{result:.2f}"
        
        # 3. Create and send the embed
        embed = discord.Embed(
            title="<:calc:1432718933659750591> Calculator",
            color=THEME["utility"]  # Green color for success
        )
        
        # Use a non-breaking space character (U+200b) for formatting
        embed.add_field(name="Input :", value=f"```\n{expression}\n```", inline=False)
        embed.add_field(name="Output :", value=f"```\n{output_str}\n```", inline=False)
        
        # Footer based on your existing bot theme
        embed.set_footer(text="POWERED BY FAITH MM | .gg/faithmm")
        
        await ctx.send(embed=embed)
        
    except (SyntaxError, NameError, ZeroDivisionError) as e:
        await ctx.send(
            embed=discord.Embed(
                title=":warning: Calculation Error",
                description=f"Could not calculate the expression: **{type(e).__name__}**",
                color=THEME["utility"]
            )
        )
    except Exception as e:
        print(f"Unexpected error in .calc: {e}")
        await ctx.send("An unexpected error occurred during calculation.")

@calculate.error
async def calculate_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide an expression to calculate, e.g., `.calc 5 * 10 / (2 - 1)`")
    else:
        # Handle other potential errors like permission issues (though none are applied here)
        print(f"Error in calculate command: {error}")

# //////////////////////////////////////////////////////////////////////////

# --------------------------
# 🧠 HELP / CMD PANEL SYSTEM
# --------------------------
from discord.ui import View, Button, Select

# ---------- CATEGORY DATA ----------
def get_categories():
    return {
        "💰 Payment": [
            ".setltc", ".setupi", ".myqr", ".ltc"
        ],
        "💥 Moderation": [
            ".nuke", ".savetemplate", ".applytemplate"
        ],
        "📜 Info": [
            ".tos", ".rules"
        ],
        "🎵 Music": [
            ".play", ".skip", ".stop"
        ],
        "🔢 Utility": [
            ".calc", ".ping"
        ],
        "👑 Staff (Team Faith)": [
            ".ltc @user", ".ltclist", ".ltcstats", ".ltcsearch"
        ],
        "⚡ System": [
            ".help", ".cmd", ".comeback"
        ],
        "🌐 Slash": [
            "/bal", "/client", "/giveroleall"
        ]
    }

# ---------- HELP COMMAND ----------
# @bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📖 Command Center",
        description="Use `.cmd` for interactive panel\n\nSelect a category below 👇",
        color=THEME["system"]
    )

    for category, cmds in get_categories().items():
        embed.add_field(
            name=category,
            value="`" + "`, `".join(cmds) + "`",
            inline=False
        )

    embed.set_footer(text="Faith MM • Command System")

    await ctx.send(embed=embed)


# ---------- PING ----------
@bot.command(name="ping")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong: `{latency}ms`")


# ---------- DROPDOWN ----------
class CommandSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=cat, description=f"View {cat} commands")
            for cat in get_categories().keys()
        ]
        super().__init__(placeholder="Choose a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        cmds = get_categories()[category]

        embed = discord.Embed(
            title=f"{category} Commands",
            description="`" + "`, `".join(cmds) + "`",
            color=THEME["system"]
        )

        await interaction.response.edit_message(embed=embed, view=self.view)


# ---------- BUTTON VIEW ----------
class CmdView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CommandSelect())

        # Quick buttons
        self.add_item(Button(label="Help", style=discord.ButtonStyle.primary, custom_id="help_btn"))
        self.add_item(Button(label="Ping", style=discord.ButtonStyle.secondary, custom_id="ping_btn"))


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data["custom_id"] == "help_btn":
            await help_cmd(await bot.get_context(interaction.message))

        elif interaction.data["custom_id"] == "ping_btn":
            latency = round(bot.latency * 1000)
            await interaction.response.send_message(f"🏓 Pong: `{latency}ms`", ephemeral=True)


# ---------- CMD PANEL ----------
@bot.command(name="cmd")
async def cmd_panel(ctx):
    embed = discord.Embed(
        title="⚡ Command Panel",
        description="Use dropdown or buttons below",
        color=THEME["system"]
    )

    embed.set_footer(text="Faith MM • Interactive Panel")

    await ctx.send(embed=embed, view=CmdView())

# //////////////////////////////////////////////////////////////////////////

# --------------------------
# 🚀 ADVANCED SYSTEM UPGRADE
# --------------------------

from collections import defaultdict

# ---------- 🎨 THEME ----------
THEME_COLOR = discord.Color.from_rgb(120, 20, 255)  # change color here

# ---------- 📊 USAGE TRACKING ----------
command_usage = defaultdict(int)

@bot.event
async def on_command(ctx):
    command_usage[ctx.command.name] += 1

# ---------- 🔐 ROLE-BASED CATEGORIES ----------
def get_categories_for(user):
    categories = {
        "💰 Payment": [".setltc", ".setupi", ".myqr"],
        "📜 Info": [".tos", ".rules"],
        "🎵 Music": [".play", ".skip", ".stop"],
        "🔢 Utility": [".calc"],
        "⚡ General": [".ping", ".help", ".cmd"]
    }

    # Add restricted ones only if user has role
    if discord.utils.get(user.roles, name="Raja"):
        categories["💥 Raja"] = [".nuke", ".savetemplate", ".applytemplate", ".comeback"]

    if discord.utils.get(user.roles, name="Team Faith"):
        categories["👑 Team"] = [".setltc", ".setupi", ".myqr"]

    return categories

# ---------- 🤖 AUTO SUGGEST ----------
def suggest_command(input_cmd):
    all_cmds = [
        "setltc","setupi","myqr","nuke","tos","rules",
        "savetemplate","applytemplate","play","skip","stop",
        "calc","comeback","help","ping","cmd"
    ]
    matches = [c for c in all_cmds if input_cmd in c]
    return matches[:3]

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        guess = suggest_command(ctx.message.content.replace(".", ""))
        if guess:
            await ctx.send(f"❌ Command not found. Did you mean: `{', '.join('.'+g for g in guess)}`?")
        else:
            await ctx.send("❌ Unknown command.")
    else:
        raise error

# ---------- 📖 UPDATED HELP ----------
@bot.command(name="help")
async def help_cmd(ctx):
    categories = get_categories_for(ctx.author)

    embed = discord.Embed(
        title="📖 Command Center",
        description="Use `.cmd` for interactive panel",
        color=THEME["system"]
    )

    for cat, cmds in categories.items():
        embed.add_field(
            name=cat,
            value="`" + "`, `".join(cmds) + "`",
            inline=False
        )

    embed.set_footer(text="Faith MM • Smart System")

    await ctx.send(embed=embed)

# ---------- 📊 STATS COMMAND ----------
@bot.command(name="stats")
@commands.has_role("Raja")
async def stats(ctx):
    if not command_usage:
        return await ctx.send("No command usage yet.")

    sorted_usage = sorted(command_usage.items(), key=lambda x: x[1], reverse=True)

    text = "\n".join([f"`.{cmd}` → {count} uses" for cmd, count in sorted_usage[:10]])

    embed = discord.Embed(
        title="📊 Command Usage Stats",
        description=text,
        color=THEME_COLOR
    )

    await ctx.send(embed=embed)

# --------------------------
# 🛒 BYPASS PANEL COMMAND
# --------------------------
class PurchasePanelView(discord.ui.View):
    def __init__(self):
        # timeout=None ensures the button doesn't stop working after the bot restarts
        super().__init__(timeout=None)
        
        # Replace these IDs with your actual Server ID and Ticket Channel ID
        ticket_channel_url = "https://discord.com/channels/1493999179280678912/1495823475208618156"
        
        self.add_item(discord.ui.Button(
            label="Purchase - Now", 
            url=ticket_channel_url, 
            emoji="🛒"
        ))

@bot.command(name="bypass")
@commands.has_role("Team Faith") # Securing it so only your team can send the panel
async def send_panel(ctx):
    # Creating the Embed matching your screenshot
    embed = discord.Embed(
        title="Emulator Bypass - Free Fire | Safe All Server",
        description=(
            "───────────────────────\n\n"
            "**Prices :**\n\n"
            "7 Days = $3 USD / 300 INR\n\n"
            "14 Days = $5 USD / 500 INR\n\n"
            "30 Days = $8.50 USD / 850 INR\n\n"
            "───────────────────────"
        ),
        color=discord.Color.red() # Creates the red side strip
    )
    
    # You must upload your banner image somewhere (like Imgur or a Discord channel)
    # Right-click it, "Copy Image Address", and paste it below.
    embed.set_image(url="https://cdn.discordapp.com/attachments/1495830730142515291/1511728746921594980/faithbypassemulator.png?ex=6a21829b&is=6a20311b&hm=df56c42394c1c4bac41515d235b7b8bc2298617f4c286dc9e291c3ae9d2e1964&")
    
    # Setting the footer and timestamp
    embed.set_footer(text=" Faith Cheats © 2025 | by faith.cheetah")
    embed.timestamp = discord.utils.utcnow() # Automatically adds the current time
    
    await ctx.send(embed=embed, view=PurchasePanelView())

# =========================================================================


# --------------------------
# 📜 FEATURES PANEL COMMAND
# --------------------------
@bot.command(name="silentaim")
@commands.has_role("Team Faith")
async def send_features(ctx):
    # The massive feature list formatted for Discord
    description_text = (
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "**Aim Functions**\n\n"
        "Enable Aim Functions\nEnable Fov Adjuster\nEnable Right FOV Adjuster\n"
        "Use FOV\nDraw FOV Circle\nIgnore Knocked\nIgnore Training Bot\n"
        "Aim Collider\nAim Track\nHead Track\nBullet Spread\nKeyBind Support\n\n\n"
        
        "**Exploits**\n\n"
        "Magnet Enemy\nTele Enemy (7 m)\nHit Sound (Sound Options)\nNo Expose Fire\n"
        "No Hit Delay\nV badge Player\nForce Shoot\nRemove Weapon Swap Time\n"
        "Instant Reload\nInfinite Ammo\nNo Spread\nDive Player\nSpin Bot\n"
        "Speed Hack\nWall Push\nFake Lag\n\n\n"
        
        "**ESP / Players**\n\n"
        "Enable ESP\nEnable ESP Preview\nShow All Entities\nRainbow ESP\n"
        "Snap Line\nESP Box\nFill Box\nPlayer Name\nPlayer Health\nPlayer Armor\n"
        "Player Bones\nPlayer Weapon On Hand\nPlayer Weapon Name\nPlayer Distance\n"
        "FOV Arrow\nClosest Tracer\nSkill Active\nGlow Line\nGlow Box\n"
        "Glow Weapon\nGlow Skeleton\n\n\n"
        
        "**World ESP**\n\n"
        "Vehicles\nVehicle FOV Arrow\nLandmines\nCyber Mushrooms\nLoot\n"
        "Grenade Tracers\nESP Radar\n\n\n"
        
        "**Visual / Misc Render**\n\n"
        "Crosshair\nChams Static\nCelest\nWhite Bodies\nHDR Map\nGlitch\nNight Sky\n\n\n"
        
        "**Settings / Config**\n\n"
        "Stream Proof\nMenu Particles\nWatermark\nShow Keybinds\nTheme Changer\n"
        "Visual Name (In Game)\nConfig System ( Save / New/ Delete/ Share)\n"
        "Auto Load\nNotify On Load\n\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )

    # Creating the Embed
    embed = discord.Embed(
        description=description_text,
        color=0x00bfff # Hex code for the Cyan/Light Blue strip in your image
    )
    
    # Add the Free Fire Peak banner image here
    embed.set_image(url="https://cdn.discordapp.com/attachments/1495830730142515291/1512147918742753451/Gemini_Generated_Image_rzrlr7rzrlr7rzrl.png?ex=6a2308fe&is=6a21b77e&hm=1fe56b1054aa92c092c2dfe61aeb06543a80fde6c8fda102e43e90599fbea898&")
    
    # Updated footer
    embed.set_footer(text="FaithCheats © 2026")
    
    # Sending the embed and reusing the Purchase button view we made earlier
    await ctx.send(embed=embed, view=PurchasePanelView())




import re
import random

# ===============================
# 🔴 YOUTUBE FORWARDER & AUTO-DELETE
# ===============================

YT_LINK_CHANNEL_ID = 1496763544174198794 # Where you drop the link
YT_ANNOUNCEMENT_CHANNEL_ID = 1496763544174198794 # Where the bot announces it
AUTO_DELETE_CHANNEL_ID = 1495823464785907803 # ⚠️ The "Nuke Everything" channel

@bot.event
async def on_message(message):
    # 1. Ignore ALL messages from bots (This protects your bot's own messages!)
    if message.author.bot:
        return

    # ==========================================
    # 🛑 INSTANT AUTO-DELETE CHANNEL
    # ==========================================
    if message.channel.id == AUTO_DELETE_CHANNEL_ID:
        try:
            await message.delete()
        except Exception as e:
            print(f"Could not delete message in auto-delete channel: {e}")
        
        # We return here so the bot stops looking at this message entirely
        return 

    # ==========================================
    # 🔴 YOUTUBE LINK FORWARDER CHANNEL
    # ==========================================
    if message.channel.id == YT_LINK_CHANNEL_ID:
        
        yt_pattern = re.compile(r"(?:youtube\.com/.*[?&]v=|youtu\.be/)([a-zA-Z0-9_-]{11})")
        match = yt_pattern.search(message.content)

        if match:
            video_id = match.group(1)
            clean_url = f"https://youtu.be/{video_id}"
            
            dest_channel = bot.get_channel(YT_ANNOUNCEMENT_CHANNEL_ID)
            if dest_channel is None:
                try:
                    dest_channel = await bot.fetch_channel(YT_ANNOUNCEMENT_CHANNEL_ID)
                except Exception as e:
                    print(f"Error fetching destination channel: {e}")
                    return
            
            # Announce it!
            await dest_channel.send(f"{clean_url}\n@everyone @here")
            
            # ✅ CHANGED: Delete your original message so the drop channel stays empty
            try:
                await message.delete()
            except Exception as e:
                print(f"Could not delete valid link message: {e}")
                
        else:
            try:
                await message.delete()
            except Exception as e:
                print(f"Could not delete message: {e}")
            
            insults = [
                f"F. OFF {message.author.mention} ITS NOT A VID URL MASTER 🤬",
                f"Are you blind {message.author.mention}? Put a YouTube link or get out of here! 🗑️",
                f"Bro {message.author.mention} really thought they could sneak a normal message in here. DENIED. 🛑",
                f"My brother in Christ {message.author.mention}, that is NOT a YouTube link. Try again. 🤡",
                f"... {message.author.mention}, did you even read the channel name? YT LINKS ONLY! 😤",
                f"Hey {message.author.mention}, That wasn't your personal chat. Drop a YouTube link or take a hike! 🚶‍♂️",
                f"Yo {message.author.mention}, this was a YouTube link channel, not your diary. Post a valid link or scram! 🏃‍♂️",
                f"MF {message.author.mention} really out here treating the YouTube drop channel like a general chat. This is why we can't have nice things! 😡",
                f"LODE {message.author.mention} PUT A YOUTUBE LINK OR GET OUT OF HERE! THIS IS NOT A CHAT CHANNEL! 🤬",
                f"Muththal saale {message.author.mention} YouTube link daalna itna mushkil hai kya? Nahi toh nikal yahan se! 🗑️",
                f"Naah yaar {message.author.mention}, this is a YouTube link channel, not your personal chat. Drop a valid link or scram! 🏃‍♂️"
            ]
            
            # Slide into their DMs with the insult
            try:
                await message.author.send(random.choice(insults))
            except discord.Forbidden:
                # This catches the error if the user has their server DMs turned off
                print(f"Could not DM {message.author.name} - they have DMs disabled.")
            
        # Return here so we don't accidentally process YouTube links as commands
        return

    # ⚠️ CRITICAL: Needed so normal commands like .help still work in all other channels!
    await bot.process_commands(message)


#===============================================================

# ======================================================================================================================
###     TEST TICKET CODES   ###
# --------------------------
# 🎫 TICKET SYSTEM LOGIC
# --------------------------


class CreateTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_btn", emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        # 1. Setup Permissions (Private channel)
        staff_role = discord.utils.get(guild.roles, name="Team Faith")
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False), # Hides from @everyone
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)

        # 2. Check for (or create) a Ticket Category
        category = discord.utils.get(guild.categories, name="🎫 Tickets")
        if not category:
            category = await guild.create_category("🎫 Tickets")

        # 3. Create the text channel
        try:
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{user.name}",
                category=category,
                overwrites=overwrites
            )
        except Exception as e:
            return await interaction.response.send_message("❌ Failed to create ticket. Check my permissions.", ephemeral=True)

        # 4. Confirm to user
        await interaction.response.send_message(f"✅ Ticket created! Jump in: {ticket_channel.mention}", ephemeral=True)

        # 5. Send Welcome message inside the ticket
        welcome_embed = discord.Embed(
            title="Thank you for reaching out!",
            description=(
                f"Welcome {user.mention},\n\n"
                "Please describe what you are looking to purchase or need help with. "
                "Our **Team Faith** staff will be with you shortly.\n\n"
                "*(Click the button below to close this ticket when finished)*"
            ),
            color=THEME["system"]
        )
        welcome_embed.set_footer(text="Faith MM • Secure Ticket")
        
        await ticket_channel.send(
            content=f"{user.mention} | <@&{staff_role.id if staff_role else ''}>", 
            embed=welcome_embed, 
            view=TicketControlView()
        )

# --------------------------
# 🎫 SEND TICKET PANEL CMD
# --------------------------
@bot.command(name="ticketpanel")
@commands.has_role("Team Faith")
async def ticket_panel(ctx):
    embed = discord.Embed(
        title="🛒 Support & Purchases",
        description=(
            "To buy **Emulator Bypasses**, **Cheats**, or request **Middleman Services**, "
            "please open a secure ticket.\n\n"
            "**Guidelines:**\n"
            "• Have your payment method ready (Crypto/UPI).\n"
            "• Be patient, staff will respond ASAP.\n"
            "• Do not ping staff unnecessarily."
        ),
        color=THEME["system"]
    )
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    embed.set_footer(text="Faith MM • Ticket System")

    await ctx.send(embed=embed, view=CreateTicketView())
    await ctx.message.delete() # Cleans up the .ticketpanel command message



###### TRANSCRIPTSSSS #########
import motor.motor_asyncio
import chat_exporter

MONGO_URI = os.environ.get("MONGO_URI")
db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = db_client["faith_tickets"] # Name of the database
collection = db["transcripts"]  # Name of the folder inside the database

# ADD THIS LINE: A new folder in the database just for user data
users_collection = db["users"]

TICKET_LOG_CHANNEL_ID = 1512371653496148129


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        user = interaction.user
        guild = interaction.guild

        if not discord.utils.get(user.roles, name="Team Faith") and user.name not in channel.name:
            return await interaction.response.send_message("You cannot close this ticket.", ephemeral=True)

        await interaction.response.send_message("🔒 **Locking ticket.** Backing up transcript...", ephemeral=False)

        # 1. Lockdown
        ticket_owner = discord.utils.get(guild.members, name=channel.name.replace("ticket-", ""))
        if ticket_owner:
            await channel.set_permissions(ticket_owner, send_messages=False)

        # 2. Scrape the HTML
        try:
            transcript_html = await chat_exporter.export(channel)
            
            ticket_id = f"{channel.name}-{interaction.message.id}"
            
            # Save to MongoDB
            await collection.insert_one({
                "_id": ticket_id,
                "html_content": transcript_html,
                "closed_by": user.name
            })
            
            # Create the physical file for Discord
            import io
            transcript_file = discord.File(
                io.BytesIO(transcript_html.encode()),
                filename=f"{ticket_id}.html"
            )
            
        except Exception as e:
            print(f"Transcript Error: {e}")
            await channel.send("❌ Failed to save transcript.")
            await asyncio.sleep(5)
            return await channel.delete(reason="Ticket closed (Transcript Failed)")

        # 3. Delivery (Send BOTH File and Embed Link)
        log_channel = guild.get_channel(TICKET_LOG_CHANNEL_ID)
        if log_channel:
            transcript_link = f"https://your-site.onrender.com/transcript/{ticket_id}"
            
            embed = discord.Embed(
                title="🎫 Ticket Closed",
                description=f"**Ticket:** {channel.name}\n**Closed By:** {user.mention}\n\n🔗 **[View Transcript Online]({transcript_link})**",
                color=discord.Color.green()
            )
            embed.set_footer(text="Faith MM • Ticket Logs")
            
            # Notice we attached file=transcript_file here!
            await log_channel.send(embed=embed, file=transcript_file)

        # 4. The Nuke
        await channel.delete(reason=f"Ticket closed by {user.name}")


# --------------------------
# 🚀 START BOT
# --------------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    
    # --- ADD THESE TWO LINES TO MAKE BUTTONS PERSISTENT ---
    bot.add_view(CreateTicketView())
    bot.add_view(TicketControlView())
    
    print(f"Bot is online as {bot.user}")
    print(f"Prefix: {bot.command_prefix}")
    print(f"Guilds: {len(bot.guilds)}")
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id})")
        await ensure_roles_exist(guild, ["Team Faith", "~ Clients"])
        

keep_alive()
bot.run(TOKEN)
