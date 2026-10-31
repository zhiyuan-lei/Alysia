"""Verify the 90-frame motion experiment and prepare visual review sheets."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

run = Path(sys.argv[1]).resolve()
summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
assert summary['status'] == 'GENERATED_PENDING_VISUAL_REVIEW'
assert summary['frames'] == 90 and summary['output_frames'] == 90
stream = summary['ffprobe']['streams'][0]
assert (stream['codec_name'], stream['width'], stream['height'], int(stream['nb_frames'])) == ('h264', 1280, 720, 90)
assert abs(float(summary['ffprobe']['format']['duration']) - 3.75) < 0.001
assert hashlib.sha256(Path(summary['artifact']).read_bytes()).hexdigest() == summary['sha256']
stages = []
for phase in ('keyframe', 'encode', 'sample', 'decode'):
    record = json.loads((run / f'{phase}_resources.json').read_text(encoding='utf-8'))
    assert record['exit_code'] == 0 and record['stop_reason'] is None
    stages.append({'phase': phase, 'elapsed_seconds': record['elapsed'],
                   'gpu_sampled_peak_mib': max(s['gpu']['used_mib'] for s in record['samples']),
                   'system_ram_sampled_peak_mib': max(s['system_used'] for s in record['samples']) / 1024**2,
                   'process_private_sampled_peak_mib': max(s['private'] for s in record['samples']) / 1024**2})
def sheet(name, filter_graph):
    subprocess.run(['ffmpeg', '-nostdin', '-n', '-v', 'error', '-i', summary['artifact'],
                    '-vf', filter_graph, '-frames:v', '1', str(run / f'{name}.png')], check=True)
sheet('overview_contact', "select='not(mod(n,5))',scale=320:180,tile=6x3")
sheet('face_contact', "select='not(mod(n,3))',crop=240:200:760:70,tile=6x5")
sheet('hand_contact', "select='not(mod(n,5))',crop=480:300:710:140,scale=320:200,tile=6x3")
sheet('leg_contact', "select='not(mod(n,5))',crop=630:400:35:315,scale=315:200,tile=6x3")
report = {'artifact': summary['artifact'], 'sha256': summary['sha256'],
          'format_validation': 'PASS', 'visual_action_validation': 'PENDING_INSPECTION',
          'sampled_gpu_budget_pass': all(s['gpu_sampled_peak_mib'] <= 6144 for s in stages),
          'sampled_ram_budget_pass': all(s['process_private_sampled_peak_mib'] <= 24576 for s in stages),
          'stages': stages, 'stage_seconds_total': sum(s['elapsed_seconds'] for s in stages),
          'sampling_limitation': 'Whole-device GPU and RAM maxima are polling samples, not instantaneous upper bounds.'}
(run / 'motion_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
