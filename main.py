import os
import discord
import asyncio
from discord import app_commands
from datetime import datetime, timedelta
from abilities import apply_sqlite_migrations
from models import Base, engine, GuildSettings, FilteredWord, UserLevel
from sqlalchemy.orm import Session
import random

def generate_oauth_link(client_id):
    base_url = "https://discord.com/api/oauth2/authorize"
    redirect_uri = "http://localhost"
    scope = "bot"
    permissions = "8"  # Administrator permission for simplicity, adjust as needed.
    return f"{base_url}?client_id={client_id}&permissions={permissions}&scope={scope}"

def calculate_xp_for_level(level):
    return int(100 * (level ** 1.5))

def calculate_level_for_xp(xp):
    level = 0
    while xp >= calculate_xp_for_level(level + 1):
        level += 1
    return level

def generate_progress_bar(current, total, length=10):
    filled = int(length * current / total)
    return '█' * filled + '░' * (length - filled)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True  # Enable member events

bot = discord.Client(intents=intents, activity=discord.CustomActivity("Moderating the server"))
tree = app_commands.CommandTree(bot)

@bot.event
async def on_guild_channel_create(channel):
    # Log the channel creation
    guild_id = str(channel.guild.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("channel_create", channel.id))
    else:
        recent_actions[guild_id] = [("channel_create", channel.id)]
    
    # Check for suspicious activity (e.g., multiple channels created)
    if len(recent_actions[guild_id]) > 5:  # Example threshold
        await handle_suspicious_activity(channel.guild)

@bot.event
async def on_guild_update(before, after):
    # Log guild updates (like name changes)
    guild_id = str(after.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("guild_update", after.name))
    else:
        recent_actions[guild_id] = [("guild_update", after.name)]
    
    # Check for suspicious activity
    if len(recent_actions[guild_id]) > 3:  # Example threshold
        await handle_suspicious_activity(after)

async def notify_suspicious_activity(guild):
    # Notify the server owner or admins
    owner = guild.owner
    await owner.send("🚨 Suspicious activity detected in your server! Please check the recent actions.")
    
    # Optionally, log the activity or take further action (like disabling permissions)
    # Temporarily restrict permissions for certain roles.
    for role in guild.roles:
        if role.name != "@everyone":
            await role.edit(permissions=discord.Permissions.none())
    
    # Send a message to a designated log channel if available
    log_channel_id = None  # Placeholder for log channel ID retrieval logic
    if log_channel_id:
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"🚨 Suspicious activity detected: {recent_actions[str(guild.id)]}")

@tree.command(name="setlogchannel", description="Set a channel for logging anti-nuke actions")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
        
        settings.log_channel_id = str(channel.id)
        session.commit()
        
        await interaction.response.send_message(f"Log channel set to {channel.mention}.", ephemeral=True)

