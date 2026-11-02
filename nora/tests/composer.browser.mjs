// Real native forms, isolated mock API only. Start tests/mock-server.mjs after build.
import assert from "node:assert/strict";
export async function verifyComposer(page, base = "http://127.0.0.1:36445") {
  const errors = [];
  page.on("dialog", async (dialog) => { errors.push(dialog.message()); await dialog.dismiss(); });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base);
  const submit = async (prompt) => {
    await page.locator("textarea:visible").fill(prompt);
    await Promise.all([
      page.waitForResponse((response) => response.url() === base + "/api/jobs" && response.request().method() === "POST"),
      page.getByRole("button", {name:"В очередь",exact:true}).filter({visible:true}).click(),
    ]);
    const captured = await (await page.request.get(base + "/__captured")).json();
    return captured.at(-1);
  };
  let job = await submit("Fixture local text-only");
  assert.equal(job.model,"qwen-local"); assert.deepEqual(job.assets,[]); assert.equal(job.seed,null);
  await page.getByRole("button",{name:/Qwen test fixture/}).click();
  await page.locator(".nora-composer-body:visible").getByText("OpenAI test fixture",{exact:true}).click();
  job = await submit("Fixture cloud text-only");
  assert.equal(job.model,"openai:gpt-image-test"); assert.deepEqual(job.assets,[]);
  await page.getByRole("button",{name:"Video Studio",exact:true}).click();
  // A real clipboard Files payload bubbles from the prompt; text pastes are untouched.
  const paste = async () => {
    await page.locator("textarea:visible").evaluate((node) => {
      const bytes = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aDhUAAAAASUVORK5CYII="), c=>c.charCodeAt(0));
      const data = new DataTransfer(); data.items.add(new File([bytes],"clipboard.png",{type:"image/png"}));
      node.dispatchEvent(new ClipboardEvent("paste",{clipboardData:data,bubbles:true,cancelable:true}));
    });
    await page.getByRole("img",{name:"Image1",exact:true}).waitFor();
    await page.getByText("Прикреплено референсов: 1",{exact:true}).filter({visible:true}).waitFor();
  };
  await paste();
  await page.getByRole("button",{name:"Свернуть промпт · Видео",exact:true}).click();
  await page.getByRole("button",{name:"Развернуть промпт · Видео",exact:true}).click();
  await page.getByRole("button",{name:"Удалить Image1",exact:true}).waitFor();
  job=await submit("Fixture H3 photo reference");
  assert.equal(job.model,"h3-simplepod"); assert.equal(job.assets.length,1); assert.equal(job.assets[0].role,"image");
  await page.getByRole("button",{name:/H3 test fixture/}).click();
  await page.getByTitle("OpenRouter", {exact:true}).click();
  await page.getByText("Veo Lite test fixture",{exact:true}).click();
  await page.locator('.nora-studio-page:not([hidden]) input[data-role="start"]').setInputFiles({name:"start.png",mimeType:"image/png",buffer:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aDhUAAAAASUVORK5CYII=","base64")});
  await page.getByRole("img",{name:"Start",exact:true}).waitFor();
  job=await submit("Fixture Veo photo reference");
  assert.match(job.model,/veo/); assert.equal(job.assets.length,1); assert.equal(job.assets[0].role,"start");
  assert.deepEqual(errors,[]);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
  return {checks:5, paidInference:false};
}
if (process.argv[1] === new URL(import.meta.url).pathname) {
  const { createRequire } = await import("node:module"); const require=createRequire(import.meta.url);
  const {chromium}=require("playwright");
  const browser=await chromium.launch({headless:true,...(process.env.NORA_TEST_CHROMIUM ? {executablePath:process.env.NORA_TEST_CHROMIUM}:{})});
  try {console.log(await verifyComposer(await browser.newPage()));} finally {await browser.close();}
}
