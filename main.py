# main.py is assumed to be the entry point into any extension, it must be named that.
import discord, asyncio
from discord import app_commands
from api import commands, config
from pathlib import Path
from utils import jsonIO
DIR = Path(__file__).parent.absolute()

PROFILES: dict =  jsonIO.load(config.datadir() / "config.json") # user_id -> {"name", "avatar", "prefix"}

# This adds the cog to the bot
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proxy(bot=bot))
    
# The cog itself
class Proxy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hooks = {}

    proxy = app_commands.Group(name="proxy", description=".")

    @proxy.command(name="edit", description="Leave a field empty to keep your current")
    async def proxy_edit(
        self,
        interaction: discord.Interaction,
        name: str | None = None,
        avatar: discord.Attachment | None = None,
        prefix: str | None = None,
    ):
        if not (name or avatar or prefix):
            await interaction.response.send_message("Give a name, an avatar, a prefix, or any mix.", ephemeral=True)
            return
        if avatar and not (avatar.content_type or "").startswith("image/"):
            await interaction.response.send_message("Avatar must be an image.", ephemeral=True)
            return

        user = interaction.user
        p = PROFILES.setdefault(str(user.id), {"name": user.name, "avatar": user.display_avatar.url, "prefix": None})
        if name: p["name"] = name
        if avatar: p["avatar"] = avatar.url
        if prefix: p["prefix"] = prefix
        config.overwrite(PROFILES)
        await interaction.response.send_message("Updated.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return

        p = PROFILES.get(str(message.author.id))
        if not p or not p["prefix"] or not message.content.startswith(p["prefix"]): return
        content = message.content[len(p["prefix"]):]
        if not content: return

        hook = self.hooks.get(message.channel.id)
        if not hook:
            hooks = await message.channel.webhooks()
            hook = next((h for h in hooks if h.user == message.guild.me), None) or await message.channel.create_webhook(name="proxy")
            self.hooks[message.channel.id] = hook
        
        await asyncio.gather(
            message.delete(),
            hook.send(
                content=content,
                username=p["name"],
                avatar_url=p["avatar"],
                allowed_mentions=discord.AllowedMentions.none(),
            ),
        )