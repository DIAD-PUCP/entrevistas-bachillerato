"""Migración de una sola ejecución.

Los timestamps de `fichacalificacion` están guardados como UTC pero en
realidad representan -05:00, así que se les suma 5 horas para que pasen a
ser UTC real.

Uso: python migrate_fechas.py [ruta_db]
"""

import sqlite3
import sys
from datetime import datetime, timedelta

DB = sys.argv[1] if len(sys.argv) > 1 else "database.db"
OFFSET = timedelta(hours=5)
FMT = "%Y-%m-%d %H:%M:%S.%f"


def shift(value: str | None) -> str | None:
    if value is None:
        return None
    return (datetime.fromisoformat(value) + OFFSET).strftime(FMT)


def main() -> None:
    with sqlite3.connect(DB) as db:
        rows = db.execute(
            "SELECT id, fecha_entrevista FROM fichacalificacion"
        ).fetchall()
        db.executemany(
            "UPDATE fichacalificacion SET fecha_entrevista = ? WHERE id = ?",
            [(shift(fe), id_) for id_, fe in rows],
        )
    print(f"{len(rows)} filas actualizadas en {DB}")


if __name__ == "__main__":
    main()
