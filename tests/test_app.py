"""The whole app, headless: add a sample folder, suggest pads, build. Skipped when no display is available."""
import os, glob
import pytest


def test_app_build_from_sample_folder(converter_library, tmp_path, monkeypatch):
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import smartkit_app as A
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(A.messagebox, 'askyesno', lambda *a, **k: True)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.notify = lambda *a, **k: None
        app.v_kit.set('App Test Kit'); app.refresh_project()
        out = str(tmp_path / 'card'); app.v_out.set(out)
        app.add_source([converter_library], 'folder')
        assert len(app.rows) == 15 and all(r.get('src') for r in app.rows.values())
        assert any('S1H' in r['pads'] for r in app.rows.values())
        app.do_build(); app.update()
        assert glob.glob(os.path.join(out, 'Kits', '*.skt'))
        assert glob.glob(os.path.join(out, 'Instruments', 'App Test Kit', 'HIHAT', 'HHEDG_*.sin'))
    finally:
        app.destroy()


def test_kit_rename_keeps_sounds(converter_library, tmp_path, monkeypatch):
    """Typing a new kit name renames the project: the sample sounds must not disappear (0.12 bug)."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import smartkit_app as A
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.v_kit.set('Kit One'); app.refresh_project()
        app.add_source([converter_library], 'folder')
        n = len(app.rows)
        os.makedirs(os.path.join(str(tmp_path / 'Projects'), 'Kit Two'))      # an old folder with only a log
        open(os.path.join(str(tmp_path / 'Projects'), 'Kit Two', 'log.txt'), 'w').write('x')
        app.v_kit.set('Kit Two'); app.kit_renamed()
        assert len(app.rows) == n and app.sources
        assert os.path.exists(os.path.join(str(tmp_path / 'Projects'), 'Kit Two', 'sounds.json'))
        app.refresh_project()                      # reopening the renamed project finds the sounds again
        assert len(app.rows) == n
    finally:
        app.destroy()


def test_open_kit_and_cleanup(converter_library, tmp_path, monkeypatch):
    """Picking another kit keeps both kits' sounds; clean-up removes the chosen project files."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import smartkit_app as A
    projects = str(tmp_path / 'Projects')
    monkeypatch.setattr(A, 'PROJECTS', projects)
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.v_kit.set('Kit A'); app.refresh_project()
        app.add_source([converter_library], 'folder')
        n = len(app.rows)
        monkeypatch.setattr(A.T, 'ask_string', lambda *a, **k: 'Kit B')
        app.new_kit()
        assert app.v_kit.get() == 'Kit B' and not app.rows
        app.v_kit.set('Kit A'); app.open_kit()
        assert len(app.rows) == n
        assert set(app.kit_names()) == {'Kit A'}          # Kit B has no files yet
        os.makedirs(os.path.join(projects, 'Kit A', 'renders', 'x'))
        open(os.path.join(projects, 'Kit A', 'renders', 'x', 'a.wav'), 'wb').write(b'0' * 4096)
        monkeypatch.setattr(A.T.Dialog, 'show', lambda self: True)      # accept the defaults
        app.cleanup_project()
        assert not os.path.exists(os.path.join(projects, 'Kit A', 'renders'))
        assert os.path.exists(os.path.join(projects, 'Kit A', 'sounds.json')) and len(app.rows) == n
    finally:
        app.destroy()


