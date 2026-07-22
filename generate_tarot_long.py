# =========================================================
# タロット 選択式リーディング（恋愛テーマ）長尺｜VOICEVOX春日部つむぎ
# 「A〜Dから直感で選んで」→選択肢ごとにカードを引いて恋愛を前向きに読む。
# カード画像は assets/cards/ のAI生成画像（逆位置は上下反転）。
# 前向きエンタメ・断定しないトーン。8分超え・15分以内。
# Gemini → VOICEVOX → MoviePy → YouTube API / 横型1920x1080
# =========================================================
import os, re, json, time, gc, random, requests
from tarot_deck import draw_from_dir, TAROT_DECK
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

VOICEVOX_URL  = "http://127.0.0.1:50021"
SPEAKER_ID    = 8
SPEAKER_NAME  = "春日部つむぎ"
SPEAKER_STYLE = "ノーマル"
VOICE_SPEED   = 1.15
MAX_SECONDS   = 14 * 60

OUT_DIR  = "out_tarot_l"
TMP_DIR  = "tmp_tarot_l"
LOG_PATH = "used_log_tarot_long.json"
AVOID_RECENT = 40
CARD_DIR = "assets/cards"

BG_IMAGE = "assets/bg_tarot_long.png" if os.path.exists("assets/bg_tarot_long.png") else None
BG_COLOR = (24, 16, 40)     # 神秘的な紫紺
BGM_PATH = "assets/bgm_tarot.mp3" if os.path.exists("assets/bgm_tarot.mp3") else None
BGM_VOLUME = 0.12

client = genai.Client(api_key=GEMINI_API_KEY)

W, H = 1920, 1080
FPS = 10

FONT = "/usr/share/fonts/truetype/custom/RocknRollOne-Regular.ttf"
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
HEADER_FONT = "/usr/share/fonts/truetype/custom/PottaOne-Regular.ttf"
if not os.path.exists(HEADER_FONT):
    HEADER_FONT = FONT
TEXT_COLOR = "white"
ACCENT_COLOR = "#E7C8FF"    # 淡い紫
STROKE_COLOR = "#2A1740"
HEADER_TEXT = "天使のたまご タロット"

def load_log():
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_log(log):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)


