import { receiptRequest, parseReceipt, receiptText, receiptEvents } from "./receipts-core.mjs";

const $ = id => document.getElementById(id);
let image = null;
let controller = null;
let loading = false;
let selection = 0;
const fields = ["store", "category", "amount", "items"];

function status(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}
function controls() {
  const busy = Boolean(controller) || loading;
  for (const id of ["choose", "file", "purpose"]) $(id).disabled = busy;
  $("extract").disabled = busy || !image;
  $("clear").disabled = Boolean(controller) || (!image && !loading);
  $("stop").hidden = !controller;
  $("extract").textContent = controller ? "読み取り中…" : "レシートを読み取る →";
}
function resetResult() {
  for (const id of fields) $(id).value = "";
  $("output").value = "";
  $("fields").disabled = true;
  $("copy").disabled = true;
  $("save").disabled = true;
  $("raw").textContent = "";
  $("raw-panel").hidden = true;
  $("raw-panel").open = false;
}
function updateText() {
  $("output").value = receiptText(Object.fromEntries(fields.map(id => [id, $(id).value])));
  $("copy").disabled = false;
  $("save").disabled = false;
}
async function chooseFile(file) {
  if (!file || controller || loading) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || !file.size || file.size > 5 * 1024 * 1024) {
    status("5MB以下のPNG・JPEG・WebP画像を1枚選択してください。", true);
    return;
  }
  const current = ++selection;
  loading = true;
  controls();
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
    if (current !== selection) return;
    image = source;
    $("preview").src = source;
    $("preview").hidden = false;
    $("empty-image").hidden = true;
    $("filename").textContent = file.name;
    $("choose").textContent = "画像を変更";
    resetResult();
    $("result-state").textContent = "読み取り準備完了";
    status("画像を確認して「レシートを読み取る」を押してください。");
  } catch {
    if (current === selection) status("画像を開けません。別の画像を選択してください。", true);
  } finally {
    if (current === selection) { loading = false; controls(); }
    $("file").value = "";
  }
}

$("choose").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", () => chooseFile($("file").files[0]));
$("drop-area").addEventListener("dragover", event => { event.preventDefault(); if (!controller && !loading) $("drop-area").classList.add("dragging"); });
$("drop-area").addEventListener("dragleave", () => $("drop-area").classList.remove("dragging"));
$("drop-area").addEventListener("drop", event => {
  event.preventDefault();
  $("drop-area").classList.remove("dragging");
  if (event.dataTransfer.files.length !== 1) { status("画像は1枚ずつ選択してください。", true); return; }
  chooseFile(event.dataTransfer.files[0]);
});
$("clear").addEventListener("click", () => {
  if (controller) return;
  selection += 1;
  loading = false;
  image = null;
  $("file").value = "";
  $("preview").removeAttribute("src");
  $("preview").hidden = true;
  $("empty-image").hidden = false;
  $("filename").textContent = "PNG・JPEG・WebP ／ 1枚・5MBまで";
  $("choose").textContent = "画像を選択";
  $("purpose").value = "";
  $("result-state").textContent = "画像を選択してください";
  resetResult();
  status("新しいレシートを選択してください。");
  controls();
});
$("extract").addEventListener("click", async () => {
  if (!image || controller || loading) return;
  resetResult();
  controller = new AbortController();
  controls();
  $("result-state").textContent = "読み取り中";
  status("文字と明細を読み取っています…");
  let raw = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(receiptRequest(image, $("purpose").value)), signal: controller.signal,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : "入力画像を確認してください。");
    }
    let completed = false;
    for await (const event of receiptEvents(response.body)) {
      if (event.type === "error") throw new Error(event.message);
      if (event.type === "delta") raw += event.text;
      if (event.type === "done") {
        if (event.metrics?.finish_reason === "length") throw new Error("明細が長く、読み取りが途中で終了しました。レシートを分けて撮影してください。");
        completed = true;
      }
    }
    if (!completed) throw new Error("読み取りが中断されました。もう一度お試しください。");
    const result = parseReceipt(raw);
    for (const id of fields) $(id).value = result[id];
    $("fields").disabled = false;
    updateText();
    $("result-state").textContent = "読み取り完了・要確認";
    status("読み取りました。画像と照合して、必要な箇所を修正してください。");
  } catch (error) {
    $("result-state").textContent = error.name === "AbortError" ? "停止しました" : "読み取りできませんでした";
    status(error.name === "AbortError" ? "読み取りを停止しました。もう一度読み取れます。" : error instanceof SyntaxError ? "結果を整理できませんでした。モデルの出力を確認し、もう一度読み取ってください。" : error.message, error.name !== "AbortError");
  } finally {
    $("raw").textContent = raw;
    $("raw-panel").hidden = !raw;
    controller = null;
    controls();
  }
});
$("stop").addEventListener("click", () => controller?.abort());
for (const id of fields) $(id).addEventListener("input", updateText);
$("copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("output").value); status("テキストをコピーしました。"); }
  catch { $("output").focus(); $("output").select(); status("テキストを選択しました。⌘ / Ctrl + C でコピーしてください。"); }
});
$("save").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([$("output").value], {type:"text/plain;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = `receipt-${new Date().toISOString().slice(0,10)}.txt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
async function connection() {
  $("connection").disabled = true;
  try {
    const response = await fetch("/api/health", {signal: AbortSignal.timeout(5000)});
    const data = await response.json();
    $("connection").textContent = data.ready ? "● 接続済み" : "未接続 · 再確認";
    if (!data.ready && !controller) status(data.message, true);
  } catch {
    $("connection").textContent = "未接続 · 再確認";
    if (!controller) status("アプリに接続できません。起動状態を確認してください。", true);
  } finally { $("connection").disabled = false; }
}
$("connection").addEventListener("click", connection);
connection();