def test_menus_open(converter_library, tmp_path, monkeypatch):
    """Every right-click / pad / header menu builds and opens without errors (0.13 broke the pad menu)."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import types as _t
    import smartkit_app as A
    import theme as T
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    opened = []
    real = T._MenuSession.open
    def spy(self, menu, x, y, level=0):
        opened.append(len(menu.items)); top = real(self, menu, x, y, level); self.close(); return top
    monkeypatch.setattr(T._MenuSession, 'open', spy)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.v_kit.set('Menu Kit'); app.refresh_project()
        app.add_source([converter_library], 'folder')
        app.nb.select(1); app.update()
        key = next(k for k, r in app.rows.items() if r.get('use') or True)
        ev = _t.SimpleNamespace(x=10, y=10, x_root=200, y_root=200, widget=app.tree)
        app.pad_menu(key, ev)                                  # Strike pads menu
        for col in ('#1', '#2', '#3', '#4', '#5'):              # right-click on every column
            monkeypatch.setattr(app, 'cell', lambda e, c=col: (key, c))
            app.on_right(ev)
        assert opened and all(n > 0 for n in opened)
        # a checkbutton entry toggles its variable and runs its command
        v, hit = tk.BooleanVar(value=False), []
        m = T.Menu(app); m.add_checkbutton(label='x', variable=v, command=lambda: hit.append(1))
        s = T._MenuSession(app); real(s, m, 100, 100); s._activate(0, 0); app.update()
        assert v.get() is True and hit == [1]
    finally:
        app.destroy()


def test_record_and_build_asks_nothing_afterwards(converter_library, tmp_path, monkeypatch):
    """Record + build: questions only before starting; the build itself runs without another OK."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import smartkit_app as A
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    asked = []
    monkeypatch.setattr(A.messagebox, 'askyesno', lambda *a, **k: asked.append(a) or True)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.notify = lambda *a, **k: None
        app.v_kit.set('RB Kit'); app.refresh_project()
        app.add_source([converter_library], 'folder')
        app.auto_pads()
        out = tmp_path / 'card'; app.v_out.set(str(out))
        app.do_record_build()
        assert (out / 'Kits' / 'RB Kit.skt').exists()
        n = len(asked)
        app.do_build(confirmed=True)                       # what runs after the recording: no questions
        assert len(asked) == n
    finally:
        app.destroy()


def test_start_dialog_new_and_open(converter_library, tmp_path, monkeypatch):
    """The start window: create a new kit, or open a saved one."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import smartkit_app as A
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.v_kit.set('Saved Kit'); app.refresh_project()
        app.add_source([converter_library], 'folder')
        n = len(app.rows)
        answers = [('new', 'Fresh Kit'), ('open', 'Saved Kit')]
        monkeypatch.setattr(A.T.Dialog, 'show', lambda self: (self.destroy(), answers.pop(0))[1])
        app.start_dialog()
        assert app.v_kit.get() == 'Fresh Kit' and not app.rows
        app.start_dialog()
        assert app.v_kit.get() == 'Saved Kit' and len(app.rows) == n
        assert app.free_kit_name() == 'New kit 1'
    finally:
        app.destroy()


def test_find_sounds_instant_with_kit_layout(tmp_path, monkeypatch):
    """With a known kit layout, Find sounds lists the sounds without playing them; ▶ Play / Record measure them."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import numpy as np
    import smartkit_app as A
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.v_kit.set('Layout Kit'); app.refresh_project()
        played = []
        class FakePlugin: raw_state = b''
        app.host.plugin = FakePlugin()
        app.host.ring_hit = lambda note, **k: (played.append(note), (np.ones((4800, 2), np.float32) * 0.5, 0.1))[1]
        app.layout = [dict(box=1, pos='Snare', drum='Tma', lib='SSD 5', type='snare', code='snareR', notes=[38], play=38,
                           suffix='R', label='Center', role='snare', inst='Snare', group='Snare – Tma', drum_name='Tma'),
                      dict(box=2, pos='Crash L', drum='Zld 18', lib='SSD 5', type='crash', code='crash1', notes=[55],
                           play=55, suffix='', label='Edge', role='crash', inst='Crash L', group='Crash L – Zld 18',
                           drum_name='Zld 18')]
        app.do_probe()
        assert len(app.rows) == 2 and not played                    # nothing played
        assert all(not r['ring'] and r['file'] is None for r in app.rows.values())
        monkeypatch.setattr(A, 'winsound', None, raising=False)
        key = next(iter(app.rows))
        app.play_key(key)                                           # ▶ Play measures it once
        assert played == [38 if app.rows[key]['note'] == 38 else 55] and app.rows[key]['ring'] == 0.1
        assert app.rows[key]['file'] and os.path.exists(app.rows[key]['file'])
    finally:
        app.destroy()


