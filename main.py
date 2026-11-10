from pathlib import Path
from types import ModuleType
from typing import Literal
import discord
import importlib.util as importlib
from discord import app_commands
from psycopg import sql
from psycopg.types.json import Jsonb
from api import commands, db, permission

DIR = Path(__file__).parent.absolute()

def load_module(path: Path):
    spec = importlib.spec_from_file_location(f"filters.{path.stem}", path)
    mod = importlib.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
    
FILTERS: dict[str, ModuleType] = {p.stem: load_module(p) for p in (DIR / "filters").glob("[!_.]*.py")}

def get_profiles(userid: int):
    query = sql.SQL("SELECT {column} FROM {schema}.{table} WHERE {key} = %s").format(
        schema = db.SCHEMA,
        table = sql.Identifier("sonny_proxy$profiles"),
        column = sql.SQL(", ").join(sql.Identifier(c) for c in ["userid", "name", "avatar", "prefix", "filter"]),
        key = sql.Identifier("userid")
        )
    return db.multiple(query, (userid,))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proxy(bot=bot))

class Proxy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    proxy = app_commands.Group(name="proxy", description="Manage proxy profiles")

    @proxy.command(name="edit", description="Edit your proxy profile")
    async def proxy_edit(
        self,
        interaction: discord.Interaction,
        name: str | None = None,
        avatar: discord.Attachment | None = None,
        prefix: str | None = None,
        filter: Literal[tuple(FILTERS) + ("None",)] | None = None,
        filter_arg: str | None = None):
        user = interaction.user
        name = name or user.name
        # Should i default the avatar to the user's or none?
        db.insert("sonny_proxy$profiles", ("userid", "name"), ("avatar",), (user.id, name, avatar.url if avatar else None or user.avatar.url))
        
        if prefix: db.insert("sonny_proxy$profiles", ("userid", "name"), ("prefix",), (user.id, name, prefix))
        if filter: db.insert("sonny_proxy$profiles", ("userid", "name"), ("filter",), (user.id, name, Jsonb({filter: filter_arg})))
            
        await interaction.response.send_message("Updated!", ephemeral=True)

    @proxy.command(name="list", description="List your proxy profiles")
    async def proxy_list(self, interaction: discord.Interaction):
        profiles = get_profiles(interaction.user.id)
        if not profiles: await interaction.response.send_message("None or failed", ephemeral=True)
        else: await interaction.response.send_message(profiles, ephemeral=True)

    @proxy.command(name="delete", description="Delete a proxy profile")
    async def proxy_delete(self, interaction: discord.Interaction, name: str):
        profiles = get_profiles(interaction.user.id)
        if not (p for p in profiles if p[1] == name): await interaction.response.send_message("No profile of that name")
        db.delete("sonny_proxy$profiles", ("userid", "name"), (interaction.user.id, name))
        profiles = get_profiles(interaction.user.id)
        if (p for p in profiles if p[1] == name): await interaction.response.send_message("Deleted", ephemeral=True)

    @proxy.command(name="lock", description="Lock a user to a filter.")
    async def filter_lock(self, interaction: discord.Interaction, member: discord.Member,
        filter: Literal[tuple(FILTERS) + ("None",)], filter_arg: str | None = None):
        if not permission.check(interaction.guild_id, interaction.user.id, "filter_lock"):
             await interaction.response.send_message(":x: No permission")
        db.insert("sonny_proxy$locks", ("serverid", "userid"), ("filter",), (interaction.guild_id, member.id, Jsonb({filter: filter_arg})))
        await interaction.response.send_message(f"Locked {member.name} to {filter}", ephemeral=True)

    @proxy.command(name="locks", description="View a filter lock on a user.")
    async def filter_lock_list(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not permission.check(interaction.guild_id, interaction.user.id, "filter_lock"):
                await interaction.response.send_message(":x: No permission")
        if member:
            id = member.id
        else:
            id = interaction.user.id

        filter = db.get("sonny_proxy$locks", (interaction.guild.id, id), ("serverid", "userid"), ("filter",))
        if filter:
            await interaction.response.send_message(filter, ephemeral=True)
        else:
            await interaction.response.send_message("None or failed", ephemeral=True)
            
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        
        profiles = get_profiles(message.author.id)
        if not profiles: return        
        profile = next((p for p in sorted(profiles, key=lambda p: -len(p[3] or "")) if p[3] and message.content.startswith(p[3])), None)
        
        content = message.content
        if profile: content = message.content[len(profile[3]):].strip()
        else:
            profile = next((p for p in profiles if p[1] == message.author.name and p[2] == message.author.avatar.url), None)
        if not profile: return

        lock = db.get("sonny_proxy$locks", (message.guild.id, message.author.id), ("serverid", "userid"), ("filter",))
        for f, m in FILTERS.items():
            if lock and f in lock: content = await m.apply(content, lock[f])
            elif profile[4] and f in profile[4]: content = await m.apply(content, profile[4][f])

        hooks = await message.channel.webhooks()
        hook = next((h for h in hooks if h.user == message.guild.me and h.token), None) or await message.channel.create_webhook(name="proxy")

        await hook.send(
            content=content,
            username=profile[1] if profile else message.author.display_name,
            avatar_url=profile[2] if profile else message.author.display_avatar.url,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            files=[await a.to_file() for a in message.attachments],
        )
        await message.delete()