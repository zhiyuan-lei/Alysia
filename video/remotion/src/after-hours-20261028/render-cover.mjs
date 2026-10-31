import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderStill,selectComposition} from '@remotion/renderer';
const root=path.resolve(process.argv[2]);
const serveUrl=await bundle({entryPoint:path.join(path.dirname(fileURLToPath(import.meta.url)),'cover.jsx'),publicDir:root});
const composition=await selectComposition({serveUrl,id:'AfterHoursCover'});
await renderStill({serveUrl,composition,frame:0,output:path.join(root,'cover_4x3.png'),imageFormat:'png'});
const wide=await selectComposition({serveUrl,id:'AfterHoursCoverWide'});
await renderStill({serveUrl,composition:wide,frame:0,output:path.join(root,'cover_16x9_preview.png'),imageFormat:'png'});
console.log('COVER_READY');




