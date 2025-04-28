from datetime import datetime
from typing import Annotated, Any, Optional
from sqlmodel import Field, Relationship, SQLModel
from pydantic import BaseModel, EmailStr, field_validator


class LoginData(BaseModel):
    email: str
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
    nombres: Optional[str] = None # type: ignore
    apellido_paterno: Optional[str] = None # type: ignore
    apellido_materno: Optional[str] = None # type: ignore
    email: Optional[EmailStr] = None # type: ignore
    activo: bool = False
    perfil: Optional[str] = None # type: ignore
    password: Optional[str] = None


class Usuario(UsuarioBase, table=True):
    hashed_password: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates='calificador',
        sa_relationship_kwargs={
            'order_by': 'FichaCalificacion.fecha_entrevista'
        }
    )


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
    criterio1: Optional[int] = None
    criterio2: Optional[int] = None
    criterio3: Optional[int] = None
    criterio4: Optional[int] = None
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
    criterio1: str
    criterio2: str
    criterio3: str
    criterio4: str
