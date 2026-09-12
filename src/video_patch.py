"""Video-mode patch helpers for 240p60 and experimental PAL 288p50."""
from __future__ import annotations

import struct

import vc64tool as T


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack(">I", buf[off:off + 4])[0]


def _opcode(op: int) -> int:
    return op >> 26


def _is_addis_r0(w: int, reg: int) -> bool:
    # addis reg,r0,imm
    return _opcode(w) == 15 and ((w >> 21) & 0x1F) == reg and ((w >> 16) & 0x1F) == 0


def _is_addi_same(w: int, reg: int) -> bool:
    # addi reg,reg,imm
    return _opcode(w) == 14 and ((w >> 21) & 0x1F) == reg and ((w >> 16) & 0x1F) == reg


def _is_sth_r0(w: int, imm: int) -> bool:
    # sth r0,imm(rA)
    return _opcode(w) == 44 and ((w >> 21) & 0x1F) == 0 and (w & 0xFFFF) == imm


def _encode_addi_r0(value: int) -> int:
    return (14 << 26) | (value & 0xFFFF)


def inspect_pal_runtime(emu: bytes, pal_mode_off: int):
    """Locate the PAL runtime 574-height override.

    The locator follows the runtime pointer to the PAL render-mode struct rather
    than relying on a fixed DOL offset. This is intended to work across emulator
    revisions that keep the same code structure.
    """
    dol = T.Dol(emu)
    pal_va = dol.f2v(pal_mode_off)
    if pal_va is None:
        return {"ok": False, "reason": "Could not map the PAL render mode to a runtime address."}

    target_hi = (pal_va >> 16) & 0xFFFF
    target_lo = pal_va & 0xFFFF

    for wanted_height in (574, 288):
        for p in range(0, len(emu) - 4, 4):
            if not dol.is_text(p):
                continue
            if _u32(emu, p) != _encode_addi_r0(wanted_height):
                continue

            # The PAL pointer construction can straddle the height load:
            #   addis rX,r0,hi
            #   addi  rX,rX,lo
            #   addi  r0,r0,574/288
            found_ptr = False
            for q in range(max(0, p - 96), min(p + 4, len(emu) - 4), 4):
                w1 = _u32(emu, q)
                reg = (w1 >> 21) & 0x1F
                if not _is_addis_r0(w1, reg) or (w1 & 0xFFFF) != target_hi:
                    continue
                for r in range(q + 4, min(p + 20, len(emu) - 4), 4):
                    w2 = _u32(emu, r)
                    if _is_addi_same(w2, reg) and (w2 & 0xFFFF) == target_lo:
                        found_ptr = True
                        break
                if found_ptr:
                    break
            if not found_ptr:
                continue

            vi_store = None
            xfb_store = None
            for r in range(p + 4, min(len(emu), p + 96), 4):
                w2 = _u32(emu, r)
                if _is_sth_r0(w2, 16):
                    vi_store = r
                elif _is_sth_r0(w2, 8):
                    xfb_store = r
                if vi_store is not None and xfb_store is not None:
                    break

            if vi_store is None or xfb_store is None:
                continue

            state = "unpatched" if wanted_height == 574 else (
                "patched" if _u32(emu, xfb_store) == 0x60000000 else "partial"
            )
            return {
                "ok": True,
                "li_offset": p,
                "vi_store": vi_store,
                "xfb_store": xfb_store,
                "current_height": wanted_height,
                "pal_va": pal_va,
                "state": state,
            }

    return {"ok": False, "reason": "Could not locate the PAL runtime height override."}


def build_video_ops(emu: bytes, target_tv: str, target_height: int):
    """Return patch ops and metadata for the selected CRT video mode."""
    if target_tv not in ("NTSC", "PAL"):
        raise ValueError(f"Unsupported target TV mode: {target_tv}")

    modes = T.find_render_modes(emu)
    base = T.TV_BASE[target_tv]
    mode = next((m for m in modes if m["tv"] == base), None)
    if mode is None:
        mode = next((m for m in modes if m["tv"] == base + 1), None)
    if mode is None:
        raise RuntimeError(f"Could not locate the {target_tv} render mode table entry.")

    dol = T.Dol(emu)
    adds = T.find_field_adds(emu, dol)
    main = [h for h in adds if h["field"] == 0x30]
    if not main:
        raise RuntimeError("Could not locate the main VI field-offset instruction.")

    already_ds = (mode["tv"] & 3) == 1
    if already_ds:
        ops = []
    else:
        ops = [
            (mode["off"], 4, mode["tv"] | 1),
            (mode["off"] + 0x10, 2, target_height),
        ]
        for i, value in enumerate(T.PROG_VFILTER):
            ops.append((mode["off"] + 0x32 + i, 1, value))

    runtime = None
    if target_tv == "PAL":
        runtime = inspect_pal_runtime(emu, mode["off"])
        if not runtime["ok"]:
            raise RuntimeError(runtime["reason"])
        if runtime["current_height"] == 574:
            ops.append((runtime["li_offset"], 4, _encode_addi_r0(288)))
        if _u32(emu, runtime["xfb_store"]) != 0x60000000:
            ops.append((runtime["xfb_store"], 4, 0x60000000))

    # Remove the one-line field-base offset that causes even/odd line alternation.
    ops.append((main[0]["off"], 4, 0x60000000))

    return ops, {
        "mode": mode,
        "already_ds": already_ds,
        "target_height": target_height,
        "runtime": runtime,
    }
