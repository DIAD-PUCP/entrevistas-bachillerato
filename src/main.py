from datetime import datetime, timedelta, timezone
from typing import Annotated
import json
import os
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import SQLModel, Session, create_engine
from dotenv import load_dotenv
from starlette import status
from . import models
from . import crud

load_dotenv()

sqlite_file_name = os.getenv('DATABASE_FILE', "database.db")
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SECRET_KEY = os.getenv('SECRET_KEY', "")
ALGORITHM = os.getenv('ALGORITHM', "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 60)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: str | None = None


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id)
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = crud.get_usuario(db, token_data.user_id)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[models.Usuario, Depends(get_current_user)],
):
    if not current_user.activo:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user


def verify_password(plain_password, hashed_password) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str):
    user = crud.get_usuario_by_email(db, email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.post("/token")
async def login_for_access_token(login_data: Annotated[models.LoginData, Form()], db: Session = Depends(get_session)) -> Token:
    user = authenticate_user(db, login_data.usuario, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


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