def test_themed_popups_and_plugin_panel(tmp_path, monkeypatch):
    """Pop-ups use SmartKit's theme (not Windows' message boxes); the floating panel next to the plugin window
    closes it with 'Kit chosen' or 'Cancel'."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import threading, types
    import smartkit_app as A, theme as T
    assert A.messagebox is T.messagebox
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    app = A.App()
    try:
        def answer(value):
            for w in app.winfo_children():
                if isinstance(w, T.Dialog):
                    w.ok(value); return
            app.after(50, lambda: answer(value))
        app.after(100, lambda: answer(False))
        assert T.messagebox.askyesno('SmartKit', 'Long question ' * 30, parent=app) is False
        app.after(100, lambda: answer('ok'))
        assert T.messagebox.showerror('SmartKit', 'Something went wrong', parent=app) == 'ok'
        app.after(100, lambda: answer(None))
        assert T.messagebox.askyesnocancel('SmartKit', 'Yes, no or cancel?', parent=app) is None

        app.host.editor_open = True
        app.host.plugin = types.SimpleNamespace(modal_editor=True)
        app.editor_ev = threading.Event()
        app.plugin_panel()
        assert app.panel is not None and app.panel.winfo_exists()
        buttons = [w for w in app.panel.winfo_children()[0].winfo_children() if isinstance(w, A.ttk.Button)]
        buttons[1].invoke()                        # Cancel
        assert app.editor_ev.is_set() and app.editor_cancel
        app.host.editor_open = False
        app.editor_before = None
        app.editor_closed(None)
        assert app.panel is None and not app.editor_cancel
    finally:
        app.destroy()


def test_layer_b_and_numbered_names(converter_library, tmp_path, monkeypatch):
    """A sound on layer B of a pad ends up in the kit's layer B; toms/crashes are named TM1HD…, CR1ED…;
    pads are shown by name."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk(); r.destroy()
    except tk.TclError:
        pytest.skip('no display')
    import smartkit_app as A, strikefmt as SF, sources as SRC
    monkeypatch.setattr(A, 'PROJECTS', str(tmp_path / 'Projects'))
    monkeypatch.setattr(A, 'SETTINGS_FILE', str(tmp_path / 'studio_settings.json'))
    for name in ('showinfo', 'showerror', 'showwarning'):
        monkeypatch.setattr(A.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(A.messagebox, 'askyesno', lambda *a, **k: True)
    app = A.App()
    try:
        app.run_bg = lambda fn, done=None, text='': (lambda res: done(res) if done else None)(fn())
        app.notify = lambda *a, **k: None
        app.v_kit.set('Layer Kit'); app.refresh_project()
        out = str(tmp_path / 'card'); app.v_out.set(out)
        app.add_source([converter_library], 'folder')
        names = sorted(r['name'] for r in app.rows.values())
        assert any(n.startswith('TM1HD_') for n in names) and any(n.startswith('TM3HD_') for n in names)
        assert not any(n.startswith(('TOMHD', 'CRSED')) for n in names)
        rim = next(k for k, r in app.rows.items() if r['sfx'] == 'SNRRI')
        tom = next(k for k, r in app.rows.items() if r['name'].startswith('TM1HD'))
        app.rows[rim]['pads_b'] = ['S1H']                       # rimshot as layer B of the snare head
        app.rows[tom]['pads_b'] = ['T2H']                       # tom 1 also on layer B of tom 2
        assert 'Snare head' in app.row_values(app.rows[rim])[5]
        assert A.pad_label('C1B') == 'Crash 1 bow' and A.pad_label('H1B open 2') == 'Hi-hat bow open 2'
        app.do_build(); app.update()
        skt = open(glob.glob(os.path.join(out, 'Kits', '*.skt'))[0], 'rb').read()
        insts = {d[:3].decode('latin1'): d for cid, d in SF.read_chunks(skt) if cid == 'inst'}
        strs = [d for cid, d in SF.read_chunks(skt) if cid == 'str '][0]
        paths = SF.parse_strs(strs)
        b = lambda pid: int.from_bytes(insts[pid][24:26], 'little')
        a = lambda pid: int.from_bytes(insts[pid][4:6], 'little')
        assert b('S1H') != 0xFFFF and 'SNRRI' in paths[b('S1H')] and 'SNRHD' in paths[a('S1H')]
        assert b('T2H') != 0xFFFF and 'TM1HD' in paths[b('T2H')] and 'TM2HD' in paths[a('T2H')]
        assert b('K1H') == 0xFFFF
        sins = glob.glob(os.path.join(out, 'Instruments', '**', 'TM2HD_*.sin'), recursive=True)
        back = SRC.scan_sin(sins, log=lambda *a: None)          # SmartKit's own names read back
        assert back and back[0]['sfx'] == 'TOMHD' and back[0]['num'] == 2
    finally:
        app.destroy()
