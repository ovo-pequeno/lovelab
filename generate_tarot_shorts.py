# =========================================================
# タロット「今日のヒント」Shorts｜VOICEVOX春日部つむぎ
# カードを1枚引く→カード名→意味→今日の前向きメッセージ。縦型1分前後。
# カード画像は assets/cards/（逆位置は上下反転）。断定しないエンタメ占い。
# Gemini → VOICEVOX → MoviePy → YouTube API / 縦型1080x1920
# =========================================================
import os, re, json, time, gc, random, requests
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
VOICE_SPEED=1.2
OUT_DIR="out_tarot_s"; TMP_DIR="tmp_tarot_s"; LOG_PATH="used_log_tarot_shorts.json"; AVOID_RECENT=40
CARD_DIR="assets/cards"
BG_IMAGE = "assets/bg_tarot_short.png" if os.path.exists("assets/bg_tarot_short.png") else None
BG_COLOR=(24,16,40)
BGM_PATH = "assets/bgm_tarot.mp3" if os.path.exists("assets/bgm_tarot.mp3") else None
BGM_VOLUME=0.10

client = genai.Client(api_key=GEMINI_API_KEY)
W, H = 1080, 1920
FPS = 10
FONT = "/usr/share/fonts/truetype/custom/RocknRollOne-Regular.ttf"
if not os.path.exists(FONT): FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
HEADER_FONT = "/usr/share/fonts/truetype/custom/PottaOne-Regular.ttf"
if not os.path.exists(HEADER_FONT): HEADER_FONT = FONT
TEXT_COLOR="white"; ACCENT_COLOR="#E7C8FF"; STROKE_COLOR="#2A1740"
HEADER_TEXT="今日のタロット"

MAJOR_ARCANA = [
    ("00_fool","愚者"),("01_magician","魔術師"),("02_high_priestess","女教皇"),("03_empress","女帝"),
    ("04_emperor","皇帝"),("05_hierophant","教皇"),("06_lovers","恋人"),("07_chariot","戦車"),
    ("08_strength","力"),("09_hermit","隠者"),("10_wheel","運命の輪"),("11_justice","正義"),
    ("12_hanged_man","吊るされた男"),("13_death","死神"),("14_temperance","節制"),("15_devil","悪魔"),
    ("16_tower","塔"),("17_star","星"),("18_moon","月"),("19_sun","太陽"),("20_judgement","審判"),("21_world","世界"),
]


def load_log():
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    return []

def save_log(log):
    with open(LOG_PATH, "w", encoding="utf-8") as f: json.dump(log, f, ensure_ascii=False, indent=1)


def generate_message(card, avoid, max_retries=5):
    models=[MODEL,"gemini-2.5-flash-lite","gemini-3.1-flash-lite"]
    avoid_text=""
    if avoid:
        avoid_text = "\n\n【最近と被らない表現で】\n" + "\n".join(f"- {s}" for s in avoid)
    pos = "逆位置" if card["reversed"] else "正位置"
    prompt=f"""あなたは優しいタロット占い師です。今日のワンオラクル（1枚引き）Shortsの台本を作ります。
引いたカード：「{card['jp']}」（{pos}）

トーン：前向きで背中を押すエンタメ占い。断定や不安を煽る表現は避ける。
カードの伝統的な意味を踏まえ、今日を明るく過ごすヒントにする。

JSON形式のみ（前後に説明・マークダウン不要）:
{{
  "youtube_title": "タップしたくなる日本語タイトル（25文字以内）",
  "summary": "被り防止ログ用一行（30文字以内）",
  "keyword": "このカードのキーワード一言（10文字以内）",
  "meaning": "カードの意味をやさしく（50文字以内）",
  "message": "今日のあなたへの前向きメッセージ（60文字以内）",
  "action": "今日ちょっと試すといいこと一言（40文字以内）"
}}{avoid_text}
"""
    cfg=genai_types.GenerateContentConfig(temperature=1.1) if genai_types else None
    for attempt in range(max_retries):
        m=models[min(attempt,len(models)-1)]
        try:
            resp=client.models.generate_content(model=m,contents=prompt,config=cfg) if cfg else client.models.generate_content(model=m,contents=prompt)
            text=resp.text.strip().replace("```json","").replace("```","").strip()
            data=json.loads(text)
            if not data.get("message"): raise ValueError("message空")
            return data
        except Exception as e:
            msg=str(e)
            if ("503" in msg or "429" in msg or "UNAVAILABLE" in msg) and attempt<max_retries-1: time.sleep(15*(attempt+1))
            elif attempt<max_retries-1: time.sleep(5)
            else: raise


def make_audio(text, filename, tail_cut=0):
    if not text.strip():
        AudioSegment.silent(duration=400).export(filename, format="mp3"); return filename
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
            if requests.get(f"{VOICEVOX_URL}/version",timeout=5).ok:
                print("✅ VOICEVOX OK"); return True
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

