# Technical notes

**English** · [Português](TECNICO.md)

This document describes how the vc64_240p patch locates its targets without relying on fixed offsets, with special attention to the current PAL/NTSC work.

The important design rule is: **do not assume one N64 VC emulator build represents all others.** Pokémon Snap was the starting point for the PAL investigation, but additional retail WADs showed that some runtime details differ between builds.

---

## 1. WAD structure

A Wii WAD contains a header, certificate chain, ticket, TMD, encrypted contents and optional footer. Sections are aligned to `0x40`.

For N64 VC channels, the emulator is normally found in content 1, either as a raw DOL or as Nintendo LZ77 (`0x10`) compressed data. The ROM and related resources are normally in the U8 archive in content 5.

The tool validates content SHA-1 values against the TMD before modifying a WAD and rewrites the affected content metadata when it writes the result.

---

## 2. Locating the render-mode table

The N64 VC emulator contains `GXRenderModeObj` structures, each `0x3C` bytes long. The locator identifies them structurally instead of using game-specific offsets.

Useful fields are:

```text
+0x00 viTVmode
+0x04 fbWidth
+0x06 efbHeight
+0x08 xfbHeight
+0x0A viXOrigin
+0x0C viYOrigin
+0x0E viWidth
+0x10 viHeight
+0x14 xFBmode
+0x18 field_rendering
+0x19 aa
+0x1A sample_pattern[24]
+0x32 vfilter[7]
```

The locator looks for plausible VC render objects including a `fbWidth` of 640, matching EFB/XFB heights, a matching VI height, a valid `viTVmode`, and a seven-tap vfilter whose coefficients sum to 64.

`viTVmode` uses the low two bits for the timing mode:

```text
0 = interlaced
1 = double-strike
2 = progressive
```

A key lesson from testing is that the emulator may contain NTSC, PAL, MPAL and EURGB60 structures side by side. The console's active video configuration selects which family is used at runtime.

The current patcher therefore selects the requested **interlaced** render structure structurally and avoids accidentally selecting a progressive PAL entry when a build contains several PAL objects.

---

## 3. Automatic PAL / NTSC detection

The GUI determines the WAD's normal video family from the channel metadata rather than from the mere presence of PAL/NTSC render structures in the emulator.

The current mapping is:

```text
TMD region 0 = Japan  → NTSC family
TMD region 1 = USA    → NTSC family
TMD region 2 = Europe/Australia → PAL family
```

A title-ID suffix fallback is used for unusual/free-region titles.

This distinction matters because a USA WAD can still contain PAL render structures. The presence of a PAL object inside the emulator does not make the title a PAL channel.

Automatic detection only selects the normal default target. The GUI still allows manual selection of all four experimental/established target combinations.

---

## 4. The low-resolution video patch

The original 240p patch is deliberately small. The emulator continues to render using its normal high-resolution framebuffer configuration; the final VI path is changed instead.

The core operations are:

1. Change the selected interlaced `viTVmode` to double-strike.
2. Change `viHeight` to the target `240` or `288` value.
3. Replace the vfilter with the progressive profile:

```text
00 00 15 16 15 00 00
```

4. NOP the instruction that adds one line to the second VI field base.

The last step is important. Without it, the resulting low-resolution signal alternates between field line sets and exhibits strong flicker.

The patch intentionally leaves the emulator's normal EFB/XFB allocation unchanged. Changing the rendering heights directly was tested and caused either black screens, cropping or zoomed output rather than the desired 2:1 low-resolution image.

---

## 5. Locating the VI field-base offset instruction

The main field-base calculation is not found by searching for literal VI register offsets. The SDK writes those registers through a shadow structure.

A useful structural signature is the framebuffer-register packing code containing four `srwi r0,r0,5` (`0x5400D97E`) instructions at regular spacing.

The relevant helper ultimately contains a pattern equivalent to:

```text
stw   rS,0(rA)       first field base
bne   +8
b     +8
add   rD,rA,rB       second field = base + one line
stw   rD,0(rA)
```

The locator further classifies which occurrence belongs to the main framebuffer by tracing the nearby `+0x30` main-framebuffer structure field.

There can be another occurrence associated with stereoscopic 3D. That path must not be confused with the main framebuffer path.

The patch replaces the one-line `add` with a PowerPC NOP (`0x60000000`).

---

## 6. PAL runtime height handling

This is the main finding from the current PAL investigation.

### Pokémon Snap starting point

The first PAL test was **Pokémon Snap (Germany)**. Its PAL path contains a runtime operation that loads a height of `574` and later stores that value into the VI/XFB-related fields.

That means changing the static PAL render-mode object's height alone is ineffective: the runtime code overwrites it again.

### Additional WAD comparison

The same structural investigation was then run against:

