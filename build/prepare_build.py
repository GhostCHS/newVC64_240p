from pathlib import Path

GUI = Path("src/vc64_240p_gui.py")
s = GUI.read_text(encoding="utf-8")

# Runtime key handling and English-only UI.
s = s.replace("import vc64tool as T", "import vc64tool as T\nimport key_runtime as K", 1)
s = s.replace("self.lang = 'pt'", "self.lang = 'en'", 1)
s = s.replace("        self.langbtn.pack(side='right')", "        self.langbtn.pack(side='right')\n        self.langbtn.pack_forget()", 1)
s = s.replace("self.keyvar = tk.StringVar(value=os.path.join(app_dir(), 'common-key.bin'))", "self.keyvar = tk.StringVar(value=K.common_key_path())", 1)
s = s.replace("        self.keybtn.pack(side='left')", "        self.keybtn.pack(side='left')\n        k.pack_forget()", 1)
s = s.replace("            key = self.keyvar.get()", "            key = K.common_key_path()", 1)
s = s.replace("            key = T.load_key(self.keyvar.get())", "            key = T.load_key(K.common_key_path())", 1)

# Add a real output-mode selector.  Only valid CRT modes are offered:
# NTSC 240p/60 Hz and PAL 288p/50 Hz.  PAL 288p is explicitly marked
# experimental in the UI because the upstream patcher does not support it yet.
needle = "        k.pack_forget()\n\n        # O tkinter pinta"
insert = '''        k.pack_forget()\n\n        modef = tk.Frame(root, bg=BG)\n        modef.pack(fill='x', padx=16, pady=(10, 0))\n        tk.Label(modef, text='Output mode:', bg=BG, fg=SUB,\n                 font=('Segoe UI', 9)).pack(side='left')\n        self.modevar = tk.StringVar(value='240p @ 60 Hz (NTSC)')\n        self.modebox = ttk.Combobox(\n            modef, textvariable=self.modevar, state='readonly',\n            values=('240p @ 60 Hz (NTSC)', '288p @ 50 Hz (PAL)'), width=25\n        )\n        self.modebox.pack(side='left', padx=10)\n        self.modebox.bind('<<ComboboxSelected>>',\n                          lambda _e: self.analyse() if self.wad else None)\n        self.modehint = tk.Label(\n            root,\n            text='240p @ 60 Hz: NTSC. 288p @ 50 Hz: PAL (experimental).',\n            bg=BG, fg=SUB, justify='left', anchor='w',\n            font=('Segoe UI', 8)\n        )\n        self.modehint.pack(fill='x', padx=16, pady=(2, 0))\n\n        # O tkinter pinta'''
if needle not in s:
    raise SystemExit('GUI insertion point not found')
s = s.replace(needle, insert, 1)

# Add mode helper methods immediately before analyse().
needle = "    # ------------------------------------------------------------------ work\n    def analyse(self):"
insert = '''    # ------------------------------------------------------------------ work\n    def selected_video_mode(self):\n        if self.modevar.get().startswith('288p'):\n            return 'PAL', 288, '288p @ 50 Hz'\n        return 'NTSC', 240, '240p @ 60 Hz'\n\n    def video_requirement_text(self):\n        tv, height, label = self.selected_video_mode()\n        if tv == 'PAL':\n            return ('Set the Wii to 50 Hz/PAL before launching this channel.\n'\n                    '288p @ 50 Hz is experimental because the original upstream patch only supported NTSC 240p.')\n        return ('Set the Wii to 60 Hz/NTSC before launching this channel.\n'\n                'The emulator uses the progressive render mode in 480p, which is not patched.')\n\n    def analyse(self):'''
if needle not in s:
    raise SystemExit('analyse insertion point not found')
s = s.replace(needle, insert, 1)

# Analysis uses the selected TV standard and reports the selected output mode.
s = s.replace("            key = K.common_key_path()\n            if not os.path.exists(key):", "            key = K.common_key_path()\n            target_tv, target_height, target_label = self.selected_video_mode()\n            if not os.path.exists(key):", 1)
s = s.replace("            v = T.verdict(self.wad, key, 'NTSC')", "            v = T.verdict(self.wad, key, target_tv)", 1)
s = s.replace("            info = (f\"{self.t('l240')}: {s240}\\n\"", "            info = (f\"{target_label}: {s240}\\n\"", 1)
s = s.replace("                                        info + '\\n' + self.t('need480i'), True)))", "                                        info + '\\n' + self.video_requirement_text(), True)))", 1)
s = s.replace("        self.q.put(('busy', self.t('working')))\n        threading.Thread", "        self.q.put(('busy', self.t('working')))\n        threading.Thread", 1)

# Conversion uses only the selected TV-format struct and the requested height.
s = s.replace("            key = T.load_key(K.common_key_path())\n            w = T.Wad(self.wad, key)", "            key = T.load_key(K.common_key_path())\n            target_tv, target_height, target_label = self.selected_video_mode()\n            w = T.Wad(self.wad, key)", 1)
s = s.replace("            t = T.Targets(emu, 'NTSC')", "            t = T.Targets(emu, target_tv)", 1)
old = """                modos = ', '.join(m['name'] for m in t.interlaced)\n                self.q.put(('log', f\"   render mode {modos} @ 0x{t.mode['off']:06X}\"\n                                   f\"   NOP @ 0x{t.nop:06X}\"))\n                ops = list(t.patch_ops(every_tv=True))"""
new = """                modos = t.mode['name']\n                self.q.put(('log', f\"   render mode {modos} -> {target_label} @ 0x{t.mode['off']:06X}\"\n                                   f\"   NOP @ 0x{t.nop:06X}\"))\n                ops = [(t.mode['off'], 4, t.mode['tv'] | 1),\n                       (t.mode['off'] + 0x10, 2, target_height)]\n                for i, v in enumerate(T.PROG_VFILTER):\n                    ops.append((t.mode['off'] + 0x32 + i, 1, v))\n                ops.append((t.nop, 4, 0x60000000))"""
if old not in s:
    raise SystemExit('conversion patch block not found')
s = s.replace(old, new, 1)
s = s.replace("            did_240 = bool(t.ok)", "            did_240 = bool(t.ok)\n            did_mode = did_240", 1)
s = s.replace("            if did_240 and not base.lower().rstrip().endswith('240p'):\n                suffix += ' 240p'", "            if did_mode:\n                suffix += ' ' + target_label.replace(' @ ', '_').replace(' ', '')", 1)

# Final verification message should mention the selected target, not generic 240p.
s = s.replace("            self.q.put(('verdict', (GREEN, self.t('saved'), os.path.basename(out), False)))", "            self.q.put(('verdict', (GREEN, self.t('saved'), f'{target_label}\\n{os.path.basename(out)}', False)))", 1)

GUI.write_text(s, encoding='utf-8', newline='')
