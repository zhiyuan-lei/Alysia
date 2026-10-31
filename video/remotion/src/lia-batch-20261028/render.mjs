import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';

const root=path.resolve(process.argv[2]);
const mode=process.argv[3]||'review';
const inputSource=fs.readFileSync(path.join(root,'timeline.json'),'utf8');
const inputProps=JSON.parse(inputSource);
const serveUrl=await bundle({entryPoint:path.join(path.dirname(fileURLToPath(import.meta.url)),'index.jsx'),publicDir:root});
const composition=await selectComposition({serveUrl,id:mode==='cover'?'LiaCover':'LiaStory',inputProps});
if(mode==='cover'){
  await renderStill({serveUrl,composition,inputProps,frame:0,output:path.join(root,'cover_4x3.png'),imageFormat:'png'});
}else if(mode==='review'){
  for(const s of inputProps.scenes){
    await renderStill({serveUrl,composition,inputProps,frame:s.start_frame+Math.floor(s.duration_frames*.55),output:path.join(root,'review',`scene_${s.id}.png`),imageFormat:'png',scale:.5});
    console.log(`REVIEW ${s.id}`);
  }
}else{
  let last=-1;
  await renderMedia({serveUrl,composition,inputProps,codec:'h264',audioCodec:'aac',crf:19,pixelFormat:'yuv420p',concurrency:3,outputLocation:path.join(root,'film.mp4'),onProgress:({progress})=>{const p=Math.floor(progress*20)*5;if(p!==last){last=p;console.log(`RENDER ${p}%`);}}});
}
if(mode==='final')fs.writeFileSync(path.join(root,'render_receipt.json'),JSON.stringify({timeline_sha256:createHash('sha256').update(inputSource).digest('hex'),renderer_sha256:createHash('sha256').update(fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)),'index.jsx'))).digest('hex'),duration_frames:composition.durationInFrames,completed_at:new Date().toISOString()},null,2));
console.log(`DONE ${mode} ${composition.durationInFrames/30}s`);