**PAL / Europe**

- Pokémon Snap (Germany)
- The Legend of Zelda: Ocarina of Time (Europe)
- Lylat Wars (Europe, Rev 3)
- Super Mario 64 (Europe)

**NTSC / USA**

- Bomberman Hero (USA)
- 1080 Snowboarding (USA)
- Yoshi's Story (USA)

The result was important: the PAL render-mode structures are broadly consistent, but the recognizable `574` runtime height override is **not present in every build**.

In other words, the Pokémon Snap implementation cannot be promoted to a universal fixed PAL assumption.

### Current implementation

The current `video_patch.py` therefore treats the PAL runtime path as optional:

```text
PAL target selected
      ↓
Find PAL interlaced render mode
      ↓
Look for PAL runtime height override
      ↓
Present?
 ┌────┴────┐
 yes       no
  ↓         ↓
patch      skip runtime step
height
and disable
XFB store
```

When the runtime pattern is present, the tool recognizes the known states `574`, `288` and `240`. A `574` value is changed to the requested target height, and the runtime XFB-height store is neutralized so the value cannot immediately be restored.

When no corresponding runtime override is found, that absence is treated as a valid build variant rather than an error. The static PAL render-mode patch is still applied.

This is the principal reason the current PAL implementation is more robust than the original Pokémon-Snap-specific approach.

---

## 7. Selecting the correct PAL/NTSC render object

Some emulator builds contain more than one PAL or NTSC-related object, including progressive variants. A naive `first match` approach can therefore select an object that is never used for the desired path.

The current selector:

1. chooses the exact requested TV family (`NTSC` or `PAL`);
2. requires the object to be interlaced;
3. prefers the normal `480`/`528` EFB sizes used by these VC builds;
4. only falls back to another suitable interlaced structure when the exact canonical object is absent.

This specifically matters for builds such as the tested **Bomberman Hero** variant, which contains multiple PAL render objects including progressive entries.

---

## 8. Dark filter

The optional dark-filter patch is independent of the video-mode patch.

The tool locates the function by its characteristic comparisons against `0xFF`, then walks backwards to the function prologue and writes a `blr` (`0x4E800020`) over that prologue.

A patched function no longer contains its original prologue, so detection checks for both the original prologue and the already-written `blr` state.

---

## 9. Important things that were wrong first

Several plausible approaches were rejected during the investigation:

| Hypothesis | Result |
|---|---|
| Set EFB/XFB height directly to 240 | black screen or incorrect scaling/cropping |
| Use 240-line EFB/XFB and let the emulator solve the rest | zoomed/cropped output |
| Patch only one NTSC render object | can silently patch an object the console never selects |
| Select the first PAL object found | unsafe for builds containing multiple PAL variants |
| Assume every PAL build overwrites height with `574` | disproved by the additional PAL comparison WADs |
| Use fixed game-specific offsets | offsets differ between emulator revisions |
| Rely on ROM strings to identify emulator behavior | generic strings can give false conclusions |

The implementation that survived testing is structural matching plus conservative validation.

---

## 10. Experimental video modes

The GUI exposes four combinations:

```text
240p @ 60 Hz (NTSC)  — established/original path
240p @ 50 Hz (NTSC)  — experimental
288p @ 60 Hz (PAL)   — experimental
288p @ 50 Hz (PAL)   — experimental
```

The labels are intentionally kept as the project currently uses them. Internally the patch selects the NTSC or PAL timing family associated with the requested output timing.

The code can generate these patches, but **real-hardware validation is still required** for the newer combinations. Successful structural patching is not proof that a particular Wii/CRT combination accepts a given timing.

For a PAL Wii and 15 kHz CRT, `288p @ 50 Hz (PAL)` is currently the principal research target.

---

## 11. WAD safety and verification

Before changing a WAD, the tool verifies that content hashes match the TMD. If they do not, it refuses to modify the WAD.

The output is written as a new file. The input file is not overwritten.

After writing, the tool reloads the resulting WAD and checks its content hashes again. This catches packaging or encryption mistakes before the user installs the result.

The standalone Windows build also generates the Wii common key automatically on first use using the bundled `gzinject` helper, so users do not need to provide a key file manually.

---

## 12. Testing philosophy

The project is intentionally being tested against multiple emulator builds instead of assuming that one retail game is representative.

The seven comparison WADs listed above were chosen specifically to answer whether the structural video targets survive differences in game, region, revision and emulator code layout.

The current conclusions are:

- the render-mode structures are sufficiently consistent to locate structurally;
- the main framebuffer field-offset code is sufficiently consistent to locate structurally;
- PAL runtime height handling varies enough that it must be detected conditionally.

That last point is the reason the current PAL patcher does not simply copy Pokémon Snap's runtime assumptions to every game.

