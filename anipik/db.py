import copy
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from .config import DB_PATH, DEFAULT_SETTINGS
from .models import Base, Setting


def make_session_factory(path=DB_PATH):
    """Create (if needed) the SQLite database and return a session factory."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # The web server and the scheduler thread share this engine; wait for locks instead of failing.
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30, "check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if str(path) != ":memory:":
            cursor.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
        cursor.close()

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    # Objects stay usable after commit; the scheduler commits at every checkpoint.
    return sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(engine):
    """Minimal schema upgrade: create_all() makes new tables, this adds new nullable columns."""
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable:
                    raise RuntimeError(f"cannot add NOT NULL column {table.name}.{column.name} automatically")
                ddl = column.type.compile(engine.dialect)
                connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}')


@contextmanager
def session_scope(factory):
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_setting(session: Session, key, default=None):
    row = session.get(Setting, key)
    if row is not None:
        return copy.deepcopy(row.value)
    return copy.deepcopy(DEFAULT_SETTINGS.get(key, default))


def set_setting(session: Session, key, value):
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value


def all_settings(session: Session):
    values = copy.deepcopy(DEFAULT_SETTINGS)
    values.update({row.key: row.value for row in session.scalars(select(Setting))})
    return values
