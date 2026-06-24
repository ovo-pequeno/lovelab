# =========================================================
# 心理テスト Shorts（VOICEVOX）1本を生成してYouTubeへ自動投稿
# GitHub Actions上でVOICEVOXエンジン(Docker)を立てて使う。
# お題もGeminiが毎回自動生成・被り防止ログつき。
# Gemini → VOICEVOX（春日部つむぎ）→ MoviePy → YouTube API
# 縦型1080x1920
# =========================================================
import os, json, time, requests
from google import genai
try:
    from google.genai import types as genai_types
except Exception:
    genai_types = None
from pydub import AudioSegment
from moviepy.editor import (
    ColorClip, ImageClip, TextClip, CompositeVideoClip,
    AudioFileClip, CompositeAudioClip, concatenate_videoclips, afx
)
import moviepy.config as cf
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

cf.change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

# ----- 環境変数（GitHub Secrets） -----
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
YT_CLIENT_ID     = os.environ["YT_CLIENT_ID"]
YT_CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
YT_REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]

PRIVACY = os.environ.get("PRIVACY", "public")
MODEL   = os.environ.get("MODEL", "gemini-2.5-flash")

VOICEVOX_URL  = "http://127.0.0.1:50021"
SPEAKER_ID    = 8        # 8=春日部つむぎ
SPEAKER_NAME  = "春日部つむぎ"
SPEAKER_STYLE = "ノーマル"
VOICE_SPEED   = 1.3

OUT_DIR  = "out_shinri"
LOG_PATH = "used_log_shinri.json"
AVOID_RECENT = 40

BG_IMAGE = "assets/bg_short.png" if os.path.exists("assets/bg_short.png") else None
USE_OVERLAY = True
OVERLAY_OPACITY = 0.45
BGM_PATH = "assets/bgm_short.mp3" if os.path.exists("assets/bgm_short.mp3") else None
BGM_VOLUME = 0.15

client = genai.Client(api_key=GEMINI_API_KEY)

W, H = 1080, 1920
FPS = 10

HEADER_TEXT = "天使のたまご\n心理テスト"
HEADER_FONT = "/usr/share/fonts/truetype/custom/PottaOne-Regular.ttf"
HEADER_FONT_SIZE = 100
HEADER_STROKE_COLOR = "#FF8FC4"
HEADER_STROKE_WIDTH = 30
HEADER_INTERLINE = -10
HEADER_Y = 0.04

FONT = "/usr/share/fonts/truetype/custom/RocknRollOne-Regular.ttf"
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if not os.path.exists(HEADER_FONT):
    HEADER_FONT = FONT
TEXT_COLOR = "white"
STROKE_COLOR = "#FF5FA8"
MAIN_STROKE_WIDTH = 18
FONT_SIZE = 80
OPT_FONT_SIZE = 60


# ----- 被り防止ログ -----
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


