# vc64_240p

**Real low-resolution output for Nintendo 64 Virtual Console on the Wii — targeting CRTs.**

This project patches the **official Nintendo N64 Virtual Console emulator** inside an existing Wii WAD so that it can output a real progressive low-resolution signal instead of the normal interlaced output.

The original project started as a 240p/60 Hz NTSC patch. It has since been extended into an experimental CRT-oriented video-mode tool with **automatic PAL/NTSC detection**, support for **240p/60, 240p/50, 288p/60 and 288p/50 targets**, and structural analysis of multiple Nintendo N64 VC emulator revisions.

The main goal is simple:

> **Keep Nintendo's original N64 Virtual Console emulator, compatibility work, saves and suspend data — but get the kind of low-resolution progressive output that is useful on a 15 kHz CRT.**

This is especially aimed at Wii setups connected to RGB/component-capable CRT displays where 240p/288p and their native scanline structure are desirable.

---

## Why this exists

Nintendo's N64 Virtual Console normally renders internally at a high-resolution framebuffer and outputs an interlaced signal. Unlike the older 2D Virtual Console systems, N64 VC does not normally expose the low-resolution progressive signal expected from an original console.

For CRT users, the difference matters. A real progressive low-resolution signal gives stable scanlines and avoids the characteristic field-to-field flicker of interlaced output.

The obvious alternatives each have drawbacks:

| route | problem |
|---|---|
| Wii N64 homebrew emulators | 240p is possible, but compatibility and performance can vary substantially by game |
| Wii U / vWii | does not provide the same 240p workflow as a real Wii CRT setup |
| replacing the Nintendo emulator | loses Nintendo's original per-title compatibility work and data handling |
| forcing a display mode only | does not help if the emulator itself continues to configure an interlaced render path |

So this project modifies the emulator itself.

---

## What it does

The current tool can target four video combinations:

| target | status |
|---|---|
| **240p @ 60 Hz (NTSC)** | established/original path |
| **240p @ 50 Hz (NTSC)** | experimental |
| **288p @ 60 Hz (PAL)** | experimental |
| **288p @ 50 Hz (PAL)** | experimental |

The labels above are retained in the GUI because they describe the requested output combinations. Internally the patch selects the NTSC or PAL render path according to the target's timing family.

For a normal **PAL Wii connected to a 15 kHz CRT**, the most relevant experimental target is currently **288p @ 50 Hz (PAL)**.

The project does **not** claim that all four combinations are electrically or temporally validated on every CRT. The non-original combinations are deliberately marked experimental and require real-hardware testing.

---

## Automatic PAL / NTSC detection

The GUI now analyses the selected WAD and determines its normal video family automatically.

Detection prefers the **TMD region metadata** carried by the channel:

- Japan / USA → NTSC family
- Europe / Australia → PAL family

For unusual/free-region titles, the tool has a title-ID fallback.

The automatic selection is a convenience only. The four target modes remain manually selectable.

This distinction is important because a VC emulator can contain several render-mode structures at the same time. The fact that a PAL structure exists inside a USA WAD does **not** make the WAD a PAL title; the channel's region and the console video system determine which family is normally used.

---

## PAL support is experimental and structural

Early work on PAL was based on Pokémon Snap and found a runtime code path that overwrote the PAL height with **574**. That meant changing only the PAL render-mode table was ineffective.

Testing against additional retail PAL and NTSC WADs showed that this runtime pattern is **not identical in every emulator build**. For example, some tested games contain the recognizable PAL runtime height override while others do not, even though their PAL render-mode structures are present.

The current patcher therefore does **not** assume that every PAL emulator must contain the Pokémon Snap-style `574` sequence.

Instead it works like this:

```text
WAD
 ↓
Detect NTSC/PAL family
 ↓
Find the correct interlaced render-mode structure structurally
 ↓
Find the main framebuffer field-offset instruction structurally
 ↓
For PAL:
    if a PAL runtime height override exists:
        patch it
        disable the runtime XFB-height store
    otherwise:
        skip that optional step
 ↓
Patch the render path
 ↓
Verify the resulting WAD
```

This is important for portability across different official Nintendo emulator builds.

### Why structural matching?

The emulator offsets differ between games and revisions. Hardcoding an address taken from one WAD is therefore unsafe.

The tool searches for the actual structures and instruction patterns it needs. When a required target cannot be located, the tool refuses to modify the WAD instead of silently writing to an unrelated address.

---

## What is actually patched

The original 240p path changes the Nintendo emulator's video configuration rather than replacing the emulator.

The core changes are:

| change | purpose |
|---|---|
| `viTVmode` interlaced → double-strike | selects progressive low-resolution output |
| `viHeight` → target height | selects 240 or 288 output lines |
| progressive video filter profile | removes the normal interlace-oriented deflicker filtering |
| field-base offset instruction → NOP | prevents the even/odd field alternation that otherwise causes heavy flicker |
| PAL runtime height override, where present | prevents the PAL path from replacing the requested height at runtime |
| PAL runtime XFB-height store, where present | prevents the runtime code from restoring the original high-resolution XFB height |

