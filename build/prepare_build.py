from pathlib import Path

GUI = Path("src/vc64_240p_gui.py")
s = GUI.read_text(encoding="utf-8")

if "import video_patch as VP" not in s:
    s = s.replace("import vc64tool as T\n", "import vc64tool as T\nimport video_patch as VP\n", 1)

old = '''            targets = T.Targets(emulator, target_tv)\n            ops = []\n            dark_offset = None\n\n            if targets.ok:\n                mode = targets.mode\n                self.q.put((\n                    "log",\n                    f"   render mode: {mode['name']} -> {target_label} @ 0x{mode['off']:06X}; "\n                    f"NOP @ 0x{targets.nop:06X}",\n                ))\n                ops = [\n                    (mode["off"], 4, mode["tv"] | 1),\n                    (mode["off"] + 0x10, 2, target_height),\n                ]\n                for i, value in enumerate(T.PROG_VFILTER):\n                    ops.append((mode["off"] + 0x32 + i, 1, value))\n                ops.append((targets.nop, 4, 0x60000000))\n            else:\n                self.q.put(("log", f"   {target_label} targets not found."))\n'''
new = '''            ops = []\n            dark_offset = None\n            did_video = False\n            video_meta = None\n\n            try:\n                ops, video_meta = VP.build_video_ops(emulator, target_tv, target_height)\n                did_video = True\n                mode = video_meta["mode"]\n                self.q.put((\n                    "log",\n                    f"   render mode: {mode['name']} -> {target_label} @ 0x{mode['off']:06X}"\n                ))\n                if target_tv == "PAL":\n                    runtime = video_meta.get("runtime") or {}\n                    self.q.put((\n                        "log",\n                        "   PAL runtime override: "\n                        f"{runtime.get('current_height', '?')} -> 288; "\n                        "runtime XFB height store disabled",\n                    ))\n            except RuntimeError as exc:\n                self.q.put(("log", f"   {target_label} patch unavailable: {exc}"))\n'''
if old not in s:
    raise SystemExit("conversion block not found")
s = s.replace(old, new, 1)

old2 = '''            base, ext = os.path.splitext(self.wad)\n            did_video = bool(targets.ok)\n            did_dark = dark_offset is not None and any(o[0] == dark_offset for o in ops)\n'''
new2 = '''            base, ext = os.path.splitext(self.wad)\n            did_dark = dark_offset is not None and any(o[0] == dark_offset for o in ops)\n'''
if old2 not in s:
    raise SystemExit("did_video block not found")
s = s.replace(old2, new2, 1)

GUI.write_text(s, encoding="utf-8")