@tree.command(name="checkrecentactions", description="Check recent actions that triggered anti-nuke")
@app_commands.checks.has_permissions(manage_guild=True)
async def check_recent_actions(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    actions = recent_actions.get(guild_id, [])
    
    if not actions:
        await interaction.response.send_message("No recent actions detected.", ephemeral=True)
        return
    
    action_messages = "\n".join([f"{action[0]}: {action[1]}" for action in actions])
    await interaction.response.send_message(f"Recent actions:\n{action_messages}", ephemeral=True)

@tree.command(name="resetrecentactions", description="Reset the recent actions log")
@app_commands.checks.has_permissions(manage_guild=True)
async def reset_recent_actions(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in recent_actions:
        del recent_actions[guild_id]
    await interaction.response.send_message("Recent actions log has been reset.", ephemeral=True)

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')
    await tree.sync()

# Global variable to keep track of recent actions
recent_actions = {}

@bot.event
async def on_member_remove(member):
    # Log the member removal
    guild_id = str(member.guild.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("member_remove", member.id))
    else:
        recent_actions[guild_id] = [("member_remove", member.id)]
    
    # Check for suspicious activity (e.g., multiple members removed)
    if len(recent_actions[guild_id]) > 4:  # Example threshold
        await handle_suspicious_activity(member.guild)

@bot.event
async def on_member_ban(guild, user):
    # Log the ban action
    guild_id = str(guild.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("member_ban", user.id))
    else:
        recent_actions[guild_id] = [("member_ban", user.id)]
    
    # Check for suspicious activity
    if len(recent_actions[guild_id]) > 4:  # Example threshold
        await handle_suspicious_activity(guild)

@bot.event
async def on_guild_channel_delete(channel):
    # Log the channel deletion
    guild_id = str(channel.guild.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("channel_delete", channel.id))
    else:
        recent_actions[guild_id] = [("channel_delete", channel.id)]
    
    # Check for suspicious activity
    if len(recent_actions[guild_id]) > 5:  # Example threshold
        await handle_suspicious_activity(channel.guild)

async def restrict_suspicious_activity(guild):
    # Notify the server owner or admins
    owner = guild.owner
    await owner.send("@Everyone 🚨 Suspicious activity detected in your server! Please check the recent actions.")
    
    # Optionally, log the activity or take further action (like disabling permissions)
    # For example, you could temporarily restrict permissions for certain roles.
    for role in guild.roles:
        if role.name != "@everyone":
            await role.edit(permissions=discord.Permissions.none())

@tree.command(name="setantinuke", description="Enable or disable anti-nuke features")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_anti_nuke(interaction: discord.Interaction, enabled: bool):
    # Save the setting to your database or configuration
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
        
        settings.anti_nuke_enabled = enabled
        session.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Anti-nuke features have been {status}.", ephemeral=True)

@bot.event
async def on_member_join(member):
    """Event handler for when a new member joins the server"""
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(member.guild.id)).first()
        
        if not settings or not settings.welcome_enabled:
            return
        
        welcome_channel = None
        if settings.welcome_channel_id:
            welcome_channel = member.guild.get_channel(int(settings.welcome_channel_id))
        
        if not welcome_channel:
            welcome_channel = member.guild.system_channel or discord.utils.get(member.guild.text_channels, name='general')
        
        if welcome_channel:
            if settings.welcome_message:
                message = settings.welcome_message.replace('{user}', member.mention) \
                                                  .replace('{server}', member.guild.name) \
                                                  .replace('{membercount}', str(member.guild.member_count))
            else:
                message = f"Welcome to the server, {member.mention}! 👋"
            
            await welcome_channel.send(message)

@bot.event
async def on_message_event(message):
    if message.author.bot:
        return

    # Word filter check
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(message.guild.id)).first()
        
        if settings and settings.filter_enabled:
            filtered_words = session.query(FilteredWord).filter_by(guild_id=str(message.guild.id)).all()
            message_content = message.content.lower()
            
            for filtered_word in filtered_words:
                if filtered_word.word.lower() in message_content:
                    try:
                        await message.delete()
                        warning = await message.channel.send(
                            f"{message.author.mention} Your message was removed because it contained a filtered word.",
                            delete_after=5
                        )
                        return
                    except discord.errors.Forbidden:
                        pass
        
        # XP gain
        if settings and settings.level_enabled:
            user_level = session.query(UserLevel).filter_by(
                guild_id=str(message.guild.id),
                user_id=str(message.author.id)
            ).first()
            
            if not user_level:
                user_level = UserLevel(
                    guild_id=str(message.guild.id),
                    user_id=str(message.author.id)
                )
                session.add(user_level)
            
            now = datetime.utcnow()
            if not user_level.last_xp_gain or (now - user_level.last_xp_gain).total_seconds() >= 60:
                old_level = calculate_level_for_xp(user_level.xp)
                xp_gain = random.randint(15, 25)
                user_level.xp += xp_gain
                user_level.last_xp_gain = now
                new_level = calculate_level_for_xp(user_level.xp)
                
                if new_level > old_level:
                    level_up_channel = message.channel
                    if settings.level_up_channel:
                        channel = message.guild.get_channel(int(settings.level_up_channel))
                        if channel:
                            level_up_channel = channel
                    
                    if settings.level_up_message:
                        level_up_msg = settings.level_up_message.replace('{user}', message.author.mention) \
                                                                .replace('{level}', str(new_level))
                    else:
                        level_up_msg = f"🎉 Congratulations {message.author.mention}! You've reached level {new_level}! 🎉"
                    
                    await level_up_channel.send(level_up_msg)
                
                session.commit()

