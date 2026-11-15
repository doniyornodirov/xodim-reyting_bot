import re
import logging
from typing import Any
import asyncpg
import aiosqlite

logger = logging.getLogger("pg_engine")

_PG_POOL: asyncpg.Pool | None = None
_IS_PG_ACTIVE: bool = False

def is_postgres_active() -> bool:
    return _IS_PG_ACTIVE

def clean_postgres_dsn(url: str) -> str:
    """Converts postgres:// to postgresql:// for asyncpg compatibility"""
    dsn = url.strip()
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return dsn

def translate_query_for_postgres(sql: str, params: Any = None) -> tuple[str, list, bool]:
    """
    Translates SQLite query syntax to PostgreSQL:
    1. PRAGMA -> SELECT 1
    2. INSERT OR IGNORE -> ON CONFLICT DO NOTHING
    3. DATE(..., '+5 hours') -> ((... + INTERVAL '5 hours')::date)
    4. ? -> $1, $2, ...
    5. Appends RETURNING id for INSERT statements if not present
    """
    if params is None:
        params_list = []
    elif isinstance(params, (tuple, list)):
        params_list = list(params)
    else:
        params_list = [params]

    clean_sql = sql.strip()
    upper_sql = clean_sql.upper()

    # 1. PRAGMA -> no-op
    if upper_sql.startswith("PRAGMA"):
        return "SELECT 1;", [], False

    is_insert = upper_sql.startswith("INSERT")

    # 2. INSERT OR IGNORE -> ON CONFLICT DO NOTHING
    if "INSERT OR IGNORE INTO" in upper_sql:
        clean_sql = re.sub(r"(?i)INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", clean_sql)
        if "ON CONFLICT" not in clean_sql.upper():
            clean_sql = clean_sql.rstrip(" \t\n;") + " ON CONFLICT DO NOTHING"

    # 3. DATE(...) conversions
    clean_sql = re.sub(r"(?i)DATE\(\s*([a-zA-Z0-9_\.]+)\s*,\s*['\"]\+5\s+hours['\"]\s*\)", r"((\1 + INTERVAL '5 hours')::date)", clean_sql)
    clean_sql = re.sub(r"(?i)DATE\(\s*['\"]now['\"]\s*,\s*['\"]\+5\s+hours['\"]\s*\)", r"((CURRENT_TIMESTAMP + INTERVAL '5 hours')::date)", clean_sql)
    clean_sql = re.sub(r"(?i)DATE\(\s*['\"]now['\"]\s*\)", r"(CURRENT_DATE)", clean_sql)
    clean_sql = re.sub(r"(?i)DATE\(\s*([a-zA-Z0-9_\.]+)\s*\)", r"((\1)::date)", clean_sql)

    # 4. Convert ? to $1, $2, ... (skipping inside string literals)
    parts = []
    i = 0
    param_idx = 1
    in_quote = False
    quote_char = ''
    while i < len(clean_sql):
        char = clean_sql[i]
        if in_quote:
            parts.append(char)
            if char == quote_char:
                if i + 1 < len(clean_sql) and clean_sql[i + 1] == quote_char:
                    parts.append(clean_sql[i + 1])
                    i += 1
                else:
                    in_quote = False
        else:
            if char in ("'", '"'):
                in_quote = True
                quote_char = char
                parts.append(char)
            elif char == '?':
                parts.append(f"${param_idx}")
                param_idx += 1
            else:
                parts.append(char)
        i += 1

    out_sql = "".join(parts).strip().rstrip(";")

    appended_returning = False
    if is_insert and "RETURNING" not in out_sql.upper() and "ON CONFLICT DO NOTHING" not in out_sql.upper():
        out_sql += " RETURNING id"
        appended_returning = True

    return out_sql + ";", params_list, appended_returning


class PostgresRecordWrapper:
    """Wraps an asyncpg.Record to provide 100% aiosqlite.Row compatibility"""
    __slots__ = ("_record", "_dict", "_keys", "_values")

    def __init__(self, record: asyncpg.Record):
        self._record = record
        self._dict = dict(record)
        self._keys = list(self._dict.keys())
        self._values = list(self._dict.values())

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, int):
            return self._values[item]
        return self._dict[item]

    def get(self, key: str, default: Any = None) -> Any:
        return self._dict.get(key, default)

    def keys(self):
        return self._keys

    def values(self):
        return self._values

    def items(self):
        return self._dict.items()

    def __contains__(self, key: str) -> bool:
        return key in self._dict

    def __iter__(self):
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def __repr__(self) -> str:
        return f"<PostgresRecordWrapper {self._dict}>"


