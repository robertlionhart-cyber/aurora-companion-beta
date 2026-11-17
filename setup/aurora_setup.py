"""Aurora Companion - beta setup wizard.

Started by Setup.bat (Windows) or Setup.command (Mac). Needs only the Python
standard library (tkinter). Everything is installed for the current user only:

  .venv/            private Python packages (requirements.txt)
  piper.exe + DLLs  Piper text-to-speech  (github.com/rhasspy/piper)
  voices/           Piper voices          (huggingface.co/rhasspy/piper-voices)
  Ollama            local AI runtime      (ollama.com) - per-user install
  Ollama model(s)   picked from the hardware check
  Whisper model     speech recognition, pre-downloaded into the user cache

Command line (for testing / support):
  python setup/aurora_setup.py --check            hardware report, changes nothing
  python setup/aurora_setup.py --plan [--tier X]  show what would be installed
  python setup/aurora_setup.py --unattended --accept-disclaimer [--tier X]
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hwcheck  # noqa: E402

APP_NAME = "Aurora Companion"
APP_VERSION = "0.9.6-beta"
SETUP_VERSION = "beta-setup 1.1"
IS_WINDOWS = os.name == "nt"
IS_MAC = platform.system() == "Darwin"
APP_ROOT = hwcheck.APP_ROOT
VENV = APP_ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
VENV_PYW = VENV / ("Scripts/pythonw.exe" if IS_WINDOWS else "bin/python")
LOGS = APP_ROOT / "logs"
PROFILES = APP_ROOT / "profiles"
STATE_PATH = APP_ROOT / "setup_state.json"
CONFIG_PATH = APP_ROOT / "aurora_config.json"
UA = {"User-Agent": "AuroraCompanionSetup/1.0"}
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

# --- Official download sources -------------------------------------------------
PIPER_TAG = "2023.11.14-2"
PIPER_BASE = f"https://github.com/rhasspy/piper/releases/download/{PIPER_TAG}/"
PIPER_ASSETS = {
    # name: (file, sha256 or None)
    "windows": ("piper_windows_amd64.zip",
                "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea"),
    "mac_arm": ("piper_macos_aarch64.tar.gz", None),
    "mac_x64": ("piper_macos_x64.tar.gz", None),
    "linux_x64": ("piper_linux_x86_64.tar.gz", None),
}
# Pinned to the v1.0.0 tag: newer voices on "main" were retrained for Piper 1.5 and their
# configs crash the 2023.11.14-2 piper.exe ("Phonemes must be one codepoint").
VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
# Robert's own voice ships inside the app folder (voices/) and is the default voice.
BUNDLED_VOICE = ("en_US-robert-medium",
                 "636bddae98651bc7749636682bba04bffc0dad033157b6eb3231437e0db2519b",
                 "8be212ec0ebdc97e08ed61554eb4a13b4a144fceb57bab36b23d1b4f1213d435")
VOICES_PAGE = "https://huggingface.co/rhasspy/piper-voices"
# Optional extra voices (user ticks them on the review screen)
VOICES = [
    # (voice id, path in repo, sha256 .onnx, sha256 .onnx.json)
    ("en_US-libritts_r-medium", "en/en_US/libritts_r/medium/",
     "10bb85e071d616fcf4071f369f1799d0491492ab3c5d552ec19fb548fac13195",
     "b471dc60d2d8335e819c393d196d6fbf792817f40051257b269878505bc9afb3"),
    ("en_US-amy-medium", "en/en_US/amy/medium/",
     "b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18",
     "95a23eb4d42909d38df73bb9ac7f45f597dbfcde2d1bf9526fdeaf5466977d77"),
    ("en_US-ryan-medium", "en/en_US/ryan/medium/",
     "abf4c274862564ed647ba0d2c47f8ee7c9b717d27bdad9219100eb310db4047a",
     "44034c056cb15681b2ad494307c7f3f2e4499d1253c700c711fa0a4607ffe78d"),
]
OLLAMA_WIN_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_MAC_URL = "https://ollama.com/download/Ollama-darwin.zip"


# ==================================================================== helpers
class SetupError(Exception):
    pass


class Log:
    def __init__(self, sink=None):
        self.sink = sink
        LOGS.mkdir(parents=True, exist_ok=True)
        self.path = LOGS / f"setup_{datetime.now():%Y-%m-%d_%H%M%S}.log"
        self.f = open(self.path, "a", encoding="utf-8")

    def __call__(self, msg: str):
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        self.f.write(line + "\n")
        self.f.flush()
        if self.sink:
            self.sink(("log", msg))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_PREFER_CURL = False  # set after the first certificate error so later downloads skip urllib


def _curl_exe():
    if not IS_WINDOWS:
        return None
    c = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
    return str(c) if c.exists() else shutil.which("curl.exe")


def _curl_download(url: str, part: Path, log, progress=None):
    cmd = [_curl_exe(), "-L", "--fail", "--retry", "3", "--retry-delay", "3", "-sS",
           "-A", UA["User-Agent"], "-o", str(part), url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         creationflags=NO_WINDOW)
    while p.poll() is None:
        if progress and part.exists():
            progress(part.stat().st_size, 0)
        time.sleep(0.5)
    out = (p.stdout.read() or "").strip() if p.stdout else ""
    if p.returncode != 0:
        raise SetupError(f"Could not download {url}\ncurl: {out or p.returncode}")
    log("  downloaded with curl.exe")


def download(url: str, dest: Path, log, progress=None, expect_sha=None, min_bytes=1000):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    log(f"Downloading {url}")
    last = 0.0
    global _PREFER_CURL
    use_curl = _PREFER_CURL
    for attempt in range(1, 4):
        if use_curl:
            _curl_download(url, part, log, progress)
            break
        try:
            with urlopen(Request(url, headers=UA), timeout=60) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    buf = r.read(1 << 18)
                    if not buf:
                        break
                    f.write(buf)
                    done += len(buf)
                    if progress and time.time() - last > 0.25:
                        last = time.time()
                        progress(done, total)
            break
        except Exception as e:
            if IS_WINDOWS and "CERTIFICATE_VERIFY_FAILED" in str(e) and _curl_exe():
                # Fresh Windows installs often lack some root certificates until Windows fetches
                # them on demand. Python can't trigger that, but Windows' own curl.exe can.
                log("  using Windows' built-in downloader (curl.exe) for secure downloads")
                _PREFER_CURL = use_curl = True
                _curl_download(url, part, log, progress)
                break
            log(f"  download attempt {attempt} failed: {e}")
            if attempt == 3:
                raise SetupError(f"Could not download {url}\n{e}")
            time.sleep(3 * attempt)
    if part.stat().st_size < min_bytes:
        raise SetupError(f"Download looks broken (too small): {url}")
    if expect_sha:
        got = sha256(part)
        if got.lower() != expect_sha.lower():
            part.unlink(missing_ok=True)
            raise SetupError(f"Checksum mismatch for {dest.name} - download corrupted, please retry.")
        log("  checksum OK")
    os.replace(part, dest)
    return dest


def run(cmd, log, cwd=None, env=None, check=True) -> int:
    log("> " + " ".join(str(c) for c in cmd))
    p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace",
                         creationflags=NO_WINDOW)
    last = ""
    for line in p.stdout:
        line = line.rstrip()
        if line:
            log("  " + line)
            last = line.strip()
    rc = p.wait()
    if check and rc != 0:
        hint = ""
        if "PortAudio" in last and not IS_WINDOWS and not IS_MAC:
            hint = "\nInstall the audio library first:  sudo apt install libportaudio2"
        raise SetupError(f"A setup command failed (exit {rc}).\nLast message: {last[:300]}{hint}")
    return rc


def ollama_api(path: str, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(hwcheck.OLLAMA_URL + path, data=data, headers={**UA, "Content-Type": "application/json"})
    return urlopen(req, timeout=timeout)


def _ollama_tray_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ollama app.exe", "/NH"], capture_output=True,
                             text=True, creationflags=NO_WINDOW, timeout=20).stdout
        return "ollama app.exe" in out.lower()
    except Exception:
        return False


def ollama_up() -> bool:
    try:
        with ollama_api("/api/version", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def unique(seq):
    out = []
    for s in seq:
        if s and s not in out:
            out.append(s)
    return out


def models_for(tier_key: str) -> list[str]:
    t = hwcheck.TIERS[tier_key]
    if t.get("skip_ollama"):
        return []
    return unique([t["model"], t["model_cpu"]])


# ==================================================================== sizes
def size_plan(tier_key: str, hw: dict, voices, knowledge: bool):
    """Rows of (component, download MB, installed MB, note) for the review screen."""
    t = hwcheck.TIERS[tier_key]
    C = hwcheck.COMPONENT_MB
    rows = []
    py_new = os.environ.get("AURORA_PY_INSTALLED") == "1"
    rows.append(("Python 3.11 (python.org)", C["python"][0] if py_new else 0, C["python"][1] if py_new else 0,
                 "installed by Setup just now" if py_new else "already on this PC - nothing to download"))
    have_venv = VENV_PY.exists()
    rows.append(("Python packages (pypi.org) - faster-whisper, OpenCV, NumPy ...",
                 0 if have_venv else C["packages"][0], 0 if have_venv else C["packages"][1],
                 "already installed" if have_venv else "private copy in .venv"))
    have_piper = (APP_ROOT / ("piper.exe" if IS_WINDOWS else "piper")).exists()
    rows.append((f"Piper voice engine {PIPER_TAG} (github.com/rhasspy/piper)",
                 0 if have_piper else C["piper"][0], 0 if have_piper else C["piper"][1],
                 "already installed" if have_piper else ""))
    rows.append(("Voice: Robert (en_US-robert-medium)", 0, hwcheck.BUNDLED_VOICE_MB, "included with the app"))
    for v in voices:
        mb = hwcheck.OPTIONAL_VOICE_MB.get(v, 65)
        rows.append((f"Voice: {v} (rhasspy/piper-voices)", mb, mb, "optional"))
    if not t.get("skip_ollama"):
        have_ollama = bool(hw.get("ollama_exe"))
        rows.append(("Ollama local AI runtime (ollama.com)", 0 if have_ollama else C["ollama"][0],
                     0 if have_ollama else C["ollama"][1], "already installed" if have_ollama else
                     "the setup file is deleted after install"))
        installed = hw.get("ollama_models") or []
        for m in models_for(tier_key):
            mb = hwcheck.MODEL_MB.get(m, 2000)
            have = m in installed
            label = f"AI model: {m}" if not m.startswith("hf.co/") else \
                f"AI model: {m.split('/')[-1]} (Hugging Face)"
            rows.append((label, 0 if have else mb, 0 if have else mb,
                         "already downloaded" if have else ("main model" if m == t["model"] else "CPU backup")))
    wmb = hwcheck.WHISPER_MB.get(t["whisper"], 150)
    rows.append((f"Speech recognition: Whisper {t['whisper']} (huggingface.co/Systran)", wmb, wmb, ""))
    if knowledge:
        rows.append(("Book library index (83 public-domain books, built by the app)", 0,
                     C["knowledge_index"][1], "uses about 1.5 GB of memory while chatting"))
    return rows


def size_totals(rows):
    return sum(r[1] for r in rows), sum(r[2] for r in rows)


def fmt_mb(mb: float) -> str:
    if not mb:
        return "-"
    return f"{mb / 1000:.1f} GB" if mb >= 1000 else f"{mb:.0f} MB"


DISCRETION_TEXT = (
    "These components are downloaded automatically from their official sources at YOUR OWN DISCRETION. "
    "The author of Aurora Companion does not own the rights to these third-party apps, models or "
    "voices - they belong to their respective owners and are provided under their own licenses. "
    "Sizes are approximate."
)


# ==================================================================== steps
class Installer:
    def __init__(self, tier_key: str, log, status=None, progress=None,
                 shortcut=True, prefetch_whisper=True, voices=None, knowledge=True):
        self.voices = list(voices or [])
        self.knowledge = bool(knowledge)
        self.tier_key = tier_key
        self.tier = hwcheck.TIERS[tier_key]
        self.log = log
        self.status = status or (lambda s: None)
        self.progress = progress or (lambda d, t: None)
        self.shortcut = shortcut
        self.prefetch_whisper = prefetch_whisper

    def steps(self):
        s = [("Python packages (private copy)", self.step_venv),
             ("Piper voice engine", self.step_piper),
             ("Voices", self.step_voices)]
        if not self.tier.get("skip_ollama"):
            s += [("Ollama (local AI runtime)", self.step_ollama),
                  ("AI chat model(s)", self.step_models)]
        if self.prefetch_whisper:
            s.append(("Speech recognition model", self.step_whisper))
        s.append(("Saving settings", self.step_config))
        if self.shortcut:
            s.append(("Shortcuts", self.step_shortcut))
        return s

    # -- 1. venv -------------------------------------------------------------
    def step_venv(self):
        if not VENV_PY.exists():
            self.log(f"Creating private Python environment in {VENV}")
            run([sys.executable, "-m", "venv", str(VENV)], self.log)
        run([VENV_PY, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check"], self.log)
        run([VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "-r",
             APP_ROOT / "requirements.txt"], self.log)
        run([VENV_PY, "-c", "import sounddevice, numpy, faster_whisper, ollama, PIL, cv2; print('imports OK')"],
            self.log)

    # -- 2. piper ------------------------------------------------------------
    def _piper_asset(self):
        if IS_WINDOWS:
            return PIPER_ASSETS["windows"]
        if IS_MAC:
            return PIPER_ASSETS["mac_arm" if platform.machine() in ("arm64", "aarch64") else "mac_x64"]
        return PIPER_ASSETS["linux_x64"]

    def step_piper(self):
        exe = APP_ROOT / ("piper.exe" if IS_WINDOWS else "piper")
        if exe.exists() and (APP_ROOT / "espeak-ng-data").exists():
            self.log("Piper already present - skipping.")
            return
        name, sha = self._piper_asset()
        with tempfile.TemporaryDirectory() as td:
            arc = download(PIPER_BASE + name, Path(td) / name, self.log, self.progress, sha)
            out = Path(td) / "x"
            if name.endswith(".zip"):
                with zipfile.ZipFile(arc) as z:
                    z.extractall(out)
            else:
                with tarfile.open(arc) as t:
                    t.extractall(out)
            src = out / "piper"
            if not src.exists():
                raise SetupError("Piper archive layout not recognised.")
            for item in src.iterdir():
                dest = APP_ROOT / item.name
                if dest.exists():
                    continue
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        if not IS_WINDOWS:
            os.chmod(exe, 0o755)
        self.log("Piper installed.")

    # -- 3. voices -----------------------------------------------------------
    def step_voices(self):
        vdir = APP_ROOT / "voices"
        vdir.mkdir(exist_ok=True)
        vid, sha_o, sha_j = BUNDLED_VOICE
        if (vdir / f"{vid}.onnx").exists() and sha256(vdir / f"{vid}.onnx") == sha_o:
            self.log(f"Bundled voice OK: {vid}")
        else:
            self.log(f"(warning) bundled voice {vid} is missing or changed - re-download the app folder.")
        for vid, rel, sha_onnx, sha_json in VOICES:
            if vid not in self.voices:
                continue
            for ext, sha in ((".onnx", sha_onnx), (".onnx.json", sha_json)):
                dest = vdir / f"{vid}{ext}"
                if dest.exists() and sha256(dest) == sha:
                    continue
                self.status(f"Voice: {vid}")
                download(f"{VOICE_BASE}{rel}{vid}{ext}?download=true", dest, self.log, self.progress,
                         expect_sha=sha, min_bytes=500)
        self.log("Voices ready.")

    # -- 4. ollama -----------------------------------------------------------
    def step_ollama(self):
        exe = hwcheck.ollama_exe()
        if exe:
            self.log(f"Ollama already installed: {exe} (existing models are left untouched)")
        elif IS_WINDOWS:
            with tempfile.TemporaryDirectory() as td:
                inst = download(OLLAMA_WIN_URL, Path(td) / "OllamaSetup.exe", self.log, self.progress,
                                min_bytes=5_000_000)
                self.status("Installing Ollama (no admin needed). If an Ollama window or notification "
                            "pops up, you can close it - setup handles everything.")
                self.log("Note: Ollama may show its own welcome popup (\"run ollama in a terminal\"). "
                         "You can close it; you don't need to type anything.")
                run([inst, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"], self.log, check=False)
            exe = hwcheck.ollama_exe()
            if not exe:
                raise SetupError("Ollama did not install. Please install it from https://ollama.com/download "
                                 "and run Setup again.")
        elif IS_MAC:
            apps = Path.home() / "Applications"
            apps.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory() as td:
                z = download(OLLAMA_MAC_URL, Path(td) / "Ollama-darwin.zip", self.log, self.progress,
                             min_bytes=5_000_000)
                run(["ditto", "-x", "-k", z, apps], self.log)
            run(["open", "-a", str(apps / "Ollama.app")], self.log, check=False)
            exe = str(apps / "Ollama.app/Contents/Resources/ollama")
        else:
            raise SetupError("Please install Ollama with:  curl -fsSL https://ollama.com/install.sh | sh  "
                             "then run setup again.")
        self.ollama_exe = exe
        self.ensure_ollama_running()

    def ensure_ollama_running(self):
        if ollama_up():
            return
        exe = getattr(self, "ollama_exe", None) or hwcheck.ollama_exe()
        if IS_WINDOWS and _ollama_tray_running():
            # The Ollama tray app ("ollama app.exe") starts its own server; on slow PCs that can take
            # a minute or two. Starting a second "ollama serve" would fight it for the port.
            self.status("Waiting for Ollama to start (can take a couple of minutes on slower PCs)...")
            for _ in range(180):
                if ollama_up():
                    self.log("Ollama is running (started by the Ollama app).")
                    return
                time.sleep(1)
        self.log("Starting the Ollama service...")
        flags = (0x00000008 | NO_WINDOW) if IS_WINDOWS else 0  # DETACHED_PROCESS
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags, start_new_session=not IS_WINDOWS)
        self.status("Starting Ollama (can take a couple of minutes on slower PCs)...")
        for _ in range(180):
            if ollama_up():
                self.log("Ollama is running.")
                return
            time.sleep(1)
        raise SetupError("Ollama did not start. Restart the PC and run Setup again.")

    # -- 5. models -----------------------------------------------------------
    def step_models(self):
        self.ensure_ollama_running()
        have = hwcheck.ollama_models() or []
        for m in models_for(self.tier_key):
            if m in have or (":" not in m and f"{m}:latest" in have):
                self.log(f"Model already installed: {m} - not touching it.")
                continue
            self.status(f"Downloading AI model {m} (this is the big one)...")
            self.log(f"Pulling {m}")
            last_status = ""
            with ollama_api("/api/pull", {"model": m, "stream": True}, timeout=600) as r:
                for raw in r:
                    try:
                        ev = json.loads(raw.decode("utf-8", "ignore"))
                    except Exception:
                        continue
                    if ev.get("error"):
                        raise SetupError(f"Ollama could not download {m}: {ev['error']}")
                    st = ev.get("status", "")
                    if st and st != last_status:
                        self.log("  " + st)
                        last_status = st
                    if ev.get("total"):
                        self.progress(ev.get("completed") or 0, ev["total"])
            if m not in (hwcheck.ollama_models() or []):
                self.log(f"  (warning) {m} not listed after pull - check Ollama.")
        self.log("Model(s) ready.")

    # -- 6. whisper ----------------------------------------------------------
    def step_whisper(self):
        size = self.tier["whisper"]
        self.status(f"Downloading speech recognition (whisper {size})...")
        run([VENV_PY, "-c",
             "from faster_whisper import WhisperModel; "
             f"WhisperModel('{size}', device='cpu', compute_type='int8'); print('whisper {size} ready')"],
            self.log, env=dict(os.environ, HF_HUB_DISABLE_SYMLINKS_WARNING="1", PYTHONWARNINGS="ignore",
                               HF_HUB_DISABLE_IMPLICIT_TOKEN="1"))

    # -- 7. config -----------------------------------------------------------
    def step_config(self):
        t = self.tier
        cfg = load_json(CONFIG_PATH, {})
        if not isinstance(cfg, dict):
            cfg = {}
        gpu_list = unique([t["model"], t["model_cpu"]])
        cpu_list = unique([t["model_cpu"]] + ([t["model"]] if t["force_cpu"] else []))
        cfg["ollama"] = {
            "model": t["model"],
            "model_cpu": t["model_cpu"],
            "active_gpu_model": t["model"],
            "active_cpu_model": t["model_cpu"],
            "gpu_models": gpu_list,
            "cpu_models": cpu_list,
            "num_ctx": int(t["num_ctx"]),
            "think": False,
            "url": hwcheck.OLLAMA_URL,
        }
        cfg["setup"] = {
            "tier": self.tier_key,
            "whisper_size": t["whisper"],
            "knowledge_library": self.knowledge,
            "default_voice": BUNDLED_VOICE[0],
            "extra_voices": self.voices,
            "app_version": APP_VERSION,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "setup_version": SETUP_VERSION,
        }
        write_json(CONFIG_PATH, cfg)
        write_json(PROFILES / "performance.json", {"force_ollama_cpu": bool(t["force_cpu"])})
        self.log(f"Wrote {CONFIG_PATH.name}: model={t['model']} cpu_model={t['model_cpu']} "
                 f"force_cpu={t['force_cpu']} whisper={t['whisper']} books={self.knowledge}")

    # -- 8. shortcuts --------------------------------------------------------
    def step_shortcut(self):
        if not IS_WINDOWS:
            self.log("Shortcuts: use Start_Aurora.command on Mac.")
            return
        def q(p):  # PowerShell single-quoted literal
            return "'" + str(p).replace("'", "''") + "'"

        ps = (
            "$s=New-Object -ComObject WScript.Shell;"
            "foreach($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))){"
            " $l=$s.CreateShortcut((Join-Path $d 'Aurora Companion.lnk'));"
            f" $l.TargetPath={q(VENV_PYW)}; $l.Arguments={q(chr(34) + str(APP_ROOT / 'Aurora_Companion.py') + chr(34))};"
            f" $l.WorkingDirectory={q(APP_ROOT)}; $l.IconLocation={q(APP_ROOT / 'aurora_icon.ico')};"
            " $l.Description='Aurora Companion'; $l.Save() }"
        )
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], self.log, check=False)
        self.log("Desktop and Start-menu shortcuts created.")


def save_state(**kw):
    st = load_json(STATE_PATH, {})
    if not isinstance(st, dict):
        st = {}
    st.update(kw)
    write_json(STATE_PATH, st)


# ==================================================================== GUI
def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    BG, PANEL, FG, DIM, ACC = "#0d0d12", "#16161e", "#f0f0f5", "#9a9aae", "#c45c8a"
    root = tk.Tk()
    root.title(f"{APP_NAME} {APP_VERSION} - Setup")
    root.geometry("820x640")
    root.minsize(720, 560)
    root.configure(bg=BG)
    try:
        root.iconbitmap(str(APP_ROOT / "aurora_icon.ico"))
    except Exception:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TProgressbar", troughcolor=PANEL, background=ACC)

    q: "queue.Queue" = queue.Queue()
    hw_holder = {}
    state = {"tier": tk.StringVar(), "agree": tk.BooleanVar(value=False),
             "shortcut": tk.BooleanVar(value=True), "books": None, "discretion": tk.BooleanVar(value=False),
             "voices": {v[0]: tk.BooleanVar(value=False) for v in VOICES}}
    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=24, pady=(18, 6))
    nav = tk.Frame(root, bg=BG)
    nav.pack(fill="x", padx=24, pady=(0, 16))

    def clear():
        for w in body.winfo_children():
            w.destroy()
        for w in nav.winfo_children():
            w.destroy()

    def title(text, sub=None):
        tk.Label(body, text=text, font=("Segoe UI", 20, "bold"), fg=FG, bg=BG).pack(anchor="w")
        if sub:
            tk.Label(body, text=sub, font=("Segoe UI", 11), fg=DIM, bg=BG, justify="left",
                     wraplength=760).pack(anchor="w", pady=(4, 12))

    def button(text, cmd, primary=True, side="right", state_="normal"):
        b = tk.Button(nav, text=text, command=cmd, font=("Segoe UI", 12, "bold" if primary else "normal"),
                      bg=ACC if primary else PANEL, fg="#ffffff", activebackground="#e07aa8",
                      relief="flat", padx=18, pady=6, cursor="hand2", state=state_)
        b.pack(side=side, padx=4)
        return b

    # ---- 1 welcome
    def page_welcome():
        clear()
        title(f"Welcome to {APP_NAME} {APP_VERSION}",
              "This setup gets everything ready for you. It will:\n\n"
              "  1.  Show you the third-party software notice\n"
              "  2.  Check what your computer can handle\n"
              "  3.  Show what will be downloaded and how big it is, so you can decide\n"
              "  4.  Download and install the voice engine, the local AI and a model that fits\n"
              "  5.  Create a desktop shortcut\n\n"
              "It installs for your Windows user only - no administrator password needed.\n"
              "You need an internet connection. Depending on your choice it downloads about 1 to 10 GB,\n"
              "so it can take a while. You can leave it running.")
        try:
            from tkinter import PhotoImage
            img = PhotoImage(file=str(APP_ROOT / "aurora_logo.png"))
            if img.width() > 300:
                img = img.subsample(max(1, img.width() // 300))
            lbl = tk.Label(body, image=img, bg=BG)
            lbl.image = img
            lbl.pack(pady=10)
        except Exception:
            pass
        button("Next  >", page_disclaimer)
        button("Cancel", root.destroy, primary=False, side="left")

    # ---- 2 disclaimer
    def page_disclaimer():
        clear()
        title("Please read and accept", "Third-party software and AI notice")
        frame = tk.Frame(body, bg=PANEL)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="word", bg=PANEL, fg=FG, relief="flat", font=("Consolas", 10),
                      padx=12, pady=10)
        sb = tk.Scrollbar(frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        try:
            txt.insert("1.0", (APP_ROOT / "DISCLAIMER.txt").read_text(encoding="utf-8"))
        except Exception:
            txt.insert("1.0", "DISCLAIMER.txt is missing - please re-download the app.")
        txt.configure(state="disabled")
        nxt = None

        def toggle():
            nxt.configure(state="normal" if state["agree"].get() else "disabled")

        tk.Checkbutton(body, text="I have read this and I agree", variable=state["agree"], command=toggle,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 12)).pack(anchor="w", pady=(10, 0))
        nxt = button("I agree  >", page_hw, state_="normal" if state["agree"].get() else "disabled")
        button("<  Back", page_welcome, primary=False, side="left")

    # ---- 3 hardware + choice
    def page_hw():
        save_state(disclaimer_accepted=True, disclaimer_accepted_at=datetime.now().isoformat(timespec="seconds"))
        clear()
        title("Checking your computer...", "This takes a few seconds.")
        root.update()
        if "hw" not in hw_holder:
            hw_holder["hw"] = hwcheck.detect()
            hw_holder["rec"] = hwcheck.recommend(hw_holder["hw"])
        page_choose()

    def page_choose():
        clear()
        hw, rec = hw_holder["hw"], hw_holder["rec"]
        title("Your computer", None)
        tk.Label(body, text="\n".join(hwcheck.summary_lines(hw)), font=("Consolas", 10), fg=FG, bg=PANEL,
                 justify="left", anchor="w", padx=10, pady=8).pack(fill="x")
        rt = hwcheck.TIERS[rec["tier"]]
        msg = "Recommended: " + rt["label"] + "\n" + " ".join(rec["reasons"])
        if rec["warnings"]:
            msg += "\nNote: " + " ".join(rec["warnings"])
        tk.Label(body, text=msg, font=("Segoe UI", 11, "bold"), fg="#7dcea0", bg=BG, justify="left",
                 wraplength=760).pack(anchor="w", pady=(10, 6))
        if not state["tier"].get():
            state["tier"].set(rec["tier"])
        box = tk.Frame(body, bg=BG)
        box.pack(fill="both", expand=True)
        keys = ["cloud"] + hwcheck.LOCAL_TIER_ORDER
        have = bool(hw.get("ollama_exe"))
        for k in keys:
            t = hwcheck.TIERS[k]
            star = "  (recommended)" if k == rec["tier"] else ""
            size = f"needs ~{hwcheck.tier_need_gb(k, have):.0f} GB free disk"
            tk.Radiobutton(box, text=f"{t['label']}{star}   [{size}]", value=k, variable=state["tier"],
                           bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 11, "bold" if star else "normal"),
                           anchor="w").pack(fill="x")
            tk.Label(box, text="      " + t["blurb"], font=("Segoe UI", 9), fg=DIM, bg=BG, justify="left",
                     wraplength=740, anchor="w").pack(fill="x")
        if state["books"] is None:
            ram = hw.get("ram_gb") or 0
            state["books"] = tk.BooleanVar(value=rec["tier"] not in ("tiny", "cloud") and ram >= 6)
        opts = tk.Frame(body, bg=BG)
        opts.pack(fill="x", pady=4)
        tk.Checkbutton(opts, text="Book library (83 public-domain books; needs ~1.5 GB extra memory)",
                       variable=state["books"], bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                       font=("Segoe UI", 10)).pack(side="left")
        tk.Checkbutton(opts, text="Desktop shortcut", variable=state["shortcut"], bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, font=("Segoe UI", 10)).pack(side="left", padx=16)

        def go():
            k = state["tier"].get()
            order = hwcheck.TIERS[k]["order"]
            if order > hwcheck.TIERS[rec["tier"]]["order"]:
                if not messagebox.askyesno("Bigger than recommended",
                                           "This choice is bigger than what we recommend for this PC.\n"
                                           "It may be very slow or fail to load. Continue anyway?"):
                    return
            page_review()

        button("Next  >", go)
        button("<  Back", page_disclaimer, primary=False, side="left")

    # ---- 3b review sizes + optional voices
    def page_review():
        clear()
        tier_key = state["tier"].get()
        title("Review downloads", "Approximate download and installed sizes for your choice "
              f"({hwcheck.TIERS[tier_key]['label']}).")
        tk.Label(body, text=DISCRETION_TEXT, font=("Segoe UI", 10), fg="#e0c070", bg=BG, justify="left",
                 wraplength=760).pack(anchor="w", pady=(0, 8))
        vbox = tk.Frame(body, bg=BG)
        vbox.pack(fill="x")
        tk.Label(vbox, text="Optional extra voices (Robert's voice is already included):",
                 font=("Segoe UI", 10, "bold"), fg=FG, bg=BG).pack(anchor="w")
        table = tk.Text(body, height=14, bg=PANEL, fg=FG, relief="flat", font=("Consolas", 9), padx=8, pady=6)

        def refresh():
            voices = [k for k, v in state["voices"].items() if v.get()]
            rows = size_plan(tier_key, hw_holder["hw"], voices, bool(state["books"].get()))
            dl, inst = size_totals(rows)
            table.configure(state="normal")
            table.delete("1.0", "end")
            table.insert("end", f"{'Component':<78}{'Download':>10}{'Installed':>11}\n")
            table.insert("end", "-" * 99 + "\n")
            for name, d, i, note in rows:
                table.insert("end", f"{name[:78]:<78}{fmt_mb(d):>10}{fmt_mb(i):>11}\n")
                if note:
                    table.insert("end", f"    {note}\n")
            table.insert("end", "-" * 99 + "\n")
            table.insert("end", f"{'TOTAL (approximate)':<78}{fmt_mb(dl):>10}{fmt_mb(inst):>11}\n")
            free = hw_holder["hw"].get("disk_free_gb")
            if free is not None:
                table.insert("end", f"Free disk space: {free:g} GB\n")
            table.configure(state="disabled")

        for vid, *_ in VOICES:
            mb = hwcheck.OPTIONAL_VOICE_MB.get(vid, 65)
            tk.Checkbutton(vbox, text=f"{vid}  (~{mb} MB)", variable=state["voices"][vid], command=refresh,
                           bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                           font=("Segoe UI", 10)).pack(anchor="w", padx=12)
        tk.Label(vbox, text=f"More voices: {VOICES_PAGE} (put both .onnx and .onnx.json files in voices\\)",
                 font=("Segoe UI", 9), fg=DIM, bg=BG).pack(anchor="w", padx=12)
        table.pack(fill="both", expand=True, pady=6)
        refresh()
        nxt = None

        def toggle():
            nxt.configure(state="normal" if state["discretion"].get() else "disabled")

        tk.Checkbutton(body, text="I choose to download these third-party components at my own discretion",
                       variable=state["discretion"], command=toggle, bg=BG, fg=FG, selectcolor=PANEL,
                       activebackground=BG, font=("Segoe UI", 11)).pack(anchor="w")
        nxt = button("Install  >", page_install, state_="normal" if state["discretion"].get() else "disabled")
        button("<  Back", page_choose, primary=False, side="left")

    # ---- 4 install
    def page_install():
        clear()
        tier_key = state["tier"].get()
        title("Installing...", f"Option: {hwcheck.TIERS[tier_key]['label']}. Please keep this window open.")
        step_lbl = tk.Label(body, text="", font=("Segoe UI", 12, "bold"), fg=FG, bg=BG, anchor="w")
        step_lbl.pack(fill="x")
        overall = ttk.Progressbar(body, mode="determinate")
        overall.pack(fill="x", pady=(4, 2))
        sub_lbl = tk.Label(body, text="", font=("Segoe UI", 10), fg=DIM, bg=BG, anchor="w")
        sub_lbl.pack(fill="x")
        dl = ttk.Progressbar(body, mode="determinate")
        dl.pack(fill="x", pady=(2, 8))
        frame = tk.Frame(body, bg=PANEL)
        frame.pack(fill="both", expand=True)
        logbox = tk.Text(frame, bg=PANEL, fg="#c8c8d0", relief="flat", font=("Consolas", 9), height=12)
        sb = tk.Scrollbar(frame, command=logbox.yview)
        logbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        logbox.pack(side="left", fill="both", expand=True)
        log = Log(sink=q.put)
        save_state(downloads_accepted=True, downloads_accepted_at=datetime.now().isoformat(timespec="seconds"))
        inst = Installer(tier_key, log, status=lambda s: q.put(("sub", s)),
                         progress=lambda d, t: q.put(("dl", (d, t))), shortcut=state["shortcut"].get(),
                         voices=[k for k, v in state["voices"].items() if v.get()],
                         knowledge=bool(state["books"].get()))
        steps = inst.steps()
        overall.configure(maximum=len(steps))
        retry_btn = {"b": None}

        def worker(start=0):
            for i in range(start, len(steps)):
                name, fn = steps[i]
                q.put(("step", (i, name)))
                try:
                    fn()
                except Exception as e:
                    log("ERROR: " + str(e))
                    log(traceback.format_exc())
                    q.put(("fail", (i, str(e))))
                    return
            save_state(installed=True, tier=tier_key, installed_at=datetime.now().isoformat(timespec="seconds"))
            q.put(("done", None))

        def poll():
            try:
                while True:
                    kind, val = q.get_nowait()
                    if kind == "log":
                        logbox.insert("end", val + "\n")
                        logbox.see("end")
                    elif kind == "step":
                        i, name = val
                        step_lbl.configure(text=f"Step {i + 1} of {len(steps)}: {name}")
                        overall.configure(value=i)
                        sub_lbl.configure(text="")
                        dl.configure(value=0)
                    elif kind == "sub":
                        sub_lbl.configure(text=val)
                    elif kind == "dl":
                        d, t = val
                        if t:
                            dl.configure(maximum=t, value=d)
                            sub_lbl.configure(text=f"{d / 1e6:,.0f} of {t / 1e6:,.0f} MB")
                        else:
                            sub_lbl.configure(text=f"{d / 1e6:,.0f} MB downloaded")
                    elif kind == "fail":
                        i, err = val
                        step_lbl.configure(text=f"Problem in step {i + 1}: {steps[i][0]}", fg="#ff8080")
                        messagebox.showerror("Setup problem",
                                             f"{err}\n\nCheck your internet connection and press Retry.\n"
                                             f"Log file: {log.path}")
                        for w in nav.winfo_children():
                            w.destroy()
                        button("Retry", lambda: (nav_clear(), threading.Thread(
                            target=worker, args=(i,), daemon=True).start()))
                        button("Close", root.destroy, primary=False, side="left")
                    elif kind == "done":
                        overall.configure(value=len(steps))
                        page_done()
                        return
            except queue.Empty:
                pass
            root.after(150, poll)

        def nav_clear():
            for w in nav.winfo_children():
                w.destroy()
            step_lbl.configure(fg=FG)

        threading.Thread(target=worker, daemon=True).start()
        poll()

    # ---- 5 done
    def page_done():
        clear()
        title("All set!", "Aurora Companion is installed.\n\n"
              "- Start it from the desktop shortcut or Start_Aurora.bat in this folder.\n"
              "- The first start asks you a few questions and lets you pick a companion.\n"
              "- The first reply can take a little longer while the AI model loads.\n"
              "- Adult mode is off and locked; adults can unlock it later in Settings.")

        def launch():
            try:
                if IS_WINDOWS:
                    subprocess.Popen([str(VENV_PYW), str(APP_ROOT / "Aurora_Companion.py")], cwd=str(APP_ROOT),
                                     creationflags=0x00000008)
                else:
                    subprocess.Popen([str(VENV_PY), str(APP_ROOT / "Aurora_Companion.py")], cwd=str(APP_ROOT),
                                     start_new_session=True)
            except Exception as e:
                messagebox.showerror("Could not start", str(e))
            root.destroy()

        button("Start Aurora  >", launch)
        button("Close", root.destroy, primary=False, side="left")

    st = load_json(STATE_PATH, {})
    if isinstance(st, dict) and st.get("disclaimer_accepted"):
        state["agree"].set(True)
    page_welcome()
    root.mainloop()


# ==================================================================== CLI
def main(argv):
    def arg(name):
        return name in argv

    def val(name, default=None):
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    if arg("--check"):
        hw = hwcheck.detect()
        rec = hwcheck.recommend(hw)
        print("\n".join(hwcheck.summary_lines(hw)))
        t = hwcheck.TIERS[rec["tier"]]
        print(f"\nRecommended tier: {rec['tier']} - {t['label']}")
        print(f"  models: {', '.join(models_for(rec['tier'])) or '(none)'}  force_cpu={t['force_cpu']} "
              f"whisper={t['whisper']}  need ~{hwcheck.tier_need_gb(rec['tier'], bool(hw.get('ollama_exe'))):g} GB")
        for r in rec["reasons"] + ["note: " + w for w in rec["warnings"]]:
            print("  " + r)
        return 0
    if arg("--plan") or arg("--unattended"):
        tier = val("--tier")
        if not tier:
            tier = hwcheck.recommend(hwcheck.detect())["tier"]
        if tier not in hwcheck.TIERS:
            print(f"Unknown tier {tier}. Choose from: {', '.join(hwcheck.TIERS)}")
            return 2
        voices = [v for v in (val("--voices", "") or "").split(",") if v]
        bad = [v for v in voices if v not in {x[0] for x in VOICES}]
        if bad:
            print(f"Unknown voice(s): {bad}. Choose from: {', '.join(x[0] for x in VOICES)}")
            return 2
        hw = hwcheck.detect()
        books = not arg("--no-books") and (arg("--books") or (tier not in ("tiny", "cloud")
                                                              and (hw.get("ram_gb") or 0) >= 6))
        inst = Installer(tier, print, shortcut=not arg("--no-shortcut"), voices=voices, knowledge=books)
        print(f"Aurora Companion {APP_VERSION} - tier {tier}: models={models_for(tier)} voices={voices} books={books}")
        for i, (name, _) in enumerate(inst.steps(), 1):
            print(f"  {i}. {name}")
        rows = size_plan(tier, hw, voices, books)
        print(f"\n  {'Component':<78}{'Download':>10}{'Installed':>11}")
        for name, d, i_, note in rows:
            print(f"  {name[:78]:<78}{fmt_mb(d):>10}{fmt_mb(i_):>11}" + (f"   ({note})" if note else ""))
        dl, ins = size_totals(rows)
        print(f"  {'TOTAL (approximate)':<78}{fmt_mb(dl):>10}{fmt_mb(ins):>11}")
        print("\n  " + DISCRETION_TEXT)
        if arg("--plan"):
            return 0
        if not arg("--accept-disclaimer"):
            print("Read DISCLAIMER.txt and add --accept-disclaimer to continue.")
            return 2
        save_state(disclaimer_accepted=True, disclaimer_accepted_at=datetime.now().isoformat(timespec="seconds"))
        log = Log()
        inst.log = log
        for name, fn in inst.steps():
            log(f"=== {name} ===")
            fn()
        save_state(installed=True, tier=tier, installed_at=datetime.now().isoformat(timespec="seconds"))
        log("Setup complete.")
        return 0
    run_gui()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SetupError as e:
        print(f"\nSETUP ERROR: {e}")
        sys.exit(1)
