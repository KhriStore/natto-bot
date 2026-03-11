import discord
from discord.ext import commands
import asyncio
from typing import Optional
import json
import os
from web_server import keep_alive

# Konfigurasi - PAKE ENVIRONMENT VARIABLE
TOKEN = os.environ.get('DISCORD_TOKEN')  # AMBIL DARI ENVIRONMENT
TARGET_CHANNEL_NAME = os.environ.get('TARGET_CHANNEL', "➕ Buat Channel")

# Data untuk menyimpan channel yang dibuat
if not os.path.exists('data.json'):
    with open('data.json', 'w') as f:
        json.dump({}, f)

# Intents yang diperlukan
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

class VoiceChannelManager:
    def __init__(self):
        self.owner_channels = {}  # voice_channel_id: owner_id
        self.text_channels = {}   # voice_channel_id: text_channel_id
        self.channel_settings = {}  # channel_id: settings
        
    def load_data(self):
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)
                self.owner_channels = {int(k): v for k, v in data.get('owner_channels', {}).items()}
                self.text_channels = {int(k): v for k, v in data.get('text_channels', {}).items()}
                self.channel_settings = {int(k): v for k, v in data.get('channel_settings', {}).items()}
        except:
            pass
    
    def save_data(self):
        data = {
            'owner_channels': {str(k): v for k, v in self.owner_channels.items()},
            'text_channels': {str(k): v for k, v in self.text_channels.items()},
            'channel_settings': {str(k): v for k, v in self.channel_settings.items()}
        }
        with open('data.json', 'w') as f:
            json.dump(data, f, indent=4)

manager = VoiceChannelManager()
manager.load_data()

@bot.event
async def on_ready():
    print(f'{bot.user} telah online!')
    await bot.change_presence(activity=discord.Game(name="!bantuan untuk help"))

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    guild = member.guild
    
    # Cek jika user join ke channel target
    if after.channel and after.channel.name == TARGET_CHANNEL_NAME:
        await create_voice_channel(member, after.channel.category)
    
    # Cek jika channel kosong (tidak ada user)
    if before.channel and before.channel.id in manager.owner_channels:
        channel = before.channel
        if len(channel.members) == 0:
            await cleanup_empty_channel(channel)

async def create_voice_channel(member, category):
    """Membuat voice channel dan text channel baru untuk user"""
    guild = member.guild
    
    # Buat voice channel
    voice_channel_name = f"{member.name}'s Voice"
    
    # Set permission overwrites untuk voice channel
    voice_overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
        member: discord.PermissionOverwrite(connect=True, manage_channels=True, 
                                            mute_members=True, deafen_members=True, move_members=True)
    }
    
    try:
        # Buat voice channel
        voice_channel = await guild.create_voice_channel(
            name=voice_channel_name,
            category=category,
            overwrites=voice_overwrites,
            user_limit=0
        )
        
        # Buat text channel untuk chat
        text_channel_name = f"chat-{member.name.lower()}"
        
        # Set permission untuk text channel
        text_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, 
                                               manage_channels=True, manage_messages=True)
        }
        
        text_channel = await guild.create_text_channel(
            name=text_channel_name,
            category=category,
            overwrites=text_overwrites,
            topic=f"Text channel untuk {voice_channel_name} - Hanya owner yang bisa mengelola"
        )
        
        # Simpan data
        manager.owner_channels[voice_channel.id] = member.id
        manager.text_channels[voice_channel.id] = text_channel.id
        manager.channel_settings[voice_channel.id] = {
            'owner': member.id,
            'voice_name': voice_channel_name,
            'text_name': text_channel_name,
            'user_limit': 0,
            'created_at': str(discord.utils.utcnow())
        }
        manager.save_data()
        
        # Pindahkan user ke voice channel baru
        await member.move_to(voice_channel)
        
        # Kirim tutorial ke DM
        await send_tutorial_dm(member, voice_channel, text_channel)
        
        # Kirim tutorial ke text channel
        await send_tutorial_text_channel(text_channel, member, voice_channel)
        
        # Kirim pesan selamat datang di text channel
        welcome_embed = discord.Embed(
            title="🎉 Selamat Datang di Channel Baru!",
            description=f"Selamat {member.mention}, kamu sekarang adalah **owner** dari channel ini!",
            color=discord.Color.gold()
        )
        welcome_embed.add_field(name="📢 Info", value="Gunakan command di bawah untuk mengelola channel.")
        await text_channel.send(embed=welcome_embed)
        
    except Exception as e:
        print(f"Error creating channels: {e}")

