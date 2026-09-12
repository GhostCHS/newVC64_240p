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


def _signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _encode_addi_r0(value: int) -> int:
    return (14 << 26) | (0 << 21) | (0 << 16) | (value & 0xFFFF)


def _find_pal_mode(emu: bytes):
    modes = T.find_render_modes(emu)
    for mode in modes:
        if mode["tv"] == T.TV_BASE["PAL"]:
            return mode
    for mode in modes:
        if mode["tv"] == T.TV_BASE["PAL"] + 1:
            return mode
    return None


def inspect_pal_runtime(emu: bytes, pal_mode_off: int):
    """Locate the PAL runtime 574-height override.

    Returns a dict with state and patch offsets. The locator is based on the
    actual PAL render-mode pointer embedded in the function, not a fixed file
    offset, so it can be reused across emulator revisions.
    """
    dol = T.Dol(emu)
    pal_va = dol.f2v(pal_mode_off)
    if pal_va is None:
        return {"ok": False, "reason": "Could not map the PAL render mode to a runtime address."}

    target_hi = (pal_va >> 16) & 0xFFFF
    target_lo = pal_va & 0xFFFF

    for p in range(0, len(emu) - 4, 4):
        if not dol.is_text(p):
            continue
        w = _u32(emu, p)
        if w != _encode_addi_r0(574):
            continue

        # Look backwards for addis/addi constructing the PAL mode pointer.
        found_ptr = False
        for q in range(max(0, p - 96), p, 4):
            w1 = _u32(emu, q)
            if not _is_addis_r0(w1, (w1 >> 21) & 0x1F):
                continue
            reg = (w1 >> 21) & 0x1F
            imm_hi = w1 & 0xFFFF
            if imm_hi != target_hi:
                continue
            for r in range(q + 4, min(p, q + 32), 4):
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
            return {"ok": False, "reason": "Found the PAL height constant but not both runtime height stores."}

        return {
            "ok": True,
            "li_offset": p,
            "vi_store": vi_store,
            "xfb_store": xfb_store,
            "current_height": 574,
            "pal_va": pal_va,
            "state": "unpatched",
        }

    # Already patched builds use 288 instead of 574. Locate the same structure.
    for p in range(0, len(emu) - 4, 4):
        if not dol.is_text(p):
            continue
        if _u32(emu, p) != _encode_addi_r0(288):
            continue
        found_ptr = False
        for q in range(max(0, p - 96), p, 4):
            w1 = _u32(emu, q)
            if not _is_addis_r0(w1, (w1 >> 21) & 0x1F):
                continue
            reg = (w1 >> 21) & 0x1F
            if (w1 & 0xFFFF) != target_hi:
                continue
            for r in range(q + 4, min(p, q + 32), 4):
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
        if vi_store is not None and xfb_store is not None:
            state = "patched" if _u32(emu, xfb_store) == 0x60000000 else "partial"
            return {
                "ok": True,
                "li_offset": p,
                "vi_store": vi_store,
                "xfb_store": xfb_store,
                "current_height": 288,
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
        # A previously patched build may still need the PAL runtime fix.
    else:
        ops = [(mode["off"], 4, mode["tv"] | 1)]
        ops.append((mode["off"] + 0x10, 2, target_height))
        for i, value in enumerate(T.PROG_VFILTER):
            ops.append((mode["off"] + 0x32 + i, 1, value))

    if target_tv == "PAL":
        runtime = inspect_pal_runtime(emu, mode["off"])
        if not runtime["ok"]:
            raise RuntimeError(runtime["reason"])
        if runtime["current_height"] == 574:
            ops.append((runtime["li_offset"], 4, _encode_addi_r0(288)))
        if runtime["current_height"] == 288 and runtime["state"] == "patched":
            pass
        if _u32(emu, runtime["xfb_store"]) != 0x60000000:
            ops.append((runtime["xfb_store"], 4, 0x60000000))
    ops.append((main[0]["off"], 4, 0x60000000))

    return ops, {
        "mode": mode,
        "already_ds": already_ds,
        "target_height": target_height,
        "runtime": inspect_pal_runtime(emu, mode["off"]) if target_tv == "PAL" else None,
    }
