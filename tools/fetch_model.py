"""Telecharge le modele Whisper FP16 au format OpenVINO dans le dossier de donnees."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wispr import paths  # noqa: E402

REPO = "OpenVINO/whisper-large-v3-turbo-fp16-ov"
DEST = os.path.join(paths.models_dir(), "whisper-turbo-fp16")


def main() -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("installez huggingface_hub :  pip install huggingface_hub")
        return 1
    os.makedirs(DEST, exist_ok=True)
    print(f"telechargement de {REPO} vers {DEST}")
    snapshot_download(REPO, local_dir=DEST,
                      allow_patterns=["*.xml", "*.bin", "*.json", "*.txt"])
    print("termine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
