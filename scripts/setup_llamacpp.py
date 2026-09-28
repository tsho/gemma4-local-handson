"""Download a pinned official macOS runtime and Gemma GGUF into this project."""

import argparse
import hashlib
import json
import platform
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLAMA_TAG = "b11146"
MODEL_REPO = "google/gemma-4-12B-it-qat-q4_0-gguf"
MODEL_REVISION = "29d097773436b69ff9feafd636ab4cf873786537"
MODEL_FILE = "gemma-4-12b-it-qat-q4_0.gguf"


def read_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, target, expected_hash=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and expected_hash and sha256(target) == expected_hash:
        print(f"Already verified: {target.name}", flush=True)
        return
    partial = target.with_suffix(target.suffix + ".part")
    print(f"Downloading {target.name}", flush=True)
    with (
        urllib.request.urlopen(url, timeout=120) as response,
        partial.open("wb") as output,
    ):
        total = 0
        reported = 0
        while chunk := response.read(8 * 1024 * 1024):
            output.write(chunk)
            total += len(chunk)
            if total - reported >= 512 * 1024 * 1024:
                print(f"  {total / 1024**3:.1f} GiB downloaded", flush=True)
                reported = total
    if expected_hash and sha256(partial) != expected_hash:
        raise RuntimeError(f"Checksum mismatch: {partial}")
    partial.replace(target)


def setup_runtime():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit(
            "This installer targets Apple Silicon. See docs/setup-linux-gpu.md."
        )
    destination = ROOT / ".runtime" / LLAMA_TAG
    marker = destination / "server-path.txt"
    if marker.exists() and (ROOT / marker.read_text().strip()).is_file():
        print(f"Runtime already installed: {LLAMA_TAG}", flush=True)
        return
    release = read_json(
        f"https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{LLAMA_TAG}"
    )
    candidates = [
        asset
        for asset in release["assets"]
        if "macos-arm64" in asset["name"]
        and asset["name"].endswith((".tar.gz", ".zip"))
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one macOS arm64 archive; found {len(candidates)}"
        )
    asset = candidates[0]
    digest = (asset.get("digest") or "").removeprefix("sha256:") or None
    archive = ROOT / ".runtime" / asset["name"]
    download(asset["browser_download_url"], archive, digest)
    destination.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                path = (destination / member.filename).resolve()
                if not path.is_relative_to(destination.resolve()):
                    raise RuntimeError("Invalid archive path")
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")
    servers = list(destination.rglob("llama-server"))
    if len(servers) != 1:
        raise RuntimeError(
            "Could not locate llama-server in the official archive"
        )
    server = servers[0]
    server.chmod(server.stat().st_mode | 0o111)
    marker.write_text(str(server.relative_to(ROOT)) + "\n")
    print(f"Runtime ready: {server.relative_to(ROOT)}", flush=True)


def setup_model():
    info = read_json(
        f"https://huggingface.co/api/models/{MODEL_REPO}/revision/{MODEL_REVISION}?blobs=true"
    )
    entry = next(
        item for item in info["siblings"] if item["rfilename"] == MODEL_FILE
    )
    digest = entry.get("lfs", {}).get("sha256")
    if not digest:
        raise RuntimeError("Model SHA256 is missing from official metadata")
    model = ROOT / "models" / MODEL_FILE
    required = entry.get("size", 9 * 1024**3)
    if not model.exists() and shutil.disk_usage(ROOT).free < required + 1024**3:
        raise RuntimeError("Insufficient free disk space for model download")
    download(
        f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{MODEL_FILE}",
        model,
        digest,
    )
    manifest = {
        "repo": MODEL_REPO,
        "revision": MODEL_REVISION,
        "file": MODEL_FILE,
        "sha256": digest,
        "llama_tag": LLAMA_TAG,
    }
    (model.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print("Model checksum verified.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-only", action="store_true")
    args = parser.parse_args()
    setup_runtime()
    if not args.runtime_only:
        setup_model()
