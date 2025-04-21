from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
import json
import os
from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import HTMLResponse, RedirectResponse
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


async def get_current_user(
    token: Annotated[Optional[str], Cookie()] = None,
    db: Session = Depends(get_session)
) -> models.Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials"
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
) -> models.Usuario:
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


def show_message(text: str, type: str) -> dict[str, str]:
    return {'HX-Trigger': json.dumps({
        'showMessage': {
            'text': text,
            'type': type
        }
    })}


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class AuthException(Exception):
    pass


@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException) -> RedirectResponse:
    headers = show_message(
        'Es necesario iniciar sesión \n' + str(exc),
        'danger'
    )
    return RedirectResponse(
        f'/login?target={request.url.path}',
        status_code=301,
        headers=headers
    )


@app.get('/login', response_class=HTMLResponse)
async def login(request: Request, target: Optional[str] = None):
    return templates.TemplateResponse('login.tpl.html', {"request": request, "target": target})


@app.post("/login", response_class=HTMLResponse)
async def login_for_access_token(
    request: Request,
    login_data: Annotated[models.LoginData, Form()],
    target: Annotated[str, Query()] = '/',
    db: Session = Depends(get_session)
) -> Token:
    user = authenticate_user(db, login_data.usuario, login_data.password)
    if not user:
        return templates.TemplateResponse(
            'login.tpl.html',
            {"request": request, "target": target},
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers=show_message('Usuario o contraseña incorrectos', 'danger')
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    response = HTMLResponse(
        headers={'HX-Redirect': target}
    )
    response.set_cookie(key="token", value=access_token)
    return response


@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse('/login', status_code=status.HTTP_302_FOUND)
    response.set_cookie(key='token', value='', expires=-1)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("base.tpl.html", {"request": request})


@app.get("/usuario/{id}", response_class=HTMLResponse)
async def get_usuario(request: Request, id: str, db: Session = Depends(get_session)):
    if id == 'nuevo':
        usuario = None
    else:
        usuario = db.get(models.Usuario, id)
    return templates.TemplateResponse("usuario.tpl.html", {"request": request, "usuario": usuario})


@app.post("/usuario/nuevo", response_class=HTMLResponse)
async def nuevo_usuario(
    request: Request,
    usuario: Annotated[models.UsuarioCreate, Form()],
    db: Session = Depends(get_session)
):
    user = crud.create_usuario(db, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": user},
        headers=show_message(f'Se creo el usuario {user.id}', 'success') |
        {'HX-Push-Url': f'/usuario/{user.id}'}
    )


@app.patch("/usuario/{id}", response_class=HTMLResponse)
async def actualizar_usuario(
    request: Request,
    id: str,
    usuario: Annotated[models.UsuarioUpdate, Form()],
    db: Session = Depends(get_session)
):
    crud.update_usuario(db, id, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": usuario},
        headers=show_message('Se actualizó el usuario', 'success')
    )


@app.delete("/usuario/{id}", response_class=RedirectResponse)
async def eliminar_usuario(
    request: Request,
    id: str,
    db: Session = Depends(get_session)
):
    crud.delete_usuario(db, id)
    response = HTMLResponse(
        headers={'HX-Redirect': '/usuarios'},
        status_code=200
    )
    return response
