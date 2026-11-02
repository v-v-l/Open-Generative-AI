import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../references/web/app.js', import.meta.url), 'utf8').replace('void load();', '');
function library() {
  const elements = new Map(), requests = [];
  function element(tag = '') {
    return { tag, value: '', checked: false, hidden: false, children: [], options: [], dataset: {},
      style: { setProperty() {} }, classList: { toggle() {}, add() {}, remove() {} },
      append(...items) { this.children.push(...items); this.options.push(...items.filter(item => item.tag === 'option')); },
      replaceChildren(...items) { this.children = []; this.options = []; this.append(...items); },
      addEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {}, click() {}, remove() {}, scrollIntoView() {},
    };
  }
  const document = { body: element('body'), createElement: element, createTextNode: text => ({text}), querySelectorAll: () => [],
    querySelector(selector) { if (!elements.has(selector)) elements.set(selector, element()); return elements.get(selector); },
  };
  const context = vm.createContext({ document, console, URLSearchParams, URL: { createObjectURL: () => 'blob:fixture', revokeObjectURL() {} },
    setTimeout() {}, window: {addEventListener() {}}, location: {hash: '', assign() {}}, history: {pushState() {}},
    localStorage: {getItem: () => null, setItem() {}},
    Option: function(text, value) {return {...element('option'), textContent: text, value};},
    fetch: async (path, options) => { requests.push({path, body: JSON.parse(options.body)}); return {ok: true, headers: {get: () => path.endsWith('zip') ? 'application/zip' : 'image/png'}, blob: async () => ({})}; },
  });
  vm.runInContext(source, context);
  const run = code => vm.runInContext(code, context);
  const records = Array.from({length: 8}, (_, index) => ({id: 'B' + index, category: 'body', status: index ? 'user_supplied' : 'candidate'}));
  records.push({id: 'H0', category: 'face', collection: 'head360', status: 'candidate'}, {id: 'V0', category: 'lora', media_kind: 'video'});
  const collections = [
    {id: 'body', title: 'Body', category: 'body', curated: true, slots: records.slice(0, 8).map((item, index) => ({id: 'a' + index, title: String(index * 45), reference_id: item.id}))},
    {id: 'head', title: 'Head', category: 'face', slots: [{id: 'front', title: 'Front', reference_id: 'H0'}, {id: 'back', title: 'Back', reference_id: null}]},
    {id: 'legacy-head360', title: 'Legacy head', category: 'face', read_only: true, slots: []},
    {id: 'archive', title: 'Old', category: 'body', archived: true, slots: []},
    {id: 'lora', title: 'LoRA', category: 'lora', items: ['H0', 'V0']},
  ];
  run('catalog = ' + JSON.stringify({records, collections, supports_zip: true}));
  document.querySelector('#columns').value = '4';
  document.querySelector('#cell-width').value = '512';
  document.querySelector('#cell-height').value = '768';
  return {run, elements, requests};
}

test('entry lists active sets, honors curation and merges legacy head into the head filter', () => {
  const {run, elements} = library();
  assert.equal(run('tab'), 'all');
  assert.equal(run('visibleSets().length'), 4);
  assert.equal(run('visibleSets()[0].id'), 'body');
  run('tab = "face"');
  assert.equal(run('visibleSets().length'), 2);
  run('tab = "all"; $("#archived").checked = true');
  assert.equal(run('visibleSets().length'), 5);
  run('renderCards()');
  assert.equal(elements.get('#cards').hidden, true);
  assert.equal(elements.get('#set-cards').hidden, false);
});

test('explicit set shows candidate originals, preserves placeholders and owns URL state', () => {
  const {run, elements} = library();
  run('location.hash = "#set=head"; applyLocation()');
  assert.equal(run('visibleRecords().map(item => item.id).join(",")'), 'H0');
  assert.equal(elements.get('#cards').children.length, 2);
  assert.equal(elements.get('#set-title').textContent, 'Head');
  run('location.hash = ""; applyLocation()');
  assert.equal(elements.get('#set-cards').hidden, false);
});

test('whole-set PNG and ZIP use ordered membership independently of custom selection or search', async () => {
  const {run, requests} = library();
  run('$("#collection").value = "body"; selected = ["H0"]; $("#search").value = "no match"');
  await run('exportSet("png")');
  assert.deepEqual(requests[0].body, {ids: ['B0','B1','B2','B3','B4','B5','B6','B7'], columns: 4, cell_width: 512, cell_height: 768, labels: false});
  assert.equal(run('selected.join(",")'), 'H0');
  run('$("#collection").value = "head"');
  await run('exportSet("zip")');
  assert.deepEqual(requests[1].body, {ids: ['H0']});
});

test('mixed LoRA set excludes videos from PNG and includes them in original ZIP', async () => {
  const {run, requests} = library();
  run('$("#collection").value = "lora"');
  await run('exportSet("png")');
  await run('exportSet("zip")');
  assert.deepEqual(requests[0].body.ids, ['H0']);
  assert.deepEqual(requests[1].body.ids, ['H0', 'V0']);
});

test('failed set export preserves custom input and enables retry', async () => {
  const {run, elements} = library();
  run('$("#collection").value = "head"; selected = ["B0"]; response = async () => { throw Error("Offline"); }');
  await run('exportSet("png")');
  assert.equal(run('busy'), false);
  assert.equal(run('selected.join(",")'), 'B0');
  assert.match(elements.get('#library-status').textContent, /Offline/);
  assert.equal(elements.get('#export-set-sheet').disabled, false);
});

test('sets over the API export budget require explicit custom selection', async () => {
  const {run, requests, elements} = library();
  run('catalog.records = Array.from({length:17}, (_, i) => ({id:"L"+i,category:"lora"})); catalog.collections = [{id:"large",title:"Large",category:"lora",items:catalog.records.map(item=>item.id)}]; $("#collection").value = "large"; renderCards()');
  assert.equal(elements.get('#export-set-sheet').disabled, true);
  assert.equal(elements.get('#export-set-zip').disabled, true);
  await run('exportSet("zip")');
  assert.equal(requests.length, 0);
});
