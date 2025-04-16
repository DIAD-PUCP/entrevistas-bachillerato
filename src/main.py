from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from sqlmodel import SQLModel, Session, create_engine
from dotenv import load_dotenv
from . import models

import os

load_dotenv()

sqlite_file_name = os.getenv('DATABASE_FILE',"database.db")
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)


@app.get("/")
def index():
    return {"Hello":"World"}
