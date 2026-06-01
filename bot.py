import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import random
from player import MusicPlayer

# ── Config ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
MUSIC_DIR = os.getenv("MUSIC_DIR", "/music")
SUPPORTED_FORMATS = (".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac")

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # Required: enable in Discord Developer Portal
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
player = MusicPlayer()  # Shared state between bot and API


def find_tracks(query: str = None) -> list[str]:
    """Walk MUSIC_DIR and return matching file paths."""
    tracks = []
    for root, _, files in os.walk(MUSIC_DIR):
        for f in files:
            if f.lower().endswith(SUPPORTED_FORMATS):
                full_path = os.path.join(root, f)
                if query is None or query.lower() in f.lower() or query.lower() in root.lower():
                    tracks.append(full_path)
    return sorted(tracks)


async def play_next(guild: discord.Guild):
    """Pull the next track from the queue and play it."""
    vc = guild.voice_client
    if not vc:
        return

    track = player.next_track()
    if not track:
        player.set_now_playing(None)
        return

    player.set_now_playing(track)

    source = discord.FFmpegPCMAudio(track)
    source = discord.PCMVolumeTransformer(source, volume=player.volume)

    def after(error):
        if error:
            print(f"Player error: {error}")
        fut = asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)
        fut.add_done_callback(
            lambda f: print(f"play_next raised: {f.exception()}") if not f.cancelled() and f.exception() else None
        )

    vc.play(source, after=after)


# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# ── Slash commands ────────────────────────────────────────────────────────────
@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("You need to be in a voice channel first.", ephemeral=True)
        return
    channel = interaction.user.voice.channel
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.move_to(channel)
    else:
        await channel.connect()
    await interaction.response.send_message(f"Joined **{channel.name}**")


@bot.tree.command(name="play", description="Search and queue a track by name")
@app_commands.describe(query="Song name, artist, or album to search for")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.guild.voice_client:
        if interaction.user.voice:
            await interaction.user.voice.channel.connect()
        else:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return

    await interaction.response.defer()
    results = find_tracks(query)

    if not results:
        await interaction.followup.send(f"No tracks found matching **{query}**")
        return

    added = player.add_to_queue(results[0])
    name = os.path.basename(results[0])

    if not interaction.guild.voice_client.is_playing():
        await play_next(interaction.guild)
        await interaction.followup.send(f"▶️ Now playing: **{name}**")
    else:
        await interaction.followup.send(f"➕ Added to queue: **{name}**")


@bot.tree.command(name="queue", description="Add all results for a search to the queue")
@app_commands.describe(query="Search term — leave blank to queue everything")
async def queue_cmd(interaction: discord.Interaction, query: str = None):
    if not interaction.guild.voice_client:
        if interaction.user.voice:
            await interaction.user.voice.channel.connect()
        else:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return

    await interaction.response.defer()
    tracks = find_tracks(query)

    if not tracks:
        await interaction.followup.send("No tracks found.")
        return

    for t in tracks:
        player.add_to_queue(t)

    was_playing = interaction.guild.voice_client.is_playing()
    if not was_playing:
        await play_next(interaction.guild)

    await interaction.followup.send(f"➕ Queued **{len(tracks)}** tracks{f' matching `{query}`' if query else ''}")


@bot.tree.command(name="skip", description="Skip the current track")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()  # Triggers after() → play_next()
        await interaction.response.send_message("⏭️ Skipped")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@bot.tree.command(name="pause", description="Pause or resume playback")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        await interaction.response.send_message("Not in a voice channel.", ephemeral=True)
        return
    if vc.is_paused():
        vc.resume()
        player.set_paused(False)
        await interaction.response.send_message("▶️ Resumed")
    elif vc.is_playing():
        vc.pause()
        player.set_paused(True)
        await interaction.response.send_message("⏸️ Paused")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        player.clear_queue()
        player.set_now_playing(None)
        vc.stop()
        await vc.disconnect()
    await interaction.response.send_message("⏹️ Stopped and disconnected")


@bot.tree.command(name="shuffle", description="Shuffle the current queue")
async def shuffle(interaction: discord.Interaction):
    player.shuffle_queue()
    await interaction.response.send_message("🔀 Queue shuffled")


@bot.tree.command(name="loop", description="Toggle loop/repeat for the current track")
async def loop(interaction: discord.Interaction):
    is_looping = player.toggle_loop()
    await interaction.response.send_message(
        f"🔁 Loop **{'on' if is_looping else 'off'}**"
    )


@bot.tree.command(name="volume", description="Set volume (0-100)")
@app_commands.describe(level="Volume level between 0 and 100")
async def volume(interaction: discord.Interaction, level: int):
    if not 0 <= level <= 100:
        await interaction.response.send_message("Volume must be between 0 and 100.", ephemeral=True)
        return
    player.set_volume(level / 100)
    vc = interaction.guild.voice_client
    if vc and vc.source:
        vc.source.volume = player.volume
    await interaction.response.send_message(f"🔊 Volume set to **{level}%**")


@bot.tree.command(name="nowplaying", description="Show the current track and queue")
async def nowplaying(interaction: discord.Interaction):
    np = player.now_playing
    queue = player.get_queue()

    if not np:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return

    embed = discord.Embed(title="🎵 Now Playing", color=0x1DB954)
    embed.description = f"**{os.path.basename(np)}**"
    embed.add_field(
        name=f"Up next ({len(queue)} tracks)",
        value="\n".join(f"`{i+1}.` {os.path.basename(t)}" for i, t in enumerate(queue[:5])) or "Queue is empty",
        inline=False
    )
    embed.set_footer(text=f"Volume: {int(player.volume * 100)}% | {'⏸ Paused' if player.paused else '▶ Playing'}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="search", description="Search your library and list results")
@app_commands.describe(query="What to search for")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)
    results = find_tracks(query)[:10]
    if not results:
        await interaction.followup.send(f"No results for **{query}**")
        return
    lines = [f"`{i+1}.` {os.path.basename(t)}" for i, t in enumerate(results)]
    await interaction.followup.send(f"**Results for `{query}`:**\n" + "\n".join(lines))
