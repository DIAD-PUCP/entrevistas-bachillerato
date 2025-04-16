from typing import Annotated, Optional
from sqlmodel import Field, Relationship, SQLModel
from pydantic import EmailStr


class UsuarioBase(SQLModel):
    id: Annotated[str, Field(primary_key=True)]
    nombres: str
    apellido_paterno: str
    apellido_materno: str
    email: EmailStr
    estado: str = 'Activo'
    perfil: str = 'Calificador'


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioUpdate(UsuarioBase):
    id: Optional[str] = None
    nombres: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    email: Optional[EmailStr] = None
    estado: Optional[str] = None
    perfil: Optional[str] = None
    password: Optional[str] = None


class Usuario(UsuarioBase, table=True):
    hashed_password: str
    salt: str


class Calificador(Usuario):
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='ficha_calificacion')


class Evaluado(SQLModel, table=True):
    id: str = Field(primary_key=True)
    documento_identidad: str
    nombres: str
    apellido_paterno: str
    apellido_materno: str
    carrera: str
    edad: int
    colegio: str
    ensayo: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='ficha_calificacion')


class FichaCalificacionBase(SQLModel):
    id: Annotated[str, Field(primary_key=True)]
    calificador_id: Annotated[str, Field(foreign_key="usuario.id")]
    evaluado_id: Annotated[str, Field(foreign_key="evaluado.id")]
    criterio1: Optional[int] = None
    criterio2: Optional[int] = None
    criterio3: Optional[int] = None
    criterio4: Optional[int] = None
    comentario: Optional[str] = None


class FichaCalificacion(FichaCalificacionBase, table=True):
    calificador: Calificador = Relationship(back_populates='usuario')
    evaluado: Evaluado = Relationship(back_populates='evaluado')
