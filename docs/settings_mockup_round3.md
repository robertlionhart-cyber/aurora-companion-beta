# Aurora Companion settings — round 3 mockup

This is a layout proposal only. The live Settings menu was **not** rewritten
in this pass. A model selector was added in the existing menu (GPU model,
CPU model, and “Choose local models…”) just below Brain, so it can be used
now. Daily-use items are marked with a star (★).

Line numbers refer to `_build_settings_menu` in `Aurora_Companion.py` after
the round-3 patch. They will drift if the file is edited again.

## Current inventory (live menu, top to bottom)

- Edit companion… — `open_edit_companion`
- Dual Mode… — `open_dual_mode`
- Migrate companion guide… — `show_migrate_guide_dialog`
- Export companion pack… — `export_companion_pack`
- Import companion pack… — `import_companion_pack`
- Conversation transcript… — `open_transcript_window`
- Export conversation… — `export_conversation_text`
- Save conversation as… — `save_named_conversation`
- Load saved conversation… — `load_named_conversation_dialog`
- Clear Chat History — `clear_history`
- Restart Chat (keep profile) — `clear_history` (same command as Clear)
- — separator —
- Adult mode: ON/OFF/locked — `toggle_nsfw_mode` (hidden when age_group is under18)
- Upgrades & packs… — `show_upgrades_window`
- — separator —
- Online mode: ON/OFF — `toggle_online_mode`
- Location: … — `edit_location_dialog`
- Refresh weather / news now — `manual_refresh_live`
- — separator —
- Brain: Local Ollama / Grok / Other — `toggle_llm_provider` ★
- **GPU model: …** — cascade of installed chat models + Refresh ★ *(new)*
- **CPU model: …** — cascade of installed chat models + Refresh ★ *(new)*
- **Choose local models…** — dialog with two dropdowns + Refresh ★ *(new)*
- Voice: Local Piper / Grok TTS — `toggle_tts_provider` ★
- Think harder: ON/OFF — `toggle_think_harder` (only when Grok brain is active)
- Grok API setup… — `open_grok_api_setup`
- Other API setup… (chat only) — `open_other_api_setup`
- Run mode: Offline / Online / Online with Grok — `change_run_mode_from_settings`
- — separator —
- Reply length — cascade (`set_response_length`) ★
- Speech recognition — cascade of Whisper sizes (`set_whisper_size`)
- Memory… — memory editor
- Reminders / Schedule… — reminders
- Shared memory… — shared facts
- Summarize this chat (Grok) — only when Grok is the brain
- — separator —
- Wake word: ON/OFF — `toggle_wake_word` ★
- Minimize to tray: ON/OFF — `toggle_tray_minimize`
- — separator —
- Choose microphone… — `choose_input_device_dialog` ★
- Local Ollama: Force CPU / Auto — `toggle_force_ollama_cpu` ★
- Install local models… — `open_one_click_setup`
- System status… — `show_system_status`
- Open logs folder — `open_logs_folder`
- About Aurora… — `show_about_dialog`
- Back to Companion Select — `back_to_selection`
- Log out / Switch user — `logout_user`
- — separator —
- Quit Aurora — `quit_app`

Exact line refs in Aurora_Companion.py after the round-3 patch:

- _build_settings_menu: 12182
- Edit companion…: 12196
- Dual Mode…: 12197
- Migrate companion guide…: 12198-12200
- Export / Import companion pack…: 12202-12208
- Conversation transcript… / Export / Save / Load: 12210-12213
- Clear Chat History: 12214
- Restart Chat (keep profile): 12215
- Adult mode: 12217-12227
- Upgrades & packs…: 12228
- Online mode: 12231
- Location: 12233-12235
- Refresh weather / news now: 12237
- Brain cycle: 12239-12246
- GPU / CPU model cascades + Choose local models…: added by _add_ollama_model_menu_items() at 12247 (method 4234-4360)
- Voice Piper/Grok TTS: 12248-12252
- Think harder (Grok only): 12253-12256
- Grok API setup…: 12257
- Other API setup…: 12258
- Run mode: 12259-12265
- Reply length cascade: 12267-12286
- Speech recognition cascade: 12288-12307
- Memory (this companion)…: 12309
- Reminders / Schedule…: 12310
- Shared memory (all companions)…: 12311
- Summarize chat into memory (Grok)…: 12312-12315
- Wake word: 12318-12319
- Minimize to tray: 12320-12322
- Choose microphone…: 12324
- Local Ollama Force CPU / Auto: 12325-12331
- Install local models…: 12332-12334
- System status…: 12336
- Open logs folder: 12337
- About Aurora…: 12338
- Back to Companion Select: 12339
- Log out / Switch user: 12340-12342
- Quit Aurora: 12345


