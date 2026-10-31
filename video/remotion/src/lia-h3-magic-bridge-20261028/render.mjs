import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';

const root=path.resolve(process.argv[2]);
const mode=process.argv[3]||'review';
const folder=path.dirname(fileURLToPath(import.meta.url));
const source=fs.readFileSync(path.join(root,'timeline.json'),'utf8');
const inputProps=JSON.parse(source);
const serveUrl=await bundle({entryPoint:path.join(folder,'index.jsx'),publicDir:root});
const composition=await selectComposition({serveUrl,id:'LiaH3Bridge',inputProps});
fs.mkdirSync(path.join(root,'review'),{recursive:true});
if(mode==='review'){
  for(const scene of inputProps.scenes){
    const moment=['failure','proof'].includes(scene.id)?.96:.7;
    const frame=scene.start_frame+Math.floor(scene.duration_frames*moment);
    await renderStill({serveUrl,composition,inputProps,frame,output:path.join(root,'review',`${scene.id}.png`),imageFormat:'png'});
    console.log(`REVIEW ${scene.id}`);
  }
}else{
  let last=-1;
  await renderMedia({serveUrl,composition,inputProps,codec:'h264',audioCodec:'aac',crf:19,pixelFormat:'yuv420p',concurrency:2,
    outputLocation:path.join(root,'rendered.mp4'),onProgress:({progress})=>{
      const n=Math.floor(progress*20)*5;if(n!==last){last=n;console.log(`RENDER ${n}%`);}
    }});
  fs.writeFileSync(path.join(root,'render_receipt.json'),JSON.stringify({
    timeline_sha256:createHash('sha256').update(source).digest('hex'),
    renderer_sha256:createHash('sha256').update(fs.readFileSync(path.join(folder,'index.jsx'))).digest('hex'),
    h3_sha256:createHash('sha256').update(fs.readFileSync(path.join(root,inputProps.h3_file))).digest('hex'),
    duration_frames:composition.durationInFrames,completed_at:new Date().toISOString(),
  },null,2));
}
console.log(`DONE ${mode} ${composition.durationInFrames/24}s`);
