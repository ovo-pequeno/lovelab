# =========================================================
# 恋愛「相手の気持ちを確かめる方法」Shorts｜VOICEVOX春日部つむぎ
# 健全な心理・コミュニケーションのヒントを数個。断定/操作でなく気づき重視。
# Gemini → VOICEVOX → MoviePy → YouTube API / 縦型1080x1920
# =========================================================
import os, re, json, time, gc, requests
from google import genai
try:
    from google.genai import types as genai_types
except Exception:
    genai_types = None
from pydub import AudioSegment
from moviepy.editor import (
    ColorClip, ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
)
import moviepy.config as cf
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

cf.change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
YT_CLIENT_ID     = os.environ["YT_CLIENT_ID"]
YT_CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
YT_REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]
PRIVACY = os.environ.get("PRIVACY", "public")
MODEL   = os.environ.get("MODEL", "gemini-2.5-flash")

VOICEVOX_URL="http://127.0.0.1:50021"; SPEAKER_ID=8; SPEAKER_NAME="春日部つむぎ"; SPEAKER_STYLE="ノーマル"
VOICE_SPEED=1.25
NUM_TIPS=int(os.environ.get("NUM_TIPS","5"))
OUT_DIR="out_renai_s"; TMP_DIR="tmp_renai_s"; LOG_PATH="used_log_renai_tips.json"; AVOID_RECENT=40
BG_IMAGE = "assets/bg_renai_short.png" if os.path.exists("assets/bg_renai_short.png") else None
BG_COLOR=(48,22,44)   # 落ち着いたローズ
BGM_PATH = "assets/bgm_renai.mp3" if os.path.exists("assets/bgm_renai.mp3") else None
BGM_VOLUME=0.10

client = genai.Client(api_key=GEMINI_API_KEY)
W, H = 1080, 1920
FPS = 10
FONT = "/usr/share/fonts/truetype/custom/RocknRollOne-Regular.ttf"
if not os.path.exists(FONT): FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
HEADER_FONT = "/usr/share/fonts/truetype/custom/PottaOne-Regular.ttf"
if not os.path.exists(HEADER_FONT): HEADER_FONT = FONT
TEXT_COLOR="white"; ACCENT_COLOR="#FFC0DA"; STROKE_COLOR="#3A1030"
HEADER_TEXT="恋のヒント"


def load_log():
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH,encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    return []

def save_log(log):
    with open(LOG_PATH,"w",encoding="utf-8") as f: json.dump(log,f,ensure_ascii=False,indent=1)


def generate_tips(avoid, max_retries=5):
    models=[MODEL,"gemini-2.5-flash-lite","gemini-3.1-flash-lite"]
    avoid_text=""
    if avoid:
        avoid_text="\n\n【これらと被らないテーマ・切り口で】\n"+"\n".join(f"- {s}" for s in avoid)
    prompt=f"""あなたは恋愛カウンセラーです。「相手の気持ちを確かめる方法」をテーマに、
健全なコミュニケーション・心理のヒントを{NUM_TIPS}個、Shorts台本として作ります。

重要なトーン：
- 相手を操作・誘導したり、詮索・監視するような内容は禁止。
- 「相手の反応を観察する」「素直に伝える」「自分の気持ちを整理する」など、
  健全で誠実なコミュニケーションのヒントにする。
- 断定せず、「こういう見方もある」という気づきベース。
- 初心者にも実践しやすい、やさしい内容に。

JSON形式のみ（前後に説明・マークダウン不要）:
{{
  "youtube_title": "タップしたくなる日本語タイトル（28文字以内）",
  "summary": "被り防止ログ用一行（30文字以内）",
  "intro": "冒頭のつかみ（40文字以内）",
  "tips": [
    {{"title": "ヒントの見出し（15文字以内）", "body": "説明（60文字以内）"}}
  ],
  "outro": "締め・チャンネル登録誘導（40文字以内）"
}}
※tipsは必ず{NUM_TIPS}個。{avoid_text}
"""
    cfg=genai_types.GenerateContentConfig(temperature=1.05) if genai_types else None
    for attempt in range(max_retries):
        m=models[min(attempt,len(models)-1)]
        try:
            resp=client.models.generate_content(model=m,contents=prompt,config=cfg) if cfg else client.models.generate_content(model=m,contents=prompt)
            text=resp.text.strip().replace("```json","").replace("```","").strip()
            data=json.loads(text)
            if not data.get("tips"): raise ValueError("tips空")
            return data
        except Exception as e:
            msg=str(e)
            if ("503" in msg or "429" in msg or "UNAVAILABLE" in msg) and attempt<max_retries-1: time.sleep(15*(attempt+1))
            elif attempt<max_retries-1: time.sleep(5)
            else: raise


