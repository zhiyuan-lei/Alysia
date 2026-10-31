import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderStill,selectComposition} from '@remotion/renderer';
const root=path.resolve(process.argv[2]);
const inputProps=JSON.parse(fs.readFileSync(path.join(root,'timeline.json'),'utf8'));
const serveUrl=await bundle({entryPoint:path.join(path.dirname(fileURLToPath(import.meta.url)),'index.jsx'),publicDir:root});
const composition=await selectComposition({serveUrl,id:'AfterHours',inputProps});
const items=[['workchat','这个也顺手','new_task'],['mother','菜放冰箱','cold_dinner'],['delete','发送','sent_boundary'],['shutdown','明天见','see_you_tomorrow'],['ending','赶上了','sunset_ending']];
for(const [kind,text,name] of items){
  const s=inputProps.scenes.find(s=>s.kind===kind);
  const c=s.cues.find(c=>c.text.includes(text));
  if(!c)throw Error(`Missing cue ${kind}: ${text}`);
  const frame=Math.min(s.start_frame+s.duration_frames-1,s.start_frame+c.start_frame+7);
  await renderStill({serveUrl,composition,inputProps,frame,output:path.join(root,'review',`${name}.png`),imageFormat:'png',scale:.75});
  console.log(`KEYFRAME ${name} ${frame/30}s`);
}