def generate_reading(theme, cards, avoid_summaries, max_retries=5):
    """A〜Dの各選択肢に引いたカードで、恋愛を前向きに読むリーディングを生成。"""
    models = [MODEL, "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]
    avoid_text = ""
    if avoid_summaries:
        joined = "\n".join(f"- {s}" for s in avoid_summaries)
        avoid_text = f"\n\n【これらと被らない切り口にする】\n{joined}"
    card_desc = "\n".join(
        f"選択肢{chr(65+i)}: カード「{c['jp']}」（{'逆位置' if c['reversed'] else '正位置'}）"
        for i, c in enumerate(cards))
    prompt = f"""あなたは優しいタロット占い師です。恋愛テーマの「選択式リーディング」動画の台本を作ります。
テーマ：{theme}
視聴者は直感でA〜Dのグループを1つ選びます。各グループに以下のカードが出ています：
{card_desc}

重要なトーン：
- 前向きで、気づきや背中を押すメッセージにする（エンタメとして楽しめる占い）。
- 「絶対こうなる」「相手は必ずこう思っている」などの断定は避ける。
- 不安を煽らない。「あなたがどう向き合うか」に軸を置く。
- カードの伝統的な意味を踏まえつつ、恋愛の文脈でやさしく解釈する。

以下のJSON形式のみ（前後に説明・マークダウン不要）:
{{
  "youtube_title": "タップしたくなる日本語タイトル（30文字以内・恋愛タロット感）",
  "summary": "被り防止ログ用の一行（30文字以内）",
  "intro": "視聴者にA〜Dを選ばせる導入（80文字以内）",
  "readings": [
    {{"choice": "A", "card_line": "「カード名」からのメッセージ（30文字以内）",
      "body": ["リーディング本文1（70文字以内）", "本文2", "本文3"],
      "advice": "前向きなアドバイス一言（50文字以内）"}}
  ],
  "outro": "全体の締め・チャンネル登録誘導（60文字以内）"
}}
※readingsは必ず4つ（A/B/C/D）。各bodyは3文。{avoid_text}
"""
    cfg = genai_types.GenerateContentConfig(max_output_tokens=4096, temperature=1.05) if genai_types else None
    for attempt in range(max_retries):
        m = models[min(attempt, len(models) - 1)]
        try:
            if cfg:
                resp = client.models.generate_content(model=m, contents=prompt, config=cfg)
            else:
                resp = client.models.generate_content(model=m, contents=prompt)
            text = resp.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            if len(data.get("readings", [])) < 4:
                raise ValueError("readingsが4未満")
            return data
        except Exception as e:
            msg = str(e)
            if ("503" in msg or "429" in msg or "UNAVAILABLE" in msg) and attempt < max_retries - 1:
                time.sleep(15 * (attempt + 1))
            elif attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise


# ----- VOICEVOX -----
def make_audio(text, filename, tail_cut=0):
    if not text.strip():
        AudioSegment.silent(duration=400).export(filename, format="mp3"); return filename
    q = requests.post(f"{VOICEVOX_URL}/audio_query",
                      params={"text": text, "speaker": SPEAKER_ID}, timeout=60)
    query = q.json()
    query["speedScale"] = VOICE_SPEED
    query["prePhonemeLength"] = 0.1
    query["postPhonemeLength"] = 0.1
    s = requests.post(f"{VOICEVOX_URL}/synthesis", params={"speaker": SPEAKER_ID},
                      data=json.dumps(query), headers={"Content-Type": "application/json"}, timeout=120)
    tw = "tmp_" + filename.replace(".mp3", ".wav")
    with open(tw, "wb") as f:
        f.write(s.content)
    seg = AudioSegment.from_wav(tw)
    if tail_cut > 0 and len(seg) > tail_cut + 100:
        seg = seg[:-tail_cut]
    seg.export(filename, format="mp3"); os.remove(tw)
    return filename


def wait_voicevox(timeout=180):
    for _ in range(timeout // 3):
        try:
            if requests.get(f"{VOICEVOX_URL}/version", timeout=5).ok:
                print("✅ VOICEVOX OK"); return True
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError("VOICEVOX起動せず")


def resolve_speaker():
    global SPEAKER_ID
    try:
        sp = requests.get(f"{VOICEVOX_URL}/speakers", timeout=30).json()
    except Exception:
        return
    for s in sp:
        if SPEAKER_NAME in s.get("name", ""):
            for st in s.get("styles", []):
                if SPEAKER_STYLE in st.get("name", ""):
                    SPEAKER_ID = st["id"]; return
            if s.get("styles"):
                SPEAKER_ID = s["styles"][0]["id"]; return


# ----- 画像・描画 -----
_bg_cache = None
def _fit_bg(path):
    global _bg_cache
    if _bg_cache is None:
        from PIL import Image
        import numpy as np
        rs = getattr(Image, "Resampling", Image).LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        _bg_cache = np.array(Image.open(path).convert("RGB").resize((W, H), rs))
    return _bg_cache


def make_bg(duration):
    if BG_IMAGE and os.path.exists(BG_IMAGE):
        return ImageClip(_fit_bg(BG_IMAGE)).set_duration(duration)
    return ColorClip(size=(W, H), color=BG_COLOR, duration=duration)


def card_image_clip(card, duration, target_h=int(H * 0.62)):
    """カード画像を読み込み、逆位置なら上下反転。無ければNone。"""
    path = os.path.join(CARD_DIR, card["file"] + ".png")
    if not os.path.exists(path):
        return None
    from PIL import Image
    import numpy as np
    img = Image.open(path).convert("RGB")
    if card["reversed"]:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    w, h = img.size
    tw = int(target_h * w / h)
    rs = getattr(Image, "Resampling", Image).LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    img = img.resize((tw, target_h), rs)
    return ImageClip(np.array(img)).set_duration(duration)


def _prewrap(text, fontsize, canvas_w):
    import textwrap
    is_latin = sum(ord(c) < 128 for c in text) > len(text) * 0.6
    factor = 0.58 if is_latin else 1.05
    mx = max(6, int(canvas_w / (fontsize * factor)))
    if is_latin:
        return "\n".join(textwrap.wrap(text, width=mx)) or text
    return "\n".join(text[i:i+mx] for i in range(0, len(text), mx)) or text


def outlined(text, duration, font, fontsize, color, stroke_w, ypos, canvas_w):
    wrapped = _prewrap(text, fontsize, canvas_w)
    common = dict(font=font, fontsize=fontsize, method="label", align="center", interline=12)
    st = TextClip(wrapped, color=STROKE_COLOR, stroke_color=STROKE_COLOR, stroke_width=stroke_w, **common).set_duration(duration)
    fl = TextClip(wrapped, color=color, **common).set_duration(duration)
    return CompositeVideoClip([st.set_position(("center","center")), fl.set_position(("center","center"))],
                              size=(max(st.w, fl.w), max(st.h, fl.h))).set_duration(duration).set_position(("center", ypos))


def header_clip(duration):
    return outlined(HEADER_TEXT, duration, HEADER_FONT, 54, "#FFFFFF", 16, int(H*0.05), W-200)


def scene_text(main_text, audio_file, sub=None, big=False):
    narr = AudioFileClip(audio_file)
    dur = narr.duration + 0.6
    layers = [make_bg(dur), header_clip(dur)]
    layers.append(outlined(main_text, dur, FONT, 66 if big else 56, TEXT_COLOR, 12,
                           int(H*0.42), W-300))
    if sub:
        layers.append(outlined(sub, dur, FONT, 46, ACCENT_COLOR, 10, int(H*0.66), W-360))
    sc = CompositeVideoClip(layers, size=(W, H)).set_duration(dur)
    if dur > narr.duration + 0.02:
        narr = CompositeAudioClip([narr]).set_duration(dur)
    return sc.set_audio(narr)


def scene_card(choice, card, card_line, audio_file):
    narr = AudioFileClip(audio_file)
    dur = narr.duration + 0.8
    layers = [make_bg(dur), header_clip(dur)]
    pos_txt = "逆位置" if card["reversed"] else "正位置"
    layers.append(outlined(f"{choice} を選んだあなた", dur, HEADER_FONT, 60, "#FFE08A", 14, int(H*0.16), W-300))
    ci = card_image_clip(card, dur)
    if ci is not None:
        layers.append(ci.set_position(("center", int(H*0.24))))
        layers.append(outlined(f"{card['jp']}（{pos_txt}）", dur, FONT, 46, ACCENT_COLOR, 10, int(H*0.90), W-300))
    else:
        # 画像が無い場合はカード名を大きく表示
        layers.append(outlined(f"{card['jp']}\n（{pos_txt}）", dur, FONT, 80, "#FFFFFF", 14, int(H*0.45), W-400))
    sc = CompositeVideoClip(layers, size=(W, H)).set_duration(dur)
    if dur > narr.duration + 0.02:
        narr = CompositeAudioClip([narr]).set_duration(dur)
    return sc.set_audio(narr)


def render(scene, path):
    scene.write_videofile(path, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast", logger=None)
    try:
        if scene.audio is not None:
            scene.audio.close()
    except Exception:
        pass
    scene.close(); del scene; gc.collect()


def build_video(data, cards):
    os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(TMP_DIR, exist_ok=True)
    title = data.get("youtube_title", "恋愛タロット")
    safe = title
    for ch in r'\/:*?"<>|':
        safe = safe.replace(ch, "")
    output = os.path.join(OUT_DIR, f"{safe.strip()[:60]}.mp4")

    clips = []; idx = 0
    # イントロ
    a = make_audio(data["intro"], f"a_{idx}.mp3", tail_cut=80)
    p = f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(data["intro"], a, big=True), p)
    clips.append(p); os.remove(a); idx += 1
    # A〜D
    for i, rd in enumerate(data["readings"][:4]):
        choice = rd.get("choice", chr(65+i))
        card = cards[i]
        # カード提示
        a = make_audio(f"{choice}を選んだあなた。カードは、{card['jp']}です。", f"a_{idx}.mp3", tail_cut=80)
        p = f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_card(choice, card, rd.get("card_line",""), a), p)
        clips.append(p); os.remove(a); idx += 1
        # 本文
        for b in rd.get("body", []):
            a = make_audio(b, f"a_{idx}.mp3", tail_cut=100)
            p = f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(b, a, sub=f"{choice}のあなたへ"), p)
            clips.append(p); os.remove(a); idx += 1
        # アドバイス
        a = make_audio(rd.get("advice",""), f"a_{idx}.mp3", tail_cut=80)
        p = f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(rd.get("advice",""), a, sub="今日のアドバイス", big=True), p)
        clips.append(p); os.remove(a); idx += 1
    # アウトロ
    a = make_audio(data["outro"], f"a_{idx}.mp3", tail_cut=80)
    p = f"{TMP_DIR}/clip_{idx:04d}.mp4"; render(scene_text(data["outro"], a, big=True), p)
    clips.append(p); os.remove(a); idx += 1

    list_file = f"{TMP_DIR}/list.txt"
    with open(list_file, "w") as f:
        for cp in clips:
            f.write(f"file '{os.path.basename(cp)}'\n")
    master = f"{TMP_DIR}/master.mp4"
    os.system(f'cd {TMP_DIR} && ffmpeg -y -f concat -safe 0 -i list.txt -c:v copy -c:a aac master.mp4 -loglevel error')
    if BGM_PATH and os.path.exists(BGM_PATH):
        os.system(f'ffmpeg -y -i "{master}" -stream_loop -1 -i "{BGM_PATH}" '
                  f'-filter_complex "[1:a]volume={BGM_VOLUME}[b];[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a]" '
                  f'-map 0:v -map "[a]" -c:v copy -c:a aac "{output}" -loglevel error')
    else:
        os.replace(master, output)
    for cp in clips:
        if os.path.exists(cp): os.remove(cp)
    for f in [list_file, master]:
        if os.path.exists(f): os.remove(f)
    return output, title


