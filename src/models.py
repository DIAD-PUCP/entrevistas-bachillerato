from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Field, Relationship, SQLModel


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
    perfil: str = "Calificador"


class UsuarioCreate(UsuarioBase):
    password: str
    password_confirm: str


class UsuarioUpdate(UsuarioBase):
    nombres: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    email: Optional[EmailStr] = None
    activo: bool = False
    perfil: Optional[str] = None
    password: Optional[str] = None
    password_confirm: Optional[str] = None


class Usuario(UsuarioBase, table=True):
    hashed_password: str
    fichas: list["FichaCalificacion"] = Relationship(
        back_populates="calificador",
        sa_relationship_kwargs={"order_by": "FichaCalificacion.fecha_entrevista"},
    )


class EvaluadoBase(SQLModel):
    id: Annotated[str, Field(primary_key=True, min_length=1)]
    documento_identidad: Annotated[str, Field(unique=True, index=True)]
    nombres: Annotated[str, Field(min_length=1)]
    apellido_paterno: Annotated[str, Field(min_length=1)]
    apellido_materno: str


class Evaluado(EvaluadoBase, table=True):
    fichas: list["FichaCalificacion"] = Relationship(back_populates="evaluado")


class EvaluadoForm(EvaluadoBase):
    pass


class FichaCalificacionBase(SQLModel):
    criterio1: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    criterio2: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    criterio3: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    criterio4: Annotated[Optional[int], Field(gt=0, lt=5)] = None
    comentario: Optional[str] = None
    fecha_calificacion: Optional[datetime] = None

    @field_validator("fecha_calificacion", mode="before")
    @classmethod
    def validar_fecha(cls, value: Any) -> Any:
        if isinstance(value, str) and (value == ""):
            return None
        return value


class FichaCalificacion(FichaCalificacionBase, table=True):
    id: Annotated[str, Field(primary_key=True)]
    calificador_id: Annotated[str, Field(foreign_key="usuario.id")]
    evaluado_id: Annotated[str, Field(foreign_key="evaluado.id")]
    calificador: Usuario = Relationship(back_populates="fichas")
    evaluado: Evaluado = Relationship(back_populates="fichas")
    fecha_entrevista: datetime


class DescCriterios(SQLModel, table=True):
    id: Annotated[int, Field(primary_key=True)]
    criterio1: Annotated[str, Field(min_length=1)]
    criterio2: Annotated[str, Field(min_length=1)]
    criterio3: Annotated[str, Field(min_length=1)]
    criterio4: Annotated[str, Field(min_length=1)]
