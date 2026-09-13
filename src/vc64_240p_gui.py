#!/usr/bin/env python3
"""English standalone GUI for patching Nintendo 64 Virtual Console WADs."""

from __future__ import annotations

import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, ttk

import key_runtime as K
import vc64tool as T
import video_patch as VP

APP = "vc64 240p"
VERSION = "1.3"

BG = "#1e1e22"
FG = "#e8e8ea"
SUB = "#9a9aa2"
GREEN = "#2e7d32"
RED = "#b3261e"
AMBER = "#8a6d1f"
BLUE = "#2f4f7f"

MODES = {
    "240p @ 60 Hz (NTSC)": ("NTSC", 240, False),
    "240p @ 50 Hz (NTSC)": ("PAL", 240, True),
    "288p @ 60 Hz (PAL)": ("NTSC", 288, True),
    "288p @ 50 Hz (PAL)": ("PAL", 288, True),
}

AUTO_MODES = {
    "NTSC": "240p @ 60 Hz (NTSC)",
    "PAL": "288p @ 50 Hz (PAL)",
}


def detect_wad_tv(wad):
    """Detect the WAD region and map it to its normal 50/60 Hz family.

    TMD region is preferred because it is part of the signed channel metadata.
    Title-ID suffix is used as a fallback for unusual/free-region titles.
    """
    region_map = {
        0: ("NTSC", "TMD region: Japan"),
        1: ("NTSC", "TMD region: USA"),
        2: ("PAL", "TMD region: Europe/Australia"),
    }
    if wad.region in region_map:
        return region_map[wad.region]

    suffix = wad.code[-1:].upper()
    if suffix in ("E", "J"):
        return "NTSC", f"title ID suffix: {suffix}"
    if suffix in ("P", "D", "F", "S", "I", "U"):
        return "PAL", f"title ID suffix: {suffix}"
    return None, "region not determinable"


