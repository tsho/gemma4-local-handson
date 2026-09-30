// Test attachment state and request construction without browser automation.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: '', hidden: false, disabled: false, files: [], handlers: {},
      classList: { toggle() {}, remove() {} },
      addEventListener(name, callback) { this.handlers[name] = callback; },
      querySelector() { return element('status'); },
      querySelectorAll() { return []; },
      reportValidity() { return true; },
      append() {}, scrollIntoView() {}, focus() {}, click() {},
      removeAttribute(name) { delete this[name]; },
    });
    return elements.get(id);
  }
  const requests = [];
  const context = vm.createContext({
    document: { getElementById: element, createElement: () => element(Math.random()), querySelectorAll: () => [] },
    AbortController, AbortSignal, TextDecoder, structuredClone, console,
    FileReader: class {
      readAsDataURL(file) { this.result = file.source; this.onload(); }
    },
    Image: class { async decode() {} },
    fetch: async (url, options) => {
      if (url === '/api/health') return { json: async () => ({ready: true}) };
      requests.push(JSON.parse(options.body));
      return { ok: true, body: new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode(
          'data: {"type":"delta","text":"赤色"}\n\ndata: {"type":"done","metrics":{}}\n\n'
        ));
        controller.close();
      } }) };
    },
  });
  vm.runInContext(fs.readFileSync('src/gemma_demo/static/app.js', 'utf8'), context);
  return { element, requests };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('preview, delete, send, retry and subsequent image context', async () => {
  const {element, requests} = setup();
  const source = 'data:image/png;base64,aW1hZ2U=';
  async function attach() {
    element('image-file').files = [{type:'image/png',size:20,name:'test.png',source}];
    await element('image-file').handlers.change();
  }
  await attach();
  assert.equal(element('image-preview').hidden, false);
  assert.equal(element('preview-image').src, source);
  element('remove-image').handlers.click();
  assert.equal(element('image-preview').hidden, true);
  await attach();
  element('prompt').value = '何色？';
  element('chat-form').handlers.submit({preventDefault(){}});
  await settle();
  assert.equal(requests[0].messages[0].images[0], source);
  assert.equal(element('image-preview').hidden, true);
  element('retry').handlers.click();
  await settle();
  assert.deepEqual(requests[1].messages, requests[0].messages);
  element('prompt').value = '英語では？';
  element('chat-form').handlers.submit({preventDefault(){}});
  await settle();
  assert.equal(requests[2].messages[0].images[0], source);
  assert.equal(requests[2].messages.at(-1).content, '英語では？');
});

test('oversized and unsupported attachments cannot be sent', async () => {
  const {element, requests} = setup();
  for (const file of [{type:'image/png',size:6*1024*1024},{type:'image/svg+xml',size:20}]) {
    element('image-file').files = [file];
    await element('image-file').handlers.change();
    assert.equal(element('image-preview').hidden, true);
  }
  element('prompt').value = 'text only';
  element('chat-form').handlers.submit({preventDefault(){}});
  await settle();
  assert.deepEqual(requests[0].messages[0].images, []);
});
