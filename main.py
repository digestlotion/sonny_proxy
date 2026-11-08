from pathlib import Path
from types import ModuleType
from typing import Literal
import discord
import importlib.util as importlib
from discord import app_commands
from psycopg import sql
from psycopg.types.json import Jsonb
from api import commands, db

DIR = Path(__file__).parent.absolute()


def load_module(path: Path):
    spec = importlib.spec_from_file_location(f"filters.{path.stem}", path)
    mod = importlib.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
    
FILTERS: dict[str, ModuleType] = {p.stem: load_module(p) for p in (DIR / "filters").glob("[!_.]*.py")}

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proxy(bot=bot))

class Proxy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hooks = {}

    @app_commands.command(name="edit", description="Edit your proxy profile")
    async def proxy_edit(
        self,
        interaction: discord.Interaction,
        name: str | None = None,
        avatar: discord.Attachment | None = None,
        prefix: str | None = None,
        filter: Literal[tuple(FILTERS)] | None = None,
        filter_arg: str | None = None):
            user = interaction.user
            name = name or user.name
            # Should i default the avatar to the user's or none?
            db.insert("sonny_proxy$profiles", ("userid", "name"), ("avatar",), (user.id, name, avatar.url if avatar else None or user.avatar.url))
            
            if prefix: db.insert("sonny_proxy$profiles", ("userid", "name"), ("prefix",), (user.id, name, prefix))
            if filter: db.insert("sonny_proxy$profiles", ("userid", "name"), ("filter",), (user.id, name, Jsonb({filter: filter_arg})))
                
            await interaction.response.send_message("Updated Successfully!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        
        query = sql.SQL("SELECT {column} FROM {schema}.{table} WHERE {key} = %s").format(
            schema = db.SCHEMA,
            table = sql.Identifier("sonny_proxy$profiles"),
            column = sql.SQL(", ").join(sql.Identifier(c) for c in ["userid", "name", "avatar", "prefix", "filter"]),
            key = sql.Identifier("userid")
            )
        profiles = db.multiple(query, (message.author.id,))
        if not profiles: return
        
        content = message.content
        
        profile = next((p for p in sorted(profiles, key=lambda p: -len(p[3] or "")) if p[3] and message.content.startswith(p[3])), None)
        if profile:
            content = message.content[len(profile[3]):].strip()
        else:
            profile = next((p for p in profiles if p[1] == message.author.name and p[2] == message.author.avatar.url), None)
        if not profile: return
        
        for f, m in FILTERS.items():
            if f in profile[4]: content = await m.apply(content, profile[4][f])

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