def card_clip(card, d, target_h=int(H*0.42)):
    path=os.path.join(CARD_DIR,card["file"]+".png")
    if not os.path.exists(path): return None
    from PIL import Image; import numpy as np
    img=Image.open(path).convert("RGB")
    if card["reversed"]: img=img.transpose(Image.FLIP_TOP_BOTTOM)
    w,h=img.size; tw=int(target_h*w/h)
    rs=getattr(Image,"Resampling",Image).LANCZOS if hasattr(Image,"Resampling") else Image.LANCZOS
    return ImageClip(np.array(img.resize((tw,target_h),rs))).set_duration(d)

def _prewrap(text, fontsize, cw):
    import textwrap
    is_latin=sum(ord(c)<128 for c in text)>len(text)*0.6
    factor=0.58 if is_latin else 1.05
    mx=max(6,int(cw/(fontsize*factor)))
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
    return outlined(HEADER_TEXT,d,HEADER_FONT,72,"#FFFFFF",18,int(H*0.05),W-120)


def scene_card(card, audio_file):
    narr=AudioFileClip(audio_file); d=narr.duration+0.6
    pos="逆位置" if card["reversed"] else "正位置"
    layers=[make_bg(d),header(d)]
    ci=card_clip(card,d)
    if ci is not None:
        layers.append(ci.set_position(("center",int(H*0.22))))
        layers.append(outlined(f"{card['jp']}（{pos}）",d,FONT,52,ACCENT_COLOR,10,int(H*0.70),W-120))
    else:
        layers.append(outlined(f"{card['jp']}\n（{pos}）",d,FONT,90,"#FFFFFF",14,int(H*0.42),W-160))
    sc=CompositeVideoClip(layers,size=(W,H)).set_duration(d)
    if d>narr.duration+0.02: narr=CompositeAudioClip([narr]).set_duration(d)
    return sc.set_audio(narr)

def scene_text(main, audio_file, sub=None):
    narr=AudioFileClip(audio_file); d=narr.duration+0.5
    layers=[make_bg(d),header(d)]
    if sub: layers.append(outlined(sub,d,HEADER_FONT,50,"#FFE08A",10,int(H*0.30),W-140))
    layers.append(outlined(main,d,FONT,64,TEXT_COLOR,12,int(H*0.48),W-140))
    sc=CompositeVideoClip(layers,size=(W,H)).set_duration(d)
    if d>narr.duration+0.02: narr=CompositeAudioClip([narr]).set_duration(d)
    return sc.set_audio(narr)

def render(scene,path):
    scene.write_videofile(path,fps=FPS,codec="libx264",audio_codec="aac",preset="ultrafast",logger=None)
    try:
        if scene.audio is not None: scene.audio.close()
    except Exception: pass
    scene.close(); del scene; gc.collect()


def build_video(card, data):
    os.makedirs(OUT_DIR,exist_ok=True); os.makedirs(TMP_DIR,exist_ok=True)
    title=data.get("youtube_title","今日のタロット")
    safe=title
    for ch in r'\/:*?"<>|': safe=safe.replace(ch,"")
    output=os.path.join(OUT_DIR,f"{safe.strip()[:60]}.mp4")
    clips=[]; idx=0
    # カード提示
    a=make_audio(f"今日のカードは、{card['jp']}。{data.get('keyword','')}",f"a_{idx}.mp3",tail_cut=80)
    p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_card(card,a),p); clips.append(p); os.remove(a); idx+=1
    # 意味
    a=make_audio(data.get("meaning",""),f"a_{idx}.mp3",tail_cut=100)
    p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(data.get("meaning",""),a,sub="カードの意味"),p); clips.append(p); os.remove(a); idx+=1
    # メッセージ
    a=make_audio(data.get("message",""),f"a_{idx}.mp3",tail_cut=100)
    p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(data.get("message",""),a,sub="今日のあなたへ"),p); clips.append(p); os.remove(a); idx+=1
    # アクション
    a=make_audio(data.get("action",""),f"a_{idx}.mp3",tail_cut=100)
    p=f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(data.get("action",""),a,sub="今日のワンアクション"),p); clips.append(p); os.remove(a); idx+=1

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
    description=("今日のワンオラクル・タロット占い。前向きな気づきのためのエンタメ占いです。\n"
                 "当たり外れを断定するものではありません。\n\n#タロット #タロット占い #占い #今日の運勢 #shorts #Shorts")
    body={"snippet":{"title":(title+" #shorts")[:100],"description":description[:5000],
                     "tags":["タロット","タロット占い","占い","今日の運勢","ワンオラクル","Shorts"],
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
    card=random.choice(MAJOR_ARCANA)
    card={"file":card[0],"jp":card[1],"reversed":random.random()<0.4}
    print(f"カード:{card['jp']} {'逆' if card['reversed'] else '正'}")
    data=generate_message(card,avoid)
    path,title=build_video(card,data)
    print(f"done:{path}")
    youtube=get_youtube(); res=upload(youtube,path,title)
    print(f"uploaded: https://www.youtube.com/watch?v={res['id']}")
    log.append({"summary":data.get("summary",card["jp"]),"youtube_title":data.get("youtube_title","")})
    save_log(log)

if __name__=="__main__":
    main()
