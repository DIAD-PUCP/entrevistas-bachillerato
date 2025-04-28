from datetime import datetime
from typing import Optional
from fastapi import HTTPException
from passlib.hash import bcrypt
from sqlmodel import Session, func, select, column
from . import models


def get_usuario(db: Session, usuario_id: str) -> Optional[models.Usuario]:
    return db.get(models.Usuario, usuario_id)


def get_all_usuarios(db: Session) -> list[models.Usuario]:
    return list(db.exec(
        select(models.Usuario)
    ).all())


def get_usuarios_activos(db: Session) -> list[models.Usuario]:
    return list(db.exec(
        select(models.Usuario)
        .where(models.Usuario.activo == True)
    ).all())


def get_usuario_by_email(db: Session, email: str) -> Optional[models.Usuario]:
    return db.exec(
        select(models.Usuario)
        .where(models.Usuario.email == email)
    ).first()


def create_usuario(db: Session, usuario: models.UsuarioCreate) -> models.Usuario:
    user_data = usuario.model_dump()
    user_data['hashed_password'] = bcrypt.hash(user_data['password'])
    user = models.Usuario.model_validate(user_data)
    db.add(user)
    db.commit()
    return user


def update_usuario(db: Session, usuario_id: str, usuario: models.UsuarioUpdate) -> models.Usuario:
    user = db.get(models.Usuario, usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="No se encontró usuario")
    user_data = usuario.model_dump(exclude_unset=True)
    if usuario.password != '':
        user_data['hashed_password'] = bcrypt.hash(user_data['password'])
    user.sqlmodel_update(user_data)
    db.add(user)
    db.commit()
    return user


def delete_usuario(db: Session, usuario_id: str) -> None:
    user = db.get(models.Usuario, usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="No se encontró usuario")
    db.delete(user)
    db.commit()


def get_evaluado(db: Session, evaluado_id: str) -> Optional[models.Evaluado]:
    return db.get(models.Evaluado, evaluado_id)


def get_evaluados(db: Session) -> list[models.Evaluado]:
    return list(db.exec(
        select(models.Evaluado)
    ).all())


def get_evaluado_by_doc(db: Session, doc: str) -> Optional[models.Evaluado]:
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


def update_evaluado(db: Session, evaluado_id: str, evaluado: models.Evaluado) -> models.Evaluado:
    evalua = db.get(models.Evaluado, evaluado_id)
    if not evalua:
        raise HTTPException(status_code=404, detail="No se encontró evaluado")
    evaluado_data = evaluado.model_dump(exclude_unset=True)
    evalua.sqlmodel_update(evaluado_data)
    db.add(evalua)
    db.commit()
    return evalua


def delete_evaluado(db: Session, evaluado_id: str) -> None:
    evalua = db.get(models.Evaluado, evaluado_id)
    if not evalua:
        raise HTTPException(status_code=404, detail="No se encontró evaluado")
    db.delete(evalua)
    db.commit()


def get_ficha(db: Session, ficha_id: str) -> Optional[models.FichaCalificacion]:
    return db.get(models.FichaCalificacion, ficha_id)


def get_all_fichas(db: Session) -> list[models.FichaCalificacion]:
    return list(db.exec(
        select(models.FichaCalificacion)
    ).all())


def create_ficha(db: Session, ficha: models.FichaCalificacion) -> models.FichaCalificacion:
    ficha_data = ficha.model_dump()
    f = models.FichaCalificacion.model_validate(ficha_data)
    db.add(f)
    db.commit()
    return f


def update_ficha(db: Session, ficha_id: str, ficha: models.FichaCalificacion) -> models.FichaCalificacion:
    f = db.get(models.FichaCalificacion, ficha_id)
    if not f:
        raise HTTPException(status_code=404, detail="No se encontró ficha")
    ficha_data = ficha.model_dump(exclude_unset=True)
    f.sqlmodel_update(ficha_data)
    db.add(f)
    db.commit()
    return f


def delete_ficha(db: Session, ficha_id: str) -> None:
    ficha = db.get(models.FichaCalificacion, ficha_id)
    if not ficha:
        raise HTTPException(status_code=404, detail="No se encontró ficha")
    db.delete(ficha)
    db.commit()


def calificar_ficha(db: Session, ficha_id: str, ficha: models.FichaCalificacionBase) -> models.FichaCalificacion:
    f = db.get(models.FichaCalificacion, ficha_id)
    if not f:
        raise HTTPException(status_code=404, detail="No se encontró ficha")
    ficha_data = ficha.model_dump(exclude_unset=True)
    ficha_data['fecha_calificacion'] = datetime.now()
    f.sqlmodel_update(ficha_data)
    db.add(f)
    db.commit()
    return f


def get_decripciones_criterios(db: Session) -> Optional[models.DescCriterios]:
    return db.get(models.DescCriterios, 1)

def set_decripciones_criterios(db: Session, criterios: models.DescCriterios) -> models.DescCriterios:
    crit = db.get(models.DescCriterios, 1)
    if not crit:
        crit = criterios
    else:
        crit.sqlmodel_update(criterios)
    db.add(crit)
    db.commit()
    return crit

def get_reporte_progreso(db: Session):
    stmt = (
        select(
            models.FichaCalificacion.calificador_id,
            func.IF(models.FichaCalificacion.fecha_calificacion != None,'Calificado','Sin calificar').label('estado'),
            func.count(models.FichaCalificacion.id).label('cantidad')
        )
        .group_by(
            models.FichaCalificacion.calificador_id,
            column('estado')
        )
    ).subquery()
    stmt2 = (
        select(
            (models.Usuario.apellido_paterno + ' ' + 
            models.Usuario.apellido_materno + ', ' + 
            models.Usuario.nombres).label('Calificador'),
            stmt.c.estado,
            stmt.c.cantidad
        )
        .join(stmt)
    )
    return db.exec(stmt2).all()
