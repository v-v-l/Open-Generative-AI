import test from "node:test";
import assert from "node:assert/strict";
import { runtime } from "../src/runtime.js";
import { noraReferenceError, pastedImages, pasteImageRole } from "../src/referenceValidation.js";
import { modelFromDescriptor } from "../src/catalog.js";
import { buildJob, referenceInputs } from "../src/api.js";
const photo = {id:"qwen-local", label:"Qwen", kind:"photo", provider:"local", roles:{image:3}};
const h3 = {id:"h3-simplepod", label:"H3", kind:"video", provider:"simplepod", roles:{start:1,end:1,image:9,video:3,audio:3}};
const url = "/media/" + "a".repeat(32);
test("text-only photo and video stay optional in every selected mode", () => {
  runtime.descriptors = [photo,h3]; runtime.extraAssets = {};
  for (const mode of ["t2i","i2i"]) assert.equal(modelFromDescriptor(photo,mode).imageOptional,true);
  for (const model of [photo,h3]) {
    assert.equal(noraReferenceError(model.id,{}),"");
    assert.deepEqual(buildJob({model:model.id,prompt:"literal",...referenceInputs(model.id,{})}).assets,[]);
  }
  const mapped = modelFromDescriptor(h3,"t2v");
  assert.equal(mapped.imageField,"image_url");
  assert.equal(mapped.videoField,"videos_list");
});
test("H3 additional photo alone counts; required role minima remain distinct", () => {
  runtime.descriptors=[h3]; runtime.extraAssets={[h3.id]:[{id:"a".repeat(32),url,role:"image"}]};
  assert.equal(noraReferenceError(h3.id,{}),"");
  assert.deepEqual(buildJob({model:h3.id,prompt:"move"}).assets,[{id:"a".repeat(32),role:"image"}]);
  runtime.descriptors=[{...h3,required_roles:{start:1}}];
  assert.match(noraReferenceError(h3.id,{}),/start/);
  runtime.descriptors=[h3]; runtime.extraAssets={};
  assert.equal(noraReferenceError(h3.id,{endImageUrl:url}), "");
  runtime.descriptors=[{...h3,provider:"openrouter"}];
  assert.match(noraReferenceError(h3.id,{endImageUrl:url}),/первый кадр/);
});
test("clipboard keeps image files only and never duplicates files/items", () => {
  const image={type:"image/png"}, text={type:"text/plain"};
  assert.deepEqual(pastedImages({files:[image,text],items:[{kind:"file",type:"image/png",getAsFile:()=>image}]}),[image]);
  assert.deepEqual(pastedImages({items:[{kind:"file",type:"image/png",getAsFile:()=>image}]}),[image]);
  assert.deepEqual(pastedImages({files:[text]}),[]);
});
test("clipboard defaults to H3 image reference, Veo Start, respects explicit role", () => {
  assert.equal(pasteImageRole(h3,{}),"image");
  const veo={roles:{start:1,end:1}};
  assert.equal(pasteImageRole(veo,{}),"start");
  assert.equal(pasteImageRole(veo,{start:[url]}),"end");
  assert.equal(pasteImageRole(h3,{},"start"),"start");
});
