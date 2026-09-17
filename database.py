from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,declarative_base
from sqlalchemy.engine import URL


connection = URL.create(
    drivername='postgresql',
    host = 'localhost',
    port = port,
    username = 'mydb',
    password = 'password',
    database = 'mydb'


)


engine = create_engine(connection)

session_local = sessionmaker(autocommit=False, bind=engine)
Base = declarative_base()
