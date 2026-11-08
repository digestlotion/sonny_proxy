from uwuipy import Uwuipy
_uwu = Uwuipy()

async def apply(text: str, _=None) -> str:
    return _uwu.uwuify(text)