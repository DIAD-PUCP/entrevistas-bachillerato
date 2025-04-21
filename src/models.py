from typing import Annotated, Optional
from sqlmodel import Field, Relationship, SQLModel
from pydantic import BaseModel, EmailStr


class LoginData(BaseModel):
    usuario: str
    password: str


class UsuarioBase(SQLModel):
    id: Annotated[str, Field(primary_key=True)]
    nombres: str
    apellido_paterno: str
    apellido_materno: str
    email: Annotated[EmailStr, Field(unique=True, index=True)]
    activo: bool = False
    perfil: str = 'Calificador'


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioUpdate(UsuarioBase):
    nombres: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    email: Optional[EmailStr] = None
    activo: bool = False
    perfil: Optional[str] = None
    password: Optional[str] = None


class Usuario(UsuarioBase, table=True):
    hashed_password: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='calificador')


class Evaluado(SQLModel, table=True):
    id: str = Field(primary_key=True)
    documento_identidad: Annotated[str, Field(unique=True, index=True)]
    nombres: str
    apellido_paterno: str
    apellido_materno: str
    carrera: str
    edad: int
    colegio: str
    ensayo: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='evaluado')


class FichaCalificacionBase(SQLModel):
    id: Annotated[str, Field(primary_key=True)]
    criterio1: Optional[int] = None
    criterio2: Optional[int] = None
    criterio3: Optional[int] = None
    criterio4: Optional[int] = None
    comentario: Optional[str] = None


class FichaCalificacion(FichaCalificacionBase, table=True):
    calificador_id: Annotated[str, Field(foreign_key="usuario.id")]
    evaluado_id: Annotated[str, Field(foreign_key="evaluado.id")]
    calificador: Usuario = Relationship(back_populates='fichas')
    evaluado: Evaluado = Relationship(back_populates='fichas')