class PostgresCursorWrapper:
    """Cursor that wraps asyncpg execution results"""
    def __init__(self, rows: list[asyncpg.Record] | None = None, lastrowid: int | None = None, rowcount: int = 0):
        self._rows = [PostgresRecordWrapper(r) for r in (rows or [])]
        self._idx = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    async def fetchone(self) -> PostgresRecordWrapper | None:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    async def fetchall(self) -> list[PostgresRecordWrapper]:
        remaining = self._rows[self._idx:]
        self._idx = len(self._rows)
        return remaining

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row


class PostgresConnectionWrapper:
    """Connection that wraps an asyncpg pool acquisition"""
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._conn: asyncpg.Connection | None = None
        self.row_factory = None

    def __await__(self):
        async def _acquire():
            if not self._conn:
                self._conn = await self._pool.acquire()
            return self
        return _acquire().__await__()

    async def __aenter__(self):
        if not self._conn:
            self._conn = await self._pool.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def execute(self, sql: str, params: Any = None) -> PostgresCursorWrapper:
        if not self._conn:
            self._conn = await self._pool.acquire()

        pg_sql, pg_params, appended_ret = translate_query_for_postgres(sql, params)
        upper_sql = pg_sql.strip().upper()

        lastrowid = None
        rowcount = 0

        try:
            if upper_sql.startswith("SELECT") or "RETURNING" in upper_sql:
                records = await self._conn.fetch(pg_sql, *pg_params)
                rowcount = len(records)
                if appended_ret and records:
                    first = records[0]
                    if "id" in first:
                        lastrowid = int(first["id"])
                return PostgresCursorWrapper(rows=records, lastrowid=lastrowid, rowcount=rowcount)
            else:
                status = await self._conn.execute(pg_sql, *pg_params)
                # Parse status e.g. 'UPDATE 1', 'INSERT 0 1', 'DELETE 5'
                parts = status.split()
                if parts and parts[-1].isdigit():
                    rowcount = int(parts[-1])
                return PostgresCursorWrapper(rows=[], lastrowid=lastrowid, rowcount=rowcount)
        except Exception as e:
            logger.error(f"PostgreSQL xatosi: {e} | SQL: {pg_sql} | Params: {pg_params}")
            raise

    async def executescript(self, script: str) -> None:
        if not self._conn:
            self._conn = await self._pool.acquire()
        # Execute script statements
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in statements:
            await self.execute(stmt)

    async def commit(self) -> None:
        # Autocommit is default in asyncpg
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        if self._conn:
            try:
                await self._pool.release(self._conn)
            except Exception:
                pass
            self._conn = None


async def init_postgres_pool(database_url: str) -> asyncpg.Pool:
    """Initializes asyncpg connection pool and patches aiosqlite for seamless compatibility"""
    global _PG_POOL, _IS_PG_ACTIVE
    clean_dsn = clean_postgres_dsn(database_url)
    logger.info("Supabase PostgreSQL ulanish havzasi (connection pool) yaratilmoqda...")

    # statement_cache_size=0 is REQUIRED for Supabase PgBouncer pooler (port 6543)
    _PG_POOL = await asyncpg.create_pool(
        dsn=clean_dsn,
        min_size=2,
        max_size=15,
        command_timeout=20,
        statement_cache_size=0
    )

    # Test the connection
    async with _PG_POOL.acquire() as test_conn:
        version = await test_conn.fetchval("SELECT version();")
        logger.info(f"Supabase PostgreSQL ga muvaffaqiyatli ulandi! Versiya: {version[:40]}...")

    _IS_PG_ACTIVE = True

    # Patch aiosqlite.connect globally
    def pg_connect(*args, **kwargs):
        return PostgresConnectionWrapper(_PG_POOL)

    aiosqlite.connect = pg_connect
    logger.info("aiosqlite.connect muvaffaqiyatli PostgreSQL ga yo'naltirildi (Zero-Code Change).")

    return _PG_POOL


async def close_postgres_pool() -> None:
    global _PG_POOL, _IS_PG_ACTIVE
    if _PG_POOL:
        await _PG_POOL.close()
        _PG_POOL = None
        _IS_PG_ACTIVE = False
        logger.info("PostgreSQL havzasi yopildi.")
