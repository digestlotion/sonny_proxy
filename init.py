import asyncio, sys
from api import config
from utils import jsonIO
from run import run

jsonIO.dump(config.datadir()/"config.json", {})