def make_audio(text, filename, tail_cut=0):
    if not text.strip():
        AudioSegment.silent(duration=400).export(filename,format="mp3"); return filename
    q=requests.post(f"{VOICEVOX_URL}/audio_query",params={"text":text,"speaker":SPEAKER_ID},timeout=60)
    query=q.json(); query["speedScale"]=VOICE_SPEED; query["prePhonemeLength"]=0.1; query["postPhonemeLength"]=0.1
    s=requests.post(f"{VOICEVOX_URL}/synthesis",params={"speaker":SPEAKER_ID},data=json.dumps(query),
                    headers={"Content-Type":"application/json"},timeout=120)
    tw="tmp_"+filename.replace(".mp3",".wav")
    with open(tw,"wb") as f: f.write(s.content)
    seg=AudioSegment.from_wav(tw)
    if tail_cut>0 and len(seg)>tail_cut+100: seg=seg[:-tail_cut]
    seg.export(filename,format="mp3"); os.remove(tw)
    return filename

def wait_voicevox(timeout=180):
    for _ in range(timeout//3):
        try:
            if requests.get(f"{VOICEVOX_URL}/version",timeout=5).ok: print("✅ VOICEVOX OK"); return True
        except Exception: pass
        time.sleep(3)
    raise RuntimeError("VOICEVOX起動せず")

def resolve_speaker():
    global SPEAKER_ID
    try: sp=requests.get(f"{VOICEVOX_URL}/speakers",timeout=30).json()
    except Exception: return
    for s in sp:
        if SPEAKER_NAME in s.get("name",""):
            for st in s.get("styles",[]):
                if SPEAKER_STYLE in st.get("name",""): SPEAKER_ID=st["id"]; return
            if s.get("styles"): SPEAKER_ID=s["styles"][0]["id"]; return


_bg=None
def _fit_bg(path):
    global _bg
    if _bg is None:
        from PIL import Image; import numpy as np
        rs=getattr(Image,"Resampling",Image).LANCZOS if hasattr(Image,"Resampling") else Image.LANCZOS
        _bg=np.array(Image.open(path).convert("RGB").resize((W,H),rs))
    return _bg

def make_bg(d):
    if BG_IMAGE and os.path.exists(BG_IMAGE): return ImageClip(_fit_bg(BG_IMAGE)).set_duration(d)
    return ColorClip(size=(W,H),color=BG_COLOR,duration=d)

def _prewrap(text,fs,cw):
    import textwrap
    is_latin=sum(ord(c)<128 for c in text)>len(text)*0.6
    factor=0.58 if is_latin else 1.05
    mx=max(6,int(cw/(fs*factor)))
    if is_latin: return "\n".join(textwrap.wrap(text,width=mx)) or text
    return "\n".join(text[i:i+mx] for i in range(0,len(text),mx)) or text

def outlined(text,d,font,fs,color,sw,ypos,cw):
    wr=_prewrap(text,fs,cw)
    common=dict(font=font,fontsize=fs,method="label",align="center",interline=12)
    st=TextClip(wr,color=STROKE_COLOR,stroke_color=STROKE_COLOR,stroke_width=sw,**common).set_duration(d)
    fl=TextClip(wr,color=color,**common).set_duration(d)
    return CompositeVideoClip([st.set_position(("center","center")),fl.set_position(("center","center"))],
                              size=(max(st.w,fl.w),max(st.h,fl.h))).set_duration(d).set_position(("center",ypos))

def header(d):
    return outlined(HEADER_TEXT,d,HEADER_FONT,68,"#FFFFFF",18,int(H*0.05),W-120)

def scene(main, audio_file, label=None, big=False):
    narr=AudioFileClip(audio_file); d=narr.duration+0.5
    layers=[make_bg(d),header(d)]
    if label: layers.append(outlined(label,d,HEADER_FONT,54,"#FFE08A",12,int(H*0.30),W-140))
    layers.append(outlined(main,d,FONT,72 if big else 60,TEXT_COLOR,12,int(H*0.48),W-140))
    sc=CompositeVideoClip(layers,size=(W,H)).set_duration(d)
    if d>narr.duration+0.02: narr=CompositeAudioClip([narr]).set_duration(d)
    return sc.set_audio(narr)

def render(s,path):
    s.write_videofile(path,fps=FPS,codec="libx264",audio_codec="aac",preset="ultrafast",logger=None)
    try:
        if s.audio is not None: s.audio.close()
    except Exception: pass
    s.close(); del s; gc.collect()


def build_video(data):
    os.makedirs(OUT_DIR,exist_ok=True); os.makedirs(TMP_DIR,exist_ok=True)
    title=data.get("youtube_title","相手の気持ちを確かめる方法")
    safe=title
    for ch in r'\/:*?"<>|': safe=safe.replace(ch,"")
    output=os.path.join(OUT_DIR,f"{safe.strip()[:60]}.mp4")
    clips=[]; idx=0
    a=make_audio(data.get("intro",""),f"a_{idx}.mp3",tail_cut=80)
    p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene(data.get("intro",""),a,big=True),p); clips.append(p); os.remove(a); idx+=1
    for i,t in enumerate(data["tips"]):
        label=f"{i+1}つめ"
        a=make_audio(f"{t.get('title','')}。{t.get('body','')}",f"a_{idx}.mp3",tail_cut=100)
        p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene(t.get("title",""),a,label=label,big=True),p)
        clips.append(p); os.remove(a); idx+=1
    a=make_audio(data.get("outro",""),f"a_{idx}.mp3",tail_cut=80)
    p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene(data.get("outro",""),a),p); clips.append(p); os.remove(a); idx+=1

    lf=f"{TMP_DIR}/list.txt"
    with open(lf,"w") as f:
        for cp in clips: f.write(f"file '{os.path.basename(cp)}'\n")
    master=f"{TMP_DIR}/master.mp4"
    os.system(f'cd {TMP_DIR} && ffmpeg -y -f concat -safe 0 -i list.txt -c:v copy -c:a aac master.mp4 -loglevel error')
    if BGM_PATH and os.path.exists(BGM_PATH):
        os.system(f'ffmpeg -y -i "{master}" -stream_loop -1 -i "{BGM_PATH}" '
                  f'-filter_complex "[1:a]volume={BGM_VOLUME}[b];[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a]" '
                  f'-map 0:v -map "[a]" -c:v copy -c:a aac "{output}" -loglevel error')
    else: os.replace(master,output)
    for cp in clips:
        if os.path.exists(cp): os.remove(cp)
    for f in [lf,master]:
        if os.path.exists(f): os.remove(f)
    return output,title


