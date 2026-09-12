#!/usr/bin/env python3
"""
vc64_240p - English standalone GUI for patching Nintendo 64 Virtual Console WADs.

The program patches existing N64 VC WADs. It does not inject ROMs.
The Wii common key is generated automatically by the standalone Windows build.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog

import key_runtime as K
import vc64tool as T

APP = "vc64 240p"
VERSION = "1.0"

BG = "#1e1e22"
FG = "#e8e8ea"
SUB = "#9a9aa2"
GREEN = "#2e7d32"
RED = "#b3261e"
AMBER = "#8a6d1f"
BLUE = "#2f4f7f"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Gui:
    def __init__(self, root):
        self.root = root
        self.wad = None
        self.state = None
        self.q = queue.Queue()
        self._go_enabled = False

        root.title(f"{APP} {VERSION}")
        root.configure(bg=BG)
        root.geometry("720x650")
        root.minsize(640, 590)

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(
            top,
            text=APP,
            bg=BG,
            fg=FG,
            font=("Segoe UI", 17, "bold"),
        ).pack(side="left")

        self.subtitle = tk.Label(
            root,
            text="Patch an existing N64 Virtual Console WAD to real 240p.",
            bg=BG,
            fg=SUB,
            justify="left",
            font=("Segoe UI", 9),
        )
        self.subtitle.pack(fill="x", padx=16, anchor="w")

        file_row = tk.Frame(root, bg=BG)
        file_row.pack(fill="x", padx=16, pady=(14, 4))
        self.pick_btn = tk.Button(
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
        )
        self.pick_btn.pack(side="left")
        self.file_name = tk.Label(
            file_row,
            text="No WAD chosen.",
            bg=BG,
            fg=SUB,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.file_name.pack(side="left", padx=12, fill="x", expand=True)

        self.panel = tk.Frame(root, bg=BG, height=132)
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

        info = tk.Frame(root, bg=BG)
        info.pack(fill="x", padx=16, pady=(2, 0))
        tk.Label(
            info,
            text=(
                "The common key is generated automatically on first use.\n"
                "No key file or key selection is required."
            ),
            bg=BG,
            fg=SUB,
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w")

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
            text="Convert to 240p",
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

        tk.Label(
            root,
            text="Log",
            bg=BG,
            fg=SUB,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=16)

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
        self.file_name.configure(text=os.path.basename(path))
        self.analyse()

    def set_go(self, enabled, text=None):
        self._go_enabled = enabled
        if enabled:
            self.go_btn.configure(
                state="normal",
                bg=GREEN,
                fg="#ffffff",
                activebackground="#3a9440",
                activeforeground="#ffffff",
            )
        else:
            self.go_btn.configure(
                state="disabled",
                bg="#3a3a42",
                fg="#6e6e78",
            )
        self.go_btn.configure(text=text or "Convert to 240p")

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
            verdict = T.verdict(self.wad, key_path, "NTSC")
            self.state = verdict

            if not verdict["ok"]:
                reason = verdict.get("reason") or "Could not find the emulator binary inside this WAD."
                self.q.put(("verdict", (RED, "COULD NOT READ THIS WAD", reason, False)))
                self.q.put(("log", f"-- {os.path.basename(self.wad)}: {reason}"))
                return

            if not verdict["hashes"]:
                self.q.put((
                    "verdict",
                    (RED, "COULD NOT READ THIS WAD", "The WAD hashes do not match its TMD. Refusing to modify it.", False),
                ))
                return

            status_240 = "CAN BE APPLIED" if verdict["patchable"] else "already applied, nothing to do"
            dark_status = {
                "can-remove": "CAN BE APPLIED",
                "already-removed": "already removed, nothing to do",
                "not-found": "target NOT found in this build",
            }[verdict["dark"]]

            info = (
                f"240p        : {status_240}\n"
                f"dark filter : {dark_status}\n"
                f"channel     : {verdict['code']}\n"
                f"compression : {'LZ77' if verdict['compressed'] else 'raw DOL'}"
            )

            self.q.put(("dark", verdict["dark"]))
            can_dark = verdict["dark"] == "can-remove"

            if verdict["patchable"]:
                self.q.put((
                    "verdict",
                    (
                        GREEN,
                        "THIS WAD ACCEPTS THE 240p PATCH",
                        info + "\n\nSet the console to 480i before launching the patched channel.",
                        True,
                    ),
                ))
            elif can_dark:
                self.q.put((
                    "verdict",
                    (AMBER, "ALREADY 240p", info + "\n\nOnly the dark filter can be changed.", True),
                ))
                self.q.put(("onlydark", True))
            else:
                self.q.put((
                    "verdict",
                    (AMBER, "ALREADY 240p", info + "\n\nNothing to do for this WAD.", False),
                ))

            self.q.put((
                "log",
                f"-- {os.path.basename(self.wad)} [{verdict['code']}] "
                f"{'patchable' if verdict['patchable'] else 'no 240p targets'}",
            ))
        except Exception:
            self.q.put((
                "verdict",
                (RED, "COULD NOT READ THIS WAD", traceback.format_exc(limit=1), False),
            ))

    def convert(self):
        self.q.put(("busy", "Converting..."))
        threading.Thread(target=self._convert, daemon=True).start()

    def _convert(self):
        try:
            key_path = K.common_key_path()
            key = T.load_key(key_path)
            wad = T.Wad(self.wad, key)
            index, emulator, _compressed = wad.find_emulator()
            targets = T.Targets(emulator, "NTSC")
            ops = []
            dark_offset = None

            if targets.ok:
                modes = ", ".join(m["name"] for m in targets.interlaced)
                self.q.put((
                    "log",
                    f"   render modes: {modes}  @ 0x{targets.mode['off']:06X}; "
                    f"NOP @ 0x{targets.nop:06X}",
                ))
                ops = list(targets.patch_ops(every_tv=True))
            else:
                self.q.put(("log", "   240p targets not found; the WAD may already be patched."))

            if self.dark_var.get():
                offset = T.find_dark_filter(emulator)
                if offset is None:
                    self.q.put(("log", "   Dark filter target not found in this build."))
                else:
                    dark_offset = offset
                    ops = list(ops) + [(offset, 4, T._BLR)]
                    self.q.put(("log", f"   Dark filter: BLR @ 0x{offset:06X}"))

            if not ops:
                self.q.put(("log", "Nothing to do for this WAD."))
                self.q.put(("verdict", (AMBER, "ALREADY 240p", "Nothing to do.", False)))
                return

            contents = dict(wad.contents)
            contents[index] = T.apply_ops(emulator, ops)

            base, ext = os.path.splitext(self.wad)
            did_240p = bool(targets.ok)
            did_dark = dark_offset is not None and any(o[0] == dark_offset for o in ops)

            suffix = ""
            if did_240p and not base.lower().rstrip().endswith("240p"):
                suffix += " 240p"
            if did_dark:
                suffix += " no dark filter"

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
            self.q.put((
                "log",
                f"   Written: {output} ({written:,} bytes)".replace(",", "."),
            ))
            self.q.put(("log", ""))
            self.q.put(("verdict", (GREEN, "DONE", os.path.basename(output), False)))
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
