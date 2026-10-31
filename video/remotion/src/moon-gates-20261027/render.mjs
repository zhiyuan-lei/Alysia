import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';
const root=path.resolve(process.argv[2]);
const mode=process.argv[3]||'review';
const inputProps=JSON.parse(fs.readFileSync(path.join(root,'timeline.json'),'utf8'));
const serveUrl=await bundle({entryPoint:path.join(path.dirname(fileURLToPath(import.meta.url)),'index.jsx'),publicDir:root});
const composition=await selectComposition({serveUrl,id:'MoonGates',inputProps});
if(mode==='review'){
  fs.mkdirSync(path.join(root,'review'),{recursive:true});
  for(const scene of inputProps.scenes){
    const local=Math.floor(scene.duration_frames*.65);
    await renderStill({serveUrl,composition,inputProps,frame:scene.start_frame+local,output:path.join(root,'review',`scene_${scene.id}.png`),imageFormat:'png',scale:.5});
    console.log(`REVIEW ${scene.id}`);
  }
}else{
  let last=-1;
  await renderMedia({serveUrl,composition,inputProps,codec:'h264',audioCodec:'aac',crf:19,pixelFormat:'yuv420p',concurrency:4,outputLocation:path.join(root,mode==='preview'?'preview.mp4':'moon_gates.mp4'),frameRange:mode==='preview'?[0,inputProps.scenes[2].start_frame-1]:undefined,onProgress:({progress})=>{const p=Math.floor(progress*20)*5;if(p!==last){last=p;console.log(`RENDER ${p}%`);}}});
}
console.log(`DONE ${mode}: ${composition.durationInFrames/30}s`);

