# Notes for Robert - beta-tester package

Built from `AuroraCompanion_beta` (v0.9.5.1-beta) and released as **0.9.6-beta**. Your original folder
and your voice files were **not changed** (copies only).

## New in 0.9.6-beta
- **Version** 0.9.6-beta in `APP_VERSION`, the setup window title, README and DISCLAIMER.
- **Your voice ships as the default.** `voices/en_US-robert-medium.onnx` (63,511,038 bytes, ~63.5 MB) and its
  `.onnx.json` (7,103 bytes) were copied from `Documents\piper_windows_amd64\piper\voices\`. SHA-256 is checked by
  Setup. They are un-ignored in `.gitignore`. Tested with piper 2023.11.14-2 (no multi-codepoint phonemes).
  `PIPER_MODEL` now points to it; the voice picker prefers Robert, then LibriTTS-R.
- **Optional voices.** libritts_r medium (~79 MB), amy (~63 MB) and ryan (~63 MB) are checkboxes on the review
  screen, all off by default. Only ticked voices are downloaded (still pinned to piper-voices v1.0.0).
  `voices/README.txt` links to https://huggingface.co/rhasspy/piper-voices.
- **New "Review downloads" screen** after the model choice and before Install. It lists every third-party part
  (Python if Setup installed it, pip packages, Piper, each voice, Ollama, each model, Whisper, book index) with
  approximate download and installed size, a total, and free disk space. Install stays greyed out until the user
  ticks "I choose to download these third-party components at my own discretion". `--plan` prints the same table.
  Sizes are in `setup/hwcheck.py` (`MODEL_MB`, `WHISPER_MB`, `COMPONENT_MB`, `OPTIONAL_VOICE_MB`).
- **Discretion / rights text** on the review screen, in DISCLAIMER.txt, in README and in the Python prompt of
  bootstrap.ps1: downloads are at the user's own discretion; the Aurora Companion author does not own the rights to
  third-party apps, models or voices; they belong to their owners under their own licenses.
- **Book library.** 83 public-domain Project Gutenberg texts (59.6 MB, largest 5.6 MB) are in `knowledge/`.
  The index (~190 MB JSON, ~1.2-1.5 GB RAM, ~4 s per query on a Xeon) is built by the app and never shipped.
  A "Book library" checkbox in Setup writes `setup.knowledge_library`; it's off by default on Tiny/Cloud or < 6 GB RAM.
  If that key is missing the app turns it on only with >= 6 GB RAM. `kama_sutra.txt` is searched only when Adult
  mode is on. Later improvement: an on-disk inverted index would cut the memory a lot.
- **"No" to 18+ means under-18 everywhere.** New `apply_under18_alignment()`: profile and account
  `age_group=under18` (also saved to users.json), Adult mode off and locked, confirmation cleared, flirty moods reset.
  Called when the user says No at account creation (over18 now always asks "Age confirmation"), on the Adult mode
  confirm dialog, in Dual Mode, on the legacy legal screen (Go Back / unticked box) and in `select_age("under18")`.
  For minors the system prompt drops romantic/lover/intimate/partner styles, hides the "Adult mode in Settings"
  hint, and adds an IMPORTANT under-18 rule (no romance, flirting, sexual content, alcohol/drugs/gambling).
- Gemma 4 12B Uncensored stays the gpu_high default, offered only when the PC qualifies (NVIDIA 11 GB+ / 16 GB RAM).


## What's in this package
- `Setup.bat` -> `setup/bootstrap.ps1` -> `setup/aurora_setup.py` (graphical wizard)
  1. Finds Python 3.10-3.13 with Tk. If there isn't one, it asks, then installs **Python 3.11.9**
     from python.org per-user (no admin; SHA-256 checked).
  2. Wizard: Welcome -> **Disclaimer (must tick "I agree")** -> hardware check + recommended option
     -> install with progress bars and log -> "Start Aurora".
  3. Installs into the app folder: `.venv` (pip deps), Piper 2023.11.14-2 (SHA-256 checked),
     optional voices (libritts_r, amy, ryan - user's choice), pinned to piper-voices tag **v1.0.0** with SHA-256 checks.
     The current `main` voices were retrained for Piper 1.5 and crash the 2023 piper.exe ("Phonemes must be one codepoint").
     I tested this on the box. Also installs Ollama per-user (OllamaSetup.exe /VERYSILENT),
     pulls the model(s) through Ollama's API (skips any model that is already installed), pre-downloads
     the Whisper model and adds Desktop and Start-menu shortcuts.
  4. Writes `aurora_config.json` (models, num_ctx, and a new `setup` block with tier + whisper size)
     and `profiles/performance.json` (`force_ollama_cpu`).
  5. Every step can be re-run safely. Logs go to `logs/setup_*.log`.
- `setup/hwcheck.py` can be run on its own (`python setup\hwcheck.py`) to print a hardware report
  and a recommendation. It changes nothing.
- CLI for support: `aurora_setup.py --check | --plan [--tier X] | --unattended --accept-disclaimer [--tier X]`.

## Tiers
| tier | when | model (force CPU) | CPU backup | whisper | num_ctx |
|---|---|---|---|---|---|
| tiny | no AVX, or < 6 GB RAM | llama3.2:1b (yes) | same | tiny | 2048 |
| light | no usable NVIDIA, >= 6 GB RAM | llama3.2:3b (yes) | same | base | 2048 |
| cpu_plus | no NVIDIA, >= 16 GB RAM, AVX2, >= 6 cores | dolphin3:latest (yes) | same | base | 2048 |
| gpu_small | NVIDIA ~4-6 GB | llama3.2:3b (no) | same | base | 4096 |
| gpu_mid | NVIDIA >= 6 GB (+8 GB RAM), Apple Si 16 GB+ | dolphin3:latest (no) | llama3.2:3b | small | 4096 |
| gpu_high | NVIDIA >= 11 GB + 16 GB RAM, Apple Si 32 GB+ | Gemma4-12B HauhauCS Q4_K_M (no) | llama3.2:3b | small | 8192 |
| cloud | user's choice | none pulled, no Ollama | - | tiny | - |
It steps down a tier when free disk space is too low. The SGIN laptop (J4105, 4 GB, no AVX) -> **tiny**.

## App code changes (staged copy only) - `Aurora_Companion.py`
1. **Adult mode, 18+ confirmation instead of the paid pack.**
   - New `adult_age_confirmed()`: True only if the profile says `age_group == "over18"` and
     `adult_age_confirmed` is true, and neither the profile nor the logged-in account is under18.
   - New `confirm_adult_age()`: a Yes/No "Confirm your age (18+)" dialog. Yes sets
     `age_group="over18"`, `adult_age_confirmed=true` and `adult_age_confirmed_at` (UTC), then saves the profile.
     Under-18 profiles/accounts get "not available" and nothing changes.
   - `adult_content_unlocked()` now returns True when `adult_age_confirmed()` (the pack/dev checks still
     work after that). `nsfw_enabled()` is unchanged, so under18 is still hard-blocked there.
   - `toggle_nsfw_mode()`: also blocks an under18 *account*. When locked it shows the age confirmation
     instead of "needs Adult Unlock pack". The existing "Enable Adult mode?" prompt still follows.
   - Dual Mode's "Adult mode" checkbox used to bypass the unlock completely. It now goes through
     `_dual_adult_allowed()` (needs an 18+ account plus confirmation).
   - The Settings row hides for an under18 account too. Labels now read "Adult mode: locked (18+ only - tap to unlock)".
   - The Upgrades window "Dev: Install Adult Unlock pack / Toggle unlock-all" buttons are hidden unless `AURORA_DEV=1`.
2. **Whisper default from setup:** `DEFAULT_WHISPER_SIZE` is read from `aurora_config.json` -> `setup.whisper_size`
   (falls back to "medium"). It's used for new profiles and the fallback in `ensure_whisper_model()`.
3. The missing-packages popup and the in-app setup checklist now point to `Setup.bat` / `Setup.command`.
The full diff against your original is in `docs/BETA_APP_CHANGES.diff`.
No other behavior changed. The built-in model constants are the same as yours.

## Content
- Avatars: **pebbie** (girl - office outfit, no adult clips), **ben** (guy), **leo** (cat - added a
  `character.json` with kind=pet/Cat so the pet picker finds it), **barry** (St. Bernard dog). All mp4s are < 4 MB.
- Books: see `knowledge/` (83 files). Excluded from the source knowledge folder: orphic_hymns,
  plato_apology_crito_phaedo and meditations (exact duplicates), book_of_enoch (a saved Cloudflare page),
  enoch (partial HTML scrape), python_tutorial (PSF docs - not public domain), intimate_knowledge.md (custom adult
  notes), test_aurora (personal), and 6 empty files. 12 files were renamed because their content didn't match the name.
- Excluded: profiles, logs, backups, packs, tts_tmp, __pycache__, all .bak/.prev,
  test wavs, response/preview.txt, gemma trace scripts, voices, piper binaries and DLLs, espeak-ng-data, pkgconfig,
  and the other 8 characters. No adult unlock pack ships. The app creates `profiles/` and the PG sample pack on first run.
- `.gitignore` blocks profiles/, logs/, keys, xai_config.json, other_api_config.json, voices/*.onnx (except Robert's), knowledge_index.json, piper
  binaries/DLLs, .venv, models, aurora_config.json and setup_state.json. `.gitattributes` keeps the .bat/.ps1 files CRLF.

## Things to decide
- **Gemma model for gpu_high:** it's an "Uncensored" community build. That's fine for adult-mode testers,
  but maybe use plain `gemma3:12b` as the public default?
- `Dolphin 3` is also uncensored-leaning. Llama 3.2 is the default for low and mid PCs.
- Settled in 0.9.6: books shipped (public domain only), age wording kept with under-18 alignment, version bumped.
- Your voice is licensed by you. If testers may redistribute it, consider adding a line about its license to voices/README.txt.
- Should a code-signing / SmartScreen note go in the README? It's already mentioned.
