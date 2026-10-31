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
const files=[...new Set(inputProps.motion_segments.map(segment=>segment.file))];
if(files.length < 5) throw new Error('Expected five distinct H3 action clips');
for(const file of files) if(!fs.existsSync(path.join(root,file))) throw new Error(`Missing H3 action: ${file}`);
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
  for(let i=0;i<inputProps.motion_segments.length;i++){
    const action=inputProps.motion_segments[i];
    const frame=action.from_frame+Math.min(36,Math.floor((action.end_frame-action.from_frame)/2));
    await renderStill({serveUrl,composition,inputProps,frame,output:path.join(root,'review',`action_${String(i).padStart(2,'0')}_${action.id}.png`),imageFormat:'png'});
    if(i){
      for(const delta of [-1,0]) await renderStill({serveUrl,composition,inputProps,frame:action.from_frame+delta,
        output:path.join(root,'review',`cut_${String(i).padStart(2,'0')}_${delta<0?'before':'after'}.png`),imageFormat:'png'});
    }
    console.log(`ACTION ${i} ${action.id}`);
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
    h3_sha256:Object.fromEntries(files.map(file=>[file,createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')])),
    duration_frames:composition.durationInFrames,completed_at:new Date().toISOString(),
  },null,2));
}
console.log(`DONE ${mode} ${composition.durationInFrames/24}s`);
