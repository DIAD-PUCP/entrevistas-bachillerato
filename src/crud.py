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
    return user


def get_evaluado(db: Session, id: str) -> models.Evaluado:
    return db.get(models.Evaluado, id)


def get_evaluado_by_doc(db: Session, doc: str) -> models.Evaluado:
    return db.exec(
        select(models.Evaluado)
        .where(models.Evaluado.documento_identidad == doc)
    ).first()


def create_evaluado(db: Session, evaluado: models.Evaluado) -> models.Evaluado:
    evaluado_data = evaluado.model_dump()
    evalua = models.Evaluado.model_validate(evaluado_data)
    db.add(evalua)
    db.commit()
    return evalua


def update_evaluado(db: Session, id: str, evaluado: models.Evaluado) -> models.Evaluado:
    evalua = db.get(models.Evaluado, id)
    evaluado_data = evaluado.model_dump(exclude_unset=True)
    evalua.sqlmodel_update(evaluado_data)
    db.add(evalua)
    db.commit()
    return evalua


def get_ficha(db: Session, id: str) -> models.FichaCalificacion:
    return db.get(models.FichaCalificacion, id)


def create_ficha(db: Session, ficha: models.FichaCalificacion) -> models.FichaCalificacion:
    ficha_data = ficha.model_dump()
    f = models.FichaCalificacion.model_validate(ficha_data)
    db.add(f)
    db.commit()
    return f


def update_ficha(db: Session, id: str, ficha: models.FichaCalificacion) -> models.FichaCalificacion:
    f = db.get(models.FichaCalificacion, id)
    ficha_data = ficha.model_dump(exclude_unset=True)
    f.sqlmodel_update(ficha_data)
    db.add(f)
    db.commit()
    return f


def calificar_ficha(db: Session, id: str, ficha: models.FichaCalificacionBase) -> models.FichaCalificacion:
    f = db.get(models.FichaCalificacion, id)
    ficha_data = ficha.model_dump(exclude_unset=True)
    f.sqlmodel_update(ficha_data)
    db.add(f)
    db.commit()
    return f
