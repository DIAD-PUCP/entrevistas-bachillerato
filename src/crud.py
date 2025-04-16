from . import models
from sqlmodel import Session, select

def get_usuario(db: Session, id: str) -> models.Usuario:
    return db.get(models.Usuario,id)