import discord
from discord import app_commands, SelectOption
from discord.ext import commands, tasks
from discord.ui import View, Button, Select, Modal, TextInput
import json
import os
from dotenv import load_dotenv
import re
import asyncio
import datetime

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="&", intents=intents)
bot.remove_command('help')

BAD_WORDS = ["nigger", "jobless", "kys"]
DATA_FOLDER = "guild_data"

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

BOT_CREATOR_ID = 889652253227622471

def get_guild_file(guild_id, key):
    return os.path.join(DATA_FOLDER, f"{guild_id}_{key}.json")

def load_guild_data(guild_id, key, default):
    path = get_guild_file(guild_id, key)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def get_deleted_logs_file(guild_id):
    return os.path.join(DATA_FOLDER, f"{guild_id}_deleted_logs.json")

def save_deleted_log_content(guild_id, message_id, content):
    file_path = get_deleted_logs_file(guild_id)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data[str(message_id)] = content
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_deleted_log_content(guild_id, message_id):
    file_path = get_deleted_logs_file(guild_id)
    if not os.path.exists(file_path):
        return "Message unavailable"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(str(message_id), "Message unavailable")

def delete_deleted_log_content(guild_id, message_id):
    file_path = get_deleted_logs_file(guild_id)
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if str(message_id) in data:
        del data[str(message_id)]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

def save_guild_data(guild_id, key, data):
    path = get_guild_file(guild_id, key)
    with open(path, "w") as f:
        json.dump(data, f)

def get_permissions_roles(guild_id):
    return load_guild_data(guild_id, "permissions", {"perm1": [], "perm2": [], "perm3": []})

def save_permissions_roles(guild_id, perms):
    save_guild_data(guild_id, "permissions", perms)

def get_blacklist(guild_id):
    return set(load_guild_data(guild_id, "blacklist", []))

def save_blacklist(guild_id, blacklist):
    save_guild_data(guild_id, "blacklist", list(blacklist))

def get_owners(guild_id):
    return set(load_guild_data(guild_id, "owners", []))

def save_owners(guild_id, owners):
    save_guild_data(guild_id, "owners", list(owners))


def save_user_message(guild_id, user_id):
    key = "messages"
    data = load_guild_data(guild_id, key, {})
    now = datetime.datetime.utcnow().isoformat()
    if str(user_id) not in data:
        data[str(user_id)] = []
    data[str(user_id)].append(now)
    save_guild_data(guild_id, key, data)

def parse_duration(duration_str):
    pattern = r"(\d+)([smhd])"
    match = re.fullmatch(pattern, duration_str.strip().lower())
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    return None

def get_logs_channel_id(guild_id):
    return load_guild_data(guild_id, "logs", None)

def save_logs_channel_id(guild_id, channel_id):
    save_guild_data(guild_id, "logs", channel_id)

def has_perm(ctx, perm):
    perms = get_permissions_roles(ctx.guild.id)
    user_roles = [role.id for role in ctx.author.roles]
    allowed_roles = perms.get(perm, [])
    return any(role_id in allowed_roles for role_id in user_roles)

def has_perm_slash(interaction, perm):
    perms = get_permissions_roles(interaction.guild.id)
    user_roles = [role.id for role in interaction.user.roles]
    allowed_roles = perms.get(perm, [])
    return any(role_id in allowed_roles for role_id in user_roles)


def is_owner(ctx):
    owners = get_owners(ctx.guild.id)
    return ctx.author.id == BOT_CREATOR_ID or ctx.author.id in owners

def is_owner_slash(interaction):
    owners = get_owners(interaction.guild.id)
    return interaction.user.id == BOT_CREATOR_ID or interaction.user.id in owners

def extract_user_id(arg):
    if arg.startswith("<@") and arg.endswith(">"):
        arg = arg.replace("<@", "").replace(">", "").replace("!", "")
    return int(arg)

def has_perm1_or_higher(message):
    perms = get_permissions_roles(message.guild.id)
    user_roles = [role.id for role in message.author.roles]
    for perm in ["perm1", "perm2", "perm3"]:
        allowed_roles = perms.get(perm, [])
        if any(role_id in allowed_roles for role_id in user_roles):
            return True
    owners = get_owners(message.guild.id)
    if message.author.id == BOT_CREATOR_ID or message.author.id in owners:
        return True
    return False

class DeletedMessageView(View):
    def __init__(self, message_content, guild_id):
        super().__init__(timeout=None)
        self.message_content = message_content
        self.guild_id = guild_id

    @discord.ui.button(label="Restore", style=discord.ButtonStyle.green, emoji="🔄", custom_id="restore_msg_btn")
    async def restore(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"Restored message:\n```{self.message_content}```",
            ephemeral=True
        )

    @discord.ui.button(label="Delete log", style=discord.ButtonStyle.red, emoji="🗑️", custom_id="delete_log_btn")
    async def delete_permanently(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Log deleted.", ephemeral=True
        )
        delete_deleted_log_content(self.guild_id, interaction.message.id)
        await interaction.message.delete()


async def log_ticket_action(guild, action, user, ticket_channel=None):
    channel_id = get_logs_channel_id(guild.id)
    if not channel_id:
        return
    logs_channel = guild.get_channel(channel_id)
    if not logs_channel:
        return
    embed = discord.Embed(
        title=f"🎫 Ticket {action}",
        color=discord.Color.green() if action == "Opened" else discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="User", value=user.mention, inline=True)
    if ticket_channel:
        embed.add_field(name="Channel", value=ticket_channel.mention, inline=True)
    await logs_channel.send(embed=embed)

async def log_mod_action_embed(guild, title, fields, color=discord.Color.blue(), author=None):
    channel_id = get_logs_channel_id(guild.id)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                embed = discord.Embed(
                    title=title,
                    color=color,
                    timestamp=datetime.datetime.utcnow()
                )
                if author:
                    embed.set_author(name=f"{author}", icon_url=author.avatar.url if hasattr(author, "avatar") and author.avatar else None)
                for name, value, inline in fields:
                    embed.add_field(name=name, value=value, inline=inline)
                embed.set_footer(text=f"Server: {guild.name} | ID: {guild.id}")
                await channel.send(embed=embed)
            except Exception as e:
                print(f"Error sending mod log: {e}")
        else:
            print("Log channel not found!")
    else:
        print("Log channel ID not found!")

async def log_deleted_message_embed(guild, author, content, channel, reason=None, message_url=None):
    logs_channel_id = get_logs_channel_id(guild.id)
    if not logs_channel_id:
        return
    logs_channel = guild.get_channel(logs_channel_id)
    if not logs_channel:
        return
    embed = discord.Embed(
        title="🗑️ Message Deleted",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_author(name=f"{author}", icon_url=author.avatar.url if hasattr(author, "avatar") and author.avatar else None)
    embed.add_field(name="Author", value=author.mention, inline=True)
    embed.add_field(name="Channel", value=channel.mention, inline=True)
    embed.add_field(name="Time", value=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), inline=False)
    embed.add_field(name="Content", value=f">>> {content}" if content else "*Empty message*", inline=False)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if message_url:
        embed.add_field(name="Jump to message", value=f"[Click here]({message_url})", inline=False)
    embed.set_footer(text=f"User ID: {author.id}")
    view = DeletedMessageView(content, guild.id)
    msg = await logs_channel.send(embed=embed, view=view)
    save_deleted_log_content(guild.id, msg.id, content)
    bot.add_view(DeletedMessageView(content, guild.id), message_id=msg.id)

# ----------- EVENTS -----------

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    try:
        synced = await bot.tree.sync()
        print(f"Global sync: {len(synced)} slash commands.")
    except Exception as e:
        print(f"Global sync failed: {e}")

    # Add persistent views for tickets and logs
    await setup_persistent_views()

    if not shadowrealm_timer.is_running():
        shadowrealm_timer.start()
        print("Shadowrealm timer started.")

