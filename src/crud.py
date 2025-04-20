import os
from passlib.hash import bcrypt
from sqlmodel import Session, select
from . import models

SECRET_KEY = os.getenv('SECRET_KEY', "")


def get_usuario(db: Session, id: str) -> models.Usuario:
    return db.get(models.Usuario, id)

def get_usuario_by_email(db: Session, email: str) -> models.Usuario:
    return db.exec(
        select(models.Usuario)
        .where(models.Usuario.email == email)
    ).first()


def create_usuario(db: Session, usuario: models.UsuarioCreate) -> models.Usuario:
    user_data = usuario.model_dump()
    user_data['hashed_password'] = bcrypt.hash(
        user_data['password']+SECRET_KEY
    )
    user = models.Usuario.model_validate(user_data)
    db.add(user)
    db.commit()
    return user

def update_usuario(db: Session, id: str, usuario: models.UsuarioUpdate) -> models.Usuario:
    user = db.get(models.Usuario, id)
    user_data = usuario.model_dump(exclude_unset=True)
    if usuario.password != '':
        user_data['hashed_password'] = bcrypt.hash(
            user_data['password']+SECRET_KEY
        )
    user.sqlmodel_update(user_data)
    db.add(user)
    db.commit()
