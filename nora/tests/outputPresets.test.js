import test from 'node:test';
import assert from 'node:assert/strict';
import { FORMATS, NATIVE_TIERS, nativeDimensions, ratioFor, framePresets, compatiblePatch, allowedValues, outputConflict, sizeFormat } from '../src/outputPresets.js';
import { runtime } from '../src/runtime.js';
import { buildJob } from '../src/api.js';
const native = {id:'qwen-local',provider:'local',kind:'photo',roles:{image:3},settings:{},dimension_step:32,dimension_min:256,dimension_max:1536};
const h3 = {...native,id:'h3-simplepod',provider:'simplepod',kind:'video',fps:24,frame_step:17,frame_offset:5,frames_min:107,frames_max:362};
const veo = {id:'openrouter:veo-test',provider:'openrouter',kind:'video',roles:{},settings:{resolution:{values:['720p','1080p','4K'],default:'720p'},duration:{values:[4,6,8],default:8},aspect_ratio:{values:['16:9','9:16'],default:'16:9'}},output_constraints:[{when:{resolution:'4K'},allowed:{duration:[8]}}]};
test('native formats use exact aspect, supported dimensions and bounded tiers',()=>{
 for(const format of FORMATS) for(const tier of NATIVE_TIERS){ const dims=nativeDimensions(native,format,tier);assert.equal(ratioFor(dims.width,dims.height),format);for(const dimension of Object.values(dims)){assert.equal(dimension%32,0);assert.ok(dimension>=256&&dimension<=1536);}}
 assert.deepEqual(nativeDimensions(native,'3:4',1024),{width:768,height:1024});
 assert.deepEqual(nativeDimensions(native,'16:9',1024),{width:1024,height:576});
 assert.ok(!NATIVE_TIERS.includes(2048));
});
test('H3 duration choices encode valid actual frame counts',()=>{
 runtime.descriptors=[h3];
 for(const {value:frames,label} of framePresets(h3)){
  assert.equal((frames-5)%17,0);assert.ok(frames>=107&&frames<=362);assert.ok(label.includes((frames/24).toFixed(2)));
  const payload=buildJob({model:h3.id,prompt:'move',...nativeDimensions(h3,'9:16',1024),frames});assert.equal(payload.frames,frames);assert.equal(payload.duration,undefined);
 }
});
test('Veo quality change reconciles duration, limits choices and preserves literal provider enums',()=>{
 const values={resolution:'720p',duration:4,aspect_ratio:'9:16'}, result=compatiblePatch(veo,values,{resolution:'4K'});
 assert.deepEqual(result.patch,{resolution:'4K',duration:8});assert.equal(result.adjusted.length,1);
 assert.deepEqual(allowedValues(veo,{...values,...result.patch},'duration'),[8]);
 assert.equal(outputConflict(veo,{...values,resolution:'4K'}).includes('длительность'),true);
 runtime.descriptors=[veo];const payload=buildJob({model:veo.id,prompt:'move',...values,...result.patch});assert.equal(payload.resolution,'4K');assert.equal(payload.duration,8);assert.equal(payload.aspect_ratio,'9:16');
});
test('OpenAI formats reflect literal available sizes and independent generation quality',()=>{
 const model={id:'openai:gpt-image-test',provider:'openai',kind:'photo',roles:{},settings:{size:{values:['auto','1024x1024','1024x1536'],default:'auto'},quality:{values:['low','high'],default:'high'}}};
 assert.deepEqual(model.settings.size.values.map(sizeFormat),['auto','1:1','2:3']);runtime.descriptors=[model];
 const payload=buildJob({model:model.id,prompt:'image',size:'1024x1536',quality:'low'});assert.equal(payload.size,'1024x1536');assert.equal(payload.quality,'low');assert.equal(payload.resolution,undefined);
});
test('custom native dimensions and frame counts are not silently normalized by submission',()=>{
 runtime.descriptors=[h3];const payload=buildJob({model:h3.id,prompt:'custom',width:704,height:960,frames:158});assert.equal(payload.width,704);assert.equal(payload.height,960);assert.equal(payload.frames,158);
});