@tree.command(name="setwelcome", description="Configure welcome message settings")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_welcome(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    message: str = None,
    enabled: bool = None
):
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
        
        if channel is not None:
            settings.welcome_channel_id = str(channel.id)
        
        if message is not None:
            settings.welcome_message = message
        
        if enabled is not None:
            settings.welcome_enabled = enabled
        
        session.commit()
        
        preview = "Current welcome message settings:\n"
        preview += f"Enabled: {settings.welcome_enabled}\n"
        
        if settings.welcome_channel_id:
            channel = interaction.guild.get_channel(int(settings.welcome_channel_id))
            preview += f"Channel: {channel.mention if channel else 'Not found'}\n"
        else:
            preview += "Channel: Default (system channel or #general)\n"
        
        if settings.welcome_message:
            message_preview = settings.welcome_message.replace('{user}', interaction.user.mention) \
                                                    .replace('{server}', interaction.guild.name) \
                                                    .replace('{membercount}', str(interaction.guild.member_count))
            preview += f"Message: {message_preview}\n"
        else:
            preview += "Message: Default (Welcome to the server, @user! 👋)\n"
        
        preview += "\nAvailable placeholders: {user}, {server}, {membercount}"
        
        await interaction.response.send_message(preview)

@tree.command(name="addfilter", description="Add a word or phrase to the filter list")
@app_commands.checks.has_permissions(manage_messages=True)
async def add_filter(interaction: discord.Interaction, word: str):
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
            settings.filter_enabled = True
        
        filtered_word = FilteredWord(guild_id=str(interaction.guild_id), word=word)
        session.add(filtered_word)
        session.commit()
        
        await interaction.response.send_message(f"Added '{word}' to the filter list.", ephemeral=True)

@tree.command(name="removefilter", description="Remove a word or phrase from the filter list")
@app_commands.checks.has_permissions(manage_messages=True)
async def remove_filter(interaction: discord.Interaction, word: str):
    with Session(engine) as session:
        filtered_word = session.query(FilteredWord).filter_by(
            guild_id=str(interaction.guild_id),
            word=word
        ).first()
        
        if filtered_word:
            session.delete(filtered_word)
            session.commit()
            await interaction.response.send_message(f"Removed '{word}' from the filter list.", ephemeral=True)
        else:
            await interaction.response.send_message(f"'{word}' was not found in the filter list.", ephemeral=True)

@tree.command(name="listfilters", description="List all filtered words and phrases")
@app_commands.checks.has_permissions(manage_messages=True)
async def list_filters(interaction: discord.Interaction):
    with Session(engine) as session:
        filtered_words = session.query(FilteredWord).filter_by(guild_id=str(interaction.guild_id)).all()
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not filtered_words:
            await interaction.response.send_message("No words are currently filtered.", ephemeral=True)
            return
        
        filter_status = "enabled" if settings and settings.filter_enabled else "disabled"
        word_list = "\n".join([f"• {word.word}" for word in filtered_words])
        message = f"Word filter is currently {filter_status}.\nFiltered words:\n{word_list}"
        
        await interaction.response.send_message(message, ephemeral=True)

@tree.command(name="togglefilter", description="Enable or disable the word filter")
@app_commands.checks.has_permissions(manage_messages=True)
async def toggle_filter(interaction: discord.Interaction, enabled: bool):
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
        
        settings.filter_enabled = enabled
        session.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Word filter has been {status}.", ephemeral=True)