async def send_tutorial_dm(member, voice_channel, text_channel):
    """Mengirim tutorial ke DM user"""
    embed = discord.Embed(
        title="🎮 **Voice Channel Created!**",
        description=f"Channel **{voice_channel.name}** dan **{text_channel.name}** berhasil dibuat!",
        color=discord.Color.green()
    )
    
    embed.add_field(name="📍 **Lokasi Channel**", value=f"📢 Text: {text_channel.mention}\n🔊 Voice: {voice_channel.mention}", inline=False)
    
    embed.add_field(name="📝 **Command Tersedia**", value="""
    **🔧 Basic Commands:**
    `!name <nama>` - Ganti nama voice channel
    `!tname <nama>` - Ganti nama text channel
    `!limit <jumlah>` - Set batas user (0 = unlimited)
    `!info` - Lihat info channel
    
    **🔒 Permission Commands:**
    `!hide` - Sembunyikan voice channel
    `!unhide` - Tampilkan voice channel
    `!lock` - Kunci voice channel
    `!unlock` - Buka kunci voice channel
    
    **👥 User Management:**
    `!kick @user` - Kick user dari voice
    `!ban @user` - Ban user dari channel
    `!unban @user` - Unban user
    `!give @user` - Transfer ownership
    `!claim` - Claim abandoned channel
    
    **⚠️ Danger Zone:**
    `!delete` - Hapus kedua channel
    """, inline=False)
    
    embed.add_field(name="💡 **Tips**", value="Ketik `!bantuan` di text channel untuk lihat semua command!", inline=False)
    embed.set_footer(text="Kamu adalah owner dari channel ini!")
    
    try:
        await member.send(embed=embed)
    except:
        pass  # DM terkunci

async def send_tutorial_text_channel(text_channel, member, voice_channel):
    """Mengirim tutorial ke text channel yang baru dibuat"""
    embed = discord.Embed(
        title="📚 **Tutorial Penggunaan Channel**",
        description=f"Halo {member.mention}! Selamat datang di channel pribadimu.",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="🎯 **Cara Menggunakan**", value="""
    1️⃣ **Manage Voice Channel** - Gunakan command di text channel ini
    2️⃣ **Invite Teman** - Mention mereka di sini atau beri role khusus
    3️⃣ **Customize Channel** - Atur nama, limit, dan permission
    """, inline=False)
    
    embed.add_field(name="⚡ **Quick Commands**", value="""
    `!name Ruang Gaming` - Ganti nama voice
    `!limit 5` - Batasi 5 orang
    `!hide` - Sembunyikan dari publik
    `!kick @user` - Keluarkan user
    """, inline=False)
    
    embed.add_field(name="❓ **Butuh Bantuan?**", value="Ketik `!bantuan` untuk melihat semua command yang tersedia!")
    
    await text_channel.send(embed=embed)

async def cleanup_empty_channel(voice_channel):
    """Membersihkan voice dan text channel yang sudah tidak digunakan"""
    if voice_channel.id in manager.text_channels:
        text_channel_id = manager.text_channels[voice_channel.id]
        text_channel = voice_channel.guild.get_channel(text_channel_id)
        
        # Hapus text channel
        if text_channel:
            try:
                await text_channel.delete()
                print(f"Text channel {text_channel.name} dihapus")
            except:
                pass
    
    # Hapus data
    if voice_channel.id in manager.owner_channels:
        del manager.owner_channels[voice_channel.id]
    if voice_channel.id in manager.text_channels:
        del manager.text_channels[voice_channel.id]
    if voice_channel.id in manager.channel_settings:
        del manager.channel_settings[voice_channel.id]
    manager.save_data()
    
    # Hapus voice channel
    try:
        await voice_channel.delete()
        print(f"Voice channel {voice_channel.name} dihapus karena kosong")
    except:
        pass

