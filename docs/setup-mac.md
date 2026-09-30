# Mac / llama.cpp

Apple SiliconのGPUをMetal経由で使用します。Pythonアプリへ推論エンジンを埋め込まず、
別プロセスのHTTPサーバーとして動かすことで、アプリの再起動時にモデルの再ロードが不要になります。

## 1. アプリ環境

```bash
uv sync --frozen
cp .env.example .env
```

すでに`.env`を編集済みならコピーを省略してください。

## 2. 固定バージョンを取得

```bash
uv run python scripts/setup_llamacpp.py
```

- llama.cpp: `b11146`（公式`v0.5.0`が参照するビルド）
- モデル: `google/gemma-4-12B-it-qat-q4_0-gguf`
- リビジョン: `29d097773436b69ff9feafd636ab4cf873786537`
- ファイル: `gemma-4-12b-it-qat-q4_0.gguf`

画像処理用の `mmproj-gemma-4-12b-it-qat-q4_0.gguf` も同じリビジョンから取得します。
mmprojは約175MBで、SHA256と取得元を `models/mmproj-manifest.json` に記録します。
既存環境でもセットアップを再実行し、推論サーバーとアプリを再起動してください。
モデルは公式メタデータのSHA256で照合し、結果を`models/manifest.json`に記録します。
途中でダウンロードが失敗した場合は、同じコマンドを再実行してください。
未完成の`.part`は先頭から再ダウンロードし、検証済みのモデルは再利用します。

## 3. 推論サーバーとアプリを起動

それぞれ別のターミナルで実行します。

```bash
bash scripts/serve_llamacpp.sh
```

```bash
bash scripts/serve_app.sh
```

ブラウザ: http://127.0.0.1:8000

アプリの接続確認は`/v1/models`の一覧に`gemma4`が存在することを調べます。
llama.cpp起動スクリプトの`--alias gemma4`と、アプリの`GEMMA_MODEL=gemma4`を一致させます。

## 4. 推論設定を変える

サーバーを停止してから再起動します。

```bash
CONTEXT_SIZE=16384 GPU_LAYERS=99 bash scripts/serve_llamacpp.sh
```

- `CONTEXT_SIZE`：入力と生成に使うコンテキスト。初期値8192。
- `GPU_LAYERS`：GPUに配置するレイヤー数。初期値99で全層のオフロードを要求。
- `MODEL_PATH`：別のGGUFを使う場合のパス。
- `MMPROJ_PATH`：そのモデルに対応するmmprojのパス。別モデルへ変更するときは両方を指定します。
- `LLAMA_SERVER_BIN`：自分でビルドしたllama-serverのパス。
- `INFERENCE_PORT`：推論APIのポート。初期値8080。

画像入力では `--batch-size 2048 --ubatch-size 2048 --image-max-tokens 1024`
を指定します。画像を一度に処理できるバッチを確保し、画像トークン数を制限するためです。
既定のubatch=512では、大きな画像で推論サーバーが異常終了する場合があります。
画像トークン上限を増やす場合は、ubatch・batch・コンテキスト長とメモリ使用量も
合わせて検証してください。上限を抑えると、細かい文字などの認識に影響する場合があります。

追加のllama.cpp引数はスクリプト末尾に渡せます。対応オプションは使用するバイナリの`--help`で確認します。
CPUと比較するときは `GPU_LAYERS=0 bash scripts/serve_llamacpp.sh --no-mmproj-offload` を使います。

初期設定は`--reasoning off`で、短い対話を試しやすくしています。推論モードの比較は
`bash scripts/serve_llamacpp.sh --reasoning on`で行えます。
推論部分は`reasoning_content`に分離し、アプリは回答本文だけを表示・履歴へ保存します。

## トラブルシューティング

| 状況 | 確認すること |
|---|---|
| 接続できない | 推論サーバーのロード完了、8080番ポート、`.env`の接続先 |
| 画像送信後に接続できなくなった | 推論ログの異常終了を確認。`n_ubatch >= n_tokens` のエラーなら、最新の起動スクリプトで再起動 |
| モデルが不一致 | `--alias`と`GEMMA_MODEL`の一致 |
| メモリ不足・極端に遅い | 他アプリの使用量、コンテキスト長、モデルのサイズ |
| 400エラー | 推論ログ。入力＋生成上限がコンテキストを超えていないか |
| 回答本文が空 | 生成上限を増やす。推論のみで上限を使い切っていないか |
| 長い回答が途中で終了 | `finish_reason=length`ならMax tokensを増やして再実行 |

会話の文字数による入力検証は、モデル固有のトークン上限を保証しません。
アプリは会話を黙って切り捨てないため、長くなった場合は「新しい会話」でリセットします。