@tree.command(name="setranking", description="Enable or disable the ranking system")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_ranking(interaction: discord.Interaction, enabled: bool):
    """Enable or disable the ranking system for the server."""
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
        
        settings.level_enabled = enabled
        session.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Ranking system has been {status}.", ephemeral=True)

@tree.command(name="leaderboard", description="Show the server's top 10 most active members")
async def leaderboard_top(interaction: discord.Interaction):
    """Display the leaderboard of the top 10 members based on XP."""
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild.id)).first()
        
        if not settings or not settings.level_enabled:
            await interaction.response.send_message("The ranking system is not enabled on this server.", ephemeral=True)
            return
        
        top_users = session.query(UserLevel).filter_by(guild_id=str(interaction.guild.id)) \
                            .order_by(UserLevel.xp.desc()).limit(10).all()
        
        if not top_users:
            await interaction.response.send_message("No members have earned XP yet!", ephemeral=True)
            return
        
        response = "🏆 **Server Leaderboard** 🏆\n\n"
        for i, user_level in enumerate(top_users, 1):
            member = interaction.guild.get_member(int(user_level.user_id))
            if member:
                level = calculate_level_for_xp(user_level.xp)
                response += f"{i}. {member.display_name} - Level {level} ({user_level.xp} XP)\n"
        
        await interaction.response.send_message(response)

@bot.event
async def on_guild_role_create(role):
    guild_id = str(role.guild.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("role_create", role.id))
    else:
        recent_actions[guild_id] = [("role_create", role.id)]
    
    # Check for suspicious activity
    if len(recent_actions[guild_id]) > 5:  # Example threshold for role creations
        await handle_suspicious_activity(role.guild)

message_counts = {}

@bot.event
async def on_message_spam_check(message):
    if message.author.bot:
        return
    
    guild_id = str(message.guild.id)
    now = datetime.utcnow()
    
    if guild_id not in message_counts:
        message_counts[guild_id] = {}
    
    if message.author.id not in message_counts[guild_id]:
        message_counts[guild_id][message.author.id] = []
    
    message_counts[guild_id][message.author.id].append(now)
    
    # Remove messages older than 10 seconds
    message_counts[guild_id][message.author.id] = [msg_time for msg_time in message_counts[guild_id][message.author.id] if (now - msg_time).total_seconds() < 10]
    
    if len(message_counts[guild_id][message.author.id]) > 5:  # Example threshold for spam
        await message.author.timeout(duration=60)  # Mute for 60 seconds
        await message.channel.send(f"{message.author.mention}, you have been muted for spamming.")

@bot.event
async def on_guild_update_event(before, after):
    guild_id = str(after.id)
    if before.region != after.region:
        if guild_id in recent_actions:
            recent_actions[guild_id].append(("region_change", after.region))
        else:
            recent_actions[guild_id] = [("region_change", after.region)]
    
    if before.verification_level != after.verification_level:
        if guild_id in recent_actions:
            recent_actions[guild_id].append(("verification_level_change", after.verification_level))
        else:
            recent_actions[guild_id] = [("verification_level_change", after.verification_level)]
    
    # Check for suspicious activity
    if len(recent_actions[guild_id]) > 3:  # Example threshold for critical changes
        await notify_suspicious_activity(after)

async def restore_roles(guild):
    for action in recent_actions[guild.id]:
        if action[0] == "role_delete":
            role_id = action[1]
            # Logic to restore the role (you may need to store the role data before deletion)
            # This is a placeholder example, you would need to customize this based on your needs.
            await guild.create_role(name="Restored Role", color=discord.Color.default()) 

async def handle_suspicious_activity(guild):
    # Notify the server owner or admins
    owner = guild.owner
    await owner.send("@Everyone 🚨 Suspicious activity detected in your server! Please check the recent actions.")
    
    # Notify all admins
    for member in guild.members:
        if member.guild_permissions.administrator:
            await member.send("@Everyone 🚨 Suspicious activity detected in your server! Please check the recent actions.")

