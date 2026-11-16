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
