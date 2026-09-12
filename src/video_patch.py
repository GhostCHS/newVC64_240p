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
    """Locate the PAL runtime height override, if present.

    The known PAL VC family loads 574 and stores it into both the XFB-height
    (+8) and VI-height (+16) fields. For a real PAL double-strike mode these
    runtime stores must both be disabled so the custom render-mode geometry
    survives unchanged.
    """
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
            if vi_disabled and xfb_disabled:
                state = "patched"
            elif xfb_disabled or vi_disabled:
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
    """Return patch operations and metadata for the selected CRT mode.

    NTSC 240p remains the established upstream-style patch.
    PAL low-resolution modes use the native Wii double-strike geometry:
    xfbHeight = target_height and viHeight = 2 * target_height.
    """
    if target_tv not in ("NTSC", "PAL"):
        raise ValueError(f"Unsupported target TV mode: {target_tv}")
    if target_height not in (240, 288):
        raise ValueError(f"Unsupported target height: {target_height}")

    modes = T.find_render_modes(emu)
    mode = _select_interlaced_mode(modes, target_tv)
    if mode is None:
        raise RuntimeError(f"Could not locate the {target_tv} interlaced render mode table entry.")

    dol = T.Dol(emu)
    adds = T.find_field_adds(emu, dol)
    main = [h for h in adds if h["field"] == 0x30]
    if not main:
        raise RuntimeError("Could not locate the main VI field-offset instruction.")

    already_ds = (mode["tv"] & 3) == 1
    ops = []

    if target_tv == "PAL":
        # Native Wii PAL double-strike geometry (e.g. libogc TVPal264Ds):
        # xfbHeight is the number of displayed low-res lines and viHeight is
        # exactly twice that value. This is the key difference from the
        # original NTSC 240p VC patch, which intentionally keeps its 480-line
        # XFB and uses DF decimation.
        ops.extend([
            (mode["off"], 4, mode["tv"] | 1),          # PAL_INT -> PAL_DS
            (mode["off"] + 0x06, 2, target_height),    # efbHeight
            (mode["off"] + 0x08, 2, target_height),    # xfbHeight
            (mode["off"] + 0x0C, 2, (576 - 2 * target_height) // 2),  # viYOrigin
            (mode["off"] + 0x10, 2, target_height * 2),  # viHeight
            (mode["off"] + 0x14, 4, 0),                # XFBMODE_SF
            (mode["off"] + 0x18, 1, 0),                # field_rendering=false
        ])
        for i, value in enumerate(T.PROG_VFILTER):
            if mode["vfilter"][i] != value:
                ops.append((mode["off"] + 0x32 + i, 1, value))

        runtime = inspect_pal_runtime(emu, mode["off"])
        if runtime.get("present"):
            if runtime["state"] == "partial":
                raise RuntimeError(
                    "This WAD contains an older partial PAL runtime patch. "
                    "Repatch the original unmodified WAD."
                )
            # The runtime PAL path writes 574 into both fields. Disable both
            # stores; otherwise it destroys the low-resolution DS geometry.
            for off in runtime["vi_stores"]:
                ops.append((off, 4, 0x60000000))
            ops.append((runtime["xfb_store"], 4, 0x60000000))

        # No one-line field-base fix here: PAL_DS is single-field output and
        # uses the same SF geometry as Nintendo's native PAL DS modes.
        runtime_meta = runtime
    else:
        # Keep the established NTSC path and the current experimental NTSC
        # 288p behavior unchanged.
        if not already_ds:
            ops.append((mode["off"], 4, mode["tv"] | 1))
        if mode["vh"] != target_height:
            ops.append((mode["off"] + 0x10, 2, target_height))
        if mode["vfilter"] != T.PROG_VFILTER:
            for i, value in enumerate(T.PROG_VFILTER):
                ops.append((mode["off"] + 0x32 + i, 1, value))
        ops.append((main[0]["off"], 4, 0x60000000))
        runtime_meta = None

    return ops, {
        "mode": mode,
        "already_ds": already_ds,
        "target_height": target_height,
        "runtime": runtime_meta,
    }
