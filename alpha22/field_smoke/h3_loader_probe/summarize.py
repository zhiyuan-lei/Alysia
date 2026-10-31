"""Build an evidence summary from this TEST_ONLY experiment's recorded samples."""
import hashlib
import json
from pathlib import Path
import subprocess

import psutil

ROOT = Path(__file__).resolve().parent
RUNS = ['20261001_223703_dynamic_encode', '20261001_223808_dynamic_sample',
        '20261001_223923_dynamic_decode']
stages = []
for name in RUNS:
    run = ROOT / name
    report = json.loads((run / 'result.json').read_text())
    assert report['exit_code'] == 0 and not (run / 'STOP').exists()
    events = [json.loads(line) for line in (run / 'stdout.log').read_text().splitlines()
              if line.startswith('{')]
    stage = {'run': name, 'elapsed_seconds': report['elapsed'],
             'process_tree_rss_peak_mib': max(s['rss'] for s in report['samples']) / 1024**2,
             'process_tree_private_peak_mib': max(s['private'] for s in report['samples']) / 1024**2,
             'system_ram_baseline_mib': report['samples'][0]['system_used'] / 1024**2,
             'system_ram_peak_mib': max(s['system_used'] for s in report['samples']) / 1024**2,
             'gpu_baseline_mib': report['gpu_samples'][0]['used_mib'],
             'gpu_peak_mib': max(s['used_mib'] for s in report['gpu_samples']),
             'torch_allocator_counters': events[-1], 'status': 'PASS'}
    assert stage['gpu_peak_mib'] < 6144
    assert stage['process_tree_private_peak_mib'] < 24576
    stages.append(stage)
artifact = ROOT / RUNS[-1] / 'TEST_ONLY_H3.mp4'
probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'stream=codec_name,width,height,nb_frames,r_frame_rate:format=duration,size',
                        '-of', 'json', str(artifact)], capture_output=True, text=True, check=True)
subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(artifact), '-f', 'null', '-'], check=True)
validation = json.loads(probe.stdout)
assert validation['streams'][0]['nb_frames'] == '5'
gpu_after = subprocess.run(['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free',
                            '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
summary = {'test_only': True, 'status': 'PASS_COMPONENT_STAGED_VIDEO_SMOKE', 'stages': stages,
           'elapsed_stages_total_seconds': sum(s['elapsed_seconds'] for s in stages),
           'artifact': {'path': str(artifact), 'bytes': artifact.stat().st_size,
                        'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        'validation': validation, 'bitstream_decode': 'PASS', 'audio': 'NOT_DECODED'},
           'after': {'gpu_total_used_free_mib': [int(v) for v in gpu_after.stdout.split(',')],
                     'system_ram_used_mib': psutil.virtual_memory().used / 1024**2},
           'measurement': {'gpu': 'whole-device sampled about once per second; not a driver-wide hard cap',
                           'ram': 'owned process tree including Windows venv child; nominal 0.1 s polling, slower during GPU queries',
                           'torch': 'allocator high-water marks exclude AIMDO native allocations',
                           'initial_bare_probe': 'RSS was launcher-only; excluded from RAM conclusions'},
           'alysia_adapter_acceptance': 'NOT_EXECUTED', 'alpha22_step8': 'KEEP_BLOCKED',
           'production_config_changed': False, 'ram_budget_gib': 24}
(ROOT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
