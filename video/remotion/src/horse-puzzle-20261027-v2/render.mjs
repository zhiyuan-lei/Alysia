import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';

const root = path.resolve(process.argv[2]);
const mode = process.argv[3] || 'review';
const inputProps = JSON.parse(fs.readFileSync(path.join(root, 'timeline.json'), 'utf8'));
const entryPoint = path.join(path.dirname(fileURLToPath(import.meta.url)), 'index.jsx');
console.log(`Bundling ${mode}`, {root});
const serveUrl = await bundle({entryPoint, publicDir: root});
const composition = await selectComposition({serveUrl, id: 'HorsePuzzle', inputProps});
if (mode === 'review') {
  const review = path.join(root, 'review');
  fs.mkdirSync(review, {recursive: true});
  for (const scene of inputProps.scenes) {
    const frame = scene.start_frame + Math.min(scene.duration_frames - 25, scene.kind === 'champions' ? (scene.cues[1]?.start_frame || 0) + 190 : scene.kind === 'final' ? 220 : 80);
    await renderStill({composition, serveUrl, inputProps, frame, output: path.join(review, `scene_${scene.id}.png`), imageFormat: 'png', scale: .5});
    console.log(`REVIEW ${scene.id}: frame ${frame}`);
  }
  for (const [name, sceneIndex, cueIndex, offset] of [['surprise', 1, 1, 18], ['celebrate', 7, 2, 12], ['point', 4, 0, 40], ['wave', 0, 0, 15]]) {
    const scene = inputProps.scenes[sceneIndex];
    const frame = scene.start_frame + scene.cues[cueIndex].start_frame + offset;
    await renderStill({composition, serveUrl, inputProps, frame, output: path.join(review, `action_${name}.png`), imageFormat: 'png', scale: .5});
    console.log(`ACTION ${name}: frame ${frame}`);
  }
} else {
  const preview = mode === 'preview';
  let last = -1;
  await renderMedia({
    composition, serveUrl, inputProps, codec: 'h264', audioCodec: 'aac',
    outputLocation: path.join(root, preview ? 'opening_preview.mp4' : 'horse_puzzle_v2.mp4'),
    frameRange: preview ? [0, inputProps.scenes[2].start_frame - 1] : undefined,
    crf: 19, pixelFormat: 'yuv420p', concurrency: 4,
    onProgress: ({progress}) => {const percent = Math.floor(progress * 20) * 5; if (percent !== last) {last = percent; console.log(`RENDER ${percent}%`);}},
  });
  if (!preview) {
    await renderStill({composition, serveUrl, inputProps, frame: 80, output: path.join(root, 'cover.png'), imageFormat: 'png'});
  }
}
console.log(`DONE ${mode}: ${composition.durationInFrames / composition.fps}s`);