# ----- Gemini：お題も含めて心理テストを自動生成（被り回避） -----
def generate_quiz(avoid_summaries, max_retries=5):
    models = [MODEL, "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]
    avoid_text = ""
    if avoid_summaries:
        joined = "\n".join(f"- {s}" for s in avoid_summaries)
        avoid_text = f"\n\n【これらと被らない、別テーマの心理テストにすること】\n{joined}"
    prompt = f"""
あなたは心理テストクリエイターです。
「何がわかるか」のテーマから自分で考えて、面白い心理テストを1つ作ってください。
（性格・恋愛傾向・深層心理・本音・相性・隠れた一面 など毎回違う切り口で）

以下のJSON形式のみで出力（前後に説明文やマークダウン不要）:
{{
  "theme": "このテストでわかること（被り防止ログ用・30文字以内）",
  "youtube_title": "タップしたくなるキャッチータイトル（25文字以内）",
  "title": "テストのタイトル（15文字以内）",
  "question": "問いかけ（30文字以内）",
  "options": ["選択肢A（12文字以内）", "選択肢B", "選択肢C", "選択肢D"],
  "results": [
    "Aを選んだあなたは…\\n（40文字以内）",
    "Bを選んだあなたは…\\n（40文字以内）",
    "Cを選んだあなたは…\\n（40文字以内）",
    "Dを選んだあなたは…\\n（40文字以内）"
  ]
}}
※「Aを選んだあなたは…」の直後に改行（\\n）を入れる。
※選択肢・結果はそれぞれ必ず4つ。
※youtube_titleは思わずタップしたくなる表現に。{avoid_text}
"""
    cfg = genai_types.GenerateContentConfig(temperature=1.15) if genai_types else None
    for attempt in range(max_retries):
        m = models[min(attempt, len(models) - 1)]
        try:
            if cfg:
                resp = client.models.generate_content(model=m, contents=prompt, config=cfg)
            else:
                resp = client.models.generate_content(model=m, contents=prompt)
            text = resp.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            if not data.get("results"):
                raise ValueError("resultsが空")
            return data
        except Exception as e:
            msg = str(e)
            if ("503" in msg or "429" in msg or "UNAVAILABLE" in msg) and attempt < max_retries - 1:
                time.sleep(20 * (attempt + 1))
            elif attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise


# ----- VOICEVOX音声 -----
def make_audio(text, filename, tail_cut=0):
    q = requests.post(f"{VOICEVOX_URL}/audio_query",
                      params={"text": text, "speaker": SPEAKER_ID}, timeout=60)
    query = q.json()
    query["speedScale"] = VOICE_SPEED
    query["prePhonemeLength"] = 0.1
    query["postPhonemeLength"] = 0.1
    s = requests.post(f"{VOICEVOX_URL}/synthesis",
                      params={"speaker": SPEAKER_ID},
                      data=json.dumps(query),
                      headers={"Content-Type": "application/json"}, timeout=120)
    tmp_wav = "tmp_" + filename.replace(".mp3", ".wav")
    with open(tmp_wav, "wb") as f:
        f.write(s.content)
    seg = AudioSegment.from_wav(tmp_wav)
    if tail_cut > 0 and len(seg) > tail_cut + 100:
        seg = seg[:-tail_cut]
    seg.export(filename, format="mp3")
    os.remove(tmp_wav)
    return filename


def wait_voicevox(timeout=180):
    for _ in range(timeout // 3):
        try:
            if requests.get(f"{VOICEVOX_URL}/version", timeout=5).ok:
                print("✅ VOICEVOXエンジン応答OK")
                return True
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError("VOICEVOXエンジンが起動しませんでした")


def resolve_speaker():
    global SPEAKER_ID
    try:
        sp = requests.get(f"{VOICEVOX_URL}/speakers", timeout=30).json()
    except Exception as e:
        print(f"  /speakers取得失敗（既定ID {SPEAKER_ID} のまま）: {e}")
        return
    for s in sp:
        if SPEAKER_NAME in s.get("name", ""):
            styles = s.get("styles", [])
            for st in styles:
                if SPEAKER_STYLE and SPEAKER_STYLE in st.get("name", ""):
                    SPEAKER_ID = st["id"]
                    print(f"🎙 語り手={SPEAKER_NAME}/{SPEAKER_STYLE}(id {SPEAKER_ID})")
                    return
            if styles:
                SPEAKER_ID = styles[0]["id"]
                print(f"🎙 語り手={SPEAKER_NAME}(id {SPEAKER_ID}) ※スタイル既定")
                return
    print(f"  ⚠️ 話者『{SPEAKER_NAME}』が見つからず。既定ID {SPEAKER_ID} を使用")


# ----- 背景（Pillow直接リサイズでANTIALIASエラー回避） -----
_BG_CACHE = None
def _fit_bg(path):
    global _BG_CACHE
    if _BG_CACHE is None:
        from PIL import Image
        import numpy as np
        resample = getattr(Image, "Resampling", Image).LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        _BG_CACHE = np.array(Image.open(path).convert("RGB").resize((W, H), resample))
    return _BG_CACHE


def make_background(duration, bg_color):
    if BG_IMAGE and os.path.exists(BG_IMAGE):
        return ImageClip(_fit_bg(BG_IMAGE)).set_duration(duration)
    return ColorClip(size=(W, H), color=bg_color, duration=duration)


def make_outlined_clip(text, duration, fontsize, font, stroke_color, stroke_width, interline=14):
    common = dict(font=font, fontsize=fontsize, method="caption",
                  size=(W - 80, None), align="center", interline=interline)
    stroke = TextClip(text, color=stroke_color, stroke_color=stroke_color,
                      stroke_width=stroke_width, **common).set_duration(duration)
    fill = TextClip(text, color=TEXT_COLOR, **common).set_duration(duration)
    return CompositeVideoClip(
        [stroke.set_position("center"), fill.set_position("center")],
        size=stroke.size).set_duration(duration)


def make_scene(text, duration, audio_file=None, bg_color=(20, 20, 40),
               force_duration=None, fontsize=None):
    if fontsize is None:
        fontsize = FONT_SIZE
    if audio_file:
        narration = AudioFileClip(audio_file)
        duration = force_duration if force_duration else narration.duration + 0.5
    else:
        narration = None
        if force_duration:
            duration = force_duration
    layers = [make_background(duration, bg_color)]
    if USE_OVERLAY:
        layers.append(ColorClip(size=(W, H), color=(0, 0, 0), duration=duration).set_opacity(OVERLAY_OPACITY))
    main_txt = make_outlined_clip(text, duration, fontsize, font=FONT,
                                  stroke_color=STROKE_COLOR, stroke_width=MAIN_STROKE_WIDTH
                                  ).set_position(("center", H * 0.55))
    layers.append(main_txt)
    if HEADER_TEXT:
        header = make_outlined_clip(HEADER_TEXT, duration, HEADER_FONT_SIZE,
                                    font=HEADER_FONT, stroke_color=HEADER_STROKE_COLOR,
                                    stroke_width=HEADER_STROKE_WIDTH, interline=HEADER_INTERLINE
                                    ).set_position(("center", H * HEADER_Y))
        layers.append(header)
    scene = CompositeVideoClip(layers, size=(W, H)).set_duration(duration)
    if narration:
        scene = scene.set_audio(narration)
    return scene


def make_output_path(yt_title=""):
    os.makedirs(OUT_DIR, exist_ok=True)
    safe = yt_title or "心理テスト"
    for ch in r'\/:*?"<>|':
        safe = safe.replace(ch, "")
    return os.path.join(OUT_DIR, f"{safe.strip()[:60]}.mp4")


def build_video(quiz):
    output_path = make_output_path(quiz.get("youtube_title", ""))
    scenes = []
    a = make_audio(quiz["title"], "a_title.mp3")
    scenes.append(make_scene(quiz["title"], 3, a, bg_color=(60, 30, 80)))
    a = make_audio(quiz["question"], "a_q.mp3")
    scenes.append(make_scene(quiz["question"], 3, a, bg_color=(30, 50, 80)))
    opt_text = "\n".join([f"{chr(65+i)}：{o}" for i, o in enumerate(quiz["options"])])
    opt_yomi = "　".join([f"{chr(65+i)}、{o}" for i, o in enumerate(quiz["options"])])
    a = make_audio(opt_yomi, "a_opt.mp3")
    opt_dur = AudioFileClip(a).duration + 2.5
    scenes.append(make_scene(opt_text, opt_dur, audio_file=a, bg_color=(30, 30, 55),
                             force_duration=opt_dur, fontsize=OPT_FONT_SIZE))
    for i, res in enumerate(quiz["results"]):
        a = make_audio(res, f"a_res{i}.mp3", tail_cut=100)
        scenes.append(make_scene(res, 4, a, bg_color=(60, 45, 30)))
    ending_text = "当たってた？\n結果はコメントに\n書いてね！"
    a = make_audio("当たってた？　結果はコメントに書いてね。", "a_end.mp3", tail_cut=100)
    scenes.append(make_scene(ending_text, 4, a, bg_color=(80, 40, 70)))

    final = concatenate_videoclips(scenes, method="compose")
    if BGM_PATH and os.path.exists(BGM_PATH):
        bgm = afx.audio_loop(AudioFileClip(BGM_PATH).volumex(BGM_VOLUME), duration=final.duration)
        final = final.set_audio(CompositeAudioClip([final.audio, bgm]) if final.audio else bgm)
    final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

    for f in os.listdir("."):
        if f.startswith("a_") and f.endswith(".mp3"):
            os.remove(f)
    return output_path


# ----- YouTube -----
def get_youtube():
    creds = Credentials(token=None, refresh_token=YT_REFRESH_TOKEN,
                        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET,
                        token_uri="https://oauth2.googleapis.com/token")
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload(youtube, path, quiz):
    title = quiz.get("youtube_title", "心理テスト")
    description = (
        f"{quiz.get('theme','')}\n\nあなたはどれを選ぶ？\n\n"
        "VOICEVOX:春日部つむぎ\n\n#心理テスト #心理 #診断 #shorts #Shorts"
    )
    body = {
        "snippet": {
            "title": (title + " #shorts")[:100],
            "description": description[:5000],
            "tags": ["心理テスト", "心理", "診断", "性格診断", "Shorts"],
            "categoryId": "24",
            "defaultLanguage": "ja",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, chunksize=10 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None; retry = 0
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                print(f"  ⏫ {int(status.progress()*100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                retry += 1
                if retry > 10: raise
                time.sleep(min(2 ** retry, 60))
            else:
                raise
    return response


def main():
    wait_voicevox()
    resolve_speaker()
    log = load_log()
    avoid = [e.get("theme", "") for e in log][-AVOID_RECENT:]
    print("📝 心理テストを自動生成中...")
    quiz = generate_quiz(avoid)
    print(f"   テーマ：{quiz.get('theme')} / タイトル：{quiz.get('youtube_title')}")

    path = build_video(quiz)
    print(f"🎬 生成完了：{path}")

    youtube = get_youtube()
    res = upload(youtube, path, quiz)
    print(f"✅ 投稿成功： https://www.youtube.com/watch?v={res['id']}")

    log.append({"theme": quiz.get("theme", ""), "youtube_title": quiz.get("youtube_title", "")})
    save_log(log)
    print(f"📝 ログ更新（計{len(log)}件）")


if __name__ == "__main__":
    main()
