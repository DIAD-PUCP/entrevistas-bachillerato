from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
import json
import os
from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Query, Request, Security
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
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 240)


class AuthException(HTTPException):
    pass


class ForbiddenException(HTTPException):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: str


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
    credentials_exception = AuthException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales"
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id)
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc
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
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException) -> HTMLResponse:
    msg = show_message(
        exc.detail,
        'danger'
    )
    res = templates.TemplateResponse(
        'login.tpl.html',
        {"request": request, "target": request.url.path},
        status_code=200,
        headers={'HX-Push-Url': f'/login?target={request.url.path}'}
    )
    res.headers.update(msg)
    return res


@app.exception_handler(ForbiddenException)
async def forbidden_exception_handler(request: Request, exc: ForbiddenException) -> HTMLResponse:
    res = templates.TemplateResponse(
        'forbidden.tpl.html',
        {"request": request},
        status_code=status.HTTP_403_FORBIDDEN
    )
    return res


@app.get('/login', response_class=HTMLResponse)
async def login(request: Request, target: Optional[str] = None):
    return templates.TemplateResponse('login.tpl.html', {"request": request, "target": target})


@app.post("/login", response_class=HTMLResponse)
async def login_for_access_token(
    request: Request,
    login_data: Annotated[models.LoginData, Form()],
    target: Annotated[str, Query()] = '/',
    db: Session = Depends(get_session)
):
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
async def index(request: Request, user: models.Usuario = Security(get_current_active_user)):
    return templates.TemplateResponse("index.tpl.html", {"request": request, "user": user})