## Proposed layout (collapsible sections)

Do not implement this tree yet. Advanced should be collapsed by default.
Stars (★) = daily-use, one click away (visible without opening a nested
section, or on the first row of an already-open section).

```
Settings
│
├─ Model & Backend                          [section open by default]
│  ├─ ★ Brain: Local Ollama / Grok / Other    (cycle, current behavior)
│  ├─ ★ GPU model: <dropdown / cascade>       (Ollama chat models, Refresh)
│  ├─ ★ CPU model: <dropdown / cascade>       (same list, saved separately)
│  ├─ ★ Local Ollama: Auto / Force CPU        (existing toggle)
│  ├─    Choose local models…                 (two comboboxes + Refresh)
│  ├─    Run mode: Offline / Online / Grok
│  ├─    Grok API setup…
│  ├─    Other API setup… (chat only)
│  ├─    Think harder: ON/OFF                 (Grok brain only)
│  └─    Install local models…
│
├─ Voice & Audio                            [section open by default]
│  ├─ ★ Voice: Local Piper / Grok TTS
│  ├─ ★ Wake word: ON/OFF
│  ├─ ★ Choose microphone…
│  ├─    Speech recognition (Whisper size)    (cascade, as today)
│  └─    Reply length                         (cascade, as today)
│
├─ Appearance                               [section open by default]
│  ├─    Minimize to tray: ON/OFF
│  └─    (future: theme, bubble style, font size — not in the app today)
│
├─ Companion & conversation                 [section open by default]
│  ├─    Edit companion…
│  ├─    Dual Mode…
│  ├─    Memory…
│  ├─    Reminders / Schedule…
│  ├─    Shared memory…
│  ├─    Conversation transcript…
│  ├─    Save / Load / Export conversation
│  ├─    Clear Chat History
│  ├─    Restart Chat (keep profile)
│  ├─    Summarize this chat (Grok only)
│  ├─    Adult mode: ON/OFF/locked            (over-18 only)
│  ├─    Upgrades & packs…
│  ├─    Migrate companion guide…
│  └─    Export / Import companion pack…
│
├─ Location & live data                     [section open, short]
│  ├─    Online mode: ON/OFF
│  ├─    Location: …
│  └─    Refresh weather / news now
│
├─ Advanced                                 [COLLAPSED by default]
│  ├─    System status…
│  ├─    Open logs folder
│  ├─    About Aurora…
│  └─    (future: request timeouts, log verbosity, VRAM fallback policy)
│
└─ Account                                  [always visible at the bottom]
   ├─    Back to Companion Select
   ├─    Log out / Switch user
   └─    Quit Aurora
```

## Notes for review

- Design chosen for the selector: **two selections (GPU and CPU) plus the
  existing Force CPU toggle**, not a single dropdown. Force CPU already
  switches which selection is live; one dropdown would hide the other
  model and make mid-conversation CPU/GPU flips more confusing.
- Embedding-only models (for example `nomic-embed-text`) stay out of the
  chat lists.
- `qwen3.6:latest` (~24 GB) can be picked in the GPU list if it is
  installed, but it is not in the automatic VRAM fallback chain.
- Clear Chat History and Restart Chat currently call the same function;
  that is left as a decision, not changed here.
- Timeouts and logging are not exposed in the live menu today; they are
  proposed under Advanced for a later pass.
