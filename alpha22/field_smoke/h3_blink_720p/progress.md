# Progress

2026-10-01: Read existing successful harness and installed H3 node source. No active Python workload; GPU baseline about 1337 MiB used. Preparing isolated experiment. No Alysia production code or default configuration changes.

Runner compiled. First attempt failed before VAE encode because LoadImage accepts input-directory-relative paths. Changed only caller input-directory setup and filename. Rerunning the original stage is the direct regression check.

run_20261001_225215: keyframe VAE encode PASS; real Qwen3VL image+prompt encode PASS. Real 20-step H3 sampling started, using the exact supplied image as first-frame conditioning. Sampling still pending; no video success claim yet.

Sampling completed 20/20 in about 427 seconds; sampled latents finite and saved. Independent tiled VAE decode running. Whole-device spot checks during sampling around 4532 MiB; final maxima will be taken from resource records, not extrapolated from spot checks.

First video: format PASS, 1280x720/48 frames/2 s, whole-device sampled max 4630 MiB; eye-contact-sheet review FAIL for complete blink (long eye closure; native final frame only partially reopening). Targeted second generation adds the original image as last keyframe, with matching duplicate image token conditioning. Preserve all 56 output frames (2.333 s) to include reopening. No reverse playback, synthetic eye edit, or lower-resolution substitution.

Second generation complete. Keyframe 6.046 s; multimodal encode 22.578 s; sample 500.078 s; decode 63.812 s. No resource stop. MP4 full decode and dimensions/frame count/duration assertions PASS. Eye contact sheet reviewed at all 56 frames; complete slow blink PASS. No Alysia integration and no production default changes. Deliver second output; preserve failed/first outputs as evidence.

Delivery copy saved to current workspace outputs/H3_blink_720p_20261001.mp4; SHA256 matches experiment artifact. Both scripts compile. Existing SecretScanner checked 35 evidence text files, zero findings. No Python worker remains; staged Git list empty. No reset, clean, restore, checkout, stage, commit, forced process termination, or model/runtime/driver modification.

New user steering: add drifting blossoms, hair movement, leg and hand movements. Preflight: GPU 8188/1231/6719 MiB total/used/free, no Python worker; source image still present. Added TEST_ONLY 90-frame prompt and per-run prompt snapshot; default prior 56-frame behavior remains available. Next: compile and run.

Expanded motion run_20261001_233242 completed. Keyframe PASS 6.031 s; multimodal encode PASS 23.797 s; 20-step/90-frame sample PASS 957.531 s; tiled VAE decode PASS 90.875 s. MP4 full bitstream decode and 720p/90 frame/3.75 second assertions PASS. Contact sheets reviewed: petals, blink, subtle hair, hand and leg motion visible. Whole-device sampled VRAM peak 5447 MiB; sampled system RAM peak 13105.922 MiB. All stages below configured experimental limits, with no STOP or orphan worker.

Delivery copy: workspace outputs/H3_motion_720p_20261001.mp4, SHA256 matches experiment artifact. ffprobe confirms H.264 1280x720, 24 fps, 90 frames, 3.75 seconds, 4,047,907 bytes. Both scripts compile. SecretScanner checked 51 text evidence files with zero findings. Staged Git list empty; all Python workers exited. No production/Alysia integration, model download or forced termination.
