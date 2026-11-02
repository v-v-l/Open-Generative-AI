import test from "node:test";
import assert from "node:assert/strict";
import { runtime } from "../src/runtime.js";
import { buildJob, referenceInputs } from "../src/api.js";
import { modelFromDescriptor, installCatalog } from "../src/catalog.js";
import { noraReferenceError } from "../src/referenceValidation.js";
import { avatar } from "./avatarFixture.js";
const image = "a".repeat(32), url = "/media/" + image;
function setup() { runtime.descriptors=[avatar]; runtime.extraAssets={}; }
test("Avatar is image+script only, never text-only or first/last/audio/video", () => {
  setup(); const mapped=modelFromDescriptor(avatar,"i2v");
  assert.equal(mapped.inputs.prompt.title,"Текст речи");
  assert.equal(mapped.imageOptional,false); assert.equal(mapped.maxImages,1);
  assert.equal(mapped.imageField,"images_list");
  for (const key of ["lastImageField","videoField","audioField"]) assert.equal(mapped[key],undefined);
  for (const key of ["seed","duration","generate_audio","generated_audio"]) assert.equal(mapped.inputs[key],undefined);
  assert.equal(mapped.inputs.voice_id.required,true); assert.equal(mapped.inputs.voice_id.title,"Голос HeyGen · Voice ID");
  assert.equal(mapped.inputs.remove_background.type,"boolean");
  assert.match(noraReferenceError(avatar.id,{}),/image/);
  assert.equal(noraReferenceError(avatar.id,{imageUrls:[url]}),"");
  const registry={t2iModels:[],i2iModels:[],t2vModels:[],i2vModels:[],v2vModels:[]};
  installCatalog(registry,[avatar]); assert.equal(registry.t2vModels.length,0); assert.equal(registry.i2vModels.length,1);
});
test("Avatar requires voice, preserves literal script and typed settings, omits empty optional fields", () => {
  setup(); const base={model:avatar.id,prompt:"  Exact speech\n",...referenceInputs(avatar.id,{imageUrls:[url]})};
  assert.throws(()=>buildJob(base),/Voice ID/);
  assert.throws(()=>buildJob({...base,voice_id:"  "}),/Voice ID/);
  const job=buildJob({...base,voice_id:"test-voice",motion_prompt:"",remove_background:false});
  assert.equal(job.prompt,base.prompt); assert.equal(job.voice_id,"test-voice"); assert.equal(job.remove_background,false);
  assert.equal(job.motion_prompt,undefined); assert.equal(job.duration,undefined); assert.equal(job.fit,"contain");
  assert.deepEqual(job.assets,[{id:image,role:"image"}]);
});
test("descriptor nested settings preserve object/array schema and values without stringification", () => {
  const nested={...avatar,settings:{options:{type:"object",title:"Options",properties:{speed:{type:"number",minimum:0.5,maximum:1.5},enabled:{type:"boolean"},tags:{type:"array",items:{type:"string"}}}}}};
  const schema=modelFromDescriptor(nested,"i2v").inputs.options;
  assert.equal(schema.type,"object"); assert.equal(schema.properties.speed.minimum,0.5); assert.equal(schema.properties.tags.items.type,"string");
  runtime.descriptors=[nested]; const value={speed:1.2,enabled:false,tags:["a"]};
  assert.deepEqual(buildJob({model:nested.id,prompt:"x",options:value}).options,value);
});
