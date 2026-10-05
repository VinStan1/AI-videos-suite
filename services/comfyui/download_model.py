"""Runs INSIDE Docker. Downloads only the chosen safe-tensor checkpoint."""
from pathlib import Path
from huggingface_hub import hf_hub_download
folder=Path("/opt/ComfyUI/models/checkpoints")
folder.mkdir(parents=True,exist_ok=True)
print("Download SD 1.5, circa 4.27 GB. Licenza: CreativeML Open RAIL-M.",flush=True)
path=hf_hub_download(repo_id="stable-diffusion-v1-5/stable-diffusion-v1-5",
    filename="v1-5-pruned-emaonly.safetensors",local_dir=folder)
print("Checkpoint disponibile:",path,flush=True)
