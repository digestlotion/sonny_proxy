import discord
from discord import app_commands
from api import commands, config
from pathlib import Path
from utils import jsonIO
DIR = Path(__file__).parent.absolute()

PROFILES: dict = jsonIO.load(config.datadir() / "config.json")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proxy(bot=bot))

class Proxy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hooks = {}

    proxy = app_commands.Group(name="proxy", description=".")

    @proxy.command(name="edit", description="Create or edit a profile. Leave a field empty to keep your current")
    async def proxy_edit(
        self,
        interaction: discord.Interaction,
        profile: str = "default",
        name: str | None = None,
        avatar: discord.Attachment | None = None,
        prefix: str | None = None,
    ):
        if not (name or avatar or prefix):
            await interaction.response.send_message("Give a name, an avatar, a prefix, or any mix.", ephemeral=True)
            return
        if name and (len(name) > 80 or any(w in name.lower() for w in ("discord", "clyde"))):
            await interaction.response.send_message("Name: max 80 chars, can't contain 'discord' or 'clyde'.", ephemeral=True)
            return
        if avatar and not (avatar.content_type or "").startswith("image/"):
            await interaction.response.send_message("Avatar must be an image.", ephemeral=True)
            return

        user = interaction.user
        mine = PROFILES.setdefault(str(user.id), {})
        if prefix and any(q["prefix"] == prefix for k, q in mine.items() if k != profile):
            await interaction.response.send_message("Another of your profiles already uses that prefix.", ephemeral=True)
            return
        p = mine.setdefault(profile, {"name": user.name if profile == "default" else profile,
                                      "avatar": user.display_avatar.url, "prefix": None})
        if name: p["name"] = name
        if avatar: p["avatar"] = avatar.url
        if prefix: p["prefix"] = prefix
        config.overwrite(PROFILES)
        await interaction.response.send_message(f"Updated `{profile}`.", ephemeral=True)

    @proxy.command(name="list", description="Show your profiles")
    async def proxy_list(self, interaction: discord.Interaction):
        mine = PROFILES.get(str(interaction.user.id), {})
        text = "\n".join(f"`{k}`: {q['name']} (prefix `{q['prefix']}`)" for k, q in mine.items())
        await interaction.response.send_message(text or "No profiles yet.", ephemeral=True)

    @proxy.command(name="delete", description="Delete one of your profiles")
    async def proxy_delete(self, interaction: discord.Interaction, profile: str):
        if PROFILES.get(str(interaction.user.id), {}).pop(profile, None) is None:
            await interaction.response.send_message("No such profile.", ephemeral=True)
            return
        config.overwrite(PROFILES)
        await interaction.response.send_message("Deleted.", ephemeral=True)

    async def get_hook(self, message: discord.Message):
        channel, thread = message.channel, None
        if isinstance(channel, discord.Thread):
            thread, channel = channel, channel.parent
        hook = self.hooks.get(channel.id)
        if not hook:
            hooks = await channel.webhooks()
            hook = next((h for h in hooks if h.user == message.guild.me and h.token), None) or await channel.create_webhook(name="proxy")
            self.hooks[channel.id] = hook
        return channel, hook, thread

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return

        mine = PROFILES.get(str(message.author.id), {})
        p = next((q for q in sorted(mine.values(), key=lambda q: -len(q["prefix"] or ""))
                  if q["prefix"] and message.content.startswith(q["prefix"])), None)
        if not p: return
        content = message.content[len(p["prefix"]):].strip()
        if not content and not message.attachments: return

        perms = message.channel.permissions_for(message.guild.me)
        if not (perms.manage_webhooks and perms.manage_messages): return

        ref = message.reference.resolved if message.reference else None
        if isinstance(ref, discord.Message):
            content = f"-# ↪ {ref.author.display_name}: {ref.jump_url}\n{content}"

        for _ in range(2):
            channel, hook, thread = await self.get_hook(message)
            try:
                await hook.send(
                    content=content,
                    username=p["name"],
                    avatar_url=p["avatar"],
                    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
                    files=[await a.to_file() for a in message.attachments],
                    **({"thread": thread} if thread else {}),
                )
                break
            except discord.NotFound:
                self.hooks.pop(channel.id, None)
            except discord.HTTPException:
                return
        else:
            return

        try:
            await message.delete()
        except discord.HTTPException:
            pass