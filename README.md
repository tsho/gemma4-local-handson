# Gemma Local Playground

ローカル環境でGemma 4を動かし、推論設定と応答を比較する中級者向けハンズオン。
FastAPI製のWebアプリから、別プロセスの **llama.cpp / vLLM** に接続します。

- **[Colab版](https://colab.research.google.com/drive/1W8Vl-ilqCkLcAQDHuTso7mIQB4PnXdSk#scrollTo=KI2TiESdFcEk)**：ローカルの計算資源がない人のための実行環境。はじめての方はこちらをおすすめします。
- **このプロジェクト**：推論サーバーの構築、量子化、生成設定、アプリへの組み込みまで学ぶローカル版。これらをベースに自分で改良していくベースラインの位置づけ。

Colabへの接続やクラウドAPIは不要です。初回のパッケージ・モデル取得にはネット接続が必要です。
元のColab本文は未取り込みで、現時点のサンプルプロンプトはこのプロジェクト用に用意しています。

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
画像入力、RAG、ツール実行は今後の拡張範囲です。

## Macで始める

必要なもの：Apple Silicon Mac、Python 3.11以上、[uv](https://docs.astral.sh/uv/)。
12B Q4_0を使用します。メモリ48GBの開発機を対象とし、モデル・ランタイム・作業用に
ディスクの空きを少なくとも12GB確保してください。使用可能なメモリは他のアプリにも依存します。

プロジェクトのルートで実行：

```bash
uv sync --frozen
cp .env.example .env
uv run python scripts/setup_llamacpp.py
```

セットアップは公式配布元から固定バージョンを取得します。ランタイムは`.runtime/`、モデルは
`models/`に置き、システム全体にはインストールしません。モデルはSHA256で検証します。

ターミナル1で推論サーバー：

```bash
bash scripts/serve_llamacpp.sh
```

ターミナル2でアプリ：

```bash
bash scripts/serve_app.sh
```

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
