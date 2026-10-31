"""Isolated, sequential real H3 blink experiment. No production integration."""
import argparse
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import psutil

ROOT = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/ADMINI~1/AppData/Local/Temp/codex-clipboard-e113e3f9-8ee1-4660-b19e-b5f75d99b709.png')
WIDTH, HEIGHT, FRAMES, STEPS = 1280, 736, 56, 20


def emit(event, **data):
    print(json.dumps({'event': event, **data}), flush=True)


def worker(phase, run, last_keyframe=False):
    faulthandler.enable()
    os.chdir('D:/ComfyUI')
    sys.path.insert(0, 'D:/ComfyUI')
    import comfy_aimdo.control
    assert comfy_aimdo.control.init(simple_vram_headroom=2 * 1024**3)
    import comfy.options
    comfy.options.enable_args_parsing()
    sys.argv = [sys.argv[0], '--enable-dynamic-vram', '--reserve-vram', '2',
                '--vram-headroom', '3', '--fast-disk', '--disable-pinned-memory',
                '--disable-async-offload']
    import torch
    import nodes
    import folder_paths
    folder_paths.set_input_directory(str(run))
    import comfy.memory_management
    import comfy.model_patcher
    import comfy.model_management as mm
    assert comfy_aimdo.control.init_devices([(0, 3 * 1024**3)])
    comfy.memory_management.aimdo_enabled = True
    comfy.model_patcher.CoreModelPatcher = comfy.model_patcher.ModelPatcherDynamic
    torch.cuda.set_per_process_memory_fraction(0.5, 0)
    done = threading.Event()
    def watch():
        while not done.wait(0.1):
            if (run / 'STOP').exists():
                mm.interrupt_current_processing(True)
                return
    threading.Thread(target=watch, daemon=True).start()
    try:
        with torch.inference_mode():
            if phase in {'keyframe', 'decode'}:
                vae = nodes.VAELoader().load_vae('minimax_h3_video_vae_fp16.safetensors')[0]
                assert vae.patcher.is_dynamic()
                emit('vae_loaded')
            if phase == 'keyframe':
                image = nodes.LoadImage().load_image('reference_canvas.png')[0]
                z = nodes.VAEEncodeTiled().encode(vae, image, 256, 64, 16, 8)[0]['samples']
                assert torch.isfinite(z).all()
                torch.save(z.cpu(), run / 'keyframe.pt')
                emit('keyframe_saved', shape=list(z.shape))
            elif phase == 'encode':
                import node_helpers
                from comfy_extras.nodes_minimax_h3 import EmptyMiniMaxH3LatentAV
                clip = nodes.CLIPLoader().load_clip('qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
                                                   'minimax', 'default')[0]
                assert clip.patcher.is_dynamic()
                image = nodes.LoadImage().load_image('reference_canvas.png')[0]
                tokens = clip.tokenize((run / 'prompt.txt').read_text(), images=[image, image] if last_keyframe else [image])
                emit('multimodal_encode_begin')
                cond = clip.encode_from_tokens_scheduled(tokens)
                z = torch.load(run / 'keyframe.pt', map_location='cpu', weights_only=True)
                keyframes = [{'resolved_frame_index': 0, 'latent': z}]
                if last_keyframe:
                    keyframes.append({'resolved_frame_index': FRAMES - 1, 'latent': z})
                cond = node_helpers.conditioning_set_values(cond, {
                    'minimax_keyframes': keyframes,
                    'minimax_frame_count': FRAMES})
                latent = EmptyMiniMaxH3LatentAV.execute(WIDTH, HEIGHT, FRAMES)[0]
                video, audio = latent['samples'].unbind()
                assert all(torch.isfinite(c[0]).all() for c in cond)
                torch.save({'conditioning': cond, 'video': video, 'audio': audio}, run / 'conditioning.pt')
                emit('conditioning_saved')
            elif phase == 'sample':
                from comfy.nested_tensor import NestedTensor
                from comfy_extras.nodes_custom_sampler import BasicScheduler, BasicGuider, KSamplerSelect, RandomNoise, SamplerCustomAdvanced
                data = torch.load(run / 'conditioning.pt', map_location='cpu', weights_only=True)
                model = nodes.UNETLoader().load_unet('minimax_h3_fl2va_pruned_int8_convrot.safetensors', 'default')[0]
                assert model.is_dynamic()
                sigmas = BasicScheduler.execute(model, 'simple', STEPS, 1.0)[0]
                guider = BasicGuider.execute(model, data['conditioning'])[0]
                noise = RandomNoise.execute(20261001)[0]
                sampler = KSamplerSelect.execute('res_multistep')[0]
                latent = {'samples': NestedTensor((data['video'], data['audio']))}
                emit('sampling_begin', width=WIDTH, height=HEIGHT, frames=FRAMES, steps=STEPS)
                output = SamplerCustomAdvanced.execute(noise, guider, sampler, sigmas, latent)[0]
                video, audio = output['samples'].unbind()
                assert torch.isfinite(video).all() and torch.isfinite(audio).all()
                torch.save({'video': video.cpu(), 'audio': audio.cpu()}, run / 'sampled.pt')
                emit('sampled_saved')
            elif phase == 'decode':
                from PIL import Image
                data = torch.load(run / 'sampled.pt', map_location='cpu', weights_only=True)
                images = nodes.VAEDecodeTiled().decode(vae, {'samples': data['video']}, 256, 64, 16, 8)[0]
                assert list(images.shape) == [FRAMES, HEIGHT, WIDTH, 3]
                assert torch.isfinite(images).all()
                for i, frame in enumerate(images):
                    Image.fromarray((frame.clamp(0, 1).cpu().numpy() * 255).astype('uint8')).save(run / f'frame_{i:03d}.png')
                emit('frames_saved', count=len(images))
            emit('PASS', torch_peak_allocated=torch.cuda.max_memory_allocated(),
                 torch_peak_reserved=torch.cuda.max_memory_reserved())
    finally:
        done.set()


