from api import config
from utils import jsonIO

jsonIO.dump(config.datadir()/"config.json", {})
