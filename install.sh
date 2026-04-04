#!/usr/bin/env bash
# ============================================================
# Vigour POC — Environment Setup
# Tested on: Python 3.11, Ubuntu 20.04+, NVIDIA driver 575+
# GPU support: RTX 3060 (sm_86), RTX 5080 (sm_120 / Blackwell)
# ============================================================
set -euo pipefail

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON="${PYTHON:-python3.11}"
PROJ_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Vigour POC Install ==="
echo "Project root: $PROJ_ROOT"
echo "Python:       $PYTHON"
echo "Venv:         $VENV_DIR"
echo ""

# ── 1. Create venv if missing ───────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/6] Creating virtualenv..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "[1/6] Virtualenv exists, reusing."
fi

PIP="$VENV_DIR/bin/pip"
PY="$VENV_DIR/bin/python"

"$PIP" install --upgrade pip setuptools wheel -q

# ── 2. PyTorch + CUDA (sm_120 / Blackwell needs torch>=2.6 + cu126) ─────────
echo "[2/6] Installing PyTorch 2.8.0 + CUDA 12.8 (supports sm_86 + sm_120)..."
"$PIP" install torch==2.8.0 torchvision==0.23.0 \
    --index-url https://download.pytorch.org/whl/cu128 -q

# Verify
"$PY" -c "
import torch
print(f'  torch {torch.__version__}  CUDA {torch.version.cuda}')
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        print(f'  GPU {i}: {torch.cuda.get_device_name(i)} (sm_{torch.cuda.get_device_capability(i)[0]}{torch.cuda.get_device_capability(i)[1]})')
else:
    print('  WARNING: CUDA not available — will run on CPU')
"

# ── 3. Core CV dependencies ─────────────────────────────────────────────────
echo "[3/6] Installing core dependencies..."
"$PIP" install -q \
    "opencv-python-headless>=4.9.0" \
    "numpy>=1.26.0" \
    "ultralytics>=8.4.0" \
    "onnxruntime-gpu>=1.17.0" \
    "lap>=0.5.12"

# ByteTrack (install after lap to avoid lap==0.4.0 pin)
"$PIP" install bytetracker --no-deps -q

# ── 4. Pose estimation (mmpose via openmim) ──────────────────────────────────
echo "[4/6] Installing pose estimation stack (mmpose + mmcv)..."
"$PIP" install -q "openmim>=0.3.9"
"$VENV_DIR/bin/mim" install mmengine mmcv 2>/dev/null || true
"$PIP" install -q "mmpose>=1.3.0" "mmdet>=3.0.0"

# ── 5. OCR + remaining deps ─────────────────────────────────────────────────
echo "[5/6] Installing OCR + API + notebook dependencies..."
"$PIP" install -q \
    "paddlepaddle-gpu>=2.6.0" \
    "paddleocr>=2.7.3,<3.0.0" \
    "fastapi[standard]>=0.110.0" \
    "uvicorn[standard]>=0.29.0" \
    "celery>=5.3.6" \
    "redis>=5.0.3" \
    "sqlalchemy>=2.0.28" \
    "psycopg2-binary>=2.9.9" \
    "google-cloud-storage>=2.16.0" \
    "jupyter>=1.0.0" \
    "jupyterlab>=4.0.0" \
    "matplotlib>=3.8.3" \
    "pandas>=2.2.1" \
    "tqdm>=4.66.2" \
    "ipywidgets>=8.0.0" \
    "ipympl>=0.9.0" \
    "pytest>=8.1.0" \
    "pytest-cov>=5.0.0"

# ── 6. Verify key imports ────────────────────────────────────────────────────
echo "[6/6] Verifying imports..."
"$PY" -c "
import cv2, torch, ultralytics, mmpose
print(f'  opencv:      {cv2.__version__}')
print(f'  torch:       {torch.__version__} (CUDA {torch.version.cuda})')
print(f'  ultralytics: {ultralytics.__version__}')
print(f'  mmpose:      {mmpose.__version__}')
try:
    import paddleocr
    print(f'  paddleocr:   {paddleocr.__version__}')
except Exception as e:
    print(f'  paddleocr:   FAILED ({e})')
print('  All good.')
"

echo ""
echo "=== Install complete ==="
echo ""
echo "Activate:  source $VENV_DIR/bin/activate"
echo ""
echo "Run pipeline:"
echo "  python pipeline-poc/scripts/run_full_pipeline.py data/raw_footage/shuttles_test_behind.mp4"
echo ""
echo "Run notebook (remote access):"
echo "  jupyter lab --ip 0.0.0.0 --port 8888 --no-browser --notebook-dir pipeline-poc/notebooks"
echo ""
