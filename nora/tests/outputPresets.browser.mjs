// Native studio integration against the isolated fixture only; no inference.
import assert from 'node:assert/strict';
import { avatar } from './avatarFixture.js';
export async function verifyOutputPresets(page, base='http://127.0.0.1:36445') {
 const errors=[]; page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/state',async route=>{
  const response=await route.fetch(),state=await response.json();
  const veo=state.capabilities.models.find(model=>model.id==='openrouter:veo-lite-test');
  veo.settings.resolution.values.push('4K');veo.output_constraints=[{when:{resolution:'4K'},allowed:{duration:[8]}}];
  state.capabilities.models.push(avatar);await route.fulfill({response,json:state});
 });
 await page.goto(base);
 const studio=()=>page.locator('.nora-studio-page:not([hidden])');
 const controls=()=>studio().getByRole('region',{name:'Формат, разрешение и длительность'});
 const enqueue=async()=>{
  const promise=page.waitForRequest(request=>request.url()===base+'/api/jobs'&&request.method()==='POST');
  await studio().getByRole('button',{name:'В очередь',exact:true}).click();return (await promise).postDataJSON();
 };
 await studio().getByRole('textbox').fill('Preset payload verification');
 assert.match(await controls().getByLabel('Формат',{exact:true}).inputValue(),/11:15/);
 assert.equal(await controls().getByLabel('Разрешение',{exact:true}).inputValue(),'704×960');
 await controls().getByLabel('Формат',{exact:true}).selectOption('3:4');await controls().getByLabel('Разрешение',{exact:true}).selectOption('1024');
 let payload=await enqueue();assert.equal(payload.width,768);assert.equal(payload.height,1024);
 await controls().getByLabel('Формат',{exact:true}).selectOption('16:9');payload=await enqueue();assert.equal(payload.width,1024);assert.equal(payload.height,576);
 // Switch through the native model picker, preserving its real caller state.
 await studio().getByRole('button',{name:/Qwen test fixture/}).click();await page.getByTitle('OpenAI direct',{exact:true}).click();
 await page.getByText('OpenAI test fixture', {exact:true}).click();
 await controls().getByLabel('Формат',{exact:true}).selectOption('2:3');await controls().getByLabel('Качество',{exact:true}).selectOption('low');
 payload=await enqueue();assert.equal(payload.size,'1024x1536');assert.equal(payload.quality,'low');assert.equal(payload.resolution,undefined);
 await page.getByRole('button',{name:'Video Studio',exact:true}).click();
 await studio().getByRole('textbox').fill('Native H3 preset payload');
 await controls().getByLabel('Формат',{exact:true}).selectOption('9:16');await controls().getByLabel('Разрешение',{exact:true}).selectOption('1024');
 await controls().getByLabel('Длительность',{exact:true}).selectOption('192');payload=await enqueue();
 assert.equal(payload.width,576);assert.equal(payload.height,1024);assert.equal(payload.frames,192);assert.equal(payload.duration,undefined);
 await studio().getByRole('button',{name:/H3 test fixture/}).click();await page.getByTitle('OpenRouter',{exact:true}).click();await page.getByText('Veo Lite test fixture',{exact:true}).click();
 await controls().getByLabel('Длительность',{exact:true}).selectOption('4');await controls().getByLabel('Разрешение',{exact:true}).selectOption('4K');
 assert.equal(await controls().getByLabel('Длительность',{exact:true}).inputValue(),'8');
 assert.deepEqual(await controls().getByLabel('Длительность',{exact:true}).locator('option').allTextContents(),['8 с']);
 await studio().getByRole('textbox').fill('Veo 4K payload');payload=await enqueue();assert.equal(payload.resolution,'4K');assert.equal(payload.duration,8);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await studio().getByRole('button',{name:/Veo Lite test fixture/}).click();await page.getByTitle('OpenRouter',{exact:true}).click();await page.getByText(avatar.label,{exact:true}).click();
 assert.equal(await controls().getByLabel('Длительность',{exact:true}).count(),0);
 assert.equal(await controls().getByLabel('Разрешение',{exact:true}).count(),1);
 await page.screenshot({path:'/tmp/nora-output-presets-mobile.png'});
 assert.deepEqual(errors,[]);return {checks:12,viewports:['1440x1000','390x844'],paidInference:false};
}
if(process.argv[1]===new URL(import.meta.url).pathname){
 const {createRequire}=await import('node:module'),require=createRequire(import.meta.url),{chromium}=require('playwright');
 const browser=await chromium.launch({headless:true,...(process.env.NORA_TEST_CHROMIUM?{executablePath:process.env.NORA_TEST_CHROMIUM}:{})});
 try{console.log(await verifyOutputPresets(await browser.newPage({viewport:{width:1440,height:1000}})));}finally{await browser.close();}
}
