"""TEST_ONLY bounded H3 loader probes. Never edits models or ComfyUI."""
import argparse
from contextlib import nullcontext
import faulthandler
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time

import psutil

ROOT = Path(__file__).resolve().parent
MODEL = Path('D:/ComfyUI/models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors')


def child(mode):
    faulthandler.enable()
    import torch
    import safetensors
    with MODEL.open('rb') as f:
        size = struct.unpack('<Q', f.read(8))[0]
        header = json.loads(f.read(size))
    keys = sorted(k for k, v in header.items() if k != '__metadata__'
                  and v['data_offsets'][1] - v['data_offsets'][0] <= 2 * 1024**2)
    print(json.dumps({'torch': torch.__version__, 'safetensors': safetensors.__version__,
                      'mode': mode, 'small_tensor_count': len(keys)}), flush=True)
    if mode in {'comfy', 'aimdo'} or mode.startswith('dynamic_'):
        os.chdir('D:/ComfyUI')
        sys.path.insert(0, 'D:/ComfyUI')
        if mode == 'aimdo' or mode.startswith('dynamic_'):
            import comfy_aimdo.control
            assert comfy_aimdo.control.init(simple_vram_headroom=2 * 1024**3)
        import comfy.options
        comfy.options.enable_args_parsing()
        sys.argv = ([sys.argv[0], '--enable-dynamic-vram', '--reserve-vram', '2',
                     '--vram-headroom', '2', '--fast-disk', '--disable-pinned-memory',
                     '--disable-async-offload'] if mode.startswith('dynamic_') else [sys.argv[0], '--cpu'])
        import nodes
    if mode.startswith('dynamic_'):
        import comfy.memory_management
        import comfy.model_patcher
        assert comfy_aimdo.control.init_devices([(0, 2 * 1024**3)])
        comfy.memory_management.aimdo_enabled = True
        comfy.model_patcher.CoreModelPatcher = comfy.model_patcher.ModelPatcherDynamic
        torch.cuda.set_per_process_memory_fraction(0.5, 0)
        with torch.inference_mode():
            if mode in {'dynamic_encoder', 'dynamic_encode'}:
                clip = nodes.CLIPLoader().load_clip('qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
                                                   'minimax', 'default')[0]
                model = clip.patcher
            elif mode == 'dynamic_decode':
                vae = nodes.VAELoader().load_vae('minimax_h3_video_vae_fp16.safetensors')[0]
                model = vae.patcher
            else:
                model = nodes.UNETLoader().load_unet(MODEL.name, 'default')[0]
            assert model.is_dynamic()
            print(json.dumps({'model_class': type(model.model).__name__,
                              'patcher_class': type(model).__name__, 'model_bytes': model.model_size(),
                              'torch_peak_allocated': torch.cuda.max_memory_allocated(),
                              'torch_peak_reserved': torch.cuda.max_memory_reserved()}), flush=True)
            if mode in {'dynamic_encode', 'dynamic_sample', 'dynamic_decode'}:
                import comfy.model_management as mm
                run = Path(os.environ['H3_PROBE_RUN'])
                def watch_stop():
                    while not (run / 'STOP').exists():
                        time.sleep(0.1)
                    mm.interrupt_current_processing(True)
                threading.Thread(target=watch_stop, daemon=True).start()
            if mode == 'dynamic_encode':
                from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo
                print('ENCODE_BEGIN', flush=True)
                output = MiniMaxH3ImageToVideo.execute(clip, None, 'TEST_ONLY blue circle', 320, 256, 5)
                cond, latent = output[0], output[1]
                video, audio = latent['samples'].unbind()
                assert all(torch.isfinite(c[0]).all() for c in cond)
                torch.save({'conditioning': cond, 'video': video, 'audio': audio}, run / 'conditioning.pt')
                print(json.dumps({'event': 'conditioning_saved', 'torch_peak_allocated': torch.cuda.max_memory_allocated(),
                                  'torch_peak_reserved': torch.cuda.max_memory_reserved()}), flush=True)
            if mode == 'dynamic_sample':
                from comfy.nested_tensor import NestedTensor
                from comfy_extras.nodes_custom_sampler import (
                    BasicScheduler, BasicGuider, KSamplerSelect, RandomNoise, SamplerCustomAdvanced,
                )
                source = Path(os.environ['H3_CONDITIONING'])
                data = torch.load(source, map_location='cpu', weights_only=True)
                sigmas = BasicScheduler.execute(model, 'simple', 1, 1.0)[0]
                guider = BasicGuider.execute(model, data['conditioning'])[0]
                noise = RandomNoise.execute(20260808)[0]
                sampler = KSamplerSelect.execute('res_multistep')[0]
                latent = {'samples': NestedTensor((data['video'], data['audio']))}
                print('SAMPLE_BEGIN', flush=True)
                sampled = SamplerCustomAdvanced.execute(noise, guider, sampler, sigmas, latent)[0]
                video, audio = sampled['samples'].unbind()
                assert torch.isfinite(video).all() and torch.isfinite(audio).all()
                torch.save({'video': video.cpu(), 'audio': audio.cpu()}, run / 'sampled.pt')
                print(json.dumps({'event': 'sampled_saved', 'source': str(source),
                                  'torch_peak_allocated': torch.cuda.max_memory_allocated(),
                                  'torch_peak_reserved': torch.cuda.max_memory_reserved()}), flush=True)
            if mode == 'dynamic_decode':
                from PIL import Image
                source = Path(os.environ['H3_SAMPLED'])
                data = torch.load(source, map_location='cpu', weights_only=True)
                print('DECODE_BEGIN', flush=True)
                images = nodes.VAEDecodeTiled().decode(vae, {'samples': data['video']},
                                                     tile_size=256, overlap=64, temporal_size=16)[0]
                assert torch.isfinite(images).all()
                assert list(images.shape) == [5, 256, 320, 3]
                for i, frame in enumerate(images):
                    Image.fromarray((frame.clamp(0, 1).cpu().numpy() * 255).astype('uint8')).save(
                        run / f'TEST_ONLY_frame_{i:03d}.png')
                print(json.dumps({'event': 'frames_saved', 'shape': list(images.shape), 'source': str(source),
                                  'torch_peak_allocated': torch.cuda.max_memory_allocated(),
                                  'torch_peak_reserved': torch.cuda.max_memory_reserved()}), flush=True)
        print('PASS', flush=True)
        return
    if mode == 'aimdo':
        import comfy.utils
        state, metadata = comfy.utils.load_safetensors(str(MODEL))
        assert len(state) == len(header) - int('__metadata__' in header)
        for key, value in state.items():
            assert list(value.shape) == header[key]['shape']
        print(json.dumps({'tensor_count': len(state), 'first': state[keys[0]].flatten()[0].item(),
                          'loader': 'installed comfy.utils.load_safetensors'}), flush=True)
        print('PASS', flush=True)
        return
    if mode == 'direct':
        key = keys[0]
        info = header[key]
        with MODEL.open('rb') as f:
            f.seek(8 + size + info['data_offsets'][0])
            data = bytearray(f.read(info['data_offsets'][1] - info['data_offsets'][0]))
        tensor = torch.frombuffer(data, dtype=torch.float32).view(info['shape'])
        assert torch.isfinite(tensor).all()
        print(json.dumps({'key': key, 'shape': list(tensor.shape), 'first': tensor.flatten()[0].item()}), flush=True)
        print('PASS', flush=True)
        return
    if mode == 'tiny':
        import safetensors.torch
        fixture = Path(os.environ['H3_PROBE_RUN']) / 'tiny.safetensors'
        expected = torch.arange(8200, dtype=torch.float32).reshape(1025, 8)
        safetensors.torch.save_file({'adaln_t_table': expected}, str(fixture))
        with safetensors.safe_open(str(fixture), framework='pt', device='cpu') as f:
            assert torch.equal(f.get_tensor('adaln_t_table'), expected)
        print('PASS', flush=True)
        return
    context = nullcontext() if mode == 'no_inference' else torch.inference_mode()
    framework = 'numpy' if mode == 'numpy' else 'pt'
    with context, safetensors.safe_open(str(MODEL), framework=framework, device='cpu') as f:
        for key in keys:
            print(json.dumps({'before': key, 'descriptor': header[key]}), flush=True)
            value = f.get_tensor(key)
            assert list(value.shape) == header[key]['shape']
            print(json.dumps({'after': key, 'first': value.reshape(-1)[0].item()}), flush=True)
            del value
    print('PASS', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['bare', 'comfy', 'numpy', 'no_inference', 'direct', 'aimdo', 'tiny', 'dynamic_model', 'dynamic_encoder', 'dynamic_encode', 'dynamic_sample', 'dynamic_decode'])
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    if args.child:
        child(args.mode)
        return
    run = ROOT / (time.strftime('%Y%m%d_%H%M%S') + '_' + args.mode)
    run.mkdir()
    start = time.monotonic()
    samples = []
    gpu_samples = []
    with (run / 'stdout.log').open('w') as out, (run / 'stderr.log').open('w') as err:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), args.mode, '--child'],
                                stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW,
                                env={**os.environ, 'H3_PROBE_RUN': str(run)})
        worker = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                # Windows venv python.exe can be a launcher with an actual child.
                infos = [p.memory_info() for p in [worker, *worker.children(recursive=True)]]
                samples.append({'elapsed': time.monotonic() - start,
                                'rss': sum(i.rss for i in infos),
                                'private': sum(i.private for i in infos),
                                'system_used': psutil.virtual_memory().used})
                if args.mode.startswith('dynamic_') and (not gpu_samples or time.monotonic() - gpu_samples[-1]['clock'] >= 1):
                    query = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free',
                                            '--format=csv,noheader,nounits'], capture_output=True, text=True,
                                           creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                    used, free = map(int, query.stdout.strip().split(','))
                    gpu_samples.append({'clock': time.monotonic(), 'used_mib': used, 'free_mib': free})
                if args.mode in {'dynamic_encode', 'dynamic_sample', 'dynamic_decode'} and (samples[-1]['system_used'] > 20 * 1024**3
                        or samples[-1]['private'] > 20 * 1024**3
                        or (gpu_samples and gpu_samples[-1]['used_mib'] > 5900)
                        or time.monotonic() - start > 180):
                    (run / 'STOP').touch()
            except psutil.NoSuchProcess:
                pass
            time.sleep(0.1)
    report = {'test_only': True, 'mode': args.mode, 'exit_code': proc.returncode,
              'elapsed': time.monotonic() - start, 'samples': samples,
              'gpu_workload': args.mode.startswith('dynamic_'), 'gpu_samples': gpu_samples,
              'model_file_bytes': MODEL.stat().st_size}
    (run / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'run': str(run), 'exit_code': proc.returncode,
                      'peak_rss_mib': max(s['rss'] for s in samples) / 1024**2,
                      'peak_private_mib': max(s['private'] for s in samples) / 1024**2}))
    return 0 if proc.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
