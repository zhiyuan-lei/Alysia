import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';

const root=path.resolve(process.argv[2]);
const mode=process.argv[3]||'review';
const sourceDir=path.dirname(fileURLToPath(import.meta.url));
const serveUrl=await bundle({entryPoint:path.join(sourceDir,'index.jsx'),publicDir:root});
const composition=await selectComposition({serveUrl,id:'LiaCinematicTest'});
if(mode==='review'){
  for(const sec of [1.2,3.8,6.4,9.4,12.8,18.5,22.7,26.7]){
    await renderStill({serveUrl,composition,frame:Math.round(sec*24),output:path.join(root,'review',`frame_${String(Math.round(sec*10)).padStart(3,'0')}.png`),imageFormat:'png',scale:.5});
    console.log(`REVIEW ${sec}s`);
  }
}else{
  let last=-1;
  await renderMedia({serveUrl,composition,codec:'h264',audioCodec:'aac',crf:18,pixelFormat:'yuv420p',concurrency:3,outputLocation:path.join(root,'lia_scene_test.mp4'),onProgress:({progress})=>{const n=Math.floor(progress*10)*10;if(n!==last){last=n;console.log(`RENDER ${n}%`);}}});
  const sha256=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
  fs.writeFileSync(path.join(root,'render_receipt.json'),JSON.stringify({status:'render_complete',seconds:28,fps:24,frames:672,renderer_sha256:sha256(path.join(sourceDir,'index.jsx')),audio_sha256:sha256(path.join(root,'audio/soundtrack.wav')),film_sha256:sha256(path.join(root,'lia_scene_test.mp4')),completed_at:new Date().toISOString()},null,2));
}
console.log(`DONE ${mode}`);