@bot.event
async def on_guild_join(guild):
    # Ajoute automatiquement l'owner du serveur à la liste des owners
    owners = get_owners(guild.id)
    if guild.owner.id not in owners:
        owners.add(guild.owner.id)
        save_owners(guild.id, owners)
        print(f"Owner {guild.owner} added to the owners list for guild {guild.name}.")

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.guild:
        return

    # Bad words filtering
    for word in BAD_WORDS:
        if word in message.content.lower():
            await message.delete()
            await message.channel.send(
                f"{message.author.mention}, your message was deleted for inappropriate language.",
                delete_after=5
            )
            await log_deleted_message_embed(
                message.guild,
                message.author,
                message.content,
                message.channel,
                reason=f"Forbidden word: `{word}`",
                message_url=message.jump_url
            )
            return

    save_user_message(message.guild.id, message.author.id)

    # Custom command handling
    commands_data = load_guild_data(message.guild.id, "custom_commands", {})
    prefix = "&"  # Adjust according to your bot

    if message.content.startswith(prefix):
        cmd = message.content[len(prefix):].split(" ")[0]
        if cmd in commands_data:
            # --- Only allow perm1 or higher for usage ---
            if not has_perm1_or_higher(message):
                await message.channel.send("You need perm1 or higher to use this command.", delete_after=5)
                await message.delete()
                return
            content = commands_data[cmd]
            # Handle user mentions
            if "{mention}" in content and message.mentions:
                mentions = " ".join(user.mention for user in message.mentions)
                content = content.replace("{mention}", mentions)
            # Handle role assignment (accept role name or ID)
            if "{role:" in content:
                pattern = r"\{role:([^\}]+)\}"
                matches = re.findall(pattern, content)
                for role_str in matches:
                    role_str = role_str.strip()
                    role = None
                    if role_str.isdigit():
                        role = message.guild.get_role(int(role_str))
                    if not role:
                        role = discord.utils.get(message.guild.roles, name=role_str)
                    if role:
                        for user in message.mentions:
                            await user.add_roles(role)
                        content = content.replace(f"{{role:{role_str}}}", "")
                    else:
                        content = content.replace(f"{{role:{role_str}}}", "")
            await message.channel.send(content)
            await message.delete()
            return

    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if message.guild and message.author != bot.user:
        await log_deleted_message_embed(
            message.guild,
            message.author,
            message.content,
            message.channel,
            reason="Manual or other deletion",
            message_url=message.jump_url
        )

@bot.event
async def on_member_join(member):
    # Automatically add the server owner to the owners list
    if member.guild.owner.id not in get_owners(member.guild.id):
        owners = get_owners(member.guild.id)
        owners.add(member.guild.owner.id)
        save_owners(member.guild.id, owners)

    blacklist = get_blacklist(member.guild.id)
    if member.id in blacklist:
        try:
            await member.ban(reason="Blacklisted user tried to join.")
            await log_mod_action_embed(
                member.guild,
                title="🚫 Auto-Ban: Blacklisted User Joined",
                fields=[
                    ("User", member.mention, True),
                    ("User ID", str(member.id), True),
                    ("Reason", "Blacklisted user tried to join.", False)
                ],
                color=discord.Color.red(),
                author=member
            )
        except Exception:
            pass

# ----------- LOG MANUAL ROLE ADD/REMOVE -----------

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.guild is None:
        return
    logs_channel_id = get_logs_channel_id(before.guild.id)
    if not logs_channel_id:
        return
    logs_channel = before.guild.get_channel(logs_channel_id)
    if not logs_channel:
        return

    # Roles added
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    for role in added_roles:
        embed = discord.Embed(
            title="Role Added",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=after.mention, inline=True)
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.set_footer(text=f"User ID: {after.id}")
        await logs_channel.send(embed=embed)

    for role in removed_roles:
        embed = discord.Embed(
            title="Role Removed",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=after.mention, inline=True)
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.set_footer(text=f"User ID: {after.id}")
        await logs_channel.send(embed=embed)

# ----------- LOG MANUAL ROLE CREATE/DELETE -----------

@bot.event
async def on_guild_role_create(role):
    logs_channel_id = get_logs_channel_id(role.guild.id)
    if not logs_channel_id:
        return
    logs_channel = role.guild.get_channel(logs_channel_id)
    if not logs_channel:
        return

    embed = discord.Embed(
        title="Role Created",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="Role", value=role.mention, inline=True)
    embed.add_field(name="Role ID", value=role.id, inline=True)
    embed.set_footer(text=f"Server: {role.guild.name} | ID: {role.guild.id}")
    await logs_channel.send(embed=embed)

@bot.event
async def on_guild_role_delete(role):
    logs_channel_id = get_logs_channel_id(role.guild.id)
    if not logs_channel_id:
        return
    logs_channel = role.guild.get_channel(logs_channel_id)
    if not logs_channel:
        return

    embed = discord.Embed(
        title="Role Deleted",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="Role Name", value=role.name, inline=True)
    embed.add_field(name="Role ID", value=role.id, inline=True)
    embed.set_footer(text=f"Server: {role.guild.name} | ID: {role.guild.id}")
    await logs_channel.send(embed=embed)

# ----------- LOG MANUAL BAN/KICK -----------

