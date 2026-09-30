const $ = (id) => document.getElementById(id);
const history = [];
const runs = [];
let controller = null;
let attachment = null;
let imageLoading = false;
let imageSelection = 0;
let lastRequest = null;
let server = { backend: "llama.cpp", model: "gemma4" };

function notice(text, error = false) {
  $("notice").textContent = text;
  $("notice").classList.toggle("error", error);
}

async function checkConnection() {
  try {
    const response = await fetch("/api/health", { signal: AbortSignal.timeout(5000) });
    const data = await response.json();
    server = data;
    $("model-name").textContent = data.model;
    $("backend-name").textContent = data.backend;
    $("connection").classList.toggle("ready", data.ready);
    $("connection").querySelector("span").textContent = data.ready ? `${data.backend} · 接続済み` : "未接続 · 再確認 ↻";
    if (!data.ready && !controller) notice(`${data.message} 起動後、右上で再確認できます。`);
    else if (!controller) notice("");
  } catch {
    $("connection").classList.remove("ready");
    $("connection").querySelector("span").textContent = "接続を再確認 ↻";
    if (!controller) notice("アプリに接続できません。起動状態を確認してください。", true);
  }
}

function settings() {
  return {
    system_prompt: $("system-prompt").value,
    temperature: Number($("temperature").value),
    top_p: Number($("top-p").value),
    max_tokens: Number($("max-tokens").value),
    seed: Number($("seed").value),
  };
}

function busy(value) {
  $("send").disabled = value || imageLoading;
  $("attach-image").disabled = value;
  $("image-file").disabled = value;
  $("remove-image").disabled = value;
  $("stop").hidden = !value;
  $("clear").disabled = value;
  $("retry").disabled = value || !lastRequest;
  $("export").disabled = value || !runs.length;
  $("prompt").disabled = value;
  for (const input of $("settings-form").querySelectorAll("input,textarea")) input.disabled = value;
  for (const button of document.querySelectorAll("[data-prompt]")) button.disabled = value;
}

function addMessage(role, text, images = []) {
  $("welcome").hidden = true;
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "YOU" : "GEMMA";
  const body = document.createElement("p");
  body.className = "message-body";
  body.textContent = text;
  const state = document.createElement("div");
  state.className = "message-state";
  article.append(label, body);
  for (const source of images) {
    const image = document.createElement("img");
    image.src = source;
    image.alt = "送信した画像";
    image.className = "message-image";
    article.append(image);
  }
  article.append(state);
  $("conversation").append(article);
  article.scrollIntoView({ block: "nearest" });
  return { body, state };
}

function showMetrics(metrics) {
  $("first-time").textContent = metrics?.first_content_ms == null ? "—" : `${(metrics.first_content_ms / 1000).toFixed(2)} s`;
  $("total-time").textContent = metrics?.total_ms == null ? "—" : `${(metrics.total_ms / 1000).toFixed(2)} s`;
  $("token-count").textContent = metrics?.usage?.completion_tokens ?? "—";
}

async function* readEvents(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (data) yield JSON.parse(data);
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function generate(request, replay = false) {
  if (controller) return;
  lastRequest = structuredClone(request);
  // Retry restores the original context, so the failed/previous answer is not fed back.
  history.splice(0, history.length, ...structuredClone(request.messages.slice(0, -1)));
  const userMessage = request.messages.at(-1);
  addMessage("user", userMessage.content + (replay ? "\n［再実行］" : ""), userMessage.images);
  const view = addMessage("assistant", "");
  const run = { created_at: new Date().toISOString(), backend: server.backend, model: server.model, request: structuredClone(request), output: "", status: "running", metrics: null };
  runs.push(run);
  controller = new AbortController();
  busy(true);
  showMetrics(null);
  notice("生成中…");
  try {
    const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal: controller.signal });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : "入力を確認してください。会話長または生成設定が上限を超えています。");
    }
    let completed = false;
    for await (const event of readEvents(response.body)) {
      if (event.type === "error") throw new Error(event.message);
      if (event.type === "delta") {
        run.output += event.text;
        view.body.textContent = run.output;
        const area = $("conversation");
        if (area.scrollHeight - area.scrollTop - area.clientHeight < 160) area.scrollTop = area.scrollHeight;
      }
      if (event.type === "done") {
        completed = true;
        run.metrics = event.metrics;
        showMetrics(event.metrics);
      }
    }
    if (!completed) throw new Error("回答の受信が中断されました。再実行してください。");
    if (!run.output.trim()) throw new Error("回答本文がありません。生成上限を増やして再実行してください。");
    run.status = "completed";
    history.push(userMessage, { role: "assistant", content: run.output });
    if (run.metrics.finish_reason === "length") {
      view.state.textContent = "生成上限に達しました";
      notice("生成上限に達しました。Max tokensを増やして再実行できます。");
    } else notice("生成が完了しました。");
  } catch (error) {
    run.status = error.name === "AbortError" ? "stopped" : "error";
    run.error = error.name === "AbortError" ? "生成を停止しました。" : error.message;
    view.state.textContent = run.status === "stopped" ? "停止済み · この回答は次の会話に含まれません" : "エラー · この回答は次の会話に含まれません";
    notice(run.error, run.status === "error");
  } finally {
    controller = null;
    busy(false);
    $("prompt").focus();
  }
}

