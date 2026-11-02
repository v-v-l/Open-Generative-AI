// Real-browser regression with isolated reference API fixtures; never starts generation.
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

export async function verifyReferenceSets(page) {
  const web = {};
  for (const name of ['app.js', 'app.css', 'index.html'])
    web[name] = await readFile(new URL('../references/web/' + name, import.meta.url), 'utf8');
const records=Array.from({length:8},(_,i)=>({id:'B'+i,category:'body',status:i?'user_supplied':'candidate',title:'Body '+i}));
records.push({id:'H0',category:'face',collection:'head360',status:'candidate',title:'Head'},{id:'O0',category:'outfit',status:'accepted',title:'Look'},{id:'V0',category:'lora',status:'user_supplied',media_kind:'video',title:'Clip'});
const catalog={records,supports_zip:true,collections:[{id:'body-set',title:'Фигура · хвост',category:'body',curated:true,slots:records.slice(0,8).map((r,i)=>({id:'a'+i,title:i*45+'°',angle_degrees:i*45,reference_id:r.id}))},{id:'head-set',title:'Голова · каре',category:'face',slots:[{id:'a0',title:'0°',reference_id:'H0'},{id:'a45',title:'45°',reference_id:null}]},{id:'look-set',title:'Платье',category:'outfit',slots:[{id:'front',title:'Спереди',reference_id:'O0'}]},{id:'archive-set',title:'Старый набор',category:'face',archived:true,slots:[]},{id:'lora-set',title:'LoRA фото и видео',category:'lora',slots:[],items:['V0','H0']}]};
const captured=[],checks=[];function check(v,label){if(!v)throw Error(label);checks.push(label);}
await page.route('http://nora-reference-sets.test/**',async r=>{
const p=new URL(r.request().url()).pathname;
if(p.endsWith('/catalog'))return r.fulfill({json:catalog});
if(p.endsWith('/export')||p.endsWith('/zip')){captured.push({path:p,body:r.request().postDataJSON()});return r.fulfill({contentType:p.endsWith('zip')?'application/zip':'image/png',body:'fixture'});}
const name=p.endsWith('/')?'index.html':p.split('/').pop();if(web[name])return r.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:web[name]});
return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="96"><rect width="64" height="96" fill="#aaa"/></svg>'});
});
await page.goto('http://nora-reference-sets.test/references/');
await page.getByRole('link',{name:/Фигура · хвост/}).waitFor();
check(await page.locator('#set-cards .set-card').count()===4,'active set landing');
check(await page.locator('#cards').isHidden(),'individual cards hidden at entry');
check(!(await page.locator('#sheet-builder').evaluate(e=>e.open)),'custom builder collapsed');
await page.getByRole('checkbox',{name:'Показать архив'}).check();
check(await page.getByRole('link',{name:/Старый набор/}).isVisible(),'explicit archive access');
await page.getByRole('checkbox',{name:'Показать архив'}).uncheck();
await page.getByRole('link',{name:/Фигура · хвост/}).click();
await page.getByRole('heading',{name:'Фигура · хвост',exact:true}).waitFor();
check(await page.locator('#cards .card').count()===8,'eight angle cards include candidate');
await page.getByRole('button',{name:'Выбрать все оригиналы',exact:true}).click();
check(await page.locator('#selection li').count()===8,'select all');
await page.getByRole('button',{name:/Конструктор листа/}).click();
check(await page.locator('#sheet-builder').evaluate(e=>e.open),'builder opens');
await page.getByRole('button',{name:'Скачать лист · 4 × 2',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('передан'));
check(captured[0].body.columns===4&&captured[0].body.ids.join(',')==='B0,B1,B2,B3,B4,B5,B6,B7','PNG exact set ordered 4 columns');
await page.getByRole('link',{name:'← Все наборы',exact:true}).click();
await page.getByRole('link',{name:/Голова · каре/}).click();
await page.getByRole('heading',{name:'Голова · каре',exact:true,level:2}).waitFor();
check(await page.locator('#cards .empty-slot').count()===1,'empty upload angle');
await page.getByRole('button',{name:'Скачать оригиналы · ZIP',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('передан'));
check(captured[1].body.ids.join(',')==='H0','ZIP excludes previous set selection');
await page.goBack();check(await page.locator('#set-cards').isVisible(),'browser back landing');
await page.goForward();check(await page.getByRole('heading',{name:'Голова · каре',exact:true,level:2}).isVisible(),'browser forward detail');
await page.setViewportSize({width:390,height:844});
check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile detail fits');
await page.getByRole('link',{name:'← Все наборы',exact:true}).click();
check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile landing fits');
return {checks,captured};

}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  // Use the project's Playwright installation or NODE_PATH pointing to the CLI's package directory.
  const require = createRequire(import.meta.url);
  const { chromium } = require('playwright');
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    console.log(JSON.stringify(await verifyReferenceSets(page), null, 2));
  } finally { await browser.close(); }
}

