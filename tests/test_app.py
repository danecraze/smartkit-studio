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
