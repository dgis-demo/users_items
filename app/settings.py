import os

import sqlalchemy
from databases import Database


database = Database(os.environ['DB_URI'], max_size=20)
metadata = sqlalchemy.MetaData()

TOKEN_TTL = 86400
HOST = os.environ['HOST']
PORT = os.environ['PORT']
