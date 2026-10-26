# UDF の string 戻り値が後続の string に上書きされる

- Tsurugi 1.12.0

server streaming の UDF が、16 バイト以上の `string` を2つ同じ行で返すと、先の列の値が後の列の値で上書きされた状態で INSERT される。

- 先の列の長さが後の列と同じ場合、エラーにならず、後の列の値がそのまま書き込まれる。
- 先の列の方が長い場合、上書きした文字列の終端 `0x00` が残り、INSERT が次のエラーで落ちる。

```text
SQL-02054(INVALID_RUNTIME_VALUE_EXCEPTION): detected invalid runtime value
(jogasaki/src/jogasaki/index/primary_target.cpp:323)
```

UDF サーバ上での送る直前の値は問題なさそう。
同じ値を dbapi で直接 INSERT すると正しく書ける。
日本語かどうかは関係ない。

## 構成

| ファイル                     | 内容                                                                        |
| ---------------------------- | --------------------------------------------------------------------------- |
| `sql/create_ascii_probe.sql` | `chk01_strings_source`（UDF の入力）、`chk01_strings_result`（書き込み先）  |
| `udf-ascii.proto`            | `read_two_strings(TwoStrings) returns (stream TwoStrings)`                  |
| `udf_server.py`              | 受け取った `name_a` / `name_b` をそのまま 1 行返す                          |
| `run_probe.py`               | 組み合わせごとに、dbapi の直接 INSERT と UDF 経由の INSERT を書いて見比べる |

## 1. ライブラリビルド

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. udf-ascii.proto

udf-plugin-builder --proto udf-ascii.proto -I . \
  --grpc-endpoint dns:///localhost:50061 \
  --output-dir "$TSURUGI_HOME/var/plugins" \
  --clean
```

```bash
$TSURUGI_HOME/bin/tgctl shutdown
$TSURUGI_HOME/bin/tgctl start
```

## 2. サーバ

```bash
python udf_server.py
```

## 3. クライアント

```bash
python run_probe.py
```

既定では次の3つを試す。1つだけ試すときは `python run_probe.py <name_a> <name_b>`。

| name_a   | name_b                          | 期待                                            |
| -------- | ------------------------------- | ----------------------------------------------- |
| `a` × 16 | `Person-test.jpeg`（16 バイト） | 成功するが、name_a が `Person-test.jpeg` になる |
| `a` × 17 | `Person-test.jpeg`（16 バイト） | SQL-02054                                       |
| `a` × 17 | `Reid-test.jpeg`（14 バイト）   | 正しく書ける                                    |

## 再現結果

| name_a   | name_b                          | 書き込まれた name_a | 結果             |
| -------- | ------------------------------- | ------------------- | ---------------- |
| `a` × 16 | `Person-test.jpeg`（16 バイト） | `Person-test.jpeg`  | 成功（値が違う） |
| `a` × 17 | `Person-test.jpeg`（16 バイト） | なし                | SQL-02054        |
| `a` × 16 | `Reid-test.jpeg`（14 バイト）   | `a` × 16            | 成功             |
| `a` × 17 | `Reid-test.jpeg`（14 バイト）   | `a` × 17            | 成功             |

name_b はどの行も正しく書き込まれる。name_a が 15 バイト以下（`hoge`、`a` × 15）なら正しく書ける。

## 再現ログ

- サーバ

```bash
listening on [::]:50061
return name_a='aaaaaaaaaaaaaaaa' bytes=16 nul=False name_b='Person-test.jpeg' bytes=16 nul=False
return name_a='aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b='Person-test.jpeg' bytes=16 nul=False
return name_a='aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b='Reid-test.jpeg' bytes=14 nul=False
```

- クライアント

```bash
--- name_a 'aaaaaaaaaaaaaaaa' bytes=16 nul=False name_b 'Person-test.jpeg' bytes=16 nul=False
  dbapi: ok
  udf: ok

--- name_a 'aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b 'Person-test.jpeg' bytes=16 nul=False
  dbapi: ok
  udf: FAIL SQL-02054(INVALID_RUNTIME_VALUE_EXCEPTION): detected invalid runtime value ({"source_file":"/home/svi/GLEAP/tsurugi/tsurugidb-1.12.0/jogasaki/src/jogasaki/index/primary_target.cpp:323"})

--- name_a 'aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b 'Reid-test.jpeg' bytes=14 nul=False
  dbapi: ok
  udf: ok

--- chk01_strings_result
id=1 via=dbapi name_a='aaaaaaaaaaaaaaaa' bytes=16 nul=False name_b='Person-test.jpeg' bytes=16 nul=False
id=2 via=udf name_a='Person-test.jpeg' bytes=16 nul=False name_b='Person-test.jpeg' bytes=16 nul=False
id=3 via=dbapi name_a='aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b='Person-test.jpeg' bytes=16 nul=False
id=5 via=dbapi name_a='aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b='Reid-test.jpeg' bytes=14 nul=False
id=6 via=udf name_a='aaaaaaaaaaaaaaaaa' bytes=17 nul=False name_b='Reid-test.jpeg' bytes=14 nul=False
```

## 推測

15 バイト以下の文字列は C++ の `std::string` の内部バッファに収まり、16 バイト以上はヒープに確保される。
結果はその境目と一致。

UDF の戻り値を行に詰める処理で、先の列の文字列のヒープ領域が解放されたあとも参照が残っている。後の列の文字列が同じ領域に確保されて、内容が上書きされている？
