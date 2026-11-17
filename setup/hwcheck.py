"""Aurora Companion setup - hardware check and model recommendation.

Standard library only (runs before any packages are installed).
Run directly to print a report without changing anything:

    python setup/hwcheck.py          (human readable)
    python setup/hwcheck.py --json   (machine readable)
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

IS_WINDOWS = os.name == "nt"
IS_MAC = platform.system() == "Darwin"
APP_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://127.0.0.1:11434"
GEMMA_12B = "hf.co/HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced:Q4_K_M"

# ---------------------------------------------------------------------------
# Tiers. size_gb = approximate download of the chat model(s).
# force_cpu -> profiles/performance.json  force_ollama_cpu
# ---------------------------------------------------------------------------
TIERS = {
    "tiny": {
        "order": 0,
        "label": "Tiny - older or 4 GB laptops",
        "model": "llama3.2:1b",
        "model_cpu": "llama3.2:1b",
        "force_cpu": True,
        "whisper": "tiny",
        "num_ctx": 2048,
        "size_gb": 1.32,
        "blurb": "Smallest local model (Llama 3.2 1B). Runs on almost anything, "
                 "but replies are simpler and can be slow on old CPUs.",
    },
    "light": {
        "order": 1,
        "label": "Light - CPU only, 8 GB RAM or more",
        "model": "llama3.2:3b",
        "model_cpu": "llama3.2:3b",
        "force_cpu": True,
        "whisper": "base",
        "num_ctx": 2048,
        "size_gb": 2.02,
        "blurb": "Llama 3.2 3B on the processor. Good balance for normal laptops "
                 "without a gaming graphics card.",
    },
    "cpu_plus": {
        "order": 2,
        "label": "CPU Plus - strong CPU, 16 GB RAM or more",
        "model": "dolphin3:latest",
        "model_cpu": "dolphin3:latest",
        "force_cpu": True,
        "whisper": "base",
        "num_ctx": 2048,
        "size_gb": 4.92,
        "blurb": "Dolphin 3 (8B) on the processor. Better replies, needs a fast "
                 "modern CPU and plenty of memory.",
    },
    "gpu_small": {
        "order": 3,
        "label": "GPU Small - NVIDIA with 4-6 GB",
        "model": "llama3.2:3b",
        "model_cpu": "llama3.2:3b",
        "force_cpu": False,
        "whisper": "base",
        "num_ctx": 4096,
        "size_gb": 2.02,
        "blurb": "Llama 3.2 3B on the graphics card. Fast replies on smaller GPUs.",
    },
    "gpu_mid": {
        "order": 4,
        "label": "GPU - NVIDIA with 6-10 GB (or Apple Silicon 16 GB+)",
        "model": "dolphin3:latest",
        "model_cpu": "llama3.2:3b",
        "force_cpu": False,
        "whisper": "small",
        "num_ctx": 4096,
        "size_gb": 6.94,
        "blurb": "Dolphin 3 (8B) on the graphics card, plus Llama 3.2 3B as a "
                 "light backup for CPU mode.",
    },
    "gpu_high": {
        "order": 5,
        "label": "GPU High - NVIDIA with 11 GB+ (or Apple Silicon 32 GB+)",
        "model": GEMMA_12B,
        "model_cpu": "llama3.2:3b",
        "force_cpu": False,
        "whisper": "small",
        "num_ctx": 8192,
        "size_gb": 9.58,
        "blurb": "Gemma 4 12B (community build from Hugging Face) on the graphics "
                 "card - the best quality, the same model the developer uses. "
                 "Plus Llama 3.2 3B as a CPU backup.",
    },
    "cloud": {
        "order": -1,
        "label": "Cloud only - no local AI model (needs your own xAI API key)",
        "model": "llama3.2:1b",
        "model_cpu": "llama3.2:1b",
        "force_cpu": True,
        "whisper": "tiny",
        "num_ctx": 2048,
        "size_gb": 0.0,
        "skip_ollama": True,
        "blurb": "Installs no local chat model. You add your own xAI (Grok) API key "
                 "inside the app; your messages are sent to xAI. Best for very weak PCs.",
    },
}
LOCAL_TIER_ORDER = ["tiny", "light", "cpu_plus", "gpu_small", "gpu_mid", "gpu_high"]

# ---------------------------------------------------------------------------
# Approximate sizes in MB (checked Nov 2026 against the official sources:
# ollama.com library / registry manifests, huggingface.co file listings,
# github.com/rhasspy/piper releases, python.org). Download ~= installed for models.
# ---------------------------------------------------------------------------
MODEL_MB = {
    "llama3.2:1b": 1321,
    "llama3.2:3b": 2019,
    "dolphin3:latest": 4921,
    GEMMA_12B: 7556,          # 7,381 MB Q4_K_M gguf + 175 MB vision projector
}
WHISPER_MB = {"tiny": 78, "base": 148, "small": 486, "medium": 1531}  # Systran/faster-whisper-*
COMPONENT_MB = {
    # name: (download MB, installed MB)
    "python": (26, 110),          # python-3.11.9-amd64.exe, per-user install
    "packages": (220, 700),       # requirements.txt wheels into .venv
    "piper": (22, 39),            # piper_windows_amd64.zip 2023.11.14-2
    "ollama": (1858, 3200),       # OllamaSetup.exe (includes GPU runtimes)
    "knowledge_index": (0, 190),  # book index built by the app on first chat
}
OPTIONAL_VOICE_MB = {
    "en_US-libritts_r-medium": 79,
    "en_US-amy-medium": 63,
    "en_US-ryan-medium": 63,
}
BUNDLED_VOICE_MB = 64  # en_US-robert-medium (ships with the app)
WHISPER_GB = {k: v / 1000 for k, v in WHISPER_MB.items()}
OLLAMA_INSTALL_GB = (COMPONENT_MB["ollama"][0] + COMPONENT_MB["ollama"][1]) / 1000  # setup file + install
BASE_INSTALL_GB = (COMPONENT_MB["packages"][1] + COMPONENT_MB["piper"][1]
                   + COMPONENT_MB["knowledge_index"][1]) / 1000


def _run(cmd, timeout=15) -> str:
    try:
        kw = {}
        if IS_WINDOWS:
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _ps(script: str, timeout=20) -> str:
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)


def ram_gb() -> float | None:
    try:
        if IS_WINDOWS:
            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMSTAT()
            m.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 1024 ** 3, 1)
        if IS_MAC:
            return round(int(_run(["sysctl", "-n", "hw.memsize"]) or 0) / 1024 ** 3, 1) or None
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1024 ** 2, 1)
    except Exception:
        pass
    return None


def cpu_info() -> dict:
    info = {"name": platform.processor() or "", "logical": os.cpu_count() or 0,
            "physical": None, "avx": None, "avx2": None, "arch": platform.machine()}
    arch = (platform.machine() or "").lower()
    if IS_WINDOWS:
        k32 = ctypes.windll.kernel32
        try:
            info["avx"] = bool(k32.IsProcessorFeaturePresent(39))   # PF_AVX_INSTRUCTIONS_AVAILABLE
            info["avx2"] = bool(k32.IsProcessorFeaturePresent(40))  # PF_AVX2_INSTRUCTIONS_AVAILABLE
        except Exception:
            pass
        out = _ps("Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores | "
                  "ConvertTo-Json -Compress")
        try:
            d = json.loads(out)
            info["name"] = (d.get("Name") or info["name"]).strip()
            info["physical"] = d.get("NumberOfCores")
        except Exception:
            pass
    elif IS_MAC:
        info["name"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or info["name"]
        try:
            info["physical"] = int(_run(["sysctl", "-n", "hw.physicalcpu"]) or 0) or None
        except Exception:
            pass
        if arch in ("arm64", "aarch64"):
            info["avx"] = info["avx2"] = None  # not applicable on Apple Silicon
        else:
            feats = (_run(["sysctl", "-n", "machdep.cpu.features"]) + " " +
                     _run(["sysctl", "-n", "machdep.cpu.leaf7_features"])).upper()
            info["avx"] = "AVX1.0" in feats or " AVX " in f" {feats} "
            info["avx2"] = "AVX2" in feats
    else:
        try:
            txt = Path("/proc/cpuinfo").read_text(errors="ignore")
            flags = re.search(r"^flags\s*:\s*(.*)$", txt, re.M)
            fl = set(flags.group(1).split()) if flags else set()
            info["avx"] = "avx" in fl
            info["avx2"] = "avx2" in fl
            name = re.search(r"^model name\s*:\s*(.*)$", txt, re.M)
            if name:
                info["name"] = name.group(1).strip()
        except Exception:
            pass
    return info


def gpu_info() -> dict:
    """NVIDIA via nvidia-smi; otherwise names (and registry VRAM) via WMI on Windows."""
    res = {"nvidia": False, "name": "", "vram_mb": None, "all": [], "apple_silicon": False}
    smi = shutil.which("nvidia-smi")
    if not smi and IS_WINDOWS:
        cand = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        smi = str(cand) if cand.exists() else None
    if smi:
        out = _run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        best = None
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    mb = int(float(parts[1]))
                except ValueError:
                    continue
                res["all"].append(f"{parts[0]} ({mb} MB)")
                if best is None or mb > best[1]:
                    best = (parts[0], mb)
        if best:
            res.update(nvidia=True, name=best[0], vram_mb=best[1])
            return res
    if IS_WINDOWS:
        out = _ps(
            "$r=@(); Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\"
            "{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' -ErrorAction SilentlyContinue | ForEach-Object {"
            " $m=$_.'HardwareInformation.qwMemorySize'; if(-not $m){$m=0};"
            " $r += [pscustomobject]@{Name=$_.DriverDesc; MB=[int64]($m/1MB)} }; $r | ConvertTo-Json -Compress")
        try:
            items = json.loads(out) if out else []
            if isinstance(items, dict):
                items = [items]
            for it in items:
                name = (it.get("Name") or "").strip()
                if not name:
                    continue
                mb = int(it.get("MB") or 0) or None
                res["all"].append(f"{name}" + (f" ({mb} MB)" if mb else ""))
                if "nvidia" in name.lower() and mb:
                    # driver present but nvidia-smi missing - still usable by Ollama
                    if not res["nvidia"] or mb > (res["vram_mb"] or 0):
                        res.update(nvidia=True, name=name, vram_mb=mb)
            if not res["name"] and res["all"]:
                res["name"] = res["all"][0]
        except Exception:
            pass
    elif IS_MAC and platform.machine() in ("arm64", "aarch64"):
        res.update(apple_silicon=True, name="Apple Silicon (unified memory)")
    return res


def disk_free_gb(path: Path = APP_ROOT) -> float | None:
    try:
        return round(shutil.disk_usage(str(path)).free / 1024 ** 3, 1)
    except Exception:
        return None


def ollama_exe() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    if IS_WINDOWS:
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if p.exists():
            return str(p)
    if IS_MAC:
        for p in ("/usr/local/bin/ollama", "/opt/homebrew/bin/ollama",
                  "/Applications/Ollama.app/Contents/Resources/ollama"):
            if Path(p).exists():
                return p
    return None


def ollama_models(url: str = OLLAMA_URL) -> list[str] | None:
    """Installed model tags, or None if the Ollama server is not reachable."""
    try:
        with urlopen(f"{url}/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return None


def detect() -> dict:
    os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
    if IS_WINDOWS:
        try:
            build = int(platform.version().split(".")[2])
            os_name = f"Windows {'11' if build >= 22000 else '10'} (build {build})"
        except Exception:
            pass
    hw = {
        "os": os_name,
        "python": sys.version.split()[0],
        "ram_gb": ram_gb(),
        "cpu": cpu_info(),
        "gpu": gpu_info(),
        "disk_free_gb": disk_free_gb(),
        "app_root": str(APP_ROOT),
        "ollama_exe": ollama_exe(),
        "ollama_models": ollama_models(),
    }
    return hw


def tier_need_gb(key: str, have_ollama: bool) -> float:
    t = TIERS[key]
    need = BASE_INSTALL_GB + t["size_gb"] + WHISPER_GB.get(t["whisper"], 0.2)
    if not have_ollama and not t.get("skip_ollama"):
        need += OLLAMA_INSTALL_GB
    return round(need, 1)


def recommend(hw: dict) -> dict:
    """Return {'tier': key, 'reasons': [...], 'warnings': [...]}."""
    ram = hw.get("ram_gb") or 0
    cpu = hw.get("cpu") or {}
    gpu = hw.get("gpu") or {}
    cores = cpu.get("physical") or max(1, (cpu.get("logical") or 2) // 2)
    is_x86 = (cpu.get("arch") or "").lower() in ("amd64", "x86_64", "x64", "i386", "i686", "x86")
    avx, avx2 = cpu.get("avx"), cpu.get("avx2")
    vram = gpu.get("vram_mb") or 0
    reasons, warnings = [], []

    if is_x86 and avx is False:
        tier = "tiny"
        reasons.append("This processor has no AVX instructions, so local AI runs in the slowest mode.")
    elif ram and ram < 6:
        tier = "tiny"
        reasons.append(f"Only about {ram:g} GB of memory - the smallest model is safest.")
    elif gpu.get("apple_silicon"):
        tier = "gpu_high" if ram >= 32 else "gpu_mid" if ram >= 16 else "light"
        reasons.append(f"Apple Silicon with {ram:g} GB unified memory.")
    elif gpu.get("nvidia") and vram >= 11000 and ram >= 16:
        tier = "gpu_high"
        reasons.append(f"{gpu.get('name')} with about {round(vram / 1024)} GB of video memory.")
    elif gpu.get("nvidia") and vram >= 6000 and ram >= 8:
        tier = "gpu_mid"
        reasons.append(f"{gpu.get('name')} with about {round(vram / 1024)} GB of video memory.")
    elif gpu.get("nvidia") and vram >= 3800:
        tier = "gpu_small"
        reasons.append(f"{gpu.get('name')} with about {round(vram / 1024)} GB of video memory.")
    elif ram >= 16 and avx2 and cores >= 6:
        tier = "cpu_plus"
        reasons.append(f"No suitable NVIDIA graphics card, but a strong {cores}-core CPU and {ram:g} GB memory.")
    elif ram >= 6:
        tier = "light"
        reasons.append(f"No suitable NVIDIA graphics card; {ram:g} GB memory and {cores} CPU cores.")
    else:
        tier = "tiny"
        reasons.append("Could not read the memory size - choosing the safest option.")

    if is_x86 and avx2 is False and avx:
        warnings.append("CPU lacks AVX2 - local AI will be slower than on newer PCs.")
    if cores and cores <= 4 and not gpu.get("nvidia") and not gpu.get("apple_silicon"):
        warnings.append(f"Only {cores} CPU cores - expect replies to take a while.")

    # Step down until it fits on the disk
    have_ollama = bool(hw.get("ollama_exe"))
    free = hw.get("disk_free_gb")
    if free is not None:
        order = LOCAL_TIER_ORDER
        idx = order.index(tier)
        while idx > 0 and tier_need_gb(order[idx], have_ollama) > free - 2:
            idx -= 1
        if order[idx] != tier:
            warnings.append(f"Only {free:g} GB free disk space - picked a smaller model.")
            tier = order[idx]
        if tier_need_gb(tier, have_ollama) > free - 1:
            warnings.append(f"Low disk space ({free:g} GB free). Free up space or choose Cloud only.")
    return {"tier": tier, "reasons": reasons, "warnings": warnings}


def summary_lines(hw: dict) -> list[str]:
    cpu, gpu = hw.get("cpu") or {}, hw.get("gpu") or {}

    def yn(v):
        return "n/a" if v is None else ("yes" if v else "no")

    cores = cpu.get("physical")
    lines = [
        f"System:      {hw.get('os')}",
        f"Processor:   {cpu.get('name') or 'unknown'}  ({cores or '?'} cores / {cpu.get('logical')} threads)",
        f"AVX / AVX2:  {yn(cpu.get('avx'))} / {yn(cpu.get('avx2'))}",
        f"Memory:      {hw.get('ram_gb') or '?'} GB",
        f"Graphics:    {gpu.get('name') or 'none detected'}"
        + (f"  ({gpu.get('vram_mb')} MB)" if gpu.get("vram_mb") else ""),
        f"Free disk:   {hw.get('disk_free_gb') or '?'} GB  (on the drive with this folder)",
        f"Ollama:      {'already installed' if hw.get('ollama_exe') else 'not installed yet'}",
    ]
    if gpu.get("all") and len(gpu["all"]) > 1:
        lines.append("All GPUs:    " + "; ".join(gpu["all"]))
    return lines


if __name__ == "__main__":
    hw = detect()
    rec = recommend(hw)
    if "--json" in sys.argv:
        print(json.dumps({"hardware": hw, "recommendation": rec,
                          "tier": TIERS[rec["tier"]]}, indent=2))
    else:
        print("\n".join(summary_lines(hw)))
        t = TIERS[rec["tier"]]
        print(f"\nRecommended: {t['label']}")
        print(f"  Chat model:   {t['model']}  (~{t['size_gb']} GB)")
        print(f"  CPU model:    {t['model_cpu']}   force CPU: {t['force_cpu']}")
        print(f"  Speech (STT): whisper {t['whisper']}")
        for r in rec["reasons"]:
            print("  why: " + r)
        for w in rec["warnings"]:
            print("  note: " + w)
        if hw.get("ollama_models") is not None:
            print(f"\nOllama models already on this PC: {len(hw['ollama_models'])}")
