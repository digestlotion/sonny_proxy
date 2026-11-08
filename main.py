import discord, importlib.util, json
from discord import app_commands
from api import commands, config
from pathlib import Path
from utils import jsonIO
DIR = Path(__file__).parent.absolute()

PROFILES: dict = jsonIO.load(config.datadir() / "config.json")
STATE_FILE = config.datadir() / "filters.json"
STATE: dict = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"auto": {}, "locks": {}}

def load_filters() -> dict:
    found = {}
    for f in (DIR / "filters").glob("*.py"):
        if f.stem.startswith("_"): continue
        spec = importlib.util.spec_from_file_location(f"proxy_filter_{f.stem}", f)
        found[f.stem] = module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return dict(sorted(found.items(), key=lambda kv: (getattr(kv[1], "ORDER", 0), kv[0])))

FILTERS = load_filters()
CHOICES = [app_commands.Choice(name=n, value=n) for n in FILTERS]

def save():
    config.overwrite(PROFILES)
    STATE_FILE.write_text(json.dumps(STATE))

def bucket(uid: str, profile: str | None):
    if profile is None: return STATE["auto"].setdefault(uid, {})
    p = PROFILES.get(uid, {}).get(profile)
    return None if p is None else p.setdefault("filters", {})

async def check(name: str, arg: str | None) -> str | None:
    need = getattr(FILTERS[name], "NEEDS_ARG", None)
    if need and not arg: return f"`{name}` needs {need}."
    try:
        await FILTERS[name].apply("hello", arg)
    except ValueError:
        return "That didn't work (bad argument, or the service is down)."

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proxy(bot=bot))

class Proxy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hooks = {}

    proxy = app_commands.Group(name="proxy", description=".")
    flt = app_commands.Group(name="filter", description=".")

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

    @flt.command(name="set", description="Filter your messages. Give a profile to limit it to that profile")
    @app_commands.choices(name=CHOICES)
    async def filter_set(self, interaction: discord.Interaction, name: str, arg: str | None = None, profile: str | None = None):
        await interaction.response.defer(ephemeral=True)
        b = bucket(str(interaction.user.id), profile)
        if b is None:
            await interaction.followup.send("No such profile.", ephemeral=True)
        elif err := await check(name, arg):
            await interaction.followup.send(err, ephemeral=True)
        else:
            b[name] = arg
            save()
            await interaction.followup.send(f"`{name}` is on for {'all your messages' if profile is None else f'`{profile}`'}.", ephemeral=True)

    @flt.command(name="clear", description="Turn off one of your filters")
    @app_commands.choices(name=CHOICES)
    async def filter_clear(self, interaction: discord.Interaction, name: str, profile: str | None = None):
        b = bucket(str(interaction.user.id), profile)
        if b is None or name not in b:
            await interaction.response.send_message("That filter isn't on.", ephemeral=True)
            return
        del b[name]
        save()
        await interaction.response.send_message("Off.", ephemeral=True)

    @flt.command(name="list", description="Show your active filters")
    async def filter_list(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        rows = [("all messages", STATE["auto"].get(uid, {}))]
        rows += [(f"profile {k}", q.get("filters", {})) for k, q in PROFILES.get(uid, {}).items()]
        if interaction.guild:
            rows.append(("locked by an admin here", STATE["locks"].get(str(interaction.guild.id), {}).get(uid, {})))
        text = "\n".join(f"{w}: " + ", ".join(f"{n}={a}" if a else n for n, a in f.items()) for w, f in rows if f)
        await interaction.response.send_message(text or "No filters.", ephemeral=True)

    async def admin_ok(self, interaction: discord.Interaction, user: discord.Member) -> bool:
        me, g = interaction.user, interaction.guild
        ok = bool(g and interaction.permissions.manage_guild and not user.bot and user.id != g.owner_id
                  and (me.id == g.owner_id or user.top_role < me.top_role))
        if not ok:
            await interaction.response.send_message("You need Manage Server and a higher role than them.", ephemeral=True)
        return ok

    @flt.command(name="lock", description="Admin: force a filter on someone's messages in this server")
    @app_commands.choices(name=CHOICES)
    async def filter_lock(self, interaction: discord.Interaction, user: discord.Member, name: str, arg: str | None = None):
        if not await self.admin_ok(interaction, user): return
        await interaction.response.defer(ephemeral=True)
        if err := await check(name, arg):
            await interaction.followup.send(err, ephemeral=True)
            return
        STATE["locks"].setdefault(str(interaction.guild.id), {}).setdefault(str(user.id), {})[name] = arg
        save()
        await interaction.followup.send(f"{user.mention} is locked to `{name}`.", ephemeral=True)

    @flt.command(name="unlock", description="Admin: remove a forced filter (leave name empty to remove all)")
    @app_commands.choices(name=CHOICES)
    async def filter_unlock(self, interaction: discord.Interaction, user: discord.Member, name: str | None = None):
        if not await self.admin_ok(interaction, user): return
        locks = STATE["locks"].get(str(interaction.guild.id), {})
        if name: locks.get(str(user.id), {}).pop(name, None)
        else: locks.pop(str(user.id), None)
        save()
        await interaction.response.send_message("Unlocked.", ephemeral=True)

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

        uid = str(message.author.id)
        mine = PROFILES.get(uid, {})
        p = next((q for q in sorted(mine.values(), key=lambda q: -len(q["prefix"] or ""))
                  if q["prefix"] and message.content.startswith(q["prefix"])), None)
        filters = {**STATE["auto"].get(uid, {}), **(p or {}).get("filters", {}),
                   **STATE["locks"].get(str(message.guild.id), {}).get(uid, {})}
        if not p and not filters: return

        content = message.content[len(p["prefix"]):].strip() if p else message.content
        if not content and not message.attachments: return

        perms = message.channel.permissions_for(message.guild.me)
        if not (perms.manage_webhooks and perms.manage_messages): return

        try:
            for n, f in FILTERS.items():
                if n in filters and content: content = await f.apply(content, filters[n])
        except ValueError:
            return

        ref = message.reference.resolved if message.reference else None
        if isinstance(ref, discord.Message):
            content = f"-# ↪ {ref.author.display_name}: {ref.jump_url}\n{content}"

        for _ in range(2):
            channel, hook, thread = await self.get_hook(message)
            try:
                await hook.send(
                    content=content,
                    username=p["name"] if p else message.author.display_name,
                    avatar_url=p["avatar"] if p else message.author.display_avatar.url,
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