@bot.event
async def on_guild_role_delete(role):
    guild_id = str(role.guild.id)
    if guild_id in recent_actions:
        recent_actions[guild_id].append(("role_delete", role.id))
    else:
        recent_actions[guild_id] = [("role_delete", role.id)]
    
    # Check for suspicious activity
    if len(recent_actions[guild_id]) > 2:  # Example threshold for role deletions
        await handle_suspicious_activity(role.guild)

@bot.event
async def on_member_join_role_assignment(member):
    role = discord.utils.get(member.guild.roles, name="New Member")  # Change to your role name
    if role:
        await member.add_roles(role)

@tree.command(name="reactionroles", description="Set up reaction roles")
async def reaction_roles(interaction: discord.Interaction, role: discord.Role):
    message = await interaction.channel.send(f"React to this message to get the {role.name} role!")
    await message.add_reaction("👍")  # Example reaction
    # Store the message ID and role ID in the database for later use

@tree.command(name="feedback", description="Submit feedback or suggestions")
async def feedback(interaction: discord.Interaction, *, feedback_text: str):
    feedback_channel = discord.utils.get(interaction.guild.text_channels, name="feedback")  # Change to your feedback channel name
    if feedback_channel:
        await feedback_channel.send(f"Feedback from {interaction.user.mention}: {feedback_text}")
        await interaction.response.send_message("Thank you for your feedback!", ephemeral=True)
    else:
        await interaction.response.send_message("Feedback channel not found.", ephemeral=True)

@tree.command(name="flipcoin", description="Flip a coin")
async def flip_coin(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"You flipped: {result}")

import requests

@tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    response = requests.get("https://meme-api.com/gimme")
    if response.status_code == 200:
        meme_data = response.json()
        await interaction.response.send_message(meme_data['url'])
    else:
        await interaction.response.send_message("Couldn't fetch a meme at the moment.")

@tree.command(name="roll", description="Roll a dice")
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 6)
    await interaction.response.send_message(f"You rolled a {result}!")

@tree.command(name="stats", description="Get server statistics")
async def server_stats(interaction: discord.Interaction):
    member_count = interaction.guild.member_count
    channel_count = len(interaction.guild.channels)
    role_count = len(interaction.guild.roles)
    
    stats_message = f"**Server Statistics:**\nMembers: {member_count}\nChannels: {channel_count}\nRoles: {role_count}"
    await interaction.response.send_message(stats_message)

@bot.event
async def on_member_join_welcome(member):
    channel = discord.utils.get(member.guild.text_channels, name="welcome")

