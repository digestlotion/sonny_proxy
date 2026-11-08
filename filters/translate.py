import asyncio
import aiohttp

NEEDS_ARG = "a language code, like es, ja or fr"
ORDER = 0

# shortcut: unofficial free Google endpoint, can rate-limit or break; swap in DeepL or Cloud Translation if it gets flaky
async def apply(text: str, lang: str) -> str:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get("https://translate.googleapis.com/translate_a/single",
                             params={"client": "gtx", "sl": "auto", "tl": lang, "dt": "t", "q": text}) as r:
                r.raise_for_status()
                return "".join(part[0] for part in (await r.json(content_type=None))[0])
    except (aiohttp.ClientError, asyncio.TimeoutError, IndexError, TypeError) as e:
        raise ValueError(f"translate failed: {e}")