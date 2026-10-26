# Copyright (C) 2026 GLEAP Co., Ltd.
# All rights reserved.

"""UDF が返す 2 つの string のうち、先の列が後の列で上書きされる再現。

組み合わせごとに、同じ値を dbapi の直接 INSERT と UDF 経由の INSERT で
chk01_strings_result に書き、最後に読み戻して見比べる。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tsurugi_dbapi as tsurugi

TSURUGI_ENDPOINT = "tcp://g2:12345"
TSURUGI_USER = "tsurugi"
TSURUGI_PW = "password"

CREATE_SQL = Path(__file__).resolve().parent / "create_ascii_probe.sql"

CASES = (
    ("a" * 16, "Person-test.jpeg"),
    ("a" * 17, "Person-test.jpeg"),
    ("a" * 17, "Reid-test.jpeg"),
)


def connect() -> tsurugi.Connection:
    config = tsurugi.Config()
    config.endpoint = TSURUGI_ENDPOINT
    config.user = TSURUGI_USER
    config.password = TSURUGI_PW
    config.default_timeout = 60
    return tsurugi.connect(config)


def sql_statements(path: Path) -> list[str]:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    ]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def describe(text: str) -> str:
    raw = text.encode("utf-8")
    return f"{text!r} bytes={len(raw)} nul={b'\x00' in raw}"


def setup(conn: tsurugi.Connection) -> None:
    with conn.cursor() as cur:
        for statement in sql_statements(CREATE_SQL):
            cur.execute(statement)
            conn.commit()


def insert_dbapi(
    cur: tsurugi.Cursor,
    conn: tsurugi.Connection,
    name_a: str,
    name_b: str,
) -> None:
    cur.execute(
        "insert into chk01_strings_result (via, name_a, name_b) values ('dbapi', ?, ?)",
        (name_a, name_b),
    )
    conn.commit()


def insert_udf(
    cur: tsurugi.Cursor,
    conn: tsurugi.Connection,
    case_id: int,
    name_a: str,
    name_b: str,
) -> None:
    cur.execute("delete from chk01_strings_source")
    cur.execute(
        "insert into chk01_strings_source (id, name_a, name_b) values (?, ?, ?)",
        (case_id, name_a, name_b),
    )
    conn.commit()
    cur.execute(
        """
        insert into chk01_strings_result (via, name_a, name_b)
        select 'udf', p.name_a, p.name_b
        from chk01_strings_source as s
        apply read_two_strings(s.name_a, s.name_b) as p
        """,
    )
    conn.commit()


def run_case(conn: tsurugi.Connection, title: str, fn) -> None:
    try:
        with conn.cursor() as cur:
            fn(cur, conn)
    except Exception as exc:  # noqa: BLE001
        print(f"  {title}: FAIL {exc}")
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            try:
                rollback()
            except Exception:  # noqa: BLE001
                print(f"  {title}: FAIL {exc}", file=sys.stderr)
        return
    print(f"  {title}: ok")


def dump(conn: tsurugi.Connection) -> None:
    print("\n--- chk01_strings_result")
    with conn.cursor() as cur:
        cur.execute(
            "select id, via, name_a, name_b from chk01_strings_result order by id",
        )
        rows = cur.fetchall()
        conn.commit()
    if not rows:
        print("(empty)")
    for row in rows:
        print(
            f"id={row[0]} via={row[1]} "
            f"name_a={describe(str(row[2]))} name_b={describe(str(row[3]))}",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "name_a",
        nargs="?",
        help="1 つ目の文字列。省略すると既定の組み合わせを全部試す",
    )
    parser.add_argument(
        "name_b",
        nargs="?",
        default="Person-test.jpeg",
        help="2 つ目の文字列",
    )
    args = parser.parse_args(argv)
    cases = [(args.name_a, args.name_b)] if args.name_a else list(CASES)
    try:
        with connect() as conn:
            setup(conn)
            for case_id, (name_a, name_b) in enumerate(cases, start=1):
                print(f"\n--- name_a {describe(name_a)} name_b {describe(name_b)}")
                run_case(
                    conn,
                    "dbapi",
                    lambda cur, c, a=name_a, b=name_b: insert_dbapi(cur, c, a, b),
                )
                run_case(
                    conn,
                    "udf",
                    lambda cur, c, i=case_id, a=name_a, b=name_b: insert_udf(
                        cur,
                        c,
                        i,
                        a,
                        b,
                    ),
                )
            dump(conn)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
