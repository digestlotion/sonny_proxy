try:
    from uwuipy import Uwuipy
except ImportError:
    from uwuipy import uwuipy as Uwuipy


ORDER = 1
_uwu = Uwuipy()

async def apply(text: str, _=None) -> str:
    return _uwu.uwuify(text)