# Translate to English

Live English subtitles for Brazilian Portuguese voice chat on Discord.

**[⬇ Download the latest version](https://github.com/xfelinnee/Translate-to-English/releases/latest/download/Translate-to-English.zip)** · [all releases](https://github.com/xfelinnee/Translate-to-English/releases)

People talk in Portuguese, and a second or so after each sentence the English
shows up in a small window on top of your game. It runs entirely on your own
PC with OpenAI's Whisper model, so it's free and nothing is uploaded anywhere.

It never logs into or automates Discord. It only listens to sound your PC
plays, the same way a recording program would.

## What you need

- Windows 10 or 11
- An NVIDIA graphics card with about 4 GB of free video memory (recommended).
  Without one it still works on the processor, but slower and less accurate.
- About 6 GB of free disk space
- Python 3.10 to 3.13. `install.bat` offers to install it if it's missing.

## Install

1. **[Download the zip](https://github.com/xfelinnee/Translate-to-English/releases/latest/download/Translate-to-English.zip)** and unzip it
   somewhere, for example your Documents folder (right-click → Extract All).
2. Double-click **`install.bat`** and wait a few minutes.

The speech model (about 3 GB) downloads the first time you start it.

## Set up Discord (once)

The translator listens to one audio output on your PC. You want the
Portuguese call playing into an output you don't listen to yourself, so the
easiest way is a second Discord app on a second account:

1. Install **[Discord Canary](https://discord.com/api/downloads/distributions/app/installers/latest?channel=canary&platform=win&arch=x64)**
   (Discord's own test version, which runs next to the normal app) and log
   in with an alt account.
2. In Canary: **User Settings → Voice & Video**
   - **Output Device:** an output you don't use, for example a monitor's
     speakers or a "Digital Output". It doesn't need anything plugged in.
   - **Output Volume:** 100%
   - Mute the microphone, so the alt never transmits anything.
3. Join the call with both accounts. You keep hearing everyone normally on
   your main account.

No spare output? Install [VB-Cable](https://vb-audio.com/Cable/) and use
"CABLE Input" as Canary's output.

## Use it

1. Have the alt join the call.
2. Double-click **`start.bat`**. The first time, it asks which output Canary
   plays into.
3. English lines appear as people finish each sentence.

The overlay starts **locked**: your mouse goes straight through it, so it
never gets in the way of a game. Press **Ctrl+Shift+L** (works in-game) to
unlock it, then:

- drag it to move it, and drag the ◢ corner to resize it
- click **⚙** for settings
- right-click for a quick menu

Press **Ctrl+Shift+L** again to lock it.

### Settings

Everything in the ⚙ window applies instantly and is saved:

- background opacity and text opacity, separately
- text size, text color, background color
- how many lines to keep, and hiding old lines after a few seconds
- showing the Portuguese under each line
- grey live guesses while someone is still talking (uses more GPU)
- how long a pause ends a line
- which audio output to listen to

A few more options are only in `config.json`, for example `lock_hotkey`
(like `"ctrl+alt+t"`) and `compute_type` (`"int8_float16"` uses about 1.5 GB
less video memory, slightly less accurate).

## Good to know

- **Tell people in the call** that their voices are being transcribed.
- Lines don't say who is talking, and two people talking over each other
  come out messy.
- Games in **exclusive fullscreen** draw over every other window. Use
  borderless or windowed fullscreen to see the overlay.
- Each finished sentence takes about half a second of GPU time. Capping your
  game's FPS leaves room for it so it doesn't cost you frames.
- The small bar at the top moves when audio comes in. If it never moves
  while people talk, Canary is playing into a different output than the one
  the translator listens to (change it in ⚙ settings).

## Built with

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and
  OpenAI's [Whisper](https://github.com/openai/whisper) large-v3 model
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) for recording
  Windows audio outputs

## License

MIT, see [LICENSE](LICENSE).
