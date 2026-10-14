# SOUND

An artist describes how a song should feel. The system turns that into effect settings in Ableton.

```
artist text -> llm.py (LLM box) -> list of controls -> core.py (core box) -> Ableton
```

See `CLAUDE.md` for the philosophy and vocabulary.

## Prerequisites

- macOS.
- Ableton Live 12 Suite. Tested on 12.4.2.
- Python 3. No packages are needed.
- Claude Code, installed and logged in with a Claude subscription. Check with `claude -p "hi"`. Each run uses your subscription's usage limit.

## Setup

1. Link the Ableton script into Ableton's Remote Scripts folder:
   ```
   ln -s "$PWD/SoundBridge" ~/Music/Ableton/User\ Library/Remote\ Scripts/SoundBridge
   ```
2. Restart Ableton.
3. In Ableton, open Settings, then Link, Tempo & MIDI. Set a Control Surface to **SoundBridge**.

## Run

```
python3 llm.py
```

Open your project in Ableton and click the track to mix. Then type what you want it to feel like. The controls print with a reason for each. Then they are applied in Ableton. Rejected controls print at the end.

Settings live in `.env`. Copy `.env.example` to `.env` to start. `MODEL` defaults to haiku. It is cheap for checking that everything is connected. Set `MODEL=opus` to judge how it sounds.