@app.get("/usuarios", response_class=HTMLResponse)
async def get_usuarios(
    request: Request,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    usuarios = crud.get_all_usuarios(db)
    return templates.TemplateResponse(
        "listado-usuarios.tpl.html",
        {"request": request, "usuarios": usuarios, "user": user}
    )


@app.get("/usuario/{id}", response_class=HTMLResponse)
async def get_usuario(
    request: Request,
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    if id == 'nuevo':
        usuario = None
    else:
        usuario = db.get(models.Usuario, id)
        if not usuario:
            raise HTTPException(
                status_code=404, detail="No se encontró usuario")
    return templates.TemplateResponse("usuario.tpl.html", {"request": request, "usuario": usuario, "user": user})


@app.post("/usuario/nuevo", response_class=HTMLResponse)
async def nuevo_usuario(
    request: Request,
    usuario: Annotated[models.UsuarioCreate, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    u = crud.create_usuario(db, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": u, "user": user},
        headers=show_message(f'Se creo el usuario {u.id}', 'success') |
        {'HX-Push-Url': f'/usuario/{u.id}'}
    )


@app.patch("/usuario/{id}", response_class=HTMLResponse)
async def actualizar_usuario(
    request: Request,
    id: str,
    usuario: Annotated[models.UsuarioUpdate, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    u = crud.update_usuario(db, id, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": u, "user": user},
        headers=show_message('Se actualizó el usuario', 'success')
    )


@app.delete("/usuario/{id}", response_class=HTMLResponse)
async def eliminar_usuario(
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    crud.delete_usuario(db, id)
    response = HTMLResponse(
        headers={'HX-Redirect': '/usuarios'},
        status_code=200
    )
    return response


@app.get("/usuario/{id}/por-calificar", response_class=HTMLResponse)
async def listado_por_calificar(
    request: Request,
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador' and user.id != id:
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    usuario = crud.get_usuario(db, id)
    fichas_pendientes = [
        ficha for ficha in usuario.fichas if ficha.fecha_calificacion is None]
    return templates.TemplateResponse(
        "listado-a-calificar.tpl.html",
        context={"request": request, "fichas": fichas_pendientes, "user": user}
    )


@app.get("/por-calificar", response_class=HTMLResponse)
async def listado_propios_por_calificar(
    request: Request,
    user: models.Usuario = Security(get_current_active_user)
):
    fichas_pendientes = [
        ficha for ficha in user.fichas if ficha.fecha_calificacion is None]
    return templates.TemplateResponse(
        "listado-a-calificar.tpl.html",
        context={"request": request, "fichas": fichas_pendientes, "user": user}
    )


@app.get("/evaluados", response_class=HTMLResponse)
async def get_evaluados(
    request: Request,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    evaluados = crud.get_evaluados(db)
    return templates.TemplateResponse(
        "listado-evaluados.tpl.html",
        {"request": request, "evaluados": evaluados, "user": user}
    )


@app.get("/evaluado/{id}", response_class=HTMLResponse)
async def get_evaluado(
    request: Request,
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    if id == 'nuevo':
        evaluado = None
    else:
        evaluado = db.get(models.Evaluado, id)
        if not evaluado:
            raise HTTPException(
                status_code=404, detail="No se encontró evaluado")
    return templates.TemplateResponse(
        "evaluado.tpl.html", {"request": request,
                              "evaluado": evaluado,
                              "user": user}
    )


@app.post("/evaluado/nuevo", response_class=HTMLResponse)
async def nuevo_evaluado(
    request: Request,
    evaluado: Annotated[models.Evaluado, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    evalua = crud.create_evaluado(db, evaluado)
    return templates.TemplateResponse(
        "evaluado.tpl.html",
        context={"request": request, "evaluado": evalua, "user": user},
        headers=show_message(f'Se creo el evaluado {evalua.id}', 'success') |
        {'HX-Push-Url': f'/evaluado/{evalua.id}'}
    )


@app.patch("/evaluado/{id}", response_class=HTMLResponse)
async def actualizar_evaluado(
    request: Request,
    id: str,
    evaluado: Annotated[models.Evaluado, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    evalua = crud.update_evaluado(db, id, evaluado)
    return templates.TemplateResponse(
        "evaluado.tpl.html",
        context={"request": request, "evaluado": evalua, "user": user},
        headers=show_message('Se actualizó el evaluado', 'success')
    )


@app.delete("/evaluado/{id}", response_class=HTMLResponse)
async def eliminar_evaluado(
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    crud.delete_evaluado(db, id)
    response = HTMLResponse(
        headers={'HX-Redirect': '/evaluados'},
        status_code=200
    )
    return response


@app.get("/fichas", response_class=HTMLResponse)
async def get_fichas(
    request: Request,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    fichas = crud.get_all_fichas(db)
    return templates.TemplateResponse(
        "listado-fichas.tpl.html",
        {"request": request, "fichas": fichas, "user": user}
    )


@app.get("/ficha/{id}", response_class=HTMLResponse)
async def get_ficha(
    request: Request,
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    if id == 'nueva':
        ficha = None
    else:
        ficha = db.get(models.FichaCalificacion, id)
        if not ficha:
            raise HTTPException(status_code=404, detail="No se encontró ficha")
    usuarios = crud.get_usuarios_activos(db)
    evaluados = crud.get_evaluados(db)
    return templates.TemplateResponse("ficha.tpl.html", {
        "request": request,
        "ficha": ficha,
        "usuarios": usuarios,
        "evaluados": evaluados,
        "user": user,
    })


@app.post("/ficha/nueva", response_class=HTMLResponse)
async def nueva_ficha(
    request: Request,
    ficha: Annotated[models.FichaCalificacion, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    f = crud.create_ficha(db, ficha)
    usuarios = crud.get_usuarios_activos(db)
    evaluados = crud.get_evaluados(db)
    resp = templates.TemplateResponse(
        "ficha.tpl.html",
        context={
            "request": request,
            "ficha": f,
            "usuarios": usuarios,
            "evaluados": evaluados,
            "user": user
        },
        headers={'HX-Push-Url': f'/ficha/{f.id}'}
    )
    resp.headers.update(show_message(f'Se creo la ficha {f.id}', 'success'))
    return resp


@app.patch("/ficha/{id}", response_class=HTMLResponse)
async def actualizar_ficha(
    request: Request,
    id: str,
    ficha: Annotated[models.FichaCalificacion, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    ficha = models.FichaCalificacion.model_validate(ficha)
    f = crud.update_ficha(db, id, ficha)
    usuarios = crud.get_usuarios_activos(db)
    evaluados = crud.get_evaluados(db)
    resp = templates.TemplateResponse(
        "ficha.tpl.html",
        context={
            "request": request,
            "ficha": f,
            "usuarios": usuarios,
            "evaluados": evaluados,
            "user": user
        }
    )
    resp.headers.update(show_message('Se actualizó la ficha', 'success'))
    return resp


@app.delete("/ficha/{id}", response_class=HTMLResponse)
async def eliminar_ficha(
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise ForbiddenException(status.HTTP_403_FORBIDDEN)
    crud.delete_ficha(db, id)
    response = HTMLResponse(
        headers={'HX-Redirect': '/fichas'},
        status_code=200
    )
    return response


@app.get("/ficha/{id}/calificar", response_class=HTMLResponse)
async def ver_calificar_ficha(
    request: Request,
    id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    ficha = crud.get_ficha(db, id)
    desc_crit = crud.get_decripciones_criterios(db)
    return templates.TemplateResponse(
        'calificar.tpl.html',
        context={'request': request, "ficha": ficha,
                 "user": user, "crit": desc_crit}
    )


@app.patch("/ficha/{id}/calificar", response_class=HTMLResponse)
async def calificar_ficha(
    request: Request,
    id: str,
    ficha: Annotated[models.FichaCalificacionBase, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    f = crud.calificar_ficha(db, id, ficha)
    resp = await listado_propios_por_calificar(request, user)
    resp.headers.update(show_message("Se guardó la calificación", "success"))
    resp.headers.update({'HX-Push-Url': '/por-calificar'})
    return resp