The emulator's normal framebuffer allocation is intentionally preserved. The objective is to change the final video path without replacing Nintendo's game/emulator logic.

### Dark filter removal

The GUI also contains an optional patch for the emulator's darkening function. When available, the patch makes that function return immediately.

This is separate from the video-mode patch and can be applied independently.

---

## What it is not

**The GUI is not primarily a ROM injector.** It is designed to patch an **existing N64 VC WAD** — either an official retail channel or an injected channel that already uses a compatible Nintendo N64 VC emulator build.

For building channels from ROMs, [FriishProduce](https://github.com/CatmanFan/FriishProduce) remains the preferred injector. The two tools have different jobs:

- **FriishProduce** builds/injects the channel.
- **vc64_240p** modifies the resulting emulator video path for CRT output.

The CLI in this repository contains experimental injection and `romc` support, but that is not the main purpose of the GUI.

---

## Usage

1. Run `vc64_240p.exe`.
2. Choose an N64 VC WAD.
3. The tool reads the WAD and automatically reports the detected NTSC/PAL family.
4. The normal mode is selected automatically:
   - NTSC → `240p @ 60 Hz (NTSC)`
   - PAL → `288p @ 50 Hz (PAL)`
5. Select another target manually when testing a different combination.
6. Optionally enable the dark-filter removal.
7. Apply the patch.
8. The output is written beside the original WAD. The original file is not modified.

The generated WAD keeps the original channel identity. As with any modified WAD, use a recovery method such as Priiloader when experimenting.

---

## Requirements

For the standalone Windows build:

- Windows
- An N64 Virtual Console WAD
- A Wii capable of installing/testing the resulting channel
- A CRT setup capable of accepting the requested low-resolution signal

The standalone build generates the Wii common key automatically on first use. No manual `common-key.bin` file is required.

For source builds:

- Python 3.8+
- `cryptography`
- `pyinstaller`

---

## Important Wii / CRT requirements

The patched channel does not magically override the Wii's complete video configuration. The Wii must be configured for the timing family that the patched target expects.

For example:

- 240p/60 targets require the Wii to be operating in a 60 Hz family.
- 288p/50 targets require the Wii to be operating in a 50 Hz PAL family.

The GUI displays the corresponding requirement for the selected target.

The experimental 240p/50 and 288p/60 combinations are research targets. They should be treated as tests, not as established standards for every Wii and CRT.

---

## Testing and current state

This project is actively being validated against multiple N64 Virtual Console WADs and emulator revisions rather than assuming that one game represents every build.

During the current PAL/NTSC work, the following retail WADs were used as structural comparison samples:

### PAL / Europe

- Pokémon Snap (Germany)
- The Legend of Zelda: Ocarina of Time (Europe)
- Lylat Wars (Europe, Rev 3)
- Super Mario 64 (Europe)

### NTSC / USA

- Bomberman Hero (USA)
- 1080 Snowboarding (USA)
- Yoshi's Story (USA)

These comparisons showed that the basic render-mode layout is remarkably consistent, while the PAL runtime height-handling code is **not** identical across every emulator build. That finding directly led to the current optional PAL-runtime patching logic.

### What is established vs experimental

The original 240p/60 NTSC approach is the established path of this project.

The newer PAL work is explicitly experimental. In particular, the current code has been designed to **locate and patch** PAL runtime handling safely across multiple WADs, but that does not by itself prove that every target combination works correctly on every real Wii and CRT.

Real-hardware reports are therefore important. A useful report should include:

- game / WAD region and revision
- selected target mode
- Wii video setting
- CRT / display type
- whether the channel booted
- whether the signal was actually 240p/288p
- whether the image had incorrect colors, geometry, flicker or instability

---

## Why there are no useful before/after screenshots

A screenshot is a poor way to demonstrate the change from interlaced output to progressive low-resolution CRT output. The key difference is temporal: 480i flicker exists between fields, while the benefit of 240p/288p is the stable scanline structure and progressive timing of the signal.

Real hardware is the meaningful test target.

---

## Building

The repository contains a GitHub Actions workflow that builds the standalone Windows executable.

A local build can be produced with the project's normal build scripts and dependencies.

The resulting artifact is a standalone `vc64_240p.exe`.

---

## Credits

- **BirdonWheels** — demonstrated on r/crtgaming in 2026 that low-resolution N64 VC output was possible by patching Nintendo's emulator.
- **NoobletCheese / Maeson** — dark-filter removal method.
- **[FriishProduce](https://github.com/CatmanFan/FriishProduce)** — injection workflow and related emulator research.
- **[gzinject](https://github.com/PracticeROM/gzinject)** (KrimtonZ) — WAD handling reference and common-key generation.

This repository extends the original 240p work with structural PAL/NTSC analysis, automatic region selection, and experimental multi-timing support.

## License

MIT — see [LICENSE](LICENSE).
