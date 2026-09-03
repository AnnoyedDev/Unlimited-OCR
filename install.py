#!/usr/bin/env python3
"""
Cross-platform bootstrap installer.

Creates a `.venv` (via `uv`) and installs:
  1. the base dependencies from pyproject.toml
  2. the correct torch/torchvision build for this machine:
       - NVIDIA GPU (Linux or Windows) -> default PyPI wheels (CUDA-enabled)
       - AMD GPU on Linux              -> ROCm wheels from download.pytorch.org
       - anything else (no supported GPU, or AMD on Windows) -> CPU wheels

Usage:
    python install.py                 # auto-detect everything
    python install.py --device cpu    # force CPU-only torch
    python install.py --device cuda   # force NVIDIA/CUDA wheels
    python install.py --device rocm   # force AMD/ROCm wheels (Linux only)
    python install.py --rocm-tag rocm6.3   # pin a specific ROCm wheel tag
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
TORCH_VERSION = "2.10.0"
TORCHVISION_VERSION = "0.25.0"
# Tried in order until one installs successfully. rocm7.0 is the first tag that
# actually ships torch==2.10.0 (the version this app is pinned to / tested against);
# older tags only have older torch releases and are kept as a fallback.
ROCM_TAG_CANDIDATES = ["rocm7.0", "rocm6.4", "rocm6.3", "rocm6.2"]


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT)


def venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def detect_gpu_vendor() -> str:
    """Returns 'nvidia', 'amd', or 'none'."""
    system = platform.system()

    if has_command("nvidia-smi"):
        try:
            subprocess.run(
                ["nvidia-smi"], check=True, capture_output=True, timeout=10
            )
            return "nvidia"
        except Exception:
            pass

    if system == "Linux":
        # AMD GPU present if lspci reports it, or the amdgpu kernel module / ROCm
        # userspace stack is present.
        if has_command("lspci"):
            try:
                out = subprocess.run(
                    ["lspci"], check=True, capture_output=True, text=True, timeout=10
                ).stdout
                if any(
                    kw in out
                    for kw in ("AMD/ATI", "Advanced Micro Devices")
                ) and ("VGA" in out or "Display" in out or "3D controller" in out):
                    return "amd"
            except Exception:
                pass
        if Path("/opt/rocm").exists() or has_command("rocminfo"):
            return "amd"

    return "none"


def install_torch(python_exe: Path, device: str, rocm_tag: str | None) -> None:
    base = ["uv", "pip", "install", "--python", str(python_exe)]
    torch_pkgs = [f"torch=={TORCH_VERSION}", f"torchvision=={TORCHVISION_VERSION}"]

    if device == "cpu":
        print("Installing CPU-only torch build.")
        run(base + torch_pkgs + ["--index-url", "https://download.pytorch.org/whl/cpu"])
        return

    if device == "cuda":
        print("Installing CUDA-enabled torch build (auto-detecting local CUDA driver)...")
        run(base + torch_pkgs + ["--torch-backend=auto"])
        return

    if device == "rocm":
        if platform.system() != "Linux":
            print(
                "ROCm wheels are only published for Linux; falling back to CPU. "
                "AMD GPU acceleration on Windows is not supported by this installer."
            )
            install_torch(python_exe, "cpu", None)
            return
        tags = [rocm_tag] if rocm_tag else ROCM_TAG_CANDIDATES
        last_err = None
        for tag in tags:
            try:
                print(f"Trying ROCm wheel tag '{tag}'...")
                run(
                    base
                    + torch_pkgs
                    + ["--index-url", f"https://download.pytorch.org/whl/{tag}"]
                )
                return
            except subprocess.CalledProcessError as exc:
                last_err = exc
                print(f"  '{tag}' failed, trying next candidate...")
        raise RuntimeError(
            f"Could not install a ROCm torch build (tried {tags}). "
            "Pass --rocm-tag to pin a specific version, e.g. --rocm-tag rocm6.3 "
            "(check https://download.pytorch.org/whl/ for what's currently published)."
        ) from last_err

    raise ValueError(f"Unknown device: {device}")


def load_base_dependencies() -> list[str]:
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["dependencies"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "rocm", "cpu"],
        default="auto",
        help="Force a specific torch build instead of auto-detecting the GPU.",
    )
    parser.add_argument(
        "--rocm-tag",
        default=None,
        help="Pin a specific ROCm wheel tag (e.g. rocm6.3) instead of trying candidates.",
    )
    parser.add_argument(
        "--python-version",
        default="3.12",
        help="Python version for the venv (torch/transformers here are tested on 3.12).",
    )
    args = parser.parse_args()

    if not has_command("uv"):
        sys.exit("This installer requires 'uv' (https://docs.astral.sh/uv/). Install it first.")

    if VENV_DIR.exists():
        print(f"Reusing existing venv at {VENV_DIR}.")
    else:
        print(f"Creating venv at {VENV_DIR} (python {args.python_version})...")
        run(["uv", "venv", "--python", args.python_version, str(VENV_DIR)])
    py = venv_python()

    device = args.device
    if device == "auto":
        vendor = detect_gpu_vendor()
        device = {"nvidia": "cuda", "amd": "rocm", "none": "cpu"}[vendor]
        print(f"Detected GPU vendor: {vendor} -> using device '{device}'")

    print("Installing base dependencies...")
    run(["uv", "pip", "install", "--python", str(py), *load_base_dependencies()])

    install_torch(py, device, args.rocm_tag)

    print("\nDone. Activate the environment with:")
    if platform.system() == "Windows":
        print(r"    .venv\Scripts\activate")
    else:
        print("    source .venv/bin/activate")
    print("Then run:  python -m app.main")


if __name__ == "__main__":
    main()
