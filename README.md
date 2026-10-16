# SOUND

An artist describes how a song should feel. The system turns that into effect settings in Ableton.

```
artist text -> llm.py (agent) <-> tools -> ableton.py (adapter) -> SoundBridge -> Ableton
```

See `CLAUDE.md` for the philosophy and vocabulary.

## ARCHITECTURE 

Artists specify how they want their mix to sound in raw, unstructured text. This can be a specific ask "add delay to the vocals" or something more generic "i want my audience to be energized and inspired by my vocals". 

The agent reasons about the request and outputs a set of controls that get applied to the track through the artist's DAW.

A control is an effect, a setting, and a value. 
- an effect is a device. Exmaple: Reverb. 
- a setting is a dial on an effect. Example: Decay Time on Reverb.
- a value is a number on the setting. Example: 3s decay time on Reverb. 
   - can also be a choice. example "High Pass" or "Low Pass"

Controls are the how the LLM translates the artist's input into part of the mix. They are the bridge between artist intention and sound engineering output. 

The Ableton adapter (`ableton.py`) is a determinsitic set of steps that takes in the controls and applies them to the DAW. It talks to a bridge inside Ableton (SoundBridge) that programatically interfaces with the Ableton project to apply the controls.

For v0, the agent only works with the built-in Ableton effects. Future versions will accomodate each artist's plug-in suite. 
- i think we build a generic "get me the descripiton of this effect and how to control it" for a generic plug in. will work with the stock effects and future, more niche effects. 

The agent then has a set of tools it can call, in any order it chooses. 
- it can list the stems to figure out which track it needs to target for the control its working on (example: if user wants their vocals to be energetic, it can go find the vocal track)
- it can read that track and its current effects 
- it can list the settings on a specific track so it can reason about how to tune it 
- it can apply the controls. this is calling the adapter 

There is data we need to keep track of throughout the agent flow and conversation such as:
- conversation history across turns 
   - to enable conversational feature 
- working messages
   - tracks the stems already worked on so the agent doesnt duplicate work 

## Prerequisites
- macOS.
- Ableton Live 12 Suite. Tested on 12.4.2.
- Python 3. Install the packages with `pip install -r requirements.txt`.
- An Anthropic API key in `.env` as `ANTHROPIC_API_KEY`. Each run is billed to that key.

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

Open your project in Ableton. Then type what you want the song to feel like. The agent prints each step: which stem it reads, which controls it applies and why, and what Ableton rejected. Then it replies. Keep typing to react to what you hear. Press Enter on an empty line to stop.

## Evals

```
MODEL=claude-opus-5-5 python3 evals.py
```

Runs fixed test conversations. The test project needs a few clearly named stems, one named VOCALS, and no guitar. A program checks what it can. You listen and grade each turn good or bad, with a reason. Each run is saved to `results/` with the exact instructions used and every step of every turn, with its context size and time, and its totals print beside the previous run. Commit the results.

Settings live in `.env`. Copy `.env.example` to `.env` to start. `MODEL` defaults to `claude-haiku-5-5`. It is cheap for checking that everything is connected. Set `MODEL=claude-opus-5-5` to judge how it sounds.