def gpu():
    result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True,
                            check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    used, free = map(int, result.stdout.strip().split(','))
    return {'used_mib': used, 'free_mib': free}


def main():
    global FRAMES
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=['keyframe', 'encode', 'sample', 'decode'])
    parser.add_argument('--run', type=Path)
    parser.add_argument('--last-keyframe', action='store_true')
    parser.add_argument('--frames', type=int, default=56)
    parser.add_argument('--prompt-file', type=Path, default=ROOT / 'prompt.txt')
    parser.add_argument('--output-name', choices=['H3_blink_720p_TEST_ONLY.mp4', 'H3_motion_720p_TEST_ONLY.mp4'],
                        default='H3_blink_720p_TEST_ONLY.mp4')
    args = parser.parse_args()
    if args.frames < 5 or args.frames % 17 != 5:
        parser.error('frames must be >= 5 and aligned to 17n+5')
    FRAMES = args.frames
    if args.worker:
        worker(args.worker, args.run, args.last_keyframe)
        return
    run = ROOT / time.strftime('run_%Y%m%d_%H%M%S')
    run.mkdir()
    prompt = args.prompt_file.read_text(encoding='utf-8')
    (run / 'prompt.txt').write_text(prompt, encoding='utf-8')
    summary = {'status': 'RUNNING', 'stages': [], 'width': WIDTH, 'height': HEIGHT,
               'frames': FRAMES, 'steps': STEPS, 'reference_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               'prompt': prompt, 'test_only': True,
               'last_keyframe': args.last_keyframe, 'output_frames': FRAMES if args.last_keyframe else 48}
    def save():
        (run / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    save()
    emit('run_created', path=str(run))
    subprocess.run(['ffmpeg', '-nostdin', '-n', '-v', 'error', '-i', str(SOURCE), '-vf',
                    'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,pad=1280:736:0:8',
                    '-frames:v', '1', str(run / 'reference_canvas.png')], check=True)
    for phase in ['keyframe', 'encode', 'sample', 'decode']:
        baseline = {'gpu': gpu(), 'system_used': psutil.virtual_memory().used}
        if baseline['gpu']['used_mib'] > 2500 or psutil.virtual_memory().available < 12 * 1024**3:
            summary.update(status='BLOCKED_BASELINE', baseline=baseline)
            save()
            return 1
        emit('phase_start', phase=phase)
        start = time.monotonic()
        samples = []
        stop_reason = None
        with (run / f'{phase}_stdout.log').open('w') as out, (run / f'{phase}_stderr.log').open('w') as err:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', phase, '--run', str(run),
                       '--frames', str(FRAMES)]
            if args.last_keyframe:
                command.append('--last-keyframe')
            process = subprocess.Popen(command, stdout=out, stderr=err,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            owner = psutil.Process(process.pid)
            while process.poll() is None:
                try:
                    infos = [p.memory_info() for p in [owner, *owner.children(recursive=True)]]
                    current = {'elapsed': time.monotonic() - start, 'gpu': gpu(),
                               'rss': sum(m.rss for m in infos), 'private': sum(m.private for m in infos),
                               'system_used': psutil.virtual_memory().used}
                    samples.append(current)
                    if (current['gpu']['used_mib'] > 6000 or current['private'] > 20 * 1024**3
                            or current['system_used'] > 24 * 1024**3 or current['elapsed'] > 3600):
                        stop_reason = 'resource_or_timeout'
                        (run / 'STOP').touch()
                except psutil.NoSuchProcess:
                    pass
                time.sleep(0.5)
        result = {'phase': phase, 'exit_code': process.returncode, 'elapsed': time.monotonic() - start,
                  'baseline': baseline, 'after': {'gpu': gpu(), 'system_used': psutil.virtual_memory().used},
                  'stop_reason': stop_reason, 'samples': samples}
        (run / f'{phase}_resources.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        summary['stages'].append({k: v for k, v in result.items() if k != 'samples'})
        save()
        emit('phase_exit', phase=phase, exit_code=process.returncode)
        if process.returncode or stop_reason:
            summary['status'] = 'FAILED_OR_RESOURCE_STOP'
            save()
            return 1
    video = run / args.output_name
    subprocess.run(['ffmpeg', '-nostdin', '-n', '-v', 'error', '-framerate', '24',
                    '-i', str(run / 'frame_%03d.png'), '-vf', 'crop=1280:720:0:8', '-frames:v', str(summary['output_frames']),
                    '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)], check=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video), '-f', 'null', '-'], check=True)
    info = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)],
                          capture_output=True, text=True, check=True)
    summary.update(status='GENERATED_PENDING_VISUAL_REVIEW', artifact=str(video), bytes=video.stat().st_size,
                   sha256=hashlib.sha256(video.read_bytes()).hexdigest(), ffprobe=json.loads(info.stdout))
    save()
    emit('video_saved', path=str(video))


if __name__ == '__main__':
    raise SystemExit(main())