def get_youtube():
    creds=Credentials(token=None,refresh_token=YT_REFRESH_TOKEN,client_id=YT_CLIENT_ID,
                      client_secret=YT_CLIENT_SECRET,token_uri="https://oauth2.googleapis.com/token")
    creds.refresh(Request()); return build("youtube","v3",credentials=creds)

def upload(youtube,path,title):
    description=("相手の気持ちを確かめるための、健全なコミュニケーションのヒント。\n"
                 "誠実に向き合うための気づきとしてどうぞ。\n\n#恋愛 #恋愛相談 #恋愛心理 #相手の気持ち #shorts #Shorts")
    body={"snippet":{"title":(title+" #shorts")[:100],"description":description[:5000],
                     "tags":["恋愛","恋愛相談","恋愛心理","相手の気持ち","恋愛アドバイス","Shorts"],
                     "categoryId":"24","defaultLanguage":"ja"},
          "status":{"privacyStatus":PRIVACY,"selfDeclaredMadeForKids":False}}
    media=MediaFileUpload(path,chunksize=10*1024*1024,resumable=True)
    req=youtube.videos().insert(part="snippet,status",body=body,media_body=media)
    resp=None; retry=0
    while resp is None:
        try:
            st,resp=req.next_chunk()
            if st: print(f"  up {int(st.progress()*100)}%")
        except HttpError as e:
            if e.resp.status in (500,502,503,504):
                retry+=1
                if retry>10: raise
                time.sleep(min(2**retry,60))
            else: raise
    return resp

def main():
    wait_voicevox(); resolve_speaker()
    log=load_log(); avoid=[e.get("summary","") for e in log][-AVOID_RECENT:]
    data=generate_tips(avoid)
    print(f"title:{data.get('youtube_title')} / tips:{len(data.get('tips',[]))}")
    path,title=build_video(data)
    print(f"done:{path}")
    youtube=get_youtube(); res=upload(youtube,path,title)
    print(f"uploaded: https://www.youtube.com/watch?v={res['id']}")
    log.append({"summary":data.get("summary",""),"youtube_title":data.get("youtube_title","")})
    save_log(log)

if __name__=="__main__":
    main()
