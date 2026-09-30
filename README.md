# Gemma Local Playground

ローカル環境でGemma 4を動かし、推論設定と応答を比較する中級者向けハンズオン。
FastAPI製のWebアプリから、別プロセスの **llama.cpp / vLLM** に接続します。

- **[Colab版](https://colab.research.google.com/drive/1W8Vl-ilqCkLcAQDHuTso7mIQB4PnXdSk#scrollTo=KI2TiESdFcEk)**：ローカルの計算資源がない人のための実行環境。はじめての方はこちらをおすすめします。
- **このrepository**：推論サーバーの構築、量子化、生成設定、アプリへの組み込みまで学ぶローカル版。これらをベースに自分で改良していくベースラインの位置づけ。

Colabへの接続やクラウドAPIは不要です。初回のパッケージ・モデル取得にはネット接続が必要です。

```text
Browser :8000 (もし8000ポートを使っている場合は別を利用すること)
  └─ FastAPI（画面配信 / 入力検証 / SSE中継）
       └─ OpenAI互換 HTTP API :8080
            ├─ llama.cpp + Metal（Macの基本コース）
            └─ vLLM + CUDA（Linux GPUの発展コース）
```

## できること

- 日本語チャットと回答の逐次表示、生成停止
- system prompt / temperature / top_p / max_tokens / seedの変更
- 最初の回答本文までの時間、総応答時間、サーバーが返す生成トークン数の表示
- 同じ入力を新しい設定で再実行、実行履歴をJSONでダウンロード
- 接続確認、モデル名不一致の検出、サーバー未起動時の案内
- サンプル入力を使った逐次比較スクリプト

会話はタブのメモリに保持します。再読み込みで消えるため、残したい結果はJSON保存してください。
停止・失敗した回答は次の会話へ渡しません。モデル出力はプレーンテキストで表示します。
RAG、ツール実行は現時点で対応していません。そのあたりをご自身で追加してみると次のステップとしてよいかもしれません。

## Macで始める

必要なもの：Apple Silicon Mac、Python 3.11以上、[uv](https://docs.astral.sh/uv/)。
12B Q4_0を使用します。メモリ48GBの開発機を対象とし、モデル・ランタイム・作業用に
ディスクの空きを少なくとも12GB確保してください。使用可能なメモリは他のアプリにも依存します。

他のLinux, Mac環境でも動作するとは思いますが動作保証はできないので、各自の環境にあわせてご確認ください。
Windowsは動作対象外です。WSLで実行できると思いますが、ご自身でご対応をお願いします。

プロジェクトのルートで実行：

```bash
uv sync --frozen
cp .env.example .env
uv run python scripts/setup_llamacpp.py
```

セットアップは公式配布元から固定バージョンを取得します。ランタイムは`.runtime/`、モデルは
`models/`に置き、システム全体にはインストールしません。モデル本体と画像処理用のmmproj（約175MB）はSHA256で検証します。

すでにセットアップ済みの場合も、上の `setup_llamacpp.py` を再実行してください。
検証済みのモデル本体は再利用し、不足しているmmprojを取得します。
その後、起動中の推論サーバーとアプリを停止して、以下のコマンドで再起動します。

ターミナル1で推論サーバー：

```bash
bash scripts/serve_llamacpp.sh
```

ターミナル2でアプリ：

```bash
bash scripts/serve_app.sh
```

上記２つを並行して実行する必要があります。

**http://127.0.0.1:8000** を開きます。モデルのロードが終わってから、右上の接続ボタンで再確認してください。
API仕様は http://127.0.0.1:8000/docs です。停止はそれぞれのターミナルで `Ctrl+C`。

詳しくは [Macのセットアップ](docs/setup-mac.md)、[Linux GPU / vLLM](docs/setup-linux-gpu.md) を参照してください。
実モデルでの確認内容と未確認範囲は [動作確認記録](docs/verification.md) にまとめています。

## 実験の進め方

1. 初期設定で同じ質問を試し、回答と時間を保存する。
2. Temperatureを変えて「再実行」。元の入力・会話文脈を使って再生成する。
3. モデル、量子化、コンテキスト長を変更するときは推論サーバーを再起動する。
4. 同じ入力群で比較し、速度だけでなく回答の正確さと読みやすさも確認する。

```bash
uv run python benchmarks/compare.py --temperatures 0.2 1.0 --output results/comparison.json
```

比較には推論サーバーとアプリの両方が必要です。別々のターミナルで
`bash scripts/serve_llamacpp.sh` と `bash scripts/serve_app.sh` を起動したまま、
3つ目のターミナルで実行してください。接続先は標準でアプリの
`http://127.0.0.1:8000` です。変更した場合は `--url` で指定します。

測定値の意味や比較時の注意は [実験ガイド](docs/experiments.md) に記載しています。

## 設定

アプリの設定は `.env` または環境変数で指定します。環境変数が優先されます。

| 設定 | 初期値 | 用途 |
|---|---|---|
| `GEMMA_BASE_URL` | `http://127.0.0.1:8080/v1` | 推論APIの接続先 |
| `GEMMA_MODEL` | `gemma4` | サーバーの公開モデル名 |
| `GEMMA_BACKEND` | `llama.cpp` | `llama.cpp` / `vllm` の表示・記録 |
| `GEMMA_API_KEY` | 空 | 接続先が認証を要求する場合のみ |
| `GEMMA_TIMEOUT_SECONDS` | `180` | 推論HTTP読み取りの無通信タイムアウト |

`GEMMA_BACKEND`はサーバーを起動・切り替える機能ではありません。
別エンジンを起動し、接続先・公開モデル名を合わせてアプリを再起動します。
推論用シェルスクリプトは`.env`を読みません。設定は起動コマンドの環境変数で渡します。

## 開発

```bash
uv sync --frozen --dev
uv run pytest -q
uv run ruff check src tests scripts benchmarks
uv run ruff format --check src tests scripts benchmarks
node --test tests/test_image_ui.cjs
bash scripts/serve_app.sh --reload
```

Python依存は`uv.lock`で固定します。モデルとllama.cppの固定値は
`scripts/setup_llamacpp.py`を参照してください。vLLMは独立した環境で管理します。

```text
src/gemma_demo/       FastAPI、推論クライアント、画面
scripts/             ダウンロード・起動
examples/            入力サンプル
benchmarks/          比較スクリプト
tests/               ストリーム・障害・入力検証のテスト
docs/                環境別手順と実験ガイド
```

アプリは学習用の単一ユーザー・単一ワーカー構成です。1件の生成中は別の生成をHTTP 429で拒否します。
`--workers`で複数プロセスにすると制限はプロセスごとになるため、この教材では増やさないでください。
両サーバーは標準で`127.0.0.1`にバインドします。

## 参照

- [Gemma 4公式GGUF](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [vLLM](https://docs.vllm.ai/en/latest/)
- [FastAPI](https://fastapi.tiangolo.com/)

---

# Gemma Local Playground — English

An intermediate hands-on project for running Gemma 4 locally and comparing inference settings and responses.
The FastAPI web app connects to **llama.cpp / vLLM** running in a separate process.

- **[Colab version](https://colab.research.google.com/drive/1W8Vl-ilqCkLcAQDHuTso7mIQB4PnXdSk#scrollTo=KI2TiESdFcEk)**: An environment for users without local computing resources. Recommended for beginners.
- **This repository**: A local version covering inference server setup, quantization, generation settings, and application integration. Use it as a baseline for your own improvements.

No connection to Colab or cloud API is required. Internet access is needed for the initial package and model downloads.

```text
Browser :8000 (use a different port if 8000 is already in use)
  └─ FastAPI (web UI / input validation / SSE relay)
       └─ OpenAI-compatible HTTP API :8080
            ├─ llama.cpp + Metal (basic Mac track)
            └─ vLLM + CUDA (advanced Linux GPU track)
```

## Features

- Japanese chat, streaming responses, and generation cancellation
- Adjustable system prompt / temperature / top_p / max_tokens / seed
- Display of time to first response text, total response time, and generated token counts reported by the server
- Rerun the same input with new settings and download run history as JSON
- Connection checks, model name mismatch detection, and guidance when the server is not running
- A script for sequential comparisons using sample inputs

Conversations are stored in the current tab's memory and disappear on reload. Save any results you want to keep as JSON.
Stopped or failed responses are not included in subsequent conversation context. Model output is displayed as plain text.
RAG and tool execution are not currently supported. Adding them yourself could be a useful next step.

## Getting started on Mac

Requirements: an Apple Silicon Mac, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/).
This project uses 12B Q4_0 and targets a development machine with 48GB of memory.
Allow at least 12GB of free disk space for the model, runtime, and working files. Available memory also depends on other running apps.

Other Linux and Mac environments may work, but compatibility is not guaranteed. Check and adapt the setup for your own environment.
Windows is not a supported target. WSL may work, but you will need to handle that setup yourself.

Run from the project root:

```bash
uv sync --frozen
cp .env.example .env
uv run python scripts/setup_llamacpp.py
```

The setup script downloads pinned versions from official sources. The runtime is stored in `.runtime/` and models in `models/`, without a system-wide installation.
The model and the image-processing mmproj file (approximately 175MB) are verified using SHA256.

Even if you have already completed setup, rerun `setup_llamacpp.py` above.
It reuses the verified model and downloads the mmproj file if it is missing.
Then stop the running inference server and app, and restart them with the following commands.

In terminal 1, start the inference server:

```bash
bash scripts/serve_llamacpp.sh
```

In terminal 2, start the app:

```bash
bash scripts/serve_app.sh
```

Both processes must run at the same time.

Open **http://127.0.0.1:8000**. After the model has finished loading, click the connection button in the upper-right corner to check again.
The API documentation is at http://127.0.0.1:8000/docs. Press `Ctrl+C` in each terminal to stop its process.

See [Mac setup](docs/setup-mac.md) and [Linux GPU / vLLM](docs/setup-linux-gpu.md) for details.
The [verification record](docs/verification.md) describes checks performed with the real model and areas not yet verified.

## Running experiments

1. Try the same question with the default settings and save the response and timings.
2. Change Temperature and click “再実行” (Rerun) to regenerate using the original input and conversation context.
3. Restart the inference server when changing the model, quantization, or context length.
4. Compare the same set of inputs, evaluating response accuracy and readability as well as speed.

```bash
uv run python benchmarks/compare.py --temperatures 0.2 1.0 --output results/comparison.json
```

The comparison requires both the inference server and the app. Keep `bash scripts/serve_llamacpp.sh` and `bash scripts/serve_app.sh` running in separate terminals, then run the comparison in a third terminal.
The default target is the app at `http://127.0.0.1:8000`. If you change it, specify the app URL with `--url`.

See the [experiment guide](docs/experiments.md) for metric definitions and considerations when comparing results.

## Configuration

Configure the app using `.env` or environment variables. Environment variables take precedence.

| Setting | Default | Purpose |
|---|---|---|
| `GEMMA_BASE_URL` | `http://127.0.0.1:8080/v1` | Inference API endpoint |
| `GEMMA_MODEL` | `gemma4` | Model name exposed by the server |
| `GEMMA_BACKEND` | `llama.cpp` | Backend label recorded and displayed: `llama.cpp` / `vllm` |
| `GEMMA_API_KEY` | Empty | Only needed if the endpoint requires authentication |
| `GEMMA_TIMEOUT_SECONDS` | `180` | Inference HTTP read timeout during periods with no incoming data |

`GEMMA_BACKEND` does not start or switch servers.
To use a different engine, start it separately, match the endpoint and exposed model name, and restart the app.
The inference shell scripts do not read `.env`. Pass their settings as environment variables when running the startup command.

## Development

```bash
uv sync --frozen --dev
uv run pytest -q
uv run ruff check src tests scripts benchmarks
uv run ruff format --check src tests scripts benchmarks
node --test tests/test_image_ui.cjs
bash scripts/serve_app.sh --reload
```

Python dependencies are pinned in `uv.lock`. See `scripts/setup_llamacpp.py` for the pinned model and llama.cpp versions.
vLLM is managed in a separate environment.

```text
src/gemma_demo/       FastAPI, inference client, and web UI
scripts/             Download and startup scripts
examples/            Sample inputs
benchmarks/          Comparison scripts
tests/               Streaming, failure handling, and input validation tests
docs/                Environment-specific instructions and experiment guides
```

This is an educational app designed for a single user and a single worker. While one generation is running, another generation request is rejected with HTTP 429.
With multiple processes started using `--workers`, the limit applies separately to each process, so do not increase the worker count for this tutorial.
Both servers bind to `127.0.0.1` by default.

## References

- [Official Gemma 4 GGUF](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [vLLM](https://docs.vllm.ai/en/latest/)
- [FastAPI](https://fastapi.tiangolo.com/)