@bot.event
async def on_member_ban(guild, user):
    logs_channel_id = get_logs_channel_id(guild.id)
    if not logs_channel_id:
        return
    logs_channel = guild.get_channel(logs_channel_id)
    if not logs_channel:
        return

    embed = discord.Embed(
        title="User Banned",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=True)
    embed.set_footer(text=f"Server: {guild.name} | ID: {guild.id}")
    await logs_channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    # This event triggers for both kick and voluntary leave; can't distinguish between them directly
    # Optionally, you can log every leave/kick here
    logs_channel_id = get_logs_channel_id(member.guild.id)
    if not logs_channel_id:
        return
    logs_channel = member.guild.get_channel(logs_channel_id)
    if not logs_channel:
        return

    embed = discord.Embed(
        title="User Left or Kicked",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
    embed.set_footer(text=f"Server: {member.guild.name} | ID: {member.guild.id}")
    await logs_channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have the required permissions to execute this command.", delete_after=10)
        await ctx.message.delete()
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Use `&help` to see the list of available commands.", delete_after=10)
        await ctx.message.delete()
    else:
        print(f"Error in command {ctx.command}: {error}")


# ----------- LOGS MOD COMMAND -----------

@bot.command(name="logs_mod")
@commands.has_permissions(administrator=True)
async def set_logs_mod(ctx, channel: discord.TextChannel):
    if not is_owner(ctx):
        await ctx.send("Only owners can use this command.")
        await ctx.message.delete()
        return
    save_logs_channel_id(ctx.guild.id, channel.id)
    await ctx.message.delete()
    await ctx.send(f"Moderation logs channel set to {channel.mention}!")
    await log_mod_action_embed(
        ctx.guild,
        title="✅ Moderation Logs Channel Set",
        fields=[
            ("Set by", ctx.author.mention, True),
            ("Channel", channel.mention, True)
        ],
        color=discord.Color.green(),
        author=ctx.author
    )

@bot.tree.command(name="logs_mod", description="Set the moderation logs channel")
@app_commands.describe(channel="Moderation logs channel")
async def logs_mod_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_owner_slash(interaction):
        await interaction.response.send_message("Only owners can use this command.", ephemeral=True)
        return
    save_logs_channel_id(interaction.guild.id, channel.id)
    await interaction.response.send_message(f"Moderation logs channel set to {channel.mention}!", ephemeral=True)
    await log_mod_action_embed(
        interaction.guild,
        title="✅ Moderation Logs Channel Set",
        fields=[
            ("Set by", interaction.user.mention, True),
            ("Channel", channel.mention, True)
        ],
        color=discord.Color.green(),
        author=interaction.user
    )

# ----------- BAN, KICK, TIMEOUT, UNTIMEOUT -----------
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_normal(ctx, member: discord.Member, *, reason: str = None):
    if member.id == BOT_CREATOR_ID:
        await ctx.send("You cannot ban the creator of the bot.", delete_after=5)
        return
    if not has_perm(ctx, "perm3") and not is_owner(ctx):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot ban a member with a higher or equal top role.", delete_after=5)
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await member.ban(reason=reason)
    await ctx.send(f"{member} has been banned.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="⛔ Ban",
        fields=[
            ("By", ctx.author.mention, True),
            ("User", member.mention, True),
            ("Reason", reason if reason else "No reason", False)
        ],
        color=discord.Color.red(),
        author=ctx.author
    )

@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if member.id == BOT_CREATOR_ID:
        await interaction.response.send_message("You cannot ban the creator of the bot.", ephemeral=True)
        return
    if not has_perm_slash(interaction, "perm3") and not is_owner_slash(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("You cannot ban a member with a higher or equal top role.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member} has been banned.")
        await log_mod_action_embed(
            interaction.guild,
            title="⛔ Ban",
            fields=[
                ("By", interaction.user.mention, True),
                ("User", member.mention, True),
                ("Reason", reason if reason else "No reason", False)
            ],
            color=discord.Color.red(),
            author=interaction.user
        )
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_normal(ctx, user: discord.User):
    if user.id == BOT_CREATOR_ID:
        await ctx.send("You cannot unban the creator of the bot.", delete_after=5)
        return
    owners = get_owners(ctx.guild.id)
    blacklist = get_blacklist(ctx.guild.id)
    if not (ctx.author.id == BOT_CREATOR_ID or ctx.author.id in owners or has_perm(ctx, "perm3")):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    if user.id in blacklist:
        await ctx.send("This user is blacklisted and cannot be unbanned.", delete_after=5)
        await ctx.message.delete()
        return
    try:
        await ctx.guild.unban(user)
        await ctx.message.delete()
        await ctx.send(f"{user.mention} has been unbanned.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="✅ Unban",
            fields=[
                ("By", ctx.author.mention, True),
                ("User", user.mention, True)
            ],
            color=discord.Color.green(),
            author=ctx.author
        )
    except Exception as e:
        await ctx.send(f"Error: {e}", delete_after=5)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_normal(ctx, member: discord.Member, *, reason: str = None):
    if member.id == BOT_CREATOR_ID:
        await ctx.send("You cannot kick the creator of the bot.", delete_after=5)
        return
    if not has_perm(ctx, "perm3") and not is_owner(ctx):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot kick a member with a higher or equal top role.", delete_after=5)
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await member.kick(reason=reason)
    await ctx.send(f"{member} has been kicked.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="👢 Kick",
        fields=[
            ("By", ctx.author.mention, True),
            ("User", member.mention, True),
            ("Reason", reason if reason else "No reason", False)
        ],
        color=discord.Color.orange(),
        author=ctx.author
    )

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick_slash(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if member.id == BOT_CREATOR_ID:
        await interaction.response.send_message("You cannot kick the creator of the bot.", ephemeral=True)
        return
    if not has_perm_slash(interaction, "perm3") and not is_owner_slash(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("You cannot kick a member with a higher or equal top role.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member} has been kicked.")
        await log_mod_action_embed(
            interaction.guild,
            title="👢 Kick",
            fields=[
                ("By", interaction.user.mention, True),
                ("User", member.mention, True),
                ("Reason", reason if reason else "No reason", False)
            ],
            color=discord.Color.orange(),
            author=interaction.user
        )
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.command(name="timeout", aliases=["to"])
@commands.has_permissions(moderate_members=True)
async def timeout_normal(ctx, member: discord.Member, duration: str, *, reason: str = None):
    if member.id == BOT_CREATOR_ID:
        await ctx.send("You cannot timeout the creator of the bot.", delete_after=5)
        return
    if not (has_perm(ctx, "perm1") or has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    match = re.match(r"^(\d+)([mh])$", duration.lower())
    if not match:
        msg = await ctx.send("Invalid duration format. Use `10m` for minutes or `2h` for hours.", delete_after=5)
        return
    value, unit = int(match.group(1)), match.group(2)
    delta = datetime.timedelta(hours=value) if unit == "h" else datetime.timedelta(minutes=value)
    until = datetime.datetime.now(datetime.timezone.utc) + delta
    try:
        await member.timeout(until, reason=reason)
        msg = await ctx.send(f"{member.mention} has been timed out for {value}{unit}.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="🔇 Timeout",
            fields=[
                ("By", ctx.author.mention, True),
                ("User", member.mention, True),
                ("Duration", f"{value}{unit}", True),
                ("Reason", reason if reason else "No reason", False)
            ],
            color=discord.Color.orange(),
            author=ctx.author
        )
    except discord.Forbidden:
        msg = await ctx.send("I don't have permission to timeout this member (check bot role and permissions).", delete_after=5)
    except AttributeError:
        msg = await ctx.send("Timeout is not available on this server (feature not enabled).", delete_after=5)
    except Exception as e:
        msg = await ctx.send(f"Failed to timeout {member.mention}: {e}", delete_after=5)

@bot.tree.command(name="timeout", description="Timeout (mute) a member temporarily")
@app_commands.describe(member="Member to timeout", duration="Duration (e.g. 10m or 2h)", reason="Reason for timeout")
async def timeout_slash(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
    if member.id == BOT_CREATOR_ID:
        await interaction.response.send_message("You cannot timeout the creator of the bot.", ephemeral=True)
        return
    if not (has_perm_slash(interaction, "perm1") or has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    match = re.match(r"^(\d+)([mh])$", duration.lower())
    if not match:
        await interaction.response.send_message("Invalid format. Use `10m` or `2h`.", ephemeral=True)
        return
    value, unit = int(match.group(1)), match.group(2)
    delta = datetime.timedelta(hours=value) if unit == "h" else datetime.timedelta(minutes=value)
    until = datetime.datetime.now(datetime.timezone.utc) + delta
    try:
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"{member.mention} has been timed out for {value}{unit}.")
        await log_mod_action_embed(
            interaction.guild,
            title="🔇 Timeout",
            fields=[
                ("By", interaction.user.mention, True),
                ("User", member.mention, True),
                ("Duration", f"{value}{unit}", True),
                ("Reason", reason if reason else "No reason", False)
            ],
            color=discord.Color.orange(),
            author=interaction.user
        )
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to timeout this member.", ephemeral=True)
    except AttributeError:
        await interaction.response.send_message("Timeout is not available on this server.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.command(name="untimeout", aliases=["uto"])
@commands.has_permissions(moderate_members=True)
async def untimeout_normal(ctx, member: discord.Member):
    if member.id == BOT_CREATOR_ID:
        await ctx.send("You cannot remove timeout from the creator of the bot.", delete_after=5)
        return
    if not (has_perm(ctx, "perm1") or has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await member.timeout(None, reason="Timeout removed by the owner.")
        msg = await ctx.send(f"{member.mention} has been removed from timeout.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="🔈 Timeout Removed",
            fields=[
                ("By", ctx.author.mention, True),
                ("User", member.mention, True)
            ],
            color=discord.Color.green(),
            author=ctx.author
        )
    except discord.Forbidden:
        msg = await ctx.send("I don't have permission to remove timeout from this member (check bot role and permissions).", delete_after=5)
    except AttributeError:
        msg = await ctx.send("Removing timeout is not available on this server (feature not enabled).", delete_after=5)
    except Exception as e:
        msg = await ctx.send(f"Failed to remove timeout from {member.mention}: {e}", delete_after=5)

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.describe(member="Member to remove timeout from")
async def untimeout_slash(interaction: discord.Interaction, member: discord.Member):
    if member.id == BOT_CREATOR_ID:
        await interaction.response.send_message("You cannot remove timeout from the creator of the bot.", ephemeral=True)
        return
    if not (has_perm_slash(interaction, "perm1") or has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await member.timeout(None, reason="Timeout removed by the owner.")
        await interaction.response.send_message(f"{member.mention} is no longer timed out.")
        await log_mod_action_embed(
            interaction.guild,
            title="🔈 Timeout Removed",
            fields=[
                ("By", interaction.user.mention, True),
                ("User", member.mention, True)
            ],
            color=discord.Color.green(),
            author=interaction.user
        )
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to remove timeout from this member.", ephemeral=True)
    except AttributeError:
        await interaction.response.send_message("Removing timeout is not available on this server.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)
# ----------- CLEAR -----------

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_normal(ctx, amount: int):
    if not (has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"{len(deleted)} messages deleted.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="🧹 Bulk Delete",
        fields=[
            ("By", ctx.author.mention, True),
            ("Channel", ctx.channel.mention, True),
            ("Amount", str(len(deleted)), True)
        ],
        color=discord.Color.orange(),
        author=ctx.author
    )
    for msg in deleted:
        await log_deleted_message_embed(
            ctx.guild,
            msg.author,
            msg.content,
            msg.channel,
            reason="Bulk delete by clear command",
            message_url=msg.jump_url
        )

@bot.tree.command(name="clear", description="Delete messages")
@app_commands.describe(amount="Number of messages to delete")
async def clear_slash(interaction: discord.Interaction, amount: int):
    if not (has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"{len(deleted)} messages deleted.", ephemeral=True)
    await log_mod_action_embed(
        interaction.guild,
        title="🧹 Bulk Delete",
        fields=[
            ("By", interaction.user.mention, True),
            ("Channel", interaction.channel.mention, True),
            ("Amount", str(len(deleted)), True)
        ],
        color=discord.Color.orange(),
        author=interaction.user
    )
    for msg in deleted:
        await log_deleted_message_embed(
            interaction.guild,
            msg.author,
            msg.content,
            msg.channel,
            reason="Bulk delete by clear command",
            message_url=msg.jump_url
        )

# ----------- RÔLES -----------

@bot.command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def addrole_normal(ctx, member: discord.Member, role: discord.Role):
    if not (has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await member.add_roles(role)
        await ctx.send(f"Role `{role.name}` added to {member.mention}.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="➕ Role Added",
            fields=[
                ("By", ctx.author.mention, True),
                ("User", member.mention, True),
                ("Role", role.name, True)
            ],
            color=discord.Color.green(),
            author=ctx.author
        )
    except Exception as e:
        await ctx.send(f"Error: {e}", delete_after=5)

@bot.tree.command(name="addrole", description="Add a role to a member")
@app_commands.describe(member="Member to add the role to", role="Role to add")
async def addrole_slash(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not (has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await member.add_roles(role)
        await interaction.response.send_message(f"Role `{role.name}` added to {member.mention}.")
        await log_mod_action_embed(
            interaction.guild,
            title="➕ Role Added",
            fields=[
                ("By", interaction.user.mention, True),
                ("User", member.mention, True),
                ("Role", role.name, True)
            ],
            color=discord.Color.green(),
            author=interaction.user
        )
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.command(name="removerole", aliases=["unaddrole"])
@commands.has_permissions(manage_roles=True)
async def removerole_normal(ctx, member: discord.Member, role: discord.Role):
    if not (has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    if role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot remove a role that is higher or equal to your top role.", delete_after=5)
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await member.remove_roles(role)
        await ctx.send(f"Role `{role.name}` removed from {member.mention}.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="➖ Role Removed",
            fields=[
                ("By", ctx.author.mention, True),
                ("User", member.mention, True),
                ("Role", role.name, True)
            ],
            color=discord.Color.red(),
            author=ctx.author
        )
    except Exception as e:
        await ctx.send(f"Error: {e}", delete_after=5)

@bot.tree.command(name="removerole", description="Remove a role from a member")
@app_commands.describe(member="Member to remove the role from", role="Role to remove")
async def removerole_slash(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not (has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    if role.position >= interaction.user.top_role.position and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("You cannot remove a role that is higher or equal to your top role.", ephemeral=True)
        return
    try:
        await member.remove_roles(role)
        await interaction.response.send_message(f"Role `{role.name}` removed from {member.mention}.")
        await log_mod_action_embed(
            interaction.guild,
            title="➖ Role Removed",
            fields=[
                ("By", interaction.user.mention, True),
                ("User", member.mention, True),
                ("Role", role.name, True)
            ],
            color=discord.Color.red(),
            author=interaction.user
        )
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.command(name="createrole")
@commands.has_permissions(manage_roles=True)
async def createrole_normal(ctx, name: str, color: str = "#ffffff"):
    if not (has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        color_value = int(color.lstrip("#"), 16)
        role = await ctx.guild.create_role(name=name, colour=discord.Colour(color_value))
        await ctx.send(f"Role `{role.name}` created!", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="🎨 Role Created",
            fields=[
                ("By", ctx.author.mention, True),
                ("Role", role.name, True),
                ("Color", color, True)
            ],
            color=discord.Color.green(),
            author=ctx.author
        )
    except Exception as e:
        await ctx.send(f"Error: {e}", delete_after=5)

@bot.tree.command(name="createrole", description="Create a role")
@app_commands.describe(name="Role name", color="Hex color (#ffffff)")
async def createrole_slash(interaction: discord.Interaction, name: str, color: str = "#ffffff"):
    if not (has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    try:
        color_value = int(color.lstrip("#"), 16)
        role = await interaction.guild.create_role(name=name, colour=discord.Colour(color_value))
        await interaction.response.send_message(f"Role `{role.name}` created!")
        await log_mod_action_embed(
            interaction.guild,
            title="🎨 Role Created",
            fields=[
                ("By", interaction.user.mention, True),
                ("Role", role.name, True),
                ("Color", color, True)
            ],
            color=discord.Color.green(),
            author=interaction.user
        )
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.command(name="deleterole", aliases=["delrole"])
@commands.has_permissions(manage_roles=True)
async def deleterole_normal(ctx, role: discord.Role):
    if not (has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    
    if role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot delete a role that is higher or equal to your top role.", delete_after=5)
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await role.delete()
        await ctx.send(f"Role `{role.name}` deleted.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="➖ Role Deleted",
            fields=[
                ("By", ctx.author.mention, True),
                ("Role", role.name, True)
            ],
            color=discord.Color.red(),
            author=ctx.author
        )
    except Exception as e:
        await ctx.send(f"Error: {e}", delete_after=5)

@bot.tree.command(name="deleterole", description="Delete a role")
@app_commands.describe(role="Role to delete")
async def deleterole_slash(interaction: discord.Interaction, role: discord.Role):
    if not (has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    if role.position >= interaction.user.top_role.position and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("You cannot delete a role that is higher or equal to your top role.", ephemeral=True)
        return
    try:
        await role.delete()
        await interaction.response.send_message(f"Role `{role.name}` deleted.")
        await log_mod_action_embed(
            interaction.guild,
            title="➖ Role Deleted",
            fields=[
                ("By", interaction.user.mention, True),
                ("Role", role.name, True)
            ],
            color=discord.Color.red(),
            author=interaction.user
        )
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

# ----------- BLACKLIST -----------

@bot.command(name="blacklist", aliases=["bl"])
async def blacklist_normal(ctx, user: str = None):
    owners = get_owners(ctx.guild.id)
    blacklist = get_blacklist(ctx.guild.id)
    if not (ctx.author.id == BOT_CREATOR_ID or ctx.author.id in owners):
        await ctx.send("Only owners can use this command.")
        await ctx.message.delete()
        return
    if not user:
        msg = await ctx.send("You must provide a user ID or mention. Example: `&bl 123456789012345678` or `&bl @User`", delete_after=5)
        await ctx.message.delete()
        return
    try:
        user_id = extract_user_id(user)
    except Exception:
        msg = await ctx.send("Invalid user ID or mention.", delete_after=5)
        await ctx.message.delete()
        return
    if user_id == BOT_CREATOR_ID or user_id in owners:
        msg = await ctx.send("You cannot blacklist or ban an owner or the bot creator.", delete_after=5)
        await ctx.message.delete()
        return
    blacklist.add(user_id)
    save_blacklist(ctx.guild.id, blacklist)
    await ctx.message.delete()
    msg = await ctx.send(f"<@{user_id}> has been blacklisted and will be banned from this server.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="🚫 Blacklist",
        fields=[
            ("By", ctx.author.mention, True),
            ("User", f"<@{user_id}>", True)
        ],
        color=discord.Color.red(),
        author=ctx.author
    )
    try:
        member = ctx.guild.get_member(user_id)
        if member:
            await ctx.guild.ban(member, reason="Blacklisted by bot owner")
            await log_mod_action_embed(
                ctx.guild,
                title="⛔ Ban (Blacklist)",
                fields=[
                    ("User", member.mention, True),
                    ("Reason", "Blacklisted", False)
                ],
                color=discord.Color.red(),
                author=member
            )
    except Exception:
        pass

@bot.command(name="showbl")
async def show_blacklist(ctx):
    owners = get_owners(ctx.guild.id)
    blacklist = get_blacklist(ctx.guild.id)
    if not (ctx.author.id == BOT_CREATOR_ID or ctx.author.id in owners):
        await ctx.send("Only owners can use this command.")
        await ctx.message.delete()
        return
    if not blacklist:
        await ctx.message.delete()
        msg = await ctx.send("Blacklist is empty.", delete_after=5)
        return
    embed = discord.Embed(
        title="Blacklisted Users",
        color=discord.Color.red()
    )
    for user_id in blacklist:
        try:
            user_obj = await bot.fetch_user(user_id)
            name = f"{user_obj} ({user_obj.id})"
        except Exception:
            name = f"Unknown ({user_id})"
        embed.add_field(name="", value=name, inline=False)
    await ctx.message.delete()
    await ctx.send(embed=embed)

@bot.command(name="unblacklist", aliases=["unbl"])
async def unblacklist_normal(ctx, user: str):
    owners = get_owners(ctx.guild.id)
    blacklist = get_blacklist(ctx.guild.id)
    if not (ctx.author.id == BOT_CREATOR_ID or ctx.author.id in owners):
        await ctx.send("Only owners can use this command.")
        await ctx.message.delete()
        return
    try:
        user_id = extract_user_id(user)
    except Exception:
        await ctx.send("Invalid user ID or mention.")
        await ctx.message.delete()
        return
    if user_id in blacklist:
        blacklist.remove(user_id)
        save_blacklist(ctx.guild.id, blacklist)
        await ctx.message.delete()
        await ctx.send(f"<@{user_id}> has been removed from the blacklist.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="✅ Unblacklist",
            fields=[
                ("By", ctx.author.mention, True),
                ("User", f"<@{user_id}>", True)
            ],
            color=discord.Color.green(),
            author=ctx.author
        )
    else:
        await ctx.message.delete()
        await ctx.send("User not in blacklist.", delete_after=5)

# ----------- OWNERS -----------

@bot.command(name="addowner")
@commands.has_permissions(administrator=True)
async def add_owner(ctx, user: discord.Member):
    owners = get_owners(ctx.guild.id)
    if ctx.author.id != BOT_CREATOR_ID and ctx.author.id not in owners:
        await ctx.send("Only the bot creator or an owner can add another owner.")
        await ctx.message.delete()
        return
    owners.add(user.id)
    save_owners(ctx.guild.id, owners)
    await ctx.message.delete()
    await ctx.send(f"{user.mention} is now an owner.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="👑 Owner Added",
        fields=[
            ("By", ctx.author.mention, True),
            ("New Owner", user.mention, True)
        ],
        color=discord.Color.green(),
        author=ctx.author
    )

@bot.command(name="delowner")
@commands.has_permissions(administrator=True)
async def del_owner(ctx, user: discord.Member):
    owners = get_owners(ctx.guild.id)
    if ctx.author.id != BOT_CREATOR_ID and ctx.author.id not in owners:
        await ctx.send("Only the bot creator or an owner can remove another owner.")
        await ctx.message.delete()
        return
    if user.id in owners:
        owners.remove(user.id)
        save_owners(ctx.guild.id, owners)
        await ctx.message.delete()
        await ctx.send(f"{user.mention} is no longer an owner.", delete_after=5)
        await log_mod_action_embed(
            ctx.guild,
            title="👑 Owner Removed",
            fields=[
                ("By", ctx.author.mention, True),
                ("Removed Owner", user.mention, True)
            ],
            color=discord.Color.red(),
            author=ctx.author
        )
    else:
        await ctx.message.delete()
        await ctx.send("User is not an owner.", delete_after=5)

# ----------- PERMISSIONS ROLES -----------

@bot.command(name="addperm")
@commands.has_permissions(administrator=True)
async def add_perm(ctx, perm: str, role: discord.Role):
    if perm not in ["perm1", "perm2", "perm3"]:
        await ctx.send("Perm must be perm1, perm2, or perm3.", delete_after=5)
        await ctx.message.delete()
        return
    perms = get_permissions_roles(ctx.guild.id)
    if role.id not in perms[perm]:
        perms[perm].append(role.id)
        save_permissions_roles(ctx.guild.id, perms)
    await ctx.message.delete()
    await ctx.send(f"Role `{role.name}` added to {perm}.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="🔑 Permission Role Added",
        fields=[
            ("By", ctx.author.mention, True),
            ("Role", role.name, True),
            ("Permission", perm, True)
        ],
        color=discord.Color.green(),
        author=ctx.author
    )

@bot.command(name="delperm")
@commands.has_permissions(administrator=True)
async def del_perm(ctx, perm: str, role: discord.Role):
    if perm not in ["perm1", "perm2", "perm3"]:
        await ctx.send("Perm must be perm1, perm2, or perm3.", delete_after=5)
        await ctx.message.delete()
        return
    perms = get_permissions_roles(ctx.guild.id)
    if role.id in perms[perm]:
        perms[perm].remove(role.id)
        save_permissions_roles(ctx.guild.id, perms)
    await ctx.message.delete()
    await ctx.send(f"Role `{role.name}` removed from {perm}.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="🔑 Permission Role Removed",
        fields=[
            ("By", ctx.author.mention, True),
            ("Role", role.name, True),
            ("Permission", perm, True)
        ],
        color=discord.Color.red(),
        author=ctx.author
    )

@bot.command(name="createpermission", aliases=["createperm"])
@commands.has_permissions(administrator=True)
async def create_permission(ctx, perm_name: str, perm_description: str):
    if perm_name in ["perm1", "perm2", "perm3"]:
        await ctx.send("Permission name must not be perm1, perm2, or perm3.", delete_after=5)
        await ctx.message.delete()
        return

    perms = get_permissions_roles(ctx.guild.id)
    if perm_name in perms:
        await ctx.send(f"The permission `{perm_name}` already exists.", delete_after=5)
        await ctx.message.delete()
        return

    perms[perm_name] = []  # Initialize the new permission with an empty list of roles
    save_permissions_roles(ctx.guild.id, perms)

    # Optionally: save the description in a separate file
    descs = load_guild_data(ctx.guild.id, "perm_descriptions", {})
    descs[perm_name] = perm_description
    save_guild_data(ctx.guild.id, "perm_descriptions", descs)

    await ctx.message.delete()
    await ctx.send(f"Permission `{perm_name}` created with description: {perm_description}.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="✅ Permission Created",
        fields=[
            ("By", ctx.author.mention, True),
            ("Permission Name", perm_name, True),
            ("Description", perm_description, True)
        ],
        color=discord.Color.green(),
        author=ctx.author
    )

#------------STATUS-----------#

@bot.command(name="setstatus")
@commands.has_permissions(administrator=True)
async def set_status(ctx, status: str):
    status_map = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "offline": discord.Status.offline
    }
    status_lower = status.lower()
    if status_lower not in status_map:
        await ctx.send("Invalid status. Use 'online', 'idle', 'dnd', or 'offline'.", delete_after=5)
        await ctx.message.delete()
        return

    await bot.change_presence(status=status_map[status_lower])
    await ctx.message.delete()
    await ctx.send(f"Bot status set to **{status_lower}**.", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="✅ Status Changed",
        fields=[
            ("By", ctx.author.mention, True),
            ("Status", status_lower.capitalize(), True)
        ],
        color=discord.Color.green(),
        author=ctx.author
    )

@bot.command(name="activity")
@commands.has_permissions(administrator=True)
async def set_activity(ctx, type: str, *, activity: str):
    type_map = {
        "playing": discord.ActivityType.playing,
        "streaming": discord.ActivityType.streaming,
        "listening": discord.ActivityType.listening,
        "watching": discord.ActivityType.watching
    }
    type_lower = type.lower()
    if type_lower not in type_map:
        await ctx.send("Invalid activity type. Use 'playing', 'streaming', 'listening', or 'watching'.", delete_after=5)
        await ctx.message.delete()
        return

    # Pour le type "streaming", il faut utiliser discord.Streaming (avec une URL)
    if type_lower == "streaming":
        # Par défaut, une URL factice (à adapter selon besoin)
        url = "https://www.twitch.tv/d0llnai"
        activity_obj = discord.Streaming(name=activity, url=url)
    else:
        activity_obj = discord.Activity(name=activity, type=type_map[type_lower])

    await bot.change_presence(activity=activity_obj)
    await ctx.message.delete()
    await ctx.send(f"Bot activity set to **{type_lower}**: {activity}", delete_after=5)
    await log_mod_action_embed(
        ctx.guild,
        title="✅ Activity Changed",
        fields=[
            ("By", ctx.author.mention, True),
            ("Type", type_lower.capitalize(), True),
            ("Activity", activity, True)
        ],
        color=discord.Color.green(),
        author=ctx.author
    )

# ----------- SAY -----------
@bot.command(name="say")
async def say(ctx, *, message: str):
    # Only perm2, perm3, or owner can use
    if not (has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        await ctx.message.delete()
        return
    await ctx.send(message)
    await ctx.message.delete()

# ----------- CUSTOM COMMAND -----------
@bot.command(name="custom")
async def custom_command(ctx, command_name: str, *, command_content: str):
    # Only owners can create custom commands
    if not is_owner(ctx):
        await ctx.send("Only owners can create custom commands.", delete_after=5)
        await ctx.message.delete()
        return
    if command_name in ["help", "commands"]:
        await ctx.send("Available commands: help, commands, custom, say")
        await ctx.message.delete()
        return
    commands_data = load_guild_data(ctx.guild.id, "custom_commands", {})
    commands_data[command_name] = command_content
    save_guild_data(ctx.guild.id, "custom_commands", commands_data)
    await ctx.send(f"Custom command `{command_name}` created with content: {command_content}.", delete_after=5)
    await ctx.message.delete()

@bot.command(name="customlist")
async def custom_list(ctx):
    commands_data = load_guild_data(ctx.guild.id, "custom_commands", {})
    embed = discord.Embed(
        title="Custom Commands",
        description="List of custom commands:",
        color=discord.Color.blue()
    )
    for name in commands_data.keys():
        embed.add_field(name=name, value="\u200b", inline=False)  
    await ctx.send(embed=embed)
    await ctx.message.delete()

# ----------- INFOS -----------

@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    guild_id = ctx.guild.id
    user_id = str(member.id)
    now = datetime.datetime.utcnow()
    periods = {
        "day": now - datetime.timedelta(days=1),
        "14days": now - datetime.timedelta(days=14),
        "month": now - datetime.timedelta(days=30)
    }
    data = load_guild_data(guild_id, "messages", {})
    times = data.get(user_id, [])

    count_day = sum(
        1 for t in times
        if datetime.datetime.fromisoformat(t) > periods["day"]
    )
    count_14days = sum(
        1 for t in times
        if datetime.datetime.fromisoformat(t) > periods["14days"]
    )
    count_month = sum(
        1 for t in times
        if datetime.datetime.fromisoformat(t) > periods["month"]
    )

    embed = discord.Embed(
        title=f"📊 Stats for {member.display_name}",
        description=(
            f"**Discord Tag:** `{member}`\n"
            f"**Joined server:** <t:{int(member.joined_at.timestamp())}:D>\n"
            f"**Account created:** <t:{int(member.created_at.timestamp())}:D>"
        ),
        color=discord.Color.blurple(),
        timestamp=now
    )
    embed.set_thumbnail(url=member.avatar.url if hasattr(member, "avatar") and member.avatar else None)

    embed.add_field(
        name="💬 Messages (1 day)",
        value=f"`{count_day}`",
        inline=True
    )
    embed.add_field(
        name="🗓️ Messages (14 days)",
        value=f"`{count_14days}`",
        inline=True
    )
    embed.add_field(
        name="📅 Messages (30 days)",
        value=f"`{count_month}`",
        inline=True
    )

    embed.add_field(
        name="🏷️ Top Role",
        value=member.top_role.mention,
        inline=True
    )
    embed.add_field(
        name="🆔 User ID",
        value=f"`{member.id}`",
        inline=True
    )
    embed.add_field(
        name="\u200b",
        value="\u200b",
        inline=True
    )

    embed.set_footer(
        text=f"Requested by {ctx.author.display_name}",
        icon_url=ctx.author.avatar.url if hasattr(ctx.author, "avatar") and ctx.author.avatar else None
    )

    await ctx.send(embed=embed)

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(
        title=f"Server info - {guild.name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="Owner", value=guild.owner.mention)
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Channels", value=len(guild.channels))
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if hasattr(ctx.author, "avatar") and ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command(name="avatar")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(
        title=f"Avatar - {member}",
        color=discord.Color.blurple()
    )
    embed.set_image(url=member.avatar.url if hasattr(member, "avatar") and member.avatar else None)
    await ctx.send(embed=embed)

# ----------- ShadowRealm-----------
async def resolve_member(ctx, arg):
    """
    Finds a member by mention, ID, username (new Discord format), or server nickname.
    """
    # Clean up mention if needed
    if arg.startswith("<@") and arg.endswith(">"):
        arg = arg.replace("<@", "").replace(">", "").replace("!", "")
    # Try by ID
    if arg.isdigit():
        member = ctx.guild.get_member(int(arg))
        if member:
            return member
    # Try by username (new Discord format)
    member = discord.utils.find(lambda m: m.name == arg, ctx.guild.members)
    if member:
        return member
    # Try by server nickname (display_name)
    member = discord.utils.find(lambda m: m.display_name == arg, ctx.guild.members)
    if member:
        return member
    # (Optional) Try by username#tag for legacy accounts
    if "#" in arg:
        name, discrim = arg.rsplit("#", 1)
        member = discord.utils.find(lambda m: m.name == name and m.discriminator == discrim, ctx.guild.members)
        if member:
            return member
    return None

@bot.command(name="shadowrealm")
@commands.has_permissions(manage_roles=True)
async def shadowrealm(ctx, user: str, duration: str):
    member = await resolve_member(ctx, user)
    if not member:
        await ctx.send("User not found. Please mention, provide their ID, username, or server nickname.")
        return

    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send("Invalid duration format. Use formats like 10m, 1h, 30s, etc.")
        return

    role_name = "SHADOW REALM☯️"
    role = discord.utils.get(ctx.guild.roles, name=role_name)

    if not role:
        bot_role = ctx.guild.me.top_role
        role = await ctx.guild.create_role(
            name=role_name,
            reason="Role automatically created for the shadowrealm command"
        )
        await ctx.guild.edit_role_positions({role: bot_role.position - 1})
        await ctx.send(f"The {role_name} role did not exist and has been created.")

    for channel in ctx.guild.channels:
        overwrites = channel.overwrites_for(role)
        overwrites.view_channel = False
        try:
            await channel.set_permissions(role, overwrite=overwrites)
        except Exception as e:
            print(f"Error updating {channel.name}: {e}")

    await member.add_roles(role)
    await ctx.send(f"{member.mention} has been sent to the shadow realm for {duration}.")

    await asyncio.sleep(seconds)
    await member.remove_roles(role)
    await ctx.send(f"{member.mention} has returned from the shadow realm!")

@tasks.loop(seconds=1)
async def shadowrealm_timer():
    for guild in bot.guilds:
        guild_id = guild.id
        shadow_data = load_guild_data(guild_id, "shadowrealm", {})
        updated = False

        role = guild.get_role(1209033095307726899)
        if not role:
            continue  # Skip this server if the role doesn't exist

        for user_id in list(shadow_data.keys()):
            shadow_data[user_id]["time"] -= 1
            if shadow_data[user_id]["time"] <= 0:
                member = guild.get_member(int(user_id))
                channel_id = shadow_data[user_id].get("channel_id")
                channel = guild.get_channel(channel_id) if channel_id else guild.system_channel

                if member and role in member.roles:
                    try:
                        await member.remove_roles(role)
                    except Exception:
                        pass
                    if channel:
                        await channel.send(f"{member.mention} has returned from the shadowrealm!")
                del shadow_data[user_id]
                updated = True

        if updated:
            save_guild_data(guild_id, "shadowrealm", shadow_data)

# ----------- HELP -----------

@bot.command(name="help")
async def help_command(ctx):
    moderation_cmds = []
    management_cmds = []
    info_cmds = ["userinfo", "serverinfo", "avatar"]
    logs_cmds = []
    ticket_cmds = ["ticketpanel"]  # Add ticketpanel command to the help

    # Automatically add the server owner to the owners list
    owners = get_owners(ctx.guild.id)
    if ctx.guild.owner.id not in owners:
        owners.add(ctx.guild.owner.id)
        save_owners(ctx.guild.id, owners)

    # MODERATION
    if has_perm(ctx, "perm3") or is_owner(ctx):  # Keep is_owner for moderation
        moderation_cmds += ["ban", "unban", "kick", "to", "unto", "clear", "addrole", "removerole", "createrole", "deleterole"]
    elif has_perm(ctx, "perm2"):
        moderation_cmds += ["to", "unto", "clear", "addrole", "removerole", "createrole", "deleterole"]
    elif has_perm(ctx, "perm1"):
        moderation_cmds += ["to", "unto"]

    # MANAGEMENT
    if is_owner(ctx):  # Keep is_owner for management commands
        management_cmds += ["bl", "unbl", "showbl", "addowner", "delowner", "addperm", "delperm"]

    # LOGS
    if is_owner(ctx):  # Keep is_owner for logs commands
        logs_cmds += ["logs_mod"]

    # CUSTOM COMMANDS
    commands_data = load_guild_data(ctx.guild.id, "custom_commands", {})
    custom_cmds = list(commands_data.keys())

    embed = discord.Embed(
        title="Bot Help",
        color=discord.Color.blurple()
    )

    if moderation_cmds:
        embed.add_field(name="Moderation", value="`" + "`, `".join(moderation_cmds) + "`", inline=False)
    if management_cmds:
        embed.add_field(name="Management", value="`" + "`, `".join(management_cmds) + "`", inline=False)
    if info_cmds:
        embed.add_field(name="Info", value="`" + "`, `".join(info_cmds) + "`", inline=False)
    if logs_cmds:
        embed.add_field(name="Logs", value="`" + "`, `".join(logs_cmds) + "`", inline=False)
    if ticket_cmds:  # Add ticket commands section
        embed.add_field(name="Ticket Commands", value="`" + "`, `".join(ticket_cmds) + "`", inline=False)
    if custom_cmds:
        embed.add_field(name="Custom", value="`" + "`, `".join(custom_cmds) + "`", inline=False)

    embed.set_footer(text="Slash commands also available!")
    await ctx.send(embed=embed)

# ----------- TICKET SYSTEM (guild_data) -----------

def get_panel_data(guild_id):
    return load_guild_data(guild_id, "panels", [])

def save_panel_data(guild_id, panels):
    save_guild_data(guild_id, "panels", panels)

class PanelSetupModal(Modal):
    def __init__(self, callback):
        super().__init__(title="Create Ticket Panel")
        self.panel_name = TextInput(label="Panel Name", placeholder="e.g. Support")
        self.panel_desc = TextInput(label="Panel Description", placeholder="Short description", required=False)
        self.callback_func = callback
        self.add_item(self.panel_name)
        self.add_item(self.panel_desc)

    async def on_submit(self, interaction: discord.Interaction):
        panel_info = {
            "name": self.panel_name.value,
            "description": self.panel_desc.value or "No description."
        }
        await self.callback_func(interaction, panel_info)

class PanelCategorySelect(Select):
    def __init__(self, guild: discord.Guild):
        options = [
            SelectOption(label=cat.name, value=str(cat.id))
            for cat in guild.channels if isinstance(cat, discord.CategoryChannel)
        ][:25]
        super().__init__(
            placeholder="Select the category where tickets will be created...",
            min_values=1, max_values=1, options=options
        )
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_category_id = int(self.values[0])
        await interaction.response.send_message(
            f"Selected category: <#{self.values[0]}>. Now select staff roles.",
            ephemeral=True
        )
        await interaction.followup.send(
            "Select staff roles allowed to view tickets:",
            view=PanelRoleSelectView(interaction.guild, self.view.panel_info, self.view.selected_category_id),
            ephemeral=True
        )

class PanelCategorySelectView(View):
    def __init__(self, guild: discord.Guild, panel_info: dict):
        super().__init__(timeout=120)
        self.add_item(PanelCategorySelect(guild))
        self.panel_info = panel_info
        self.selected_category_id = None

class PanelRoleSelect(Select):
    def __init__(self, guild: discord.Guild):
        options = [
            SelectOption(label=role.name, value=str(role.id))
            for role in guild.roles if not role.is_default()
        ][:25]
        super().__init__(
            placeholder="Select staff roles...", min_values=1, max_values=len(options), options=options
        )
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_role_ids = [int(v) for v in self.values]
        await interaction.response.send_message(
            "Where should the panel be posted? Select the text channel.",
            ephemeral=True,
            view=PanelTargetChannelSelectView(
                interaction.guild,
                self.view.panel_info,
                self.view.selected_category_id,
                self.view.selected_role_ids
            )
        )

class PanelRoleSelectView(View):
    def __init__(self, guild: discord.Guild, panel_info: dict, selected_category_id: int):
        super().__init__(timeout=120)
        self.add_item(PanelRoleSelect(guild))
        self.panel_info = panel_info
        self.selected_category_id = selected_category_id
        self.selected_role_ids = []

class PanelTargetChannelSelect(Select):
    def __init__(self, guild: discord.Guild):
        options = [
            SelectOption(label=ch.name, value=str(ch.id))
            for ch in guild.text_channels
        ][:25]
        super().__init__(
            placeholder="Select the channel for the ticket panel...", min_values=1, max_values=1, options=options
        )
    async def callback(self, interaction: discord.Interaction):
        self.view.target_channel_id = int(self.values[0])
        panel_info = self.view.panel_info
        panel_info['category_id'] = self.view.selected_category_id
        panel_info['staff_role_ids'] = self.view.selected_role_ids
        panel_info['target_channel_id'] = self.view.target_channel_id
        guild_id = interaction.guild.id
        panels = get_panel_data(guild_id)
        panels.append(panel_info)
        save_panel_data(guild_id, panels)
        target_channel = interaction.guild.get_channel(self.view.target_channel_id)
        if target_channel:
            embed = discord.Embed(
                title=f"🎟️ {panel_info['name']}",
                description=panel_info['description'],
                color=discord.Color.blurple()
            )
            message = await target_channel.send(embed=embed, view=UserTicketPanelView(panel_info))
            bot.add_view(UserTicketPanelView(panel_info), message_id=message.id)
        await interaction.response.send_message(
            f"Panel **{panel_info['name']}** created and posted in <#{panel_info['target_channel_id']}>!",
            ephemeral=True
        )

class PanelTargetChannelSelectView(View):
    def __init__(self, guild: discord.Guild, panel_info: dict, selected_category_id: int, selected_role_ids: list):
        super().__init__(timeout=120)
        self.add_item(PanelTargetChannelSelect(guild))
        self.panel_info = panel_info
        self.selected_category_id = selected_category_id
        self.selected_role_ids = selected_role_ids
        self.target_channel_id = None

class UserTicketPanelView(View):
    def __init__(self, panel_info: dict):
        super().__init__(timeout=None)
        self.panel_info = panel_info

    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        opener = interaction.user
        guild_id = guild.id
        panels = get_panel_data(guild_id)
        panel_idx = next((i for i, p in enumerate(panels) if p['name'] == self.panel_info['name']), None)
        
        if panel_idx is None:
            await interaction.response.send_message("Panel not found.", ephemeral=True)
            return
        
        if "counter" not in panels[panel_idx]:
            panels[panel_idx]["counter"] = 1
        
        ticket_number = panels[panel_idx]["counter"]
        panels[panel_idx]["counter"] += 1
        save_panel_data(guild_id, panels)
        
        ticket_channel_name = f"{self.panel_info['name'].lower().replace(' ', '-')}-{ticket_number}"
        category_id = self.panel_info['category_id']
        parent_category = guild.get_channel(category_id)
        
        if not parent_category or not isinstance(parent_category, discord.CategoryChannel):
            await interaction.response.send_message(
                "The panel category does not exist or is not a category. Please contact an admin.",
                ephemeral=True
            )
            return
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            opener: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        for staff_role_id in self.panel_info['staff_role_ids']:
            staff_role = guild.get_role(staff_role_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        ticket_channel = await guild.create_text_channel(
            name=ticket_channel_name,
            category=parent_category,
            overwrites=overwrites,
            reason=f"Ticket {self.panel_info['name']} opened by {opener} (#{ticket_number})"
        )

        # Log the ticket opening
        await log_ticket_action(guild, "Opened", opener, ticket_channel)

        embed = discord.Embed(
            title=f"🎫 Ticket {self.panel_info['name']}",
            description=(
                f"Hello {opener.mention}, your ticket **{self.panel_info['name']}** has been opened!\n"
                "A staff member will respond as soon as possible.\n\n"
                "Use the button below to close this ticket."
            ),
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        await ticket_channel.send(embed=embed, view=TicketCloseView())
        await interaction.response.send_message(
            f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True
        )

class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        channel = interaction.channel
        opener = interaction.user
        guild = channel.guild

        try:
            await log_mod_action_embed(
                guild,
                title="🎫 Ticket Closed",
                fields=[
                    ("Closed by", opener.mention, True),
                    ("Channel", channel.mention, True)
                ],
                color=discord.Color.red(),
                author=opener
            )
            await interaction.response.send_message("This ticket will be closed...", ephemeral=True)
            await channel.delete(reason="Ticket closed via button.")
        except Exception as e:
            print(f"Error closing ticket: {e}")
            await interaction.response.send_message("An error occurred while trying to close the ticket.", ephemeral=True)

class TicketPanelSetupView(View):
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx

    @discord.ui.button(label="Create new ticket panel", style=discord.ButtonStyle.green)
    async def create_panel(self, interaction: discord.Interaction, button: Button):
        modal = PanelSetupModal(self.panel_modal_callback)
        await interaction.response.send_modal(modal)

    async def panel_modal_callback(self, interaction: discord.Interaction, panel_info: dict):
        await interaction.response.send_message(
            f"Panel name: **{panel_info['name']}**\nNow select the ticket category:",
            view=PanelCategorySelectView(interaction.guild, panel_info),
            ephemeral=True
        )

    @discord.ui.button(label="Edit existing ticket panel", style=discord.ButtonStyle.blurple)
    async def edit_panel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Panel editing is not implemented yet.", ephemeral=True
        )

@bot.command(name="ticketpanel")
async def ticketpanel(ctx):
    if not is_owner(ctx):  # Check if the user is an owner
        await ctx.send("You do not have permission to use this command.", delete_after=5)
        return

    embed = discord.Embed(
        title="🎟️ Ticket Panel Setup",
        description="Use the buttons below to create or edit a ticket panel.",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed, view=TicketPanelSetupView(ctx))


async def setup_persistent_views():
    for guild in bot.guilds:
        panels = get_panel_data(guild.id)
        for panel in panels:
            channel_id = panel.get("target_channel_id")
            if not channel_id:
                continue
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            async for message in channel.history(limit=50):
                if (
                    message.author == bot.user
                    and message.embeds
                    and message.embeds[0].title == f"🎟️ {panel['name']}"
                    and message.embeds[0].description == panel['description']
                ):
                    # Réajouter la vue ici
                    try:
                        view = UserTicketPanelView(panel)
                        bot.add_view(view, message_id=message.id)  # Assurez-vous que cela fonctionne correctement
                        print(f"Persistent view re-added in {channel} for panel {panel['name']}")
                    except Exception as e:
                        print(f"Error adding persistent ticket view: {e}")
                    break


# --------- REMOVE THE BOT FROM SERVER---------
def is_creator():
    async def predicate(ctx):
        return ctx.author.id == BOT_CREATOR_ID
    return commands.check(predicate)

@bot.command(name="removebot")
@is_creator()  # Restrict this command to the bot creator
async def leave_server(ctx, server_id: int):
    # Attempt to retrieve the guild (server) from the provided ID
    guild = bot.get_guild(server_id)
    
    if guild is None:
        await ctx.send("The server with this ID was not found.")
        return
    
    # Check if the bot is in the server
    if guild.me not in guild.members:
        await ctx.send("The bot is not a member of this server.")
        return

    await ctx.send(f"The bot is leaving the server: {guild.name}.")
    await guild.leave()

# ----------- LANCEMENT DU BOT ---------

print("Token chargé :", token)
bot.run(token)
