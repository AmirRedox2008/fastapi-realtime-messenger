from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,declarative_base
from sqlalchemy.engine import URL


connection = URL.create(
    drivername='postgresql',
    host = 'your host name ',
    port = 'your port',
    username = 'postgres',
    password = 'Your_Password',
    database = 'your database name'

)


engine = create_engine(connection)

session_local = sessionmaker(autocommit=False, bind=engine)
Base = declarative_base()
