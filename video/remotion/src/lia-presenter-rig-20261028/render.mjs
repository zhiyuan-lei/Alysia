import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';

const root=path.resolve(process.argv[2]);
const mode=process.argv[3]||'review';
const here=path.dirname(fileURLToPath(import.meta.url));
const inputProps=JSON.parse(fs.readFileSync(path.join(root,'demo.json'),'utf8'));
const serveUrl=await bundle({entryPoint:path.join(here,'index.jsx'),publicDir:root});
const ids=mode==='review'?['LiaComparison','LiaPuzzleDemo']:mode==='comparison'?['LiaComparison']:['LiaPuzzleDemo'];
const receipts=[];
for(const id of ids){
  const composition=await selectComposition({serveUrl,id,inputProps});
  if(mode==='review'){
    const peakFrame=inputProps.mouth_open.indexOf(Math.max(...inputProps.mouth_open));
    for(const frame of [...new Set([35,78,80,83,140,235,390,423,565,peakFrame])]){
      await renderStill({serveUrl,composition,inputProps,frame,output:path.join(root,'review',`${id}_${frame}.png`),imageFormat:'png',scale:.65});
      console.log(`REVIEW ${id} ${frame}`);
    }
  }else{
    let last=-1;
    const output=path.join(root,id==='LiaComparison'?'lia_character_comparison.mp4':'lia_puzzle_demo.mp4');
    await renderMedia({serveUrl,composition,inputProps,codec:'h264',audioCodec:'aac',crf:18,pixelFormat:'yuv420p',concurrency:3,outputLocation:output,onProgress:({progress})=>{const n=Math.floor(progress*10)*10;if(n!==last){last=n;console.log(`RENDER ${id} ${n}%`);}}});
    const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
    receipts.push({composition:id,output,sha256:sha(output),puppet_sha256:sha(path.join(here,'LiaPuppet.jsx')),scene_sha256:sha(path.join(here,'index.jsx')),data_sha256:sha(path.join(root,'demo.json')),head_sha256:sha(path.join(root,'assets/head.png')),torso_sha256:sha(path.join(root,'assets/torso.png')),frames:composition.durationInFrames,seconds:composition.durationInFrames/composition.fps});
  }
}
if(receipts.length)fs.writeFileSync(path.join(root,`render_receipt_${mode}.json`),JSON.stringify(receipts,null,2));
console.log(`DONE ${mode}`);
