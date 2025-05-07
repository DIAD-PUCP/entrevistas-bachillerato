from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated, Optional
import json
import os
import os.path
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Security,
    UploadFile
)
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import jwt
import pandas as pd
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
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '240'))


class AuthException(HTTPException):
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
async def lifespan(_: FastAPI):
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
        raise AuthException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
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


def show_message(text: str, msg_type: str) -> dict[str, str]:
    return {'HX-Trigger-After-Swap': json.dumps({
        'showMessage': {
            'text': text,
            'type': msg_type
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
        status_code=exc.status_code,
        headers={'HX-Push-Url': f'/login?target={request.url.path}'}
    )
    res.headers.update(msg)
    return res


@app.exception_handler(HTTPException)
async def forbidden_exception_handler(request: Request, exc: HTTPException) -> HTMLResponse:
    res = templates.TemplateResponse(
        'error.tpl.html',
        {"request": request, 'msg': exc.detail},
        status_code=exc.status_code
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
    user = authenticate_user(db, login_data.email, login_data.password)
    if not user:
        return templates.TemplateResponse(
            'login.tpl.html',
            {"request": request, "target": target},
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers=show_message('Usuario o contraseña incorrectos', 'danger')
        )
    access_token_expires = timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES  # type: ignore
    )
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    response = HTMLResponse(
        headers={'HX-Redirect': target}
    )
    response.set_cookie(key="token", value=access_token)
    return response


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    response = templates.TemplateResponse(
        'login.tpl.html',
        {"request": request},
        status_code=status.HTTP_302_FOUND,
        headers=show_message('Se cerró sesión', 'success')
    )
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
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    usuarios = crud.get_all_usuarios(db)
    return templates.TemplateResponse(
        "listado-usuarios.tpl.html",
        {"request": request, "usuarios": usuarios, "user": user}
    )


@app.get("/usuario/{user_id}", response_class=HTMLResponse)
async def get_usuario(
    request: Request,
    user_id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if user_id == 'nuevo':
        usuario = None
    else:
        usuario = db.get(models.Usuario, user_id)
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró usuario")
    return templates.TemplateResponse("usuario.tpl.html", {"request": request, "usuario": usuario, "user": user})


@app.post("/usuario/nuevo", response_class=HTMLResponse)
async def nuevo_usuario(
    request: Request,
    usuario: Annotated[models.UsuarioCreate, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if usuario.password != usuario.password_confirm:
        return templates.TemplateResponse(
            "usuario.tpl.html",
            context={"request": request, "user": user},
            headers=show_message('Los password no coinciden.', 'danger')
        )
    u = crud.create_usuario(db, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": u, "user": user},
        headers=show_message(f'Se creo el usuario {u.id}', 'success') |
        {'HX-Push-Url': f'/usuario/{u.id}'}
    )


@app.patch("/usuario/{user_id}", response_class=HTMLResponse)
async def actualizar_usuario(
    request: Request,
    user_id: str,
    usuario: Annotated[models.UsuarioUpdate, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if usuario.password != usuario.password_confirm:
        return templates.TemplateResponse(
            "usuario.tpl.html",
            context={"request": request, "usuario": usuario, "user": user},
            headers=show_message('Los password no coinciden.', 'danger')
        )
    u = crud.update_usuario(db, user_id, usuario)
    return templates.TemplateResponse(
        "usuario.tpl.html",
        context={"request": request, "usuario": u, "user": user},
        headers=show_message('Se actualizó el usuario', 'success')
    )


@app.delete("/usuario/{user_id}", response_class=HTMLResponse)
async def eliminar_usuario(
    user_id: str,
    redirect: Annotated[bool,Query()] = False,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    crud.delete_usuario(db, user_id)
    response = HTMLResponse(
        status_code=status.HTTP_200_OK
    )
    response.headers.update(show_message('Se eliminó el usuario', 'success'))
    if redirect:
        response.headers['HX-Redirect'] = '/usuarios'
    return response


@app.get("/usuario/{user_id}/por-calificar", response_class=HTMLResponse)
async def listado_por_calificar(
    request: Request,
    user_id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador' and user.id != user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    usuario = crud.get_usuario(db, user_id)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró usuario"
        )
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
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    evaluados = crud.get_evaluados(db)
    return templates.TemplateResponse(
        "listado-evaluados.tpl.html",
        {"request": request, "evaluados": evaluados, "user": user}
    )


@app.get("/evaluado/{evaluado_id}", response_class=HTMLResponse)
async def get_evaluado(
    request: Request,
    evaluado_id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if evaluado_id == 'nuevo':
        evaluado = None
    else:
        evaluado = db.get(models.Evaluado, evaluado_id)
        if not evaluado:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró evaluado"
            )
    return templates.TemplateResponse(
        "evaluado.tpl.html", {"request": request,
                              "evaluado": evaluado,
                              "user": user}
    )


async def save_file(file: UploadFile) -> str:
    path = ""
    if file.filename and file.filename.endswith('.pdf'):
        filename, filext = os.path.splitext(os.path.basename(file.filename))
        while os.path.exists(f'static/{filename}{filext}'):
            filename = filename + '_1'
        path = f'static/{filename}{filext}'
        with open(path, 'wb') as f:
            f.write(await file.read())
    return "/" + path


@app.post("/evaluado/nuevo", response_class=HTMLResponse)
async def nuevo_evaluado(
    request: Request,
    evaluado: Annotated[models.EvaluadoForm, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if evaluado.archivo:
        ruta = await save_file(evaluado.archivo)
        if ruta:
            evaluado.ensayo = ruta
    evalua = crud.create_evaluado(db, evaluado)
    return templates.TemplateResponse(
        "evaluado.tpl.html",
        context={"request": request, "evaluado": evalua, "user": user},
        headers=show_message(f'Se creo el evaluado {evalua.id}', 'success') |
        {'HX-Push-Url': f'/evaluado/{evalua.id}'}
    )


@app.patch("/evaluado/{evaluado_id}", response_class=HTMLResponse)
async def actualizar_evaluado(
    request: Request,
    evaluado_id: str,
    evaluado: Annotated[models.EvaluadoForm, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if evaluado.archivo:
        ruta = await save_file(evaluado.archivo)
        if ruta:
            evaluado.ensayo = ruta
    evalua = crud.update_evaluado(db, evaluado_id, evaluado)
    return templates.TemplateResponse(
        "evaluado.tpl.html",
        context={"request": request, "evaluado": evalua, "user": user},
        headers=show_message('Se actualizó el evaluado', 'success')
    )


@app.delete("/evaluado/{evaluado_id}", response_class=HTMLResponse)
async def eliminar_evaluado(
    evaluado_id: str,
    redirect: Annotated[bool,Query()] = False,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    crud.delete_evaluado(db, evaluado_id)
    response = HTMLResponse(
        status_code=status.HTTP_200_OK
    )
    response.headers.update(show_message('Se eliminó el evaluado', 'success'))
    if redirect:
        response.headers['HX-Redirect'] = '/evaluados'
    return response


@app.get("/fichas", response_class=HTMLResponse)
async def get_fichas(
    request: Request,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    fichas = crud.get_all_fichas(db)
    return templates.TemplateResponse(
        "listado-fichas.tpl.html",
        {"request": request, "fichas": fichas, "user": user}
    )


@app.get("/ficha/{ficha_id}", response_class=HTMLResponse)
async def get_ficha(
    request: Request,
    ficha_id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    if ficha_id == 'nueva':
        ficha = None
    else:
        ficha = db.get(models.FichaCalificacion, ficha_id)
        if not ficha:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró ficha"
            )
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
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
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


@app.patch("/ficha/{ficha_id}", response_class=HTMLResponse)
async def actualizar_ficha(
    request: Request,
    ficha_id: str,
    ficha: Annotated[models.FichaCalificacion, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    ficha = models.FichaCalificacion.model_validate(ficha)
    f = crud.update_ficha(db, ficha_id, ficha)
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


@app.delete("/ficha/{ficha_id}", response_class=HTMLResponse)
async def eliminar_ficha(
    ficha_id: str,
    redirect: Annotated[bool,Query()] = False,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    crud.delete_ficha(db, ficha_id)
    response = HTMLResponse(
        status_code=status.HTTP_200_OK
    )
    response.headers.update(show_message('Se eliminó la ficha', 'success'))
    if redirect:
        response.headers['HX-Redirect'] = '/fichas'
    return response


@app.get("/ficha/{ficha_id}/calificar", response_class=HTMLResponse)
async def ver_calificar_ficha(
    request: Request,
    ficha_id: str,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    ficha = crud.get_ficha(db, ficha_id)
    if not ficha:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ficha"
        )
    if user.perfil != 'Administrador' and user.id != ficha.calificador_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    desc_crit = crud.get_decripciones_criterios(db)
    return templates.TemplateResponse(
        'calificar.tpl.html',
        context={'request': request, "ficha": ficha,
                 "user": user, "crit": desc_crit}
    )


@app.patch("/ficha/{ficha_id}/calificar", response_class=HTMLResponse)
async def calificar_ficha(
    request: Request,
    ficha_id: str,
    ficha: Annotated[models.FichaCalificacionBase, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    f = crud.calificar_ficha(db, ficha_id, ficha)
    if user.perfil != 'Administrador' and user.id != f.calificador_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    resp = await listado_propios_por_calificar(request, user)
    resp.headers.update(show_message("Se guardó la calificación", "success"))
    resp.headers.update({'HX-Push-Url': '/por-calificar'})
    return resp


@app.get("/criterios/", response_class=HTMLResponse)
async def ver_criterios(
    request: Request,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    criterios = crud.get_decripciones_criterios(db)
    return templates.TemplateResponse(
        "criterios.tpl.html", {
            "request": request,
            "criterios": criterios,
            "user": user
        }
    )


@app.patch("/criterios/", response_class=HTMLResponse)
async def actualizar_criterios(
    request: Request,
    criterios: Annotated[models.DescCriterios, Form()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    criterios = crud.set_decripciones_criterios(db, criterios)
    resp = templates.TemplateResponse(
        "criterios.tpl.html", {
            "request": request,
            "criterios": criterios,
            "user": user
        }
    )
    resp.headers.update(
        show_message("Se actualizaron los criterios", "success")
    )
    return resp


@app.get("/reporte-estado", response_class=HTMLResponse)
async def reporte_estado(
    request: Request,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    calificadores = crud.get_reporte_progreso(db)
    return templates.TemplateResponse(
        "reporte-estado.tpl.html", {
            "request": request,
            "calificadores": calificadores,
            "user": user
        }
    )


@app.get("/reporte-resultados", response_class=HTMLResponse)
async def get_resultados(
    request: Request,
    download: Annotated[bool, Query()] = False,
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    fichas = crud.get_reporte_resultados(db, download)
    if download:
        df = pd.read_sql(fichas, db.bind)  # type: ignore
        buffer = BytesIO()
        with pd.ExcelWriter(buffer) as writer:
            df.to_excel(writer, index=False)
        return StreamingResponse(
            BytesIO(buffer.getvalue()),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={"Content-Disposition": "attachment; filename=resultados.xlsx"}
        )
    else:
        return templates.TemplateResponse(
            "reporte-resultados.tpl.html", {
                "request": request,
                "fichas": fichas,
                "user": user
            }
        )


@app.get('/evaluados/importar', response_class=HTMLResponse)
async def cargar_evaluados(
    request: Request,
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    return templates.TemplateResponse(
        "cargar-evaluados.tpl.html", {
            "request": request,
            "user": user
        }
    )


@app.post('/evaluados/importar', response_class=HTMLResponse)
async def importar_evaluados(
    request: Request,
    archivo: Annotated[UploadFile, File()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    df = pd.read_csv(archivo.file, dtype={'documento_identidad': str})
    for _, e in df.iterrows():
        eva = models.EvaluadoForm.model_validate_json(e.to_json())
        crud.create_evaluado(db, eva)
    evaluados = crud.get_evaluados(db)
    return templates.TemplateResponse(
        "listado-evaluados.tpl.html",
        {"request": request, "evaluados": evaluados, "user": user},
        headers={'HX-Push-Url': '/evaluados'}
    )


@app.get('/usuarios/importar', response_class=HTMLResponse)
async def cargar_usuarios(
    request: Request,
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    return templates.TemplateResponse(
        "cargar-usuarios.tpl.html", {
            "request": request,
            "user": user
        }
    )


@app.post('/usuarios/importar', response_class=HTMLResponse)
async def importar_usuarios(
    request: Request,
    archivo: Annotated[UploadFile, File()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    df = pd.read_csv(archivo.file, dtype={'id': str})
    for _, u in df.iterrows():
        data = u.to_dict()
        data['password_confirm'] = data['password']
        usuario = models.UsuarioCreate.model_validate(data)
        crud.create_usuario(db, usuario)
    usuarios = crud.get_all_usuarios(db)
    return templates.TemplateResponse(
        "listado-usuarios.tpl.html",
        {"request": request, "usuarios": usuarios, "user": user},
        headers={'HX-Push-Url': '/usuarios'}
    )


@app.get('/fichas/importar', response_class=HTMLResponse)
async def cargar_fichas(
    request: Request,
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    return templates.TemplateResponse(
        "cargar-fichas.tpl.html", {
            "request": request,
            "user": user
        }
    )


@app.post('/fichas/importar', response_class=HTMLResponse)
async def importar_fichas(
    request: Request,
    archivo: Annotated[UploadFile, File()],
    db: Session = Depends(get_session),
    user: models.Usuario = Security(get_current_active_user)
):
    if user.perfil != 'Administrador':
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="No cuenta con los suficientes permisos para esta acción"
        )
    df = pd.read_csv(archivo.file, dtype={
                     'id': str, 'calificador_id': str, 'evaluado_id': str})
    for _, f in df.iterrows():
        ficha = models.FichaCalificacion.model_validate(f.to_dict())
        crud.create_ficha(db, ficha)
    fichas = crud.get_all_fichas(db)
    return templates.TemplateResponse(
        "listado-fichas.tpl.html",
        {"request": request, "fichas": fichas, "user": user},
        headers={'HX-Push-Url': '/fichas'}
    )
