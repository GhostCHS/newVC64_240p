# vc64_240p

**Real low-resolution output for Nintendo 64 Virtual Console on the Wii — targeting 15 kHz CRTs.**

This project patches the **official Nintendo N64 Virtual Console emulator** inside an existing Wii WAD so that it can output a real progressive low-resolution signal instead of the normal interlaced output.

The project started with a 240p/60 Hz NTSC patch and has been extended into a CRT-oriented video-mode tool with:

- automatic PAL/NTSC WAD detection
- 240p/60, 240p/50, 288p/60 and 288p/50 target modes
- structural detection across different Nintendo N64 VC emulator revisions
- optional removal of the emulator's dark filter
- automatic Wii common-key generation in the standalone Windows build

## Goal

The goal is not to replace Nintendo's emulator with a different N64 emulator.

The goal is to keep the things that make Nintendo's N64 Virtual Console useful — its per-title compatibility work, native save handling and suspend data — while changing the final video path so that a Wii connected to a 15 kHz CRT can produce the kind of progressive low-resolution signal associated with original consoles.

For a PAL Wii/CRT setup, the primary experimental target is **288p @ 50 Hz (PAL)**. The original **240p @ 60 Hz (NTSC)** path remains the established starting point. The other combinations are research targets and must be validated on real hardware.

---

## What the tool does

The GUI patches an **existing N64 Virtual Console WAD**. It does not need to inject a ROM in order to perform the video patch.

The four selectable target combinations are:

| Target | Status |
|---|---|
| **240p @ 60 Hz (NTSC)** | established/original path |
| **240p @ 50 Hz (NTSC)** | experimental |
| **288p @ 60 Hz (PAL)** | experimental |
| **288p @ 50 Hz (PAL)** | experimental |

The parenthetical labels are retained in the GUI as the project's target naming. Internally, the patch selects the NTSC or PAL render/timing family required for the requested output.

### Automatic region detection

When a WAD is opened, the GUI detects the channel's normal video family automatically from its TMD region metadata:

- Japan / USA → NTSC family
- Europe / Australia → PAL family

For unusual/free-region titles, a title-ID suffix fallback is used.

The automatic selection is only a default. All four targets remain manually selectable for testing.

A crucial distinction is that an emulator binary can contain NTSC, PAL, MPAL and EURGB60 render structures at the same time. The presence of a PAL structure inside a USA WAD does not make that WAD a PAL title.

---

## Why the patch is structural

The N64 VC emulator is not identical in every game, revision or injected channel. Fixed offsets taken from one WAD are therefore unsafe.

The patcher searches for the actual render-mode structures and PowerPC instruction patterns it needs. It refuses to modify a WAD when a required target cannot be located instead of silently writing to an unrelated address.

The core video work keeps the emulator's normal rendering path intact and changes the VI/display configuration needed for progressive low-resolution output.

The main changes are:

1. interlaced `viTVmode` → double-strike
2. `viHeight` → the selected 240/288 target height
3. progressive vfilter profile to remove interlace-oriented deflicker
4. NOP of the one-line field-base offset that otherwise causes heavy field-to-field flicker
5. PAL runtime-height handling, when a given emulator build actually contains it

The optional dark-filter patch is separate and simply disables the emulator function responsible for global image darkening.

See **[docs/TECHNICAL.md](docs/TECHNICAL.md)** for the structural signatures and the investigation history.

---

## PAL support: what we learned

The PAL work did **not** turn out to be identical across all tested WADs.

The first PAL investigation used **Pokémon Snap (Germany)** and found a runtime path that overwrote the PAL height with `574`. Patching only the PAL render-mode table therefore did not work.

We then compared additional retail WADs from both regions:

### PAL / Europe

- Pokémon Snap (Germany)
- The Legend of Zelda: Ocarina of Time (Europe)
- Lylat Wars (Europe, Rev 3)
- Super Mario 64 (Europe)

### NTSC / USA

- Bomberman Hero (USA)
- 1080 Snowboarding (USA)
- Yoshi's Story (USA)

The important finding was that the **basic render-mode structure is highly consistent**, while the **PAL runtime height-handling code is not**. Some builds contain the recognizable `574` runtime sequence; others have no equivalent override even though their PAL render structures are present.

The current patcher therefore treats the PAL runtime override as **optional**:

