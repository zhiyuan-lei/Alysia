"""TEST_ONLY: existing ComfyUI nodes, one model family per process."""
from __future__ import annotations

import faulthandler
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(os.environ["ALYSIA_STAGED_RUN"])
STAGE = os.environ["ALYSIA_STAGED_PHASE"]
COMFY = Path(r"D:\ComfyUI")


def event(name, **data):
    print(json.dumps({"stage": STAGE, "event": name, **data}), flush=True)


def main():
    faulthandler.enable(all_threads=True)
    os.chdir(COMFY)
    sys.path.insert(0, str(COMFY))
    import comfy.options
    comfy.options.enable_args_parsing()
    import torch
    if STAGE in {"sample", "load_diffusion"}:
        # The controller reserves current desktop usage and 512 MiB for
        # non-allocator overhead within the requested 6 GiB total envelope.
        allocator_mib = int(os.environ["ALYSIA_CUDA_ALLOCATOR_MIB"])
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(allocator_mib * 1024**2 / total, 0)
        torch.cuda.reset_peak_memory_stats()
        event("cuda_allocator_limit", mib=allocator_mib)
    import nodes
    import comfy.model_management as mm
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo

    def check_stop():
        if (ROOT / "STOP").exists():
            raise RuntimeError("RESOURCE_OR_TIMEOUT_STOP_REQUESTED")

    done = threading.Event()
    def watch_stop():
        while not done.wait(0.25):
            if (ROOT / "STOP").exists():
                mm.interrupt_current_processing(True)
                return
    watcher = threading.Thread(target=watch_stop, daemon=True)
    watcher.start()
    start = time.monotonic()
    result = {"stage": STAGE, "status": "FAIL", "test_only": True}
    try:
        check_stop()
        event("load_begin", torch_version=torch.__version__)
        # Match ComfyUI's inference execution context, outside its source tree.
        with torch.inference_mode():
            if STAGE == "encode":
                clip = nodes.CLIPLoader().load_clip(
                    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "minimax", "cpu",
                )[0]
                event("text_encoder_loaded")
                check_stop()
                output = MiniMaxH3ImageToVideo.execute(
                    clip, None, "TEST_ONLY blue circle", 320, 256, 5,
                )
                cond, latent = output[0], output[1]
                video, audio = latent["samples"].unbind()
                torch.save({"conditioning": cond, "video": video, "audio": audio}, ROOT / "conditioning.pt")
                del clip, cond, latent, output, video, audio
                event("conditioning_saved")
            elif STAGE == "load_diffusion":
                model = nodes.UNETLoader().load_unet(
                    "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "default",
                )[0]
                event("diffusion_model_loaded", model_size_bytes=model.model_size())
                check_stop()
                mm.load_models_gpu([model])
                event("diffusion_model_offload_ready", loaded_bytes=model.loaded_size())
                result["torch_peak_allocated_mib"] = torch.cuda.max_memory_allocated() / 1024**2
                result["torch_peak_reserved_mib"] = torch.cuda.max_memory_reserved() / 1024**2
                del model
            elif STAGE == "sample":
                from comfy.nested_tensor import NestedTensor
                from comfy_extras.nodes_custom_sampler import (
                    BasicScheduler, BasicGuider, KSamplerSelect, RandomNoise, SamplerCustomAdvanced,
                )
                data = torch.load(ROOT / "conditioning.pt", map_location="cpu", weights_only=True)
                model = nodes.UNETLoader().load_unet(
                    "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "default",
                )[0]
                event("diffusion_model_loaded", model_size_bytes=model.model_size())
                check_stop()
                sigmas = BasicScheduler.execute(model, "simple", 1, 1.0)[0]
                guider = BasicGuider.execute(model, data["conditioning"])[0]
                noise = RandomNoise.execute(20260808)[0]
                sampler = KSamplerSelect.execute("res_multistep")[0]
                latent = {"samples": NestedTensor((data["video"], data["audio"]))}
                event("one_step_sampling_begin")
                sampled = SamplerCustomAdvanced.execute(noise, guider, sampler, sigmas, latent)[0]
                video, audio = sampled["samples"].unbind()
                torch.save({"video": video.cpu(), "audio": audio.cpu()}, ROOT / "sampled.pt")
                event("sampled_latent_saved")
                result["torch_peak_allocated_mib"] = torch.cuda.max_memory_allocated() / 1024**2
                result["torch_peak_reserved_mib"] = torch.cuda.max_memory_reserved() / 1024**2
                del model, guider, data, sampled, latent, video, audio
            elif STAGE == "decode":
                from PIL import Image
                data = torch.load(ROOT / "sampled.pt", map_location="cpu", weights_only=True)
                vae = nodes.VAELoader().load_vae("minimax_h3_video_vae_fp16.safetensors")[0]
                event("video_vae_loaded")
                check_stop()
                images = nodes.VAEDecode().decode(vae, {"samples": data["video"]})[0]
                frames = []
                for index, frame in enumerate(images):
                    path = ROOT / f"TEST_ONLY_frame_{index:03d}.png"
                    Image.fromarray((frame.clamp(0, 1).cpu().numpy() * 255).astype("uint8")).save(path)
                    frames.append({"name": path.name, "size": path.stat().st_size,
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                if not frames:
                    raise RuntimeError("No decoded frames")
                result["frames"] = frames
                result["shape"] = list(images.shape)
                event("frames_saved", count=len(frames))
                del vae, data, images
            else:
                raise ValueError(STAGE)
        check_stop()
        result["status"] = "PASS"
    except (Exception, mm.InterruptProcessingException) as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        event("failed", **result)
    finally:
        done.set()
        mm.unload_all_models()
        gc.collect()
        mm.soft_empty_cache()
        result["elapsed_seconds"] = round(time.monotonic() - start, 3)
        (ROOT / f"{STAGE}_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        event("finished", status=result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