def is_voice_owner():
    """Check if user is owner of the voice channel"""
    async def predicate(ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ Kamu harus berada di voice channel!")
            return False
        
        channel_id = ctx.author.voice.channel.id
        if channel_id not in manager.owner_channels:
            await ctx.send("❌ Ini bukan channel privat yang bisa dikustomisasi!")
            return False
        
        if manager.owner_channels[channel_id] != ctx.author.id:
            # Cek apakah user punya permission manage_channels
            permissions = ctx.author.voice.channel.permissions_for(ctx.author)
            if not permissions.manage_channels:
                await ctx.send("❌ Kamu bukan owner channel ini!")
                return False
        
        return True
    return commands.check(predicate)

@bot.command(name='name')
@is_voice_owner()
async def change_name(ctx, *, new_name: str):
    """Mengganti nama voice channel"""
    if len(new_name) > 100:
        await ctx.send("❌ Nama channel terlalu panjang! Maksimal 100 karakter.")
        return
    
    channel = ctx.author.voice.channel
    old_name = channel.name
    await channel.edit(name=new_name)
    
    # Update settings
    if channel.id in manager.channel_settings:
        manager.channel_settings[channel.id]['voice_name'] = new_name
        manager.save_data()
    
    await ctx.send(f"✅ Nama voice channel diubah dari **{old_name}** menjadi **{new_name}**")

@bot.command(name='tname')
@is_voice_owner()
async def change_text_name(ctx, *, new_name: str):
    """Mengganti nama text channel"""
    if len(new_name) > 100:
        await ctx.send("❌ Nama channel terlalu panjang! Maksimal 100 karakter.")
        return
    
    if ctx.author.voice.channel.id not in manager.text_channels:
        await ctx.send("❌ Text channel tidak ditemukan!")
        return
    
    text_channel_id = manager.text_channels[ctx.author.voice.channel.id]
    text_channel = ctx.guild.get_channel(text_channel_id)
    
    if not text_channel:
        await ctx.send("❌ Text channel tidak ditemukan!")
        return
    
    old_name = text_channel.name
    await text_channel.edit(name=new_name)
    
    # Update settings
    if ctx.author.voice.channel.id in manager.channel_settings:
        manager.channel_settings[ctx.author.voice.channel.id]['text_name'] = new_name
        manager.save_data()
    
    await ctx.send(f"✅ Nama text channel diubah dari **{old_name}** menjadi **{new_name}**")

@bot.command(name='limit')
@is_voice_owner()
async def set_limit(ctx, limit: int):
    """Mengatur batas user dalam channel (0 = unlimited)"""
    if limit < 0:
        await ctx.send("❌ Limit tidak boleh negatif!")
        return
    
    channel = ctx.author.voice.channel
    await channel.edit(user_limit=limit)
    
    # Update settings
    if channel.id in manager.channel_settings:
        manager.channel_settings[channel.id]['user_limit'] = limit
        manager.save_data()
    
    if limit == 0:
        await ctx.send("✅ Batas user dihapus (unlimited)")
    else:
        await ctx.send(f"✅ Batas user diatur menjadi **{limit}** orang")

@bot.command(name='hide')
@is_voice_owner()
async def hide_channel(ctx):
    """Menyembunyikan channel dari semua orang"""
    channel = ctx.author.voice.channel
    guild = ctx.guild
    
    # Set permission untuk @everyone
    await channel.set_permissions(guild.default_role, connect=False, view_channel=False)
    
    await ctx.send("✅ Voice channel disembunyikan dari semua orang!")

@bot.command(name='unhide')
@is_voice_owner()
async def unhide_channel(ctx):
    """Menampilkan channel ke semua orang"""
    channel = ctx.author.voice.channel
    guild = ctx.guild
    
    # Reset permission untuk @everyone
    await channel.set_permissions(guild.default_role, connect=False, view_channel=None)
    
    await ctx.send("✅ Voice channel sekarang terlihat oleh semua orang!")

@bot.command(name='lock')
@is_voice_owner()
async def lock_channel(ctx):
    """Mengunci channel (tidak bisa join)"""
    channel = ctx.author.voice.channel
    guild = ctx.guild
    
    await channel.set_permissions(guild.default_role, connect=False)
    
    await ctx.send("✅ Voice channel dikunci! Tidak ada yang bisa join.")

@bot.command(name='unlock')
@is_voice_owner()
async def unlock_channel(ctx):
    """Membuka kunci channel"""
    channel = ctx.author.voice.channel
    guild = ctx.guild
    
    await channel.set_permissions(guild.default_role, connect=None)
    
    await ctx.send("✅ Voice channel dibuka! Semua orang bisa join.")

@bot.command(name='kick')
@is_voice_owner()
async def kick_user(ctx, member: discord.Member):
    """Mengeluarkan user dari voice channel"""
    channel = ctx.author.voice.channel
    
    if member == ctx.author:
        await ctx.send("❌ Tidak bisa kick diri sendiri!")
        return
    
    if member.voice and member.voice.channel == channel:
        await member.move_to(None)
        await ctx.send(f"✅ **{member.display_name}** dikeluarkan dari voice channel!")
    else:
        await ctx.send(f"❌ **{member.display_name}** tidak ada di voice channel ini!")

@bot.command(name='ban')
@is_voice_owner()
async def ban_user(ctx, member: discord.Member):
    """Melarang user masuk ke channel"""
    channel = ctx.author.voice.channel
    
    # Kick user jika sedang di channel
    if member.voice and member.voice.channel == channel:
        await member.move_to(None)
    
    # Set permission banned
    await channel.set_permissions(member, connect=False, view_channel=False)
    
    await ctx.send(f"✅ **{member.display_name}** dilarang masuk ke voice channel!")

@bot.command(name='unban')
@is_voice_owner()
async def unban_user(ctx, member: discord.Member):
    """Membatalkan larangan user"""
    channel = ctx.author.voice.channel
    
    # Reset permission
    await channel.set_permissions(member, overwrite=None)
    
    await ctx.send(f"✅ **{member.display_name}** bisa masuk voice channel lagi!")

@bot.command(name='give')
@is_voice_owner()
async def give_ownership(ctx, member: discord.Member):
    """Memberikan kepemilikan channel ke user lain"""
    voice_channel = ctx.author.voice.channel
    
    if member.bot:
        await ctx.send("❌ Tidak bisa memberikan kepemilikan ke bot!")
        return
    
    # Dapatkan text channel
    text_channel_id = manager.text_channels.get(voice_channel.id)
    text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None
    
    # Update owner
    manager.owner_channels[voice_channel.id] = member.id
    if voice_channel.id in manager.channel_settings:
        manager.channel_settings[voice_channel.id]['owner'] = member.id
    manager.save_data()
    
    # Set permissions di voice channel
    await voice_channel.set_permissions(ctx.author, overwrite=None)
    await voice_channel.set_permissions(member, connect=True, manage_channels=True, 
                                       mute_members=True, deafen_members=True, move_members=True)
    
    # Set permissions di text channel jika ada
    if text_channel:
        await text_channel.set_permissions(ctx.author, overwrite=None)
        await text_channel.set_permissions(member, read_messages=True, send_messages=True,
                                          manage_channels=True, manage_messages=True)
    
    await ctx.send(f"✅ Kepemilikan channel diberikan ke **{member.display_name}**!")

@bot.command(name='claim')
async def claim_ownership(ctx):
    """Mengambil alih channel yang ditinggal owner"""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Kamu harus berada di voice channel!")
        return
    
    voice_channel = ctx.author.voice.channel
    if voice_channel.id not in manager.owner_channels:
        await ctx.send("❌ Ini bukan channel privat!")
        return
    
    # Dapatkan text channel
    text_channel_id = manager.text_channels.get(voice_channel.id)
    text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None
    
    # Cek apakah owner masih ada di channel
    owner_id = manager.owner_channels[voice_channel.id]
    owner = ctx.guild.get_member(owner_id)
    
    if owner and owner.voice and owner.voice.channel == voice_channel:
        await ctx.send("❌ Owner masih ada di channel!")
        return
    
    # Claim channel
    manager.owner_channels[voice_channel.id] = ctx.author.id
    if voice_channel.id in manager.channel_settings:
        manager.channel_settings[voice_channel.id]['owner'] = ctx.author.id
    manager.save_data()
    
    # Set permissions di voice channel
    if owner:
        await voice_channel.set_permissions(owner, overwrite=None)
    await voice_channel.set_permissions(ctx.author, connect=True, manage_channels=True,
                                       mute_members=True, deafen_members=True, move_members=True)
    
    # Set permissions di text channel
    if text_channel:
        if owner:
            await text_channel.set_permissions(owner, overwrite=None)
        await text_channel.set_permissions(ctx.author, read_messages=True, send_messages=True,
                                          manage_channels=True, manage_messages=True)
    
    await ctx.send(f"✅ Kamu sekarang menjadi owner channel **{voice_channel.name}**!")

@bot.command(name='delete')
@is_voice_owner()
async def delete_channels(ctx):
    """Menghapus voice dan text channel (hanya owner)"""
    voice_channel = ctx.author.voice.channel
    
    # Confirm deletion
    await ctx.send("⚠️ Apakah kamu yakin ingin menghapus **SEMUA** channel ini? (Ketik `yes` dalam 10 detik)")
    
    def check(m):
        return m.author == ctx.author and m.content.lower() == 'yes'
    
    try:
        await bot.wait_for('message', timeout=10.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("❌ Penghapusan dibatalkan.")
        return
    
    # Dapatkan text channel
    text_channel_id = manager.text_channels.get(voice_channel.id)
    text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None
    
    # Hapus text channel dulu
    if text_channel:
        try:
            await text_channel.delete()
        except:
            pass
    
    # Clean up data
    if voice_channel.id in manager.owner_channels:
        del manager.owner_channels[voice_channel.id]
    if voice_channel.id in manager.text_channels:
        del manager.text_channels[voice_channel.id]
    if voice_channel.id in manager.channel_settings:
        del manager.channel_settings[voice_channel.id]
    manager.save_data()
    
    await ctx.send(f"✅ Channel **{voice_channel.name}** dan text channel akan dihapus!")
    await voice_channel.delete()

@bot.command(name='info')
async def channel_info(ctx):
    """Menampilkan informasi channel"""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Kamu harus berada di voice channel!")
        return
    
    voice_channel = ctx.author.voice.channel
    if voice_channel.id not in manager.owner_channels:
        await ctx.send("❌ Ini bukan channel privat!")
        return
    
    owner = ctx.guild.get_member(manager.owner_channels[voice_channel.id])
    settings = manager.channel_settings.get(voice_channel.id, {})
    text_channel_id = manager.text_channels.get(voice_channel.id)
    text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None
    
    embed = discord.Embed(
        title=f"📊 Informasi Channel",
        color=discord.Color.blue()
    )
    embed.add_field(name="👑 Owner", value=owner.mention if owner else "Unknown")
    embed.add_field(name="🔊 Voice Channel", value=voice_channel.name)
    embed.add_field(name="📢 Text Channel", value=text_channel.mention if text_channel else "None")
    embed.add_field(name="👥 Member Voice", value=f"{len(voice_channel.members)}/{voice_channel.user_limit if voice_channel.user_limit > 0 else '∞'}")
    embed.add_field(name="📝 Dibuat", value=settings.get('created_at', 'Unknown')[:10])
    
    await ctx.send(embed=embed)

@bot.command(name='bantuan')
async def custom_help(ctx):
    """Menampilkan bantuan"""
    embed = discord.Embed(
        title="🎮 **Voice Channel Bot - Command List**",
        description="Commands untuk mengelola voice channel privat dan text channel-nya",
        color=discord.Color.purple()
    )
    
    embed.add_field(name="📝 **Basic Commands**", value="""
    `!name <nama>` - Ganti nama voice channel
    `!tname <nama>` - Ganti nama text channel
    `!limit <jumlah>` - Set batas user (0 = unlimited)
    `!info` - Lihat info channel
    """, inline=False)
    
    embed.add_field(name="🔒 **Permission Commands**", value="""
    `!hide` - Sembunyikan voice channel
    `!unhide` - Tampilkan voice channel
    `!lock` - Kunci voice channel
    `!unlock` - Buka kunci voice channel
    """, inline=False)
    
    embed.add_field(name="👥 **User Management**", value="""
    `!kick @user` - Kick user dari voice
    `!ban @user` - Ban user dari channel
    `!unban @user` - Unban user
    `!give @user` - Transfer ownership
    `!claim` - Claim abandoned channel
    """, inline=False)
    
    embed.add_field(name="⚠️ **Danger Zone**", value="""
    `!delete` - Hapus voice dan text channel
    """, inline=False)
    
    embed.add_field(name="💡 **Cara Membuat Channel**", value=f"Join voice channel **{TARGET_CHANNEL_NAME}** untuk membuat channel pribadimu!")
    
    embed.set_footer(text="Semua command bisa digunakan di text channel ini!")
    
    await ctx.send(embed=embed)

# Jalankan bot
if __name__ == "__main__":
    keep_alive()  # NYALAKAN WEB SERVER DULU

    bot.run(TOKEN)
