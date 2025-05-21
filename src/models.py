from datetime import datetime
from typing import Annotated, Any, Optional
from fastapi import UploadFile
from sqlmodel import Field, Relationship, SQLModel
from pydantic import BaseModel, EmailStr, field_validator


class LoginData(BaseModel):
    email: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class UsuarioBase(SQLModel):
    id: Annotated[str, Field(primary_key=True, min_length=1)]
    nombres: Annotated[str, Field(min_length=1)]
    apellido_paterno: Annotated[str, Field(min_length=1)]
    apellido_materno: Annotated[str, Field(min_length=1)]
    email: Annotated[EmailStr, Field(unique=True, index=True)]
    activo: bool = False
    perfil: str = 'Calificador'


class UsuarioCreate(UsuarioBase):
    password: str
    password_confirm: str


class UsuarioUpdate(UsuarioBase):
    nombres: Optional[str] = None  # type: ignore
    apellido_paterno: Optional[str] = None  # type: ignore
    apellido_materno: Optional[str] = None  # type: ignore
    email: Optional[EmailStr] = None  # type: ignore
    activo: bool = False
    perfil: Optional[str] = None  # type: ignore
    password: Optional[str] = None
    password_confirm: Optional[str] = None


class Usuario(UsuarioBase, table=True):
    hashed_password: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='calificador',
        sa_relationship_kwargs={
            'order_by': 'FichaCalificacion.fecha_entrevista'
        }
    )


class EvaluadoBase(SQLModel):
    id: Annotated[str, Field(primary_key=True, min_length=1)]
    documento_identidad: Annotated[str, Field(unique=True, index=True)]
    nombres: Annotated[str, Field(min_length=1)]
    apellido_paterno: Annotated[str, Field(min_length=1)]
    apellido_materno: str
    carrera: Annotated[str, Field(min_length=1)]
    edad: Annotated[int, Field(gt=0, lt=130)]
    colegio: Annotated[str, Field(min_length=1)]


class Evaluado(EvaluadoBase, table=True):
    ensayo: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='evaluado')


class EvaluadoForm(EvaluadoBase):
    ensayo: Optional[str] = None
    archivo: Optional[UploadFile] = None


class FichaCalificacionBase(SQLModel):
    criterio1: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    criterio2: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    criterio3: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    criterio4: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    comentario: Optional[str] = None
    fecha_calificacion: Optional[datetime] = None

    @field_validator('fecha_calificacion', mode='before')
    @classmethod
    def validar_fecha(cls, value: Any) -> Any:
        if isinstance(value, str) and (value == ''):
            return None
        return value


class FichaCalificacion(FichaCalificacionBase, table=True):
    id: Annotated[str, Field(primary_key=True)]
    calificador_id: Annotated[str, Field(foreign_key="usuario.id")]
    evaluado_id: Annotated[str, Field(foreign_key="evaluado.id")]
    calificador: Usuario = Relationship(back_populates='fichas')
    evaluado: Evaluado = Relationship(back_populates='fichas')
    fecha_entrevista: datetime


class DescCriterios(SQLModel, table=True):
    id: Annotated[int, Field(primary_key=True)]
    criterio1: Annotated[str, Field(min_length=1)]
    criterio2: Annotated[str, Field(min_length=1)]
    criterio3: Annotated[str, Field(min_length=1)]
    criterio4: Annotated[str, Field(min_length=1)]
