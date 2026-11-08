import asyncio, sys
from api import config
from utils import jsonIO
from run import run

jsonIO.dump(config.datadir()/"config.json", {})

try:
    from uwuipy import Uwuipy
except ModuleNotFoundError:
    print("Module 'uwuipy' not found. Would you like to install?")
    if input("Enter 'y' to install: ").lower() == 'y':
        print(asyncio.run(run([sys.executable, "-m", "pip", "install", "-U", "uwuipy"])))
    else:
        print("Installation skipped.")
        quit()