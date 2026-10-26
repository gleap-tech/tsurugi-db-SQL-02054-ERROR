# Copyright (C) 2026 GLEAP Co., Ltd.
# All rights reserved.

"""受け取った 2 つの文字列をそのまま返す UDF。listen は [::]:50061。"""

from __future__ import annotations

from concurrent import futures

import grpc

try:
    from udf_ascii_pb2 import TwoStrings
    from udf_ascii_pb2_grpc import UdfAsciiServicer, add_UdfAsciiServicer_to_server
except ImportError as exc:
    raise SystemExit(
        "udf_ascii_pb2 がありません。README の protoc を先に実行してください。",
    ) from exc

LISTEN = "[::]:50061"


def _describe(text: str) -> str:
    raw = text.encode("utf-8")
    return f"{text!r} bytes={len(raw)} nul={b'\x00' in raw}"


class UdfAsciiServer(UdfAsciiServicer):
    def read_two_strings(self, request, context):  # noqa: ANN001, ARG002
        print(
            f"return name_a={_describe(request.name_a)} "
            f"name_b={_describe(request.name_b)}",
            flush=True,
        )
        yield TwoStrings(name_a=request.name_a, name_b=request.name_b)


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    add_UdfAsciiServicer_to_server(UdfAsciiServer(), server)
    server.add_insecure_port(LISTEN)
    server.start()
    print(f"listening on {LISTEN}", flush=True)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("停止します")
    finally:
        server.stop(0)


if __name__ == "__main__":
    serve()