$("temperature").addEventListener("input", () => { $("temperature-value").value = Number($("temperature").value).toFixed(1); });
$("settings-form").addEventListener("submit", (event) => event.preventDefault());
$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (controller || imageLoading || !$("settings-form").reportValidity()) return;
  const content = $("prompt").value.trim();
  if (!content) return;
  const images = attachment ? [attachment] : [];
  if (images.length + history.reduce((count, message) => count + (message.images?.length || 0), 0) > 4) {
    notice("画像は会話全体で4枚までです。新しい会話を始めてください。", true);
    return;
  }
  $("prompt").value = "";
  clearAttachment();
  generate({ ...settings(), messages: [...history, { role: "user", content, images }] });
});
$("prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.isComposing) {
    event.preventDefault();
    $("chat-form").requestSubmit();
  }
});
$("stop").addEventListener("click", () => controller?.abort());
$("retry").addEventListener("click", () => {
  if (lastRequest && $("settings-form").reportValidity()) generate({ ...lastRequest, ...settings() }, true);
});
$("clear").addEventListener("click", () => {
  clearAttachment();
  history.length = 0;
  lastRequest = null;
  for (const message of document.querySelectorAll(".message")) message.remove();
  $("welcome").hidden = false;
  showMetrics(null);
  notice("新しい会話を始めました。過去の実行結果はJSON保存に含まれます。");
  busy(false);
});
$("export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ schema_version: 1, runs }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `gemma-runs-${new Date().toISOString().replaceAll(":", "-")}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => { $("prompt").value = button.dataset.prompt.replaceAll("\\n", "\n"); $("prompt").focus(); });
}
$("connection").addEventListener("click", checkConnection);
checkConnection();

function clearAttachment() {
  imageSelection += 1;
  imageLoading = false;
  attachment = null;
  $("image-file").value = "";
  $("preview-image").removeAttribute("src");
  $("image-preview").hidden = true;
  $("image-name").textContent = "";
  busy(Boolean(controller));
}

$("attach-image").addEventListener("click", () => $("image-file").click());
$("remove-image").addEventListener("click", clearAttachment);
$("image-file").addEventListener("change", async () => {
  const file = $("image-file").files[0];
  if (!file) return;
  clearAttachment();
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024 || !file.size) {
    notice("5MB以下のPNG・JPEG・WebP画像を選択してください。", true);
    return;
  }
  const selection = imageSelection;
  imageLoading = true;
  busy(false);
  try {
    const source = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("画像を読み込めませんでした。"));
      reader.readAsDataURL(file);
    });
    const probe = new Image();
    probe.src = source;
    await probe.decode();
    if (selection !== imageSelection) return;
    attachment = source;
    $("preview-image").src = source;
    $("image-name").textContent = file.name;
    $("image-preview").hidden = false;
    notice("画像を添付しました。質問を入力して送信してください。");
  } catch {
    if (selection === imageSelection) notice("画像を読み込めません。別の画像を選択してください。", true);
  } finally {
    if (selection === imageSelection) {
      imageLoading = false;
      busy(Boolean(controller));
    }
  }
});
