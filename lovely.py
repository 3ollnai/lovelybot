import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import json
import os
from dotenv import load_dotenv
import re
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

# ----------- INTERACTIVE LOG VIEW FOR DELETED MESSAGES -----------

class DeletedMessageView(View):
    def __init__(self, message_content):
        super().__init__(timeout=120)
        self.message_content = message_content

    @discord.ui.button(label="Restore", style=discord.ButtonStyle.green, emoji="🔄")
    async def restore(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"Restored message:\n```{self.message_content}```",
            ephemeral=True
        )

    @discord.ui.button(label="Delete log", style=discord.ButtonStyle.red, emoji="🗑️")
    async def delete_permanently(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Log deleted.", ephemeral=True
        )
        await interaction.message.delete()

# ----------- EMBED LOGS -----------

async def log_mod_action_embed(guild, title, fields, color=discord.Color.blue(), author=None):
    channel_id = get_logs_channel_id(guild.id)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
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
    view = DeletedMessageView(content)
    await logs_channel.send(embed=embed, view=view)

# ----------- EVENTS -----------

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    try:
        synced = await bot.tree.sync()
        print(f"Global sync: {len(synced)} slash commands.")
    except Exception as e:
        print(f"Global sync failed: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user or not message.guild:
        return
    for word in BAD_WORDS:
        if word in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, your message was deleted for inappropriate language.", delete_after=5)
            await log_deleted_message_embed(
                message.guild,
                message.author,
                message.content,
                message.channel,
                reason=f"Forbidden word: `{word}`",
                message_url=message.jump_url
            )
            return
    save_user_message(message.guild.id, message.author.id)  # <--- AJOUT ICI
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
    if not (has_perm(ctx, "perm3") or is_owner(ctx)):
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
    if not (has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
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
    if not (has_perm(ctx, "perm3") or is_owner(ctx)):
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
    if not (has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
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
    until = discord.utils.utcnow() + delta
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
    if not (has_perm_slash(interaction, "perm1") or has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    match = re.match(r"^(\d+)([mh])$", duration.lower())
    if not match:
        await interaction.response.send_message("Invalid format. Use `10m` or `2h`.", ephemeral=True)
        return
    value, unit = int(match.group(1)), match.group(2)
    delta = datetime.timedelta(hours=value) if unit == "h" else datetime.timedelta(minutes=value)
    until = discord.utils.utcnow() + delta
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
    if not (has_perm(ctx, "perm1") or has_perm(ctx, "perm2") or has_perm(ctx, "perm3") or is_owner(ctx)):
        await ctx.send("You don't have permission to use this command.")
        await ctx.message.delete()
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await member.timeout(None, reason="Timeout removed by owner.")
        msg = await ctx.send(f"{member.mention} has been un-timed out.", delete_after=5)
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
        msg = await ctx.send("I don't have permission to untimeout this member (check bot role and permissions).", delete_after=5)
    except AttributeError:
        msg = await ctx.send("Untimeout is not available on this server (feature not enabled).", delete_after=5)
    except Exception as e:
        msg = await ctx.send(f"Failed to untimeout {member.mention}: {e}", delete_after=5)

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.describe(member="Member to remove timeout from")
async def untimeout_slash(interaction: discord.Interaction, member: discord.Member):
    if not (has_perm_slash(interaction, "perm1") or has_perm_slash(interaction, "perm2") or has_perm_slash(interaction, "perm3") or is_owner_slash(interaction)):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    try:
        await member.timeout(None, reason="Timeout removed by owner.")
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
        await interaction.response.send_message("I don't have permission to untimeout this member.", ephemeral=True)
    except AttributeError:
        await interaction.response.send_message("Timeout is not available on this server.", ephemeral=True)
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

# ----------- HELP -----------

@bot.command(name="help")
async def help_command(ctx):
    moderation_cmds = []
    management_cmds = []
    info_cmds = ["userinfo", "serverinfo", "avatar"] 
    logs_cmds = []

    # MODÉRATION
    if has_perm(ctx, "perm3") or is_owner(ctx):
        moderation_cmds += ["ban","unban", "kick", "to", "unto", "clear", "addrole", "removerole", "createrole", "delrole"]
    elif has_perm(ctx, "perm2"):
        moderation_cmds += ["to", "unto", "clear", "addrole", "removerole", "createrole", "deleterole"]
    elif has_perm(ctx, "perm1"):
        moderation_cmds += ["to", "unto"]

    # MANAGEMENT
    if is_owner(ctx):
        management_cmds += ["bl", "unbl", "showbl", "addowner", "delowner", "addperm", "delperm"]

    # LOGS
    if is_owner(ctx):
        logs_cmds += ["logs_mod"]

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

    embed.set_footer(text="Slash commands also available!")
    await ctx.send(embed=embed)


# ----------- LANCEMENT DU BOT ---------

print("Token chargé :", token)
bot.run(token)