def get_youtube():
    creds = Credentials(token=None, refresh_token=YT_REFRESH_TOKEN,
                        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET,
                        token_uri="https://oauth2.googleapis.com/token")
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload(youtube, path, title, theme):
    description = (
        f"【選択式タロット】{theme}\n"
        "A〜Dから直感で選んで、今のあなたへのメッセージを受け取ってください。\n"
        "前向きな気づきのためのエンタメ占いです。当たる・当たらないを断定するものではありません。\n\n"
        "#タロット #タロット占い #恋愛 #占い #選択式 #相手の気持ち"
    )
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": ["タロット", "タロット占い", "恋愛", "占い", "相手の気持ち", "選択式リーディング", "恋愛占い"],
                    "categoryId": "24", "defaultLanguage": "ja"},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, chunksize=10*1024*1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None; retry = 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st: print(f"  up {int(st.progress()*100)}%")
        except HttpError as e:
            if e.resp.status in (500,502,503,504):
                retry += 1
                if retry > 10: raise
                time.sleep(min(2**retry, 60))
            else:
                raise
    return resp


def main():
    wait_voicevox(); resolve_speaker()
    log = load_log()
    avoid = [e.get("summary","") for e in log][-AVOID_RECENT:]
    themes = ["片思いの相手の気持ち", "あの人との今後", "復縁の可能性", "出会い・新しい恋",
              "相手の本音", "二人の関係の変化", "恋の障害と乗り越え方", "あの人があなたをどう見ているか"]
    theme = random.choice(themes)
    cards = draw_from_dir(CARD_DIR, n=4)
    print(f"テーマ:{theme} / カード:{[c['jp'] for c in cards]}")
    data = generate_reading(theme, cards, avoid)
    path, title = build_video(data, cards)
    print(f"done: {path}")
    youtube = get_youtube()
    res = upload(youtube, path, title, theme)
    print(f"uploaded: https://www.youtube.com/watch?v={res['id']}")
    log.append({"summary": data.get("summary", theme), "youtube_title": data.get("youtube_title","")})
    save_log(log)


if __name__ == "__main__":
    main()
