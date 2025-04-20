from typing import Annotated
import json
from fastapi import Depends, FastAPI, Form, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Session, create_engine
from dotenv import load_dotenv
from . import models
from . import crud

import os

load_dotenv()

sqlite_file_name = os.getenv('DATABASE_FILE', "database.db")
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
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("base.tpl.html", {"request": request})


@app.get("/usuario/{id}", response_class=HTMLResponse)
def get_usuario(request: Request, id: str, db: Session = Depends(get_session)):
    if id == 'nuevo':
        usuario = None
    else:
        usuario = db.get(models.Usuario, id)
    return templates.TemplateResponse("usuario.tpl.html", {"request": request, "usuario": usuario})


@app.post("/usuario/nuevo", response_class=HTMLResponse)
def nuevo_usuario(request: Request, usuario: Annotated[models.UsuarioCreate, Form()], db: Session = Depends(get_session)):
    user = crud.create_usuario(db, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": user},
        headers={
            'HX-Trigger': json.dumps({
                'showMessage': {
                    'text': f'Se creo el usuario {user.id}',
                    'type': 'success'
                }
            }),
            'HX-Push-Url': f'/usuario/{user.id}'
        }
    )


@app.patch("/usuario/{id}", response_class=HTMLResponse)
def actualizar_usuario(request: Request, id: str, usuario: Annotated[models.UsuarioUpdate, Form()], db: Session = Depends(get_session)):
    crud.update_usuario(db, id, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": usuario},
        headers={
            'HX-Trigger': json.dumps({
                'showMessage': {
                    'text': 'Se actualizó el usuario',
                    'type': 'success'
                }
            })
        }
    )
