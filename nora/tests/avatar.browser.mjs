// Native studio form against the isolated mock server; no provider calls.
import assert from "node:assert/strict";
import { avatar } from "./avatarFixture.js";
export async function verifyAvatar(page, base="http://127.0.0.1:36445") {
  const errors=[]; page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/api/state", async route=>{
    const response=await route.fetch(), state=await response.json();
    state.capabilities.models.push(avatar); await route.fulfill({response,json:state});
  });
  await page.goto(base); await page.getByRole("button",{name:"Video Studio",exact:true}).click();
  await page.getByRole("button",{name:/H3 test fixture/}).click();
  await page.getByTitle("OpenRouter",{exact:true}).click();
  await page.getByText(avatar.label,{exact:true}).click();
  const studio=page.locator('.nora-studio-page:not([hidden])');
  await studio.getByRole("textbox",{name:"Текст речи",exact:true}).fill("Exact speech for avatar");
  assert.equal(await studio.locator('input[data-role="image"]').count(),1);
  for(const role of ["start","end","audio","video"]) assert.equal(await studio.locator(`input[data-role="${role}"]`).count(),0);
  await studio.getByText(avatar.input_note,{exact:true}).waitFor(); await studio.getByText(avatar.pricing_note,{exact:true}).waitFor();
  const bytes=Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aDhUAAAAASUVORK5CYII=","base64");
  await studio.locator('input[data-role="image"]').setInputFiles({name:"face.png",mimeType:"image/png",buffer:bytes});
  await studio.getByRole("img",{name:"Image1",exact:true}).waitFor();
  await studio.getByRole("button",{name:/Параметры модели/}).click();
  const dialog=page.getByRole("dialog",{name:"Параметры модели"});
  await dialog.getByLabel("Голос HeyGen · Voice ID",{exact:true}).fill("fixture-voice");
  await dialog.getByLabel("Движения персонажа",{exact:true}).fill("gentle nod");
  await dialog.getByRole("button",{name:"Применить",exact:true}).click();
  const submitted=page.waitForRequest(r=>r.url()===base+"/api/jobs" && r.method()==="POST");
  await studio.getByRole("button",{name:"В очередь",exact:true}).click();
  const payload=(await submitted).postDataJSON();
  assert.equal(payload.model,avatar.id); assert.equal(payload.prompt,"Exact speech for avatar");
  assert.equal(payload.voice_id,"fixture-voice"); assert.equal(payload.motion_prompt,"gentle nod");
  assert.equal(payload.remove_background,false); assert.equal(payload.assets.length,1); assert.equal(payload.assets[0].role,"image");
  for(const key of ["duration","generate_audio","generated_audio","frames"]) assert.equal(payload[key],undefined);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await studio.getByRole("button",{name:/Параметры модели/}).click();
  await dialog.getByLabel("Голос HeyGen · Voice ID",{exact:true}).waitFor();
  const bounds=await dialog.boundingBox(); assert.ok(bounds.width<=390 && bounds.height<=844);
  await dialog.getByRole("button",{name:"Отменить",exact:true}).click();
  assert.deepEqual(errors,[]); return {checks:10,paidInference:false};
}
if(process.argv[1]===new URL(import.meta.url).pathname){
  const {createRequire}=await import("node:module"),require=createRequire(import.meta.url),{chromium}=require("playwright");
  const browser=await chromium.launch({headless:true,...(process.env.NORA_TEST_CHROMIUM?{executablePath:process.env.NORA_TEST_CHROMIUM}:{})});
  try{console.log(await verifyAvatar(await browser.newPage({viewport:{width:1440,height:1000}})));}finally{await browser.close();}
}
