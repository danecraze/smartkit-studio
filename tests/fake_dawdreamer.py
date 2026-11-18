import numpy as np, time
class P:
    def __init__(s): s.notes=[]; s.state=b'STATE0'
    def get_num_output_channels(s): return 48
    def clear_midi(s): s.notes=[]
    def add_midi_note(s,n,v,t,d): s.notes.append((n,v,t,d))
    def save_state(s,f): open(f,'wb').write(s.state)
    def load_state(s,f): s.state=open(f,'rb').read()
    def open_editor(s): time.sleep(1)
class RenderEngine:
    def __init__(s,sr,b): s.sr=sr
    def make_plugin_processor(s,name,path): s.p=P(); return s.p
    def load_graph(s,g): pass
    def render(s,sec): s.n=int(sec*s.sr)
    def get_audio(s):
        a=np.zeros((48,s.n),np.float32)
        for n,v,t,d in s.p.notes: a[4,int(t*s.sr):int(t*s.sr)+100]=v/127
        return a
