# Aurora Companion 0.9.6-beta

## How to install (Windows 10 / 11)

1. **Download:** click the green **Code** button at the top of this page, then **Download ZIP**.
   (Or use this direct link: https://github.com/robertlionhart-cyber/aurora-companion-beta/archive/refs/heads/main.zip)
2. **Unzip:** open your Downloads folder, right-click `aurora-companion-beta-main.zip` and choose
   **Extract All...**, then click **Extract**. Put it somewhere easy, like your Documents folder.
   (Don't run it from inside the zip.)
3. **Run Setup:** open the extracted folder and double-click **`Setup.bat`**. Follow the window -
   it checks your PC, recommends what to install, shows the download sizes and installs everything for you.

That's it. When setup finishes, click **Start Aurora**. Next time, use the **Aurora Companion**
shortcut on your desktop.

> If Windows shows "Windows protected your PC", click **More info > Run anyway**.
> If it asks to install Python, type **Y** and press Enter.

---

Aurora is a talking AI companion for your desktop. It listens, talks back with a
voice, and shows an animated character. It runs **on your own computer** - no
account and no internet needed after setup (cloud features are optional).

> Beta version - thank you for testing! Please report anything odd (see the end).

## What happens during setup

1. A setup window opens. Read and accept the notice, then setup checks your computer
   and **recommends** an option. Click **Next** to use the recommendation.
2. Setup then shows a **review screen**: every third-party component it will download
   (Python packages, Piper, optional voices, Ollama, each AI model, Whisper) with its
   approximate download and installed size, plus a total. Tick any extra voices you want,
   tick **"I choose to download ... at my own discretion"** and click **Install**.
3. Wait while it downloads - roughly 3.5 GB on small PCs, up to about 12 GB on gaming PCs.
4. Click **Start Aurora**.

Everything installs for your Windows user only. You don't need an administrator password.

**Mac (experimental):** install Python 3.11 from python.org, then double-click
`Setup.command` (right-click > Open the first time). Mac support is not fully tested yet.

## What the options mean

| Option | Good for | AI model | Model download |
|---|---|---|---|
| Tiny | old laptops, 4 GB memory | Llama 3.2 1B | ~1.3 GB |
| Light | normal laptops, no gaming graphics card | Llama 3.2 3B | ~2.0 GB |
| CPU Plus | fast PC, 16 GB+ memory, no NVIDIA card | Dolphin 3 (8B) | ~4.9 GB |
| GPU Small | NVIDIA card with 4-6 GB | Llama 3.2 3B | ~2.0 GB |
| GPU | NVIDIA 6-10 GB, or Apple Silicon 16 GB+ | Dolphin 3 (8B) + 3B backup | ~6.9 GB |
| GPU High | NVIDIA 11 GB+ | Gemma 4 12B Uncensored (HauhauCS, Q4_K_M) + 3B backup | ~9.6 GB |
| Cloud only | very weak PCs | none (uses your own xAI Grok API key) | none |

### Approximate sizes of the third-party parts

| Component | Download | Installed |
|---|---|---|
| Python 3.11 (only if you don't have 3.10-3.13) | ~26 MB | ~110 MB |
| Python packages (faster-whisper, OpenCV, NumPy ...) | ~220 MB | ~700 MB |
| Ollama (local AI runtime, only if not installed) | ~1.9 GB | ~3.2 GB |
| Piper voice engine 2023.11.14-2 | ~22 MB | ~39 MB |
| Robert voice (default) | included | ~64 MB |
| Optional voices: LibriTTS-R / Amy / Ryan | ~79 / 63 / 63 MB | same |
| Whisper speech recognition: tiny / base / small | ~78 / 148 / 486 MB | same |
| Book library index (if turned on) | none | ~190 MB |

Setup shows the exact list for your choice before it downloads anything. You can run `Setup.bat`
again any time to pick a different option. Nothing you've already downloaded is lost.

## First start

- Aurora asks a few questions (your name, age group, companion name).
- Pick a look: this beta includes **4 characters - a girl, a guy, a cat and a dog**.
- The default voice is **Robert** (included). en_US-robert-medium is Robert's own voice model, included for personal use with Aurora Companion only. Do not redistribute it or use it to impersonate him. Extra voices you ticked in Setup appear in the
  voice list. More Piper voices: https://huggingface.co/rhasspy/piper-voices (use the
  `v1.0.0` versions - put the `.onnx` and `.onnx.json` files in the `voices` folder).
- Press the mic button to talk, or type.
- The first reply is slower while the AI model loads.

## Adult mode

Adult mode is **off and locked**. An adult can unlock it in **Settings > Adult mode**
by confirming they are 18 or older. If you answer **No** to the 18+ question (when creating
your account or when unlocking), the account is switched to **under-18 mode**: Adult mode
stays locked for good and the companion follows under-18 content rules.

## Book library

The `knowledge` folder has 83 classic books that are in the public domain in the US (from
Project Gutenberg). Your companion can look things up in them. The library needs about
1.5 GB of extra memory, so Setup turns it **off** on 4 GB PCs and the Tiny/Cloud options -
you can switch it with the "Book library" box in Setup.

## Privacy

- Chats, memories and settings stay in the `profiles` folder on your computer.
- Offline mode sends nothing to the internet.
- If you choose to use xAI Grok (optional), what you send goes to xAI, and you need your
  own API key. See `DISCLAIMER.txt`.

## If something goes wrong

- **No voice:** run `Setup.bat` again (it repairs missing pieces).
- **"Ollama not running":** restart the PC, or start Ollama from the Start menu.
- **Very slow replies:** run `Setup.bat` again and choose a smaller option.
- **Mic not working:** Windows Settings > Privacy > Microphone > allow desktop apps.
- **Reporting a bug:** start with `Start_Aurora_Debug.bat`, reproduce the problem, and send
  the newest file from the `logs` folder. Please check it first - logs can contain bits
  of your chats. Never send anything from the `profiles` folder.

## Uninstall

Delete the Aurora folder and the desktop shortcut. Ollama and Python can be removed in
Windows **Settings > Apps** (only if no other program uses them). AI models live in
`%USERPROFILE%\.ollama` and speech models in `%USERPROFILE%\.cache\huggingface`.

## Third-party software

Aurora uses Python, Ollama, Piper, Piper voices, faster-whisper/Whisper and third-party AI
models. **Automatic downloads by the installer are at your own discretion.** The author of
Aurora Companion does **not** own the rights to these third-party apps, models or voices -
they belong to their respective owners and are provided under their own licenses, downloaded
from their official sites. See `DISCLAIMER.txt` for details.