@tree.command(name="rank", description="Show your current level and XP")
async def rank(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings or not settings.level_enabled:
            await interaction.response.send_message("Leveling system is not enabled on this server.", ephemeral=True)
            return
        
        user_level = session.query(UserLevel).filter_by(
            guild_id=str(interaction.guild_id),
            user_id=str(target_user.id)
        ).first()
        
        if not user_level:
            await interaction.response.send_message(f"{target_user.display_name} hasn't earned any XP yet!", ephemeral=True)
            return
        
        current_level = calculate_level_for_xp(user_level.xp)
        current_level_xp = calculate_xp_for_level(current_level)
        next_level_xp = calculate_xp_for_level(current_level + 1)
        level_progress = user_level.xp - current_level_xp
        level_requirement = next_level_xp - current_level_xp
        progress_bar = generate_progress_bar(level_progress, level_requirement)
        
        response = f"**{target_user.display_name}'s Level Stats**\n"
        response += f"Level: {current_level}\n"
        response += f"Total XP: {user_level.xp}\n"
        response += f"Progress to Level {current_level + 1}:\n"
        response += f"{progress_bar} {level_progress}/{level_requirement} XP"
        
        await interaction.response.send_message(response)

@tree.command(name="leaderboards", description="Show the server's top 10 most active members")
async def leaderboard(interaction: discord.Interaction):
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings or not settings.level_enabled:
            await interaction.response.send_message("Leveling system is not enabled on this server.", ephemeral=True)
            return
        
        top_users = session.query(UserLevel).filter_by(guild_id=str(interaction.guild_id)) \
                           .order_by(UserLevel.xp.desc()).limit(10).all()
        
        if not top_users:
            await interaction.response.send_message("No one has earned any XP yet!", ephemeral=True)
            return
        
        response = "🏆 **Server Leaderboard** 🏆\n\n"
        for i, user_level in enumerate(top_users, 1):
            member = interaction.guild.get_member(int(user_level.user_id))
            if member:
                level = calculate_level_for_xp(user_level.xp)
                response += f"{i}. {member.display_name} - Level {level} ({user_level.xp} XP)\n"
        
        await interaction.response.send_message(response)

@tree.command(name="setupvoice", description="Setup a channel for creating temporary voice channels")
@app_commands.checks.has_permissions(manage_channels=True)
async def setup_voice(interaction: discord.Interaction):
    guild = interaction.guild
    existing_channel = discord.utils.get(guild.voice_channels, name="Create Voice Channel")
    if existing_channel:
        await interaction.response.send_message("The 'Create Voice Channel' already exists.", ephemeral=True)
        return

    new_channel = await guild.create_voice_channel("Create Voice Channel")
    await interaction.response.send_message(f"'Create Voice Channel' has been created: {new_channel.mention}", ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.name == "Create Voice Channel":
        guild = member.guild
        category = after.channel.category
        temp_channel = await guild.create_voice_channel(f"🎮 {member.display_name}'s Channel", category=category)
        await member.move_to(temp_channel)
        await temp_channel.set_permissions(member, manage_channels=True)

        def check_empty_channel():
            if len(temp_channel.members) == 0:
                return True
            return False

        while not check_empty_channel():
            await asyncio.sleep(60)  # Check every minute

        await temp_channel.delete()

@tree.command(name="clear", description="Clear a specified number of messages from a channel")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_messages(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount + 1)  # +1 to remove the command message
    await interaction.response.send_message(f"Cleared {amount} messages.", ephemeral=True)

class NukeView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=60)
        self.channel = channel
    
    @discord.ui.button(label="Confirm Nuke", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Create a new channel with the same settings
            new_channel = await self.channel.clone(reason=f"Channel nuked by {interaction.user}")
            await self.channel.delete()
            await new_channel.send(f"Channel has been nuked by {interaction.user.mention}! 💥")
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to nuke this channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Channel nuke cancelled.", ephemeral=True)
        self.stop()

@tree.command(name="settrustedadmin", description="Set the trusted admin role for nuke command")
@app_commands.checks.has_permissions(administrator=True)
async def set_trusted_admin(interaction: discord.Interaction, role: discord.Role):
    """Set the trusted admin role that can use the nuke command"""
    if not interaction.user.id == interaction.guild.owner_id:
        await interaction.response.send_message("Only the server owner can set the trusted admin role!", ephemeral=True)
        return
    
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings:
            settings = GuildSettings(guild_id=str(interaction.guild_id))
            session.add(settings)
        
        settings.trusted_admin_role_id = str(role.id)
        session.commit()
        
        await interaction.response.send_message(f"Set {role.mention} as the trusted admin role.", ephemeral=True)

@tree.command(name="nuke", description="💣 Completely clear a channel by recreating it")
@app_commands.checks.has_permissions(administrator=True)
async def nuke_channel(interaction: discord.Interaction):
    """Nuke the current channel by deleting and recreating it"""
    with Session(engine) as session:
        settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
        
        if not settings or not settings.trusted_admin_role_id:
            await interaction.response.send_message(
                "The trusted admin role has not been set up. Please ask the server owner to set it up using /settrustedadmin",
                ephemeral=True
            )
            return
        
        member = interaction.guild.get_member(interaction.user.id)
        if not any(role.id == int(settings.trusted_admin_role_id) for role in member.roles):
            await interaction.response.send_message(
                "You need the trusted admin role to use this command!",
                ephemeral=True
            )
            return
    
    view = NukeView(interaction.channel)
    await interaction.response.send_message(
        "⚠️ **WARNING**: This will delete **ALL** messages in this channel.\n"
        "The channel will be recreated with the same permissions and settings.\n"
        "This action cannot be undone!\n\n"
        "Are you sure you want to proceed?",
        view=view,
        ephemeral=True
    )


@tree.command(name="remind", description="Set a reminder")
async def set_reminder(interaction: discord.Interaction, duration: int, *, reminder: str):
    await interaction.response.send_message(f"Reminder set for {duration} minutes!", ephemeral=True)
    await asyncio.sleep(duration * 60)
    await interaction.user.send(f"⏰ Reminder: {reminder}")

@tree.command(name="avatar", description="Get a user's avatar")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    await interaction.response.send_message(user.avatar.url)

@tree.command(name="say", description="Make the bot say something")
@app_commands.checks.has_permissions(manage_messages=True)
async def say(interaction: discord.Interaction, *, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent!", ephemeral=True)

@tree.command(name="unban", description="Unban a user from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        
        # Log the unban if there's a log channel
        with Session(engine) as session:
            settings = session.query(GuildSettings).filter_by(guild_id=str(interaction.guild_id)).first()
            if settings and settings.log_channel_id:
                log_channel = interaction.guild.get_channel(int(settings.log_channel_id))
                if log_channel:
                    await log_channel.send(f"🔓 {interaction.user.mention} unbanned user {user.name} (ID: {user.id})")
        
        await interaction.response.send_message(f"Successfully unbanned {user.name}#{user.discriminator}", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("Invalid user ID provided.", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("User not found or already unbanned.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to unban members.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

@tree.command(name="invite", description="Get the bot's invite link")
async def invite_link(interaction: discord.Interaction):
    client_id = os.environ.get('CLIENT_ID')
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot"
    await interaction.response.send_message(f"Invite me to your server: {invite_url}")

@tree.command(name="kickall", description="Kick all members with a specific role")
@app_commands.checks.has_permissions(kick_members=True)
async def kick_all(interaction: discord.Interaction, role: discord.Role):
    for member in role.members:
        await member.kick(reason="Kicked by command")
    await interaction.response.send_message(f"Kicked all members with the role {role.name}.")

@tree.command(name="slowmode", description="Set slowmode for a channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"Slowmode set to {seconds} seconds for this channel.")

@tree.command(name="quote", description="Quote a message by message ID")
async def quote_message(interaction: discord.Interaction, message_id: int):
    channel = interaction.channel
    try:
        message = await channel.fetch_message(message_id)
        await interaction.response.send_message(f"> {message.content} - {message.author.mention}", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("Message not found.", ephemeral=True)

@tree.command(name="weather", description="Get the current weather for a specified location")
async def weather(interaction: discord.Interaction, location: str):
    # You would need to integrate with a weather API
    weather_info = f"Current weather in {location}: Sunny, 25°C."  # Placeholder response
    await interaction.response.send_message(weather_info)

@tree.command(name="flip", description="Flip a coin")
async def flip_coin_alternative(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"You flipped: {result}")

@tree.command(name="userinfo", description="Get information about a user")
async def user_info(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.name}'s Info", color=discord.Color.blue())
    embed.add_field(name="ID", value=user.id)
    embed.add_field(name="Joined at", value=user.joined_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.add_field(name="Roles", value=", ".join([role.name for role in user.roles if role.name != "@everyone"]))
    embed.set_thumbnail(url=user.avatar.url)
    await interaction.response.send_message(embed=embed)


@tree.command(name="servericon", description="Get the server's icon URL")
async def server_icon(interaction: discord.Interaction):
    await interaction.response.send_message(interaction.guild.icon.url)

@tree.command(name="setnickname", description="Set a user's nickname")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def set_nickname(interaction: discord.Interaction, user: discord.Member, nickname: str):
    await user.edit(nick=nickname)
    await interaction.response.send_message(f"Set {user.mention}'s nickname to {nickname}.")

@tree.command(name="clearroles", description="Clear all roles from a user")
@app_commands.checks.has_permissions(manage_roles=True)
async def clear_roles(interaction: discord.Interaction, user: discord.Member):
    roles = user.roles[1:]  # Exclude @everyone
    await user.remove_roles(*roles)
    await interaction.response.send_message(f"Cleared all roles from {user.mention}.")

@tree.command(name="help", description="List all available commands")
async def help_command(interaction: discord.Interaction):
    help_message = (
        "**Available Commands:**\n"
        "/help - List all available commands\n"
        "/poll <question> <option1, option2, ...> - Create a poll with options\n"
        "/setlogchannel <channel> - Set a channel for logging anti-nuke actions\n"
        "/checkrecentactions - Check recent actions that triggered anti-nuke\n"
        "/resetrecentactions - Reset the recent actions log\n"
        "/setantinuke <enabled> - Enable or disable anti-nuke features\n"
        "/setwelcome <channel> <message> <enabled> - Configure welcome message settings\n"
        "/addfilter <word> - Add a word or phrase to the filter list\n"
        "/removefilter <word> - Remove a word or phrase from the filter list\n"
        "/listfilters - List all filtered words and phrases\n"
        "/togglefilter <enabled> - Enable or disable the word filter\n"
        "/setranking <enabled> - Enable or disable the ranking system\n"
        "/leaderboard - Show the server's top 10 most active members\n"
        "/rank <user> - Show your current level and XP\n"
        "/meme - Get a random meme\n"
        "/flipcoin - Flip a coin\n"
        "/roll - Roll a dice\n"
        "/stats - Get server statistics\n"
        "/reactionroles <role> - Set up reaction roles\n"
        "/feedback <text> - Submit feedback or suggestions\n"
        "/setupvoice - Setup a channel for creating temporary voice channels"
    )

    await interaction.response.send_message(help_message, ephemeral=True)

@tree.command(name="voicelimit", description="Set user limit for your temporary voice channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def voice_limit(interaction: discord.Interaction, limit: int):
    if interaction.user.voice and interaction.user.voice.channel:
        channel = interaction.user.voice.channel
        if channel.name.startswith("🎮") and channel.name.endswith("'s Channel"):
            await channel.edit(user_limit=limit)
            await interaction.response.send_message(f"User limit set to {limit} for {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message("You can only set the limit for your own temporary channel.", ephemeral=True)
    else:
        await interaction.response.send_message("You are not in a temporary voice channel.", ephemeral=True)

def main():
    apply_sqlite_migrations(engine, Base, 'migrations')
    
    client_id = os.environ.get('CLIENT_ID')
    bot_token = os.environ.get('BOT_TOKEN')
    
    if not client_id and not bot_token:
        print("🚨 Error: Both CLIENT_ID and BOT_TOKEN are invalid or missing. Please check your Discord Developer Portal for the correct values.")
        return
    elif not client_id:
        print("🚨 Error: CLIENT_ID is invalid or missing. Please check your Discord Developer Portal for the correct value.")
        return
    elif not bot_token:
        print("🚨 Error: BOT_TOKEN is invalid or missing. Please check your Discord Developer Portal for the correct value.")
        return
    try:
        oauth_link = generate_oauth_link(client_id)
        print(f"🔗 Click this link to invite your Discord bot to your server 👉 {oauth_link}")
        bot.run(bot_token)
    except discord.errors.LoginFailure:
        print("🚨 Error: Invalid BOT_TOKEN. Please check your Discord Developer Portal for the correct value.")
    except Exception as e:
        print(f"🚨 Error: An unexpected error occurred: {str(e)}")
    return

if __name__ == "__main__":
    main()