```text
WAD
 ↓
Detect NTSC/PAL family
 ↓
Find the requested interlaced render-mode structure
 ↓
Find the main framebuffer field-offset instruction
 ↓
PAL only:
    runtime height override present?
       yes → patch requested height and disable runtime XFB-height store
       no  → skip that optional step
 ↓
Apply video patch
 ↓
Write and verify the resulting WAD
```

This avoids making Pokémon Snap's implementation a hardcoded assumption for every N64 VC build.

---

## Important experimental status

The code can **locate and patch** several low-resolution target combinations, but that is not the same as proving that every combination is electrically or temporally valid on every Wii and CRT.

Current status should therefore be understood as:

- **240p @ 60 Hz (NTSC):** established project path.
- **288p @ 50 Hz (PAL):** main experimental target for PAL Wii/CRT testing.
- **240p @ 50 Hz:** experimental.
- **288p @ 60 Hz:** experimental.

Real-hardware testing is required, especially for the latter three modes.

Useful test reports should state the game/WAD region and revision, selected target mode, Wii video setting, CRT/display, whether the channel boots, whether the signal is actually 240p/288p, and whether there are color, geometry, flicker or stability problems.

---

## What it is not

The GUI is **not primarily a ROM injector**. It is designed to patch an existing N64 VC WAD: an official retail channel or an injected channel that already uses a compatible Nintendo N64 VC emulator build.

For building a channel from a ROM, **[FriishProduce](https://github.com/CatmanFan/FriishProduce)** remains the preferred injector. The intended workflow is:

```text
ROM
 ↓
FriishProduce
 ↓
N64 VC WAD
 ↓
vc64_240p
 ↓
CRT-oriented video patch
```

The repository's CLI contains experimental injection/`romc` functionality, but that is not the main purpose of the GUI.

---

## Usage

1. Run `vc64_240p.exe`.
2. Choose an N64 VC WAD.
3. The tool verifies the WAD content hashes and detects its normal NTSC/PAL family.
4. A default target is selected automatically:
   - NTSC → **240p @ 60 Hz (NTSC)**
   - PAL → **288p @ 50 Hz (PAL)**
5. Select another target manually when testing a different timing combination.
6. Optionally enable dark-filter removal.
7. Apply the patch.
8. A new WAD is written beside the original; the input WAD is left untouched.

The standalone build generates the Wii common key automatically on first use. No manual `common-key.bin` file is required.

### Wii / CRT setup

The Wii must be configured for the timing family expected by the selected target. For example, a 240p/60 target requires a 60 Hz family, while 288p/50 requires the PAL 50 Hz family. The GUI displays the corresponding requirement.

A recovery method such as **Priiloader** is strongly recommended when installing and testing modified WADs.

---

## Testing philosophy

This project deliberately tests multiple emulator builds instead of assuming that one retail game represents the whole N64 VC library.

The comparison WADs above were used to separate three different questions:

1. Is the render-mode layout consistent enough to find structurally?
2. Is the main framebuffer field-offset code consistent enough to patch structurally?
3. Is PAL runtime height handling identical across builds?

The answer so far is effectively **yes, yes, no**.

That is why the implementation does not use a Pokémon-Snap-specific PAL offset and why the PAL runtime step is conditional.

---

## Screenshots and CRT output

A normal screenshot is not a useful demonstration of the change from 480i to 240p/288p on a CRT. The important differences are temporal and signal-level: interlaced field flicker versus stable progressive scanlines.

Real hardware is the meaningful test target.

---

## Building

The repository contains a GitHub Actions workflow that produces a standalone Windows executable:

```text
vc64_240p.exe
```

The workflow downloads `gzinject.exe` at build time and bundles it into the standalone application so that common-key generation works automatically.

For a local source build, use Python 3.8+ with `cryptography` and `pyinstaller`.

---

## Credits

- **BirdonWheels** — demonstrated low-resolution N64 VC output by patching Nintendo's emulator.
- **NoobletCheese / Maeson** — dark-filter removal method.
- **[FriishProduce](https://github.com/CatmanFan/FriishProduce)** — N64 VC injection workflow and related emulator research.
- **[gzinject](https://github.com/PracticeROM/gzinject)** (KrimtonZ) — WAD handling reference and common-key generation.

This repository extends the original 240p work with structural PAL/NTSC analysis, automatic region selection and experimental multi-timing support.

## License

MIT — see [LICENSE](LICENSE).
