# Linux GPU / vLLM

このコースではLinux + NVIDIA GPUを対象に、同じFastAPIアプリからvLLMに接続します。
**vLLMのGPU実行を検証していません。** 以下は公式のサーバー起動形式に合わせた手順です。
GPUの世代、VRAM、CUDAと量子化カーネルの対応は対象マシンで確認してください。

## 1. vLLMを別環境へ導入

FastAPI用の`.venv`にvLLMやPyTorchを混在させず、別の環境を用意します。
対象GPUに合うインストール方法を[vLLM公式](https://docs.vllm.ai/en/latest/getting_started/installation/)
で確認してください。一般的なpip導入例：

```bash
uv venv --python 3.12 .runtime/vllm-venv
uv pip install --python .runtime/vllm-venv/bin/python vllm
source .runtime/vllm-venv/bin/activate
vllm --version
```

対応バージョンはGPU実機で確認後に固定します。現時点ではこのプロジェクトの検証済みバージョンとして
扱いません。GGUFはllama.cpp向けで、vLLMでは対応するHugging Faceチェックポイントを使います。

## 2. サーバーを起動

```bash
bash scripts/serve_vllm.sh
```

標準では`google/gemma-4-12B-it-qat-w4a16-ct`を使用します。
初回はモデルのダウンロードが発生します。
この形式は[GoogleがvLLM向けに公開する量子化形式](https://huggingface.co/google/gemma-4-12B-it-qat-w4a16-ct)です。

設定例：

```bash
CONTEXT_SIZE=8192 GPU_MEMORY_UTILIZATION=0.85 MAX_NUM_SEQS=1 \
  bash scripts/serve_vllm.sh
```

別のチェックポイントは`HF_MODEL`で指定します。モデルのリビジョンを固定する場合は
`bash scripts/serve_vllm.sh --revision <確認したコミットSHA>`と指定します。
`--generation-config vllm`でモデルリポジトリの生成設定による暗黙の上書きを避けています。

## 3. アプリを接続

別ターミナルで、プロジェクトルートから：

```bash
GEMMA_BACKEND=vllm GEMMA_BASE_URL=http://127.0.0.1:8080/v1 \
  bash scripts/serve_app.sh
```

モデルの公開名は両エンジンとも`gemma4`です。アプリとサーバーを同じLinuxマシンで動かすのが
最初の構成です。リモートGPUを使う場合は、SSHポートフォワード等でローカルに接続します。

## 発展：同時リクエストx

このWebアプリは1件ずつの実験用で、同時生成はHTTP 429になります。
vLLMのバッチ処理を測定する場合は、まずアプリを経由せずvLLMのAPIに対して専用の負荷試験を行い、
その後アプリ側の同時実行制御を設計し直してください。

llama.cppとvLLMでは量子化形式・カーネル・チャットテンプレートなどが異なるため、
同じseedでも出力の完全一致は前提にしません。