class Gui:
    def __init__(self, root):
        self.root = root
        self.wad = None
        self.state = None
        self.q = queue.Queue()
        self.mode_manual = False
        self.detected_tv = None

        root.title(f"{APP} {VERSION}")
        root.configure(bg=BG)
        root.geometry("760x750")
        root.minsize(680, 680)

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text=APP, bg=BG, fg=FG,
                 font=("Segoe UI", 17, "bold")).pack(side="left")

        tk.Label(
            root,
            text="Patch an existing N64 Virtual Console WAD to real low-resolution output.",
            bg=BG,
            fg=SUB,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=16)

        file_row = tk.Frame(root, bg=BG)
        file_row.pack(fill="x", padx=16, pady=(14, 4))
        tk.Button(
            file_row,
            text="Choose WAD...",
            command=self.pick,
            relief="flat",
            bg=BLUE,
            fg="white",
            activebackground="#3d6499",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(side="left")
        self.file_name = tk.Label(
            file_row,
            text="No WAD chosen.",
            bg=BG,
            fg=SUB,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.file_name.pack(side="left", padx=12, fill="x", expand=True)

        mode_row = tk.Frame(root, bg=BG)
        mode_row.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(mode_row, text="Output mode:", bg=BG, fg=SUB,
                 font=("Segoe UI", 9)).pack(side="left")
        self.mode_var = tk.StringVar(value="240p @ 60 Hz (NTSC)")
        self.mode_box = ttk.Combobox(
            mode_row,
            textvariable=self.mode_var,
            state="readonly",
            values=tuple(MODES),
            width=29,
        )
        self.mode_box.pack(side="left", padx=10)
        self.mode_box.bind("<<ComboboxSelected>>", self.mode_changed)

        self.detected_label = tk.Label(
            mode_row,
            text="Detected source: —",
            bg=BG,
            fg=SUB,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.detected_label.pack(side="left", padx=(6, 0))

        self.mode_hint = tk.Label(
            root,
            text="240p @ 60 Hz is the established NTSC path. The other three combinations are experimental.",
            bg=BG,
            fg=SUB,
            justify="left",
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.mode_hint.pack(fill="x", padx=16, pady=(2, 0))

        self.panel = tk.Frame(root, bg=BG, height=138)
        self.panel.pack(fill="x", padx=16, pady=10)
        self.panel.pack_propagate(False)
        self.verdict_header = tk.Label(
            self.panel,
            text="Choose a WAD to begin.",
            bg=BG,
            fg=FG,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        )
        self.verdict_header.pack(fill="x", padx=12, pady=(10, 2))
        self.verdict_text = tk.Label(
            self.panel,
            text="",
            bg=BG,
            fg=FG,
            anchor="w",
            justify="left",
            font=("Consolas", 9),
        )
        self.verdict_text.pack(fill="both", padx=12, pady=(0, 8))

        tk.Label(
            root,
            text="The Wii common key is generated automatically on first use. No key file is required.",
            bg=BG,
            fg=SUB,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=16, pady=(2, 0))

        self.dark_var = tk.BooleanVar(value=False)
        self.dark_box = tk.Checkbutton(
            root,
            variable=self.dark_var,
            text="Also remove the dark filter (restore original brightness)",
            bg=BG,
            fg=FG,
            selectcolor="#2a2a30",
            activebackground=BG,
            activeforeground=FG,
            anchor="w",
            font=("Segoe UI", 9),
            state="disabled",
            disabledforeground="#6e6e78",
        )
        self.dark_box.pack(fill="x", padx=14, pady=(12, 0))

        self.go_btn = tk.Button(
            root,
            text="Apply selected video mode",
            command=self.convert,
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            pady=10,
            cursor="hand2",
            bd=0,
            highlightthickness=0,
            disabledforeground="#6e6e78",
        )
        self.go_btn.pack(fill="x", padx=16, pady=14)
        self.set_go(False)

        tk.Label(root, text="Log", bg=BG, fg=SUB, anchor="w",
                 font=("Segoe UI", 9)).pack(fill="x", padx=16)
        self.log = tk.Text(
            root,
            height=10,
            bg="#141417",
            fg="#c9c9d0",
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, padx=16, pady=(2, 14))
        self.log.configure(state="disabled")

        self.root.after(100, self.drain)

    def selected_video_mode(self, label=None):
        label = label or self.mode_var.get()
        tv, height, experimental = MODES[label]
        return tv, height, label, experimental

    def mode_changed(self, _event=None):
        self.mode_manual = True
        if self.wad:
            self.analyse()

    def requirement_text(self, mode_label=None):
        tv, height, label, experimental = self.selected_video_mode(mode_label)
        hz = 60 if "60 Hz" in label else 50
        region = "NTSC" if tv == "NTSC" else "PAL"
        text = f"Set the Wii to {hz} Hz / {region} before launching the patched channel."
        if experimental:
            text += "\nThis video combination is experimental and must be tested on real hardware."
        return text

    def say(self, msg=""):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.say(payload)
                elif kind == "verdict":
                    self.show_verdict(*payload)
                elif kind == "onlydark":
                    self.dark_var.set(True)
                    self.set_go(True, "Remove dark filter")
                elif kind == "dark":
                    if payload == "can-remove":
                        self.dark_box.configure(state="normal", fg=FG)
                    else:
                        self.dark_var.set(False)
                        self.dark_box.configure(state="disabled")
                elif kind == "detected":
                    tv, source, auto_label = payload
                    self.detected_tv = tv
                    self.detected_label.configure(text=f"Detected source: {tv} ({source})")
                    if not self.mode_manual and auto_label:
                        self.mode_var.set(auto_label)
                        self.say(f"Auto-detected {tv}; selected {auto_label}.")
                elif kind == "busy":
                    self.set_go(False, payload)
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def pick(self):
        path = filedialog.askopenfilename(
            title="Choose a WAD...",
            filetypes=[("Wii WAD", "*.wad"), ("All files", "*.*")],
        )
        if not path:
            return
        self.wad = path
        self.mode_manual = False
        self.detected_tv = None
        self.detected_label.configure(text="Detected source: analysing...")
        self.file_name.configure(text=os.path.basename(path))
        self.analyse()

    def set_go(self, enabled, text=None):
        if enabled:
            self.go_btn.configure(
                state="normal", bg=GREEN, fg="#ffffff",
                activebackground="#3a9440", activeforeground="#ffffff",
            )
        else:
            self.go_btn.configure(state="disabled", bg="#3a3a42", fg="#6e6e78")
        self.go_btn.configure(text=text or "Apply selected video mode")

    def show_verdict(self, colour, header, body, can_go):
        self.panel.configure(bg=colour)
        self.verdict_header.configure(bg=colour, text=header)
        self.verdict_text.configure(bg=colour, text=body)
        self.set_go(can_go)

    def analyse(self):
        self.set_go(False)
        self.show_verdict(BG, "Analysing...", "", False)
        threading.Thread(target=self._analyse, daemon=True).start()

    def _analyse(self):
        try:
            key_path = K.common_key_path()
            wad_obj = T.Wad(self.wad, T.load_key(key_path))
            detected_tv, source = detect_wad_tv(wad_obj)

            if detected_tv:
                auto_label = AUTO_MODES[detected_tv]
                self.q.put(("detected", (detected_tv, source, auto_label)))
            else:
                auto_label = None
                self.q.put(("detected", (None, source, None)))

            target_label_for_analysis = (
                auto_label if detected_tv and not self.mode_manual else self.mode_var.get()
            )
            target_tv, target_height, target_label, experimental = self.selected_video_mode(target_label_for_analysis)
            verdict = T.verdict(self.wad, key_path, target_tv)
            self.state = verdict

            if not verdict["ok"]:
                reason = verdict.get("reason") or "Could not find the emulator binary inside this WAD."
                self.q.put(("verdict", (RED, "COULD NOT READ THIS WAD", reason, False)))
                return

            if not verdict["hashes"]:
                self.q.put((
                    "verdict",
                    (RED, "COULD NOT READ THIS WAD",
                     "The WAD hashes do not match its TMD. Refusing to modify it.", False),
                ))
                return

            patch_status = "CAN BE LOCATED" if verdict["patchable"] else "target not found in this build"
            dark_status = {
                "can-remove": "CAN BE APPLIED",
                "already-removed": "already removed",
                "not-found": "target not found",
            }[verdict["dark"]]
            info = (
                f"{target_label:24}: {patch_status}\n"
                f"dark filter             : {dark_status}\n"
                f"channel                 : {verdict['code']}\n"
                f"compression             : {'LZ77' if verdict['compressed'] else 'raw DOL'}"
            )

            self.q.put(("dark", verdict["dark"]))
            can_dark = verdict["dark"] == "can-remove"

            if verdict["patchable"]:
                header = f"TARGETS FOUND FOR {target_label.upper()}"
                if experimental:
                    header += " [EXPERIMENTAL]"
                self.q.put((
                    "verdict",
                    (GREEN, header, info + "\n\n" + self.requirement_text(target_label), True),
                ))
            elif can_dark:
                self.q.put((
                    "verdict",
                    (AMBER, "ONLY DARK FILTER CAN BE CHANGED",
                     info + "\n\nThe selected video target was not found.", True),
                ))
                self.q.put(("onlydark", True))
            else:
                self.q.put((
                    "verdict",
                    (AMBER, "NO PATCH TARGET FOUND",
                     info + "\n\nNothing to do for this WAD.", False),
                ))

            self.q.put((
                "log",
                f"-- {os.path.basename(self.wad)} [{verdict['code']}] "
                f"region={detected_tv or 'unknown'} "
                f"target={target_label} {'available' if verdict['patchable'] else 'not found'}",
            ))
        except Exception:
            self.q.put((
                "verdict",
                (RED, "COULD NOT READ THIS WAD", traceback.format_exc(limit=1), False),
            ))

    def convert(self):
        self.q.put(("busy", "Applying selected video mode..."))
        threading.Thread(target=self._convert, daemon=True).start()

    def _convert(self):
        try:
            target_tv, target_height, target_label, _experimental = self.selected_video_mode()
            key = T.load_key(K.common_key_path())
            wad = T.Wad(self.wad, key)
            index, emulator, _compressed = wad.find_emulator()
            ops = []
            dark_offset = None
            did_video = False

            try:
                ops, meta = VP.build_video_ops(emulator, target_tv, target_height)
                did_video = True
                mode = meta["mode"]
                self.q.put((
                    "log",
                    f"   render mode: {mode['name']} -> {target_label} @ 0x{mode['off']:06X}",
                ))
                if target_tv == "PAL":
                    runtime = meta.get("runtime") or {}
                    if meta.get("native_pal288_geometry"):
                        self.q.put((
                            "log",
                            f"   PAL 288 runtime: VI 574 -> 576, XFB 574 store disabled; "
                            "static XFB=288, field-base preserved",
                        ))
                    else:
                        self.q.put((
                            "log",
                            f"   PAL runtime height: {runtime.get('current_height', '?')} -> {target_height}; "
                            "runtime XFB height store disabled",
                        ))
            except RuntimeError as exc:
                self.q.put(("log", f"   {target_label} patch unavailable: {exc}"))

            if self.dark_var.get():
                offset = T.find_dark_filter(emulator)
                if offset is None:
                    self.q.put(("log", "   Dark filter target not found in this build."))
                else:
                    dark_offset = offset
                    ops.append((offset, 4, T._BLR))
                    self.q.put(("log", f"   Dark filter: BLR @ 0x{offset:06X}"))

            if not ops:
                self.q.put(("log", "Nothing to do for this WAD."))
                self.q.put(("verdict", (AMBER, "NOTHING TO DO", "No selected target or dark-filter change is available.", False)))
                return

            contents = dict(wad.contents)
            contents[index] = T.apply_ops(emulator, ops)

            base, ext = os.path.splitext(self.wad)
            did_dark = dark_offset is not None and any(o[0] == dark_offset for o in ops)
            suffix = " " + target_label.replace(" @ ", "_").replace(" ", "") if did_video else ""
            if did_dark:
                suffix += " no-dark-filter"

            output = f"{base}{suffix}{ext}"
            n = 2
            while os.path.exists(output):
                output = f"{base}{suffix} ({n}){ext}"
                n += 1

            written = wad.write(output, title_id=None, contents=contents)
            check = T.Wad(output, key)
            _, emulator2, _ = check.find_emulator()
            changed = sum(1 for a, b in zip(emulator, emulator2) if a != b)

            self.q.put((
                "log",
                f"   Verification: hashes {'OK' if check.sha_ok else 'FAILED'}, "
                f"{changed:,} emulator bytes changed".replace(",", "."),
            ))
            self.q.put(("log", f"   Written: {output} ({written:,} bytes)".replace(",", ".")))
            self.q.put(("verdict", (GREEN, "DONE", f"{target_label}\n{os.path.basename(output)}", False)))
        except SystemExit as exc:
            self.q.put(("log", f"Error: {exc}"))
            self.q.put(("verdict", (RED, "PATCH FAILED", str(exc), False)))
        except Exception:
            tb = traceback.format_exc()
            self.q.put(("log", tb))
            self.q.put(("verdict", (RED, "PATCH FAILED", tb.splitlines()[-1], False)))


def main():
    root = tk.Tk()
    Gui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
