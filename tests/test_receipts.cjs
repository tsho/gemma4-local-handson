const {test} = require('node:test');
const assert = require('node:assert/strict');
const core = import('../src/gemma_demo/static/receipts-core.mjs');

test('request includes exactly one image, purpose and transcription constraints', async () => {
  const {receiptRequest} = await core;
  const request = receiptRequest('data:image/png;base64,AA==', '事務用品');
  assert.deepEqual(request.messages[0].images, ['data:image/png;base64,AA==']);
  assert.match(request.messages[0].content, /事務用品/);
  assert.match(request.system_prompt, /預り金・お釣り/);
  assert.match(request.system_prompt, /不明/);
  assert.equal(request.temperature, 0);
});

test('parse structured results, preserve currency and generate editable text', async () => {
  const {parseReceipt, receiptText} = await core;
  const result = parseReceipt('```json\n{"store":"文具店","category":"消耗品費","amount":"1,280円","items":["ノート 2冊 800円","ペン 480円"]}\n```');
  assert.equal(result.items, 'ノート 2冊 800円\nペン 480円');
  result.amount = '1,200円';
  const output = receiptText(result);
  assert.match(output, /店名：文具店/);
  assert.match(output, /合計金額：1,200円/);
  assert.match(output, /勘定項目（候補）：消耗品費/);
});

test('reject malformed or partial results without silently inventing fields', async () => {
  const {parseReceipt} = await core;
  for (const raw of ['null', '{', '{"store":"A"}', '{"store":"A","category":"B","amount":500,"items":[]}', '{"store":"A","category":"B","amount":"500円","items":[{}]}']) {
    assert.throws(() => parseReceipt(raw));
  }
  const unknown = parseReceipt('{"store":"","category":"","amount":"","items":[]}');
  assert.deepEqual(unknown, {store:'不明', category:'不明', amount:'不明', items:'不明'});
});

test('SSE parser handles byte splits and CRLF boundaries', async () => {
  const {receiptEvents} = await core;
  const bytes = new TextEncoder().encode('data: {"type":"delta","text":"店名"}\r\n\r\ndata: {"type":"done"}\n\n');
  const body = new ReadableStream({start(controller) {
    for (let i = 0; i < bytes.length; i++) controller.enqueue(bytes.slice(i,i+1));
    controller.close();
  }});
  const events = [];
  for await (const event of receiptEvents(body)) events.push(event);
  assert.deepEqual(events, [{type:'delta',text:'店名'},{type:'done'}]);
});

async function ui(events) {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const elements = new Map();
  let request;
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value:'', hidden:false, disabled:false, textContent:'', handlers:{}, files:[],
      classList:{add(){},remove(){},toggle(){}},
      addEventListener(name, handler){this.handlers[name]=handler;},
      removeAttribute(name){delete this[name];}, click(){}, focus(){}, select(){},
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    ...await core,
    document:{getElementById:element,createElement:()=>element('link')},
    AbortController, AbortSignal, console,
    FileReader:class {readAsDataURL(file){this.result=file.source;this.onload();}},
    Image:class {async decode(){}},
    fetch: async (url, options) => {
      if (url === '/api/health') return {json:async()=>({ready:true})};
      request = JSON.parse(options.body);
      if (events === null) return new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => {
          const error = new Error('Stopped');
          error.name = 'AbortError';
          reject(error);
        });
      });
      return {ok:true,body:new ReadableStream({start(controller){
        for (const event of events) controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
        controller.close();
      }})};
    },
  });
  const script = fs.readFileSync('src/gemma_demo/static/receipts.js','utf8').replace(/^import .*\n/,'');
  vm.runInContext(script,context);
  element('file').files=[{type:'image/png',size:100,name:'receipt.png',source:'data:image/png;base64,AA=='}];
  await element('file').handlers.change();
  return {element,getRequest:()=>request};
}

test('UI extracts four fields, updates copied text after edits and clears stale results',async()=>{
  const raw=JSON.stringify({store:'みどり文具店',category:'消耗品費',amount:'500円',items:['ノート 400円','ペン 100円']});
  const {element,getRequest}=await ui([{type:'delta',text:raw},{type:'done',metrics:{finish_reason:'stop'}}]);
  assert.equal(element('preview').hidden,false);
  await element('extract').handlers.click();
  assert.equal(getRequest().messages[0].images.length,1);
  assert.equal(element('store').value,'みどり文具店');
  assert.equal(element('fields').disabled,false);
  assert.equal(element('copy').disabled,false);
  element('amount').value='550円';
  element('amount').handlers.input();
  assert.match(element('output').value,/550円/);
  element('clear').handlers.click();
  assert.equal(element('preview').hidden,true);
  assert.equal(element('output').value,'');
  assert.equal(element('copy').disabled,true);
  assert.equal(element('extract').disabled,true);
});

test('UI keeps failed or truncated output out of editable results and permits retry',async()=>{
  for (const events of [
    [{type:'error',message:'推論サーバーに接続できません。'}],
    [{type:'delta',text:'partial'}],
    [{type:'delta',text:'{}'},{type:'done',metrics:{finish_reason:'length'}}],
    [{type:'delta',text:'not JSON'},{type:'done',metrics:{finish_reason:'stop'}}],
  ]) {
    const {element}=await ui(events);
    await element('extract').handlers.click();
    assert.equal(element('output').value,'');
    assert.equal(element('copy').disabled,true);
    assert.equal(element('fields').disabled,true);
    assert.equal(element('extract').disabled,false);
    assert.equal(element('stop').hidden,true);
  }
});


test('stop cancels the request and restores controls without exporting partial data',async()=>{
  const {element}=await ui(null);
  const running=element('extract').handlers.click();
  assert.equal(element('stop').hidden,false);
  assert.equal(element('extract').disabled,true);
  element('stop').handlers.click();
  await running;
  assert.equal(element('stop').hidden,true);
  assert.equal(element('extract').disabled,false);
  assert.equal(element('output').value,'');
  assert.equal(element('copy').disabled,true);
  assert.match(element('status').textContent,/停止/);
});
