from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import BinaryIO

from fastapi.responses import FileResponse
from starlette.requests import Request

from .config import SESSION_COOKIE, database_path
from .db import connect_db


DEMO_MODE_ENV = "OPOTEST_DEMO_MODE"
DEMO_ROOT_ENV = "OPOTEST_DEMO_ROOT"
DEMO_TTL_ENV = "OPOTEST_DEMO_TTL_SECONDS"
BASE_PATH_ENV = "OPOTEST_BASE_PATH"
DEMO_ASSET_ROOT_ENV = "OPOTEST_DEMO_ASSET_ROOT"
MADRID = ZoneInfo("Europe/Madrid")


def demo_mode_enabled() -> bool:
    return os.environ.get(DEMO_MODE_ENV, "1").strip().lower() not in {"0", "false", "no", "off"}


def demo_cookie_path() -> str:
    raw = os.environ.get(BASE_PATH_ENV, "/opotest").strip()
    if not raw or raw == "/":
        return "/"
    return "/" + raw.strip("/")


def _demo_root() -> Path:
    root = Path(os.environ.get(DEMO_ROOT_ENV, "/tmp/opotest-demo"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ttl_seconds() -> int:
    try:
        return max(900, int(os.environ.get(DEMO_TTL_ENV, "21600")))
    except ValueError:
        return 21600


def _session_key(raw_token: str) -> str:
    if not raw_token:
        raise RuntimeError("La sesión de demo no tiene token.")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _db_dir() -> Path:
    path = _demo_root() / "db"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _storage_dir() -> Path:
    path = _demo_root() / "storage"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _demo_asset_root() -> Path:
    return Path(os.environ.get(DEMO_ASSET_ROOT_ENV, "/app/demo_attachments"))


def _safe_relative_storage_key(key: str) -> Path:
    relative = Path(str(key).replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError("Ruta de adjunto de demo no válida.")
    return relative


def _seed_asset_path(key: str) -> Path | None:
    relative = _safe_relative_storage_key(key)
    if not relative.parts or relative.parts[0] != "demo-seed":
        return None
    target = _demo_asset_root().joinpath(*relative.parts)
    return target


def _locks_dir() -> Path:
    path = _demo_root() / "locks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_db(raw_token: str) -> Path:
    return _db_dir() / f"{_session_key(raw_token)}.db"


def _session_storage(raw_token: str) -> Path:
    return _storage_dir() / _session_key(raw_token)


def _safe_storage_path(raw_token: str, key: str) -> Path:
    relative = _safe_relative_storage_key(key)
    root = _session_storage(raw_token)
    target = root.joinpath(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _remove_sqlite_family(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _cleanup_expired() -> None:
    cutoff = time.time() - _ttl_seconds()
    try:
        db_files = list(_db_dir().glob("*.db"))
    except OSError:
        return
    for db_file in db_files:
        try:
            if db_file.stat().st_mtime >= cutoff:
                continue
        except FileNotFoundError:
            continue
        key = db_file.stem
        _remove_sqlite_family(db_file)
        shutil.rmtree(_storage_dir() / key, ignore_errors=True)
        try:
            (_locks_dir() / f"{key}.lock").unlink()
        except FileNotFoundError:
            pass


def _business_date_shift_days(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT value FROM opotest_demo_meta WHERE key='seed_anchor_date'"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    if not row:
        return 0
    try:
        anchor = date.fromisoformat(str(row[0]))
    except ValueError:
        return 0
    return (datetime.now(MADRID).date() - anchor).days


def _shift_demo_business_dates(conn: sqlite3.Connection) -> None:
    """Move synthetic business dates so the demo is always recent.

    The master SQLite remains completely fixed. Only the private session snapshot is
    shifted, preserving the relative two-month history while aligning its reference
    date with today. Technical session timestamps are deliberately left untouched.
    """
    days = _business_date_shift_days(conn)
    if days == 0:
        return
    modifier = f"{days:+d} days"
    timestamp_columns = (
        ("attempts", "created_at", False),
        ("users", "created_at", False),
        ("users", "deactivated_at", True),
        ("topics", "created_at", False),
        ("questions", "created_at", False),
        ("questions", "updated_at", False),
        ("topic_attachments", "created_at", False),
        ("topic_attachment_drafts", "created_at", False),
    )
    for table, column, nullable in timestamp_columns:
        where = f" WHERE {column} IS NOT NULL" if nullable else ""
        try:
            conn.execute(
                f"UPDATE {table} SET {column} = strftime('%Y-%m-%dT%H:%M:%f+00:00', {column}, ?){where}",
                (modifier,),
            )
        except sqlite3.OperationalError:
            # Makes the runtime tolerant of older/newer schemas where an optional table is absent.
            continue
    try:
        # daily_tests tiene UNIQUE(user_id, completed_on). Un UPDATE directo puede
        # colisionar temporalmente con otra fecha consecutiva del mismo usuario.
        # Movemos primero todo a una zona temporal lejana y después a su destino.
        temporary_offset = 10_000
        conn.execute(
            "UPDATE daily_tests SET completed_on = date(completed_on, ?)",
            (f"+{temporary_offset} days",),
        )
        conn.execute(
            "UPDATE daily_tests SET completed_on = date(completed_on, ?)",
            (f"{days - temporary_offset:+d} days",),
        )
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute(
            "UPDATE opotest_demo_meta SET value=? WHERE key='seed_anchor_date'",
            (datetime.now(MADRID).date().isoformat(),),
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _clone_base_database(target: Path) -> None:
    source_path = database_path()
    if not Path(source_path).is_file():
        raise RuntimeError(f"No existe la base SQLite base de la demo: {source_path}")

    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    _remove_sqlite_family(tmp)

    source = connect_db(source_path)
    destination = sqlite3.connect(tmp, timeout=5.0, check_same_thread=False)
    try:
        source.backup(destination)
        destination.commit()
        _shift_demo_business_dates(destination)
    finally:
        destination.close()
        source.close()

    os.replace(tmp, target)


def _ensure_session_database(raw_token: str) -> Path:
    _cleanup_expired()
    target = _session_db(raw_token)
    key = _session_key(raw_token)
    lock_path = _locks_dir() / f"{key}.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        if not target.exists():
            _clone_base_database(target)
        os.utime(target, None)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return target


def demo_connection_for_request(http_request: Request) -> sqlite3.Connection:
    """Return the correct DB connection for a demo request.

    Login/logout intentionally use the base DB only for the technical `sessions`
    table. Every authenticated business request uses a private temporary snapshot.
    """
    if not demo_mode_enabled():
        return connect_db()

    path = http_request.url.path
    public_prefix = demo_cookie_path().rstrip("/")
    if public_prefix and public_prefix != "/" and (path == public_prefix or path.startswith(public_prefix + "/")):
        path = path[len(public_prefix):] or "/"
    raw_token = http_request.cookies.get(SESSION_COOKIE, "")

    if path in {"/api/login", "/api/demo-login", "/api/logout", "/health"} or not raw_token:
        return connect_db()

    return connect_db(_ensure_session_database(raw_token))


def cleanup_demo_session(raw_token: str) -> None:
    if not raw_token:
        return
    try:
        key = _session_key(raw_token)
    except RuntimeError:
        return
    _remove_sqlite_family(_db_dir() / f"{key}.db")
    shutil.rmtree(_storage_dir() / key, ignore_errors=True)
    try:
        (_locks_dir() / f"{key}.lock").unlink()
    except FileNotFoundError:
        pass


def _copy_stream(stream: BinaryIO, target: Path) -> None:
    try:
        position = stream.tell()
    except Exception:
        position = None
    try:
        try:
            stream.seek(0)
        except Exception:
            pass
        with target.open("wb") as output:
            shutil.copyfileobj(stream, output)
    finally:
        if position is not None:
            try:
                stream.seek(position)
            except Exception:
                pass


def demo_storage_put(raw_token: str, file_storage, key: str) -> None:
    target = _safe_storage_path(raw_token, key)
    _copy_stream(file_storage.file, target)


def demo_storage_delete(raw_token: str, key: str) -> None:
    if not raw_token:
        return
    # Los adjuntos precargados pertenecen a la plantilla inmutable. Al borrarlos
    # desde una sesión solo desaparece su fila en la SQLite privada; el fichero
    # maestro queda disponible para el siguiente visitante.
    if _seed_asset_path(key) is not None:
        return
    target = _safe_storage_path(raw_token, key)
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def demo_storage_response(raw_token: str, key: str, filename: str, mime_type: str):
    if not raw_token:
        return None

    # Primero se respeta cualquier archivo temporal de la sesión.
    target = _safe_storage_path(raw_token, key)
    if target.is_file():
        return FileResponse(target, media_type=mime_type, filename=filename)

    # Los adjuntos del seed se sirven desde el filesystem local de la imagen y
    # nunca requieren S3.
    seeded = _seed_asset_path(key)
    if seeded is not None and seeded.is_file():
        return FileResponse(seeded, media_type=mime_type, filename=filename)
    return None
