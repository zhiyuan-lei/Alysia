import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';

const folder=path.dirname(fileURLToPath(import.meta.url));
const result=await bundle({entryPoint:path.join(folder,'index.jsx')});
console.log(`BUNDLE_OK ${result}`);
