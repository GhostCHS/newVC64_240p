"""Video-mode patch helpers for 240p60/240p50/288p60/288p50."""
from __future__ import annotations

import struct

import vc64tool as T


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack(">I", buf[off:off + 4])[0]


def _opcode(op: int) -> int:
    return op >> 26


def _is_addis_r0(w: int, reg: int) -> bool:
    return _opcode(w) == 15 and ((w >> 21) & 0x1F) == reg and ((w >> 16) & 0x1F) == 0


def _is_addi_same(w: int, reg: int) -> bool:
    return _opcode(w) == 14 and ((w >> 21) & 0x1F) == reg and ((w >> 16) & 0x1F) == reg


def _is_sth_r0(w: int, imm: int) -> bool:
    return _opcode(w) == 44 and ((w >> 21) & 0x1F) == 0 and (w & 0xFFFF) == imm


def _encode_addi_r0(value: int) -> int:
    return (14 << 26) | (value & 0xFFFF)


def _select_interlaced_mode(modes, target_tv: str):
    """Select the base interlaced render mode for the requested TV family."""
    base = T.TV_BASE[target_tv]
    exact = [m for m in modes if m["tv"] == base and (m["tv"] & 3) == 0]
    if exact:
        sized = [m for m in exact if m["efb"] in (480, 528)]
        return sized[0] if sized else exact[0]

    fallback = [
        m for m in modes
        if m["tv"] not in (base + 1, base + 2, base + 3)
        and (m["tv"] & 3) == 0
        and m["efb"] in (480, 528)
    ]
    if fallback:
        return fallback[0]
    return None


def inspect_pal_runtime(emu: bytes, pal_mode_off: int):
    """Locate a PAL runtime height override for diagnostics only."""
    dol = T.Dol(emu)
    pal_va = dol.f2v(pal_mode_off)
    if pal_va is None:
        return {"ok": False, "present": False,
                "reason": "Could not map the PAL render mode to a runtime address."}

    target_hi = (pal_va >> 16) & 0xFFFF
    target_lo = pal_va & 0xFFFF

    for wanted_height in (574, 288, 240):
        for p in range(0, len(emu) - 4, 4):
            if not dol.is_text(p):
                continue
            if _u32(emu, p) != _encode_addi_r0(wanted_height):
                continue

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

            vi_stores = []
            xfb_store = None
            for r in range(p + 4, min(len(emu), p + 96), 4):
                w2 = _u32(emu, r)
                if _is_sth_r0(w2, 16):
                    vi_stores.append(r)
                elif _is_sth_r0(w2, 8):
                    xfb_store = r

            if not vi_stores or xfb_store is None:
                continue

            vi_disabled = all(_u32(emu, r) == 0x60000000 for r in vi_stores)
            xfb_disabled = _u32(emu, xfb_store) == 0x60000000
            if vi_disabled and not xfb_disabled:
                state = "patched"
            elif xfb_disabled and not vi_disabled:
                state = "legacy-partial"
            elif vi_disabled and xfb_disabled:
                state = "partial"
            else:
                state = "unpatched"

            return {
                "ok": True,
                "present": True,
                "li_offset": p,
                "vi_stores": vi_stores,
                "xfb_store": xfb_store,
                "current_height": wanted_height,
                "pal_va": pal_va,
                "state": state,
            }

    return {"ok": True, "present": False,
            "reason": "No PAL runtime height override found in this emulator build.",
            "pal_va": pal_va}


def build_video_ops(emu: bytes, target_tv: str, target_height: int):
    """Return patch operations for the selected CRT mode.

    PAL 288p is currently a controlled one-change experiment: only the
    PAL_INT -> PAL_DS render-mode flag is changed. Every other PAL value is
    deliberately left untouched until the effect of PAL_DS alone is known.
    """
    if target_tv not in ("NTSC", "PAL"):
        raise ValueError(f"Unsupported target TV mode: {target_tv}")
    if target_height not in (240, 288):
        raise ValueError(f"Unsupported target height: {target_height}")

    modes = T.find_render_modes(emu)
    mode = _select_interlaced_mode(modes, target_tv)
    if mode is None:
        raise RuntimeError(f"Could not locate the {target_tv} interlaced render mode table entry.")

    if target_tv == "PAL" and target_height == 288:
        runtime = inspect_pal_runtime(emu, mode["off"])
        return [(mode["off"], 4, mode["tv"] | 1)], {
            "mode": mode,
            "already_ds": (mode["tv"] & 3) == 1,
            "target_height": target_height,
            "runtime": runtime,
            "single_change_test": True,
        }

    dol = T.Dol(emu)
    adds = T.find_field_adds(emu, dol)
    main = [h for h in adds if h["field"] == 0x30]
    if not main:
        raise RuntimeError("Could not locate the main VI field-offset instruction.")

    already_ds = (mode["tv"] & 3) == 1
    ops = []
    if not already_ds:
        ops.append((mode["off"], 4, mode["tv"] | 1))
    if mode["vh"] != target_height:
        ops.append((mode["off"] + 0x10, 2, target_height))
    if mode["vfilter"] != T.PROG_VFILTER:
        for i, value in enumerate(T.PROG_VFILTER):
            ops.append((mode["off"] + 0x32 + i, 1, value))

    runtime = None
    if target_tv == "PAL":
        runtime = inspect_pal_runtime(emu, mode["off"])
        if runtime.get("present"):
            if runtime["state"] == "legacy-partial":
                raise RuntimeError(
                    "This WAD contains the older experimental PAL runtime patch "
                    "that disabled the XFB-height store. Repatch the original WAD."
                )
            for off in runtime["vi_stores"]:
                if _u32(emu, off) != 0x60000000:
                    ops.append((off, 4, 0x60000000))

    ops.append((main[0]["off"], 4, 0x60000000))

    return ops, {
        "mode": mode,
        "already_ds": already_ds,
        "target_height": target_height,
        "runtime": runtime,
    }
