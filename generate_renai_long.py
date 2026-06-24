# =========================================================
# 恋愛テクニック長尺動画（VOICEVOX）1本を生成してYouTubeへ自動投稿
# GitHub Actions上でVOICEVOXエンジン(Docker)を立てて使う。
# テーマもGeminiが毎回自動生成・被り防止ログつき。
# Gemini → VOICEVOX（春日部つむぎ）→ MoviePy → YouTube API
# 横型1920x1080 / 収益化ライン8分超え狙い
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
    AudioFileClip, CompositeAudioClip
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
VOICE_SPEED   = 1.2      # 長尺は少しゆっくりめが聴きやすい

NUM_TECHNIQUES = 7       # テクニック数（7本で8〜10分＝収益化ライン狙い）
OUT_DIR  = "out_renai"
TMP_DIR  = "tmp_renai"
LOG_PATH = "used_log_renai.json"
AVOID_RECENT = 40

BG_IMAGE = "assets/bg_long.png" if os.path.exists("assets/bg_long.png") else None
USE_OVERLAY = True
OVERLAY_OPACITY = 0.45
BGM_PATH = "assets/bgm_long.mp3" if os.path.exists("assets/bgm_long.mp3") else None
BGM_VOLUME = 0.12

HEADER_TEXT = "天使のたまご"

client = genai.Client(api_key=GEMINI_API_KEY)

W, H = 1920, 1080
FPS = 10

HEADER_FONT = "/usr/share/fonts/truetype/custom/PottaOne-Regular.ttf"
HEADER_FONT_SIZE = 60
HEADER_STROKE_COLOR = "#FF8FC4"
HEADER_STROKE_WIDTH = 25

FONT = "/usr/share/fonts/truetype/custom/RocknRollOne-Regular.ttf"
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if not os.path.exists(HEADER_FONT):
    HEADER_FONT = FONT
TEXT_COLOR = "white"
STROKE_COLOR = "#FF5FA8"
MAIN_STROKE_WIDTH = 10
FONT_SIZE_TITLE   = 90
FONT_SIZE_BODY    = 62
FONT_SIZE_LABEL   = 52
FONT_SIZE_CHAPTER = 72


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


# ----- Gemini：テーマも含めて構成を自動生成（被り回避） -----
def generate_techniques(avoid_summaries, max_retries=5):
    models = [MODEL, "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]
    avoid_text = ""
    if avoid_summaries:
        joined = "\n".join(f"- {s}" for s in avoid_summaries)
        avoid_text = f"\n\n【これらと被らない、別テーマにすること】\n{joined}"
    prompt = f"""
あなたは恋愛心理の専門家です。
恋愛・モテに役立つ「テーマ」を自分で1つ考え、その効果的なテクニックを
{NUM_TECHNIQUES}個解説する動画の台本を作ってください。
（例：会話術、LINE、第一印象、デート、駆け引き、自己演出 など毎回違う切り口で）

以下のJSON形式のみで出力してください（前後に説明文・マークダウン不要）:
{{
  "theme": "今回のテーマ（30文字以内・被り防止ログ用）",
  "youtube_title": "YouTubeでバズりそうなタイトル（30文字以内・煽り気味でOK）",
  "intro": {{
    "hook": "冒頭の掴み文句（視聴者の興味を引く一言・40文字以内）",
    "overview": "今回解説する内容の概要（50文字以内）"
  }},
  "techniques": [
    {{
      "number": 1,
      "title": "テクニック名（15文字以内）",
      "lead": "このテクニックの導入・なぜ効くか（70文字以内）",
      "explanation": ["解説文1（80文字以内）", "解説文2", "解説文3", "解説文4", "解説文5"],
      "example": "具体的な事例・使い方（80文字以内）",
      "caution": "注意点・やりすぎNG（60文字以内）",
      "summary": "このテクニックのまとめ1文（50文字以内）"
    }}
  ],
  "outro": {{
    "recap": "全テクニックの振り返り一言（60文字以内）",
    "cta": "チャンネル登録・コメント誘導（40文字以内）"
  }}
}}
※techniquesは必ず{NUM_TECHNIQUES}個。explanationは必ず5文。
※各解説は具体的で説得力のある内容にし、心理学的な根拠や具体例を盛り込む。
※「悪用厳禁」「心理的テクニック」などの煽り表現をうまく使ってください。{avoid_text}
"""
    cfg = genai_types.GenerateContentConfig(max_output_tokens=8192, temperature=1.1) if genai_types else None
    for attempt in range(max_retries):
        m = models[min(attempt, len(models) - 1)]
        try:
            if cfg:
                resp = client.models.generate_content(model=m, contents=prompt, config=cfg)
            else:
                resp = client.models.generate_content(model=m, contents=prompt)
            text = resp.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            if not data.get("techniques"):
                raise ValueError("techniquesが空")
            return data
        except Exception as e:
            msg = str(e)
            if ("503" in msg or "429" in msg or "UNAVAILABLE" in msg) and attempt < max_retries - 1:
                time.sleep(15 * (attempt + 1))
            elif attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise


# ----- VOICEVOX音声 -----
def make_audio(text, filename, speed=None, tail_cut=100):
    if speed is None:
        speed = VOICE_SPEED
    q = requests.post(f"{VOICEVOX_URL}/audio_query",
                      params={"text": text, "speaker": SPEAKER_ID}, timeout=60)
    query = q.json()
    query["speedScale"] = speed
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


def make_background(duration, bg_color=(20, 20, 40)):
    if BG_IMAGE and os.path.exists(BG_IMAGE):
        return ImageClip(_fit_bg(BG_IMAGE)).set_duration(duration)
    return ColorClip(size=(W, H), color=bg_color, duration=duration)


def make_outlined_clip(text, duration, fontsize, font=None,
                       stroke_color=None, stroke_width=None, interline=22, size=None):
    if font is None: font = FONT
    if stroke_color is None: stroke_color = STROKE_COLOR
    if stroke_width is None: stroke_width = MAIN_STROKE_WIDTH
    if size is None: size = (W - 160, None)
    common = dict(font=font, fontsize=fontsize, method="caption",
                  size=size, align="center", interline=interline)
    stroke = TextClip(text, color=stroke_color, stroke_color=stroke_color,
                      stroke_width=stroke_width, **common).set_duration(duration)
    fill = TextClip(text, color=TEXT_COLOR, **common).set_duration(duration)
    return CompositeVideoClip(
        [stroke.set_position("center"), fill.set_position("center")],
        size=stroke.size).set_duration(duration)


def make_header_logo(duration):
    logo = make_outlined_clip(HEADER_TEXT, duration, HEADER_FONT_SIZE,
                              font=HEADER_FONT, stroke_color=HEADER_STROKE_COLOR,
                              stroke_width=HEADER_STROKE_WIDTH, size=(400, None))
    return logo.set_position((40, 30))


def make_scene(main_text, audio_file=None, bg_color=(20, 20, 40),
               force_duration=None, fontsize=None,
               sub_text=None, sub_fontsize=None, label_text=None, main_y_ratio=None):
    if fontsize is None: fontsize = FONT_SIZE_BODY
    if audio_file:
        narration = AudioFileClip(audio_file)
        duration = force_duration if force_duration else narration.duration + 0.8
    else:
        narration = None
        duration = force_duration if force_duration else 3.0
    layers = [make_background(duration, bg_color)]
    if USE_OVERLAY:
        layers.append(ColorClip(size=(W, H), color=(0, 0, 0), duration=duration).set_opacity(OVERLAY_OPACITY))
    if label_text:
        layers.append(make_outlined_clip(label_text, duration, FONT_SIZE_LABEL,
                                          size=(W - 160, None), interline=10).set_position((80, 120)))
    if main_y_ratio is not None:
        main_y = H * main_y_ratio
    else:
        main_y = H * 0.38 if sub_text else H * 0.45
    layers.append(make_outlined_clip(main_text, duration, fontsize, size=(W - 200, None))
                  .set_position(("center", main_y)))
    if sub_text:
        sub_fs = sub_fontsize if sub_fontsize else FONT_SIZE_LABEL
        layers.append(make_outlined_clip(sub_text, duration, sub_fs, size=(W - 240, None),
                                          stroke_color="#FFAACC", stroke_width=14)
                      .set_position(("center", H * 0.68)))
    layers.append(make_header_logo(duration))
    scene = CompositeVideoClip(layers, size=(W, H)).set_duration(duration)
    if narration:
        if duration > narration.duration + 0.02:
            narration = CompositeAudioClip([narration]).set_duration(duration)
        scene = scene.set_audio(narration)
    return scene


def make_output_path(yt_title=""):
    os.makedirs(OUT_DIR, exist_ok=True)
    safe = yt_title or "恋愛テクニック解説"
    for ch in r'\/:*?"<>|':
        safe = safe.replace(ch, "")
    return os.path.join(OUT_DIR, f"{safe.strip()[:60]}.mp4")


def render_scene_to_file(out_path, *args, **kwargs):
    import gc
    scene = make_scene(*args, **kwargs)
    scene.write_videofile(out_path, fps=FPS, codec="libx264",
                          audio_codec="aac", preset="ultrafast", logger=None)
    try:
        if scene.audio is not None:
            scene.audio.close()
    except Exception:
        pass
    scene.close(); del scene; gc.collect()


def build_long_video(data):
    output_path = make_output_path(data.get("youtube_title", ""))
    os.makedirs(TMP_DIR, exist_ok=True)
    clip_paths = []
    fi = [0]; ci = [0]

    def next_audio():
        fi[0] += 1
        return f"a_{fi[0]:03d}.mp3"

    def add_scene(*args, **kwargs):
        p = f"{TMP_DIR}/clip_{ci[0]:04d}.mp4"
        render_scene_to_file(p, *args, **kwargs)
        clip_paths.append(p); ci[0] += 1

    # (1) フック
    a = make_audio(data["intro"]["hook"], next_audio(), tail_cut=80)
    add_scene(data["intro"]["hook"], audio_file=a, bg_color=(60, 20, 80), fontsize=FONT_SIZE_CHAPTER)
    # (2) 概要
    a = make_audio(data["intro"]["overview"], next_audio(), tail_cut=80)
    add_scene(data["intro"]["overview"], audio_file=a, bg_color=(30, 30, 70), label_text="今回のテーマ")
    # (3) 目次
    total = len(data["techniques"])
    syms = "①②③④⑤⑥⑦⑧⑨⑩"
    titles_text = "\n".join(f"{syms[i] if i < len(syms) else i+1}　{t['title']}"
                            for i, t in enumerate(data["techniques"]))
    a = make_audio(f"今回紹介するテクニックは、こちらの{total}つです。順番に見ていきましょう。", next_audio(), tail_cut=80)
    toc_dur = AudioFileClip(a).duration + 2.5
    add_scene(titles_text, audio_file=a, force_duration=toc_dur, bg_color=(20, 40, 60),
              fontsize=FONT_SIZE_LABEL, label_text="🔥 今回のテクニック一覧", main_y_ratio=0.30)
    # (4) テクニックごと
    for i, tech in enumerate(data["techniques"]):
        sym = syms[i] if i < len(syms) else str(i + 1)
        label = f"{sym} {tech['title']}"
        print(f"  テクニック {i+1}/{total}: {tech['title']}")
        a = make_audio(f"{i+1}つ目。{tech['title']}。{tech['lead']}", next_audio(), tail_cut=80)
        add_scene(tech["title"], audio_file=a, bg_color=(50, 25, 70), fontsize=FONT_SIZE_TITLE,
                  label_text=label, sub_text=tech["lead"], sub_fontsize=FONT_SIZE_LABEL)
        for exp in tech["explanation"]:
            a = make_audio(exp, next_audio(), tail_cut=100)
            add_scene(exp, audio_file=a, bg_color=(25, 35, 65), label_text=label)
        a = make_audio(tech["example"], next_audio(), tail_cut=100)
        add_scene(tech["example"], audio_file=a, bg_color=(30, 50, 40), label_text="💡 具体例")
        a = make_audio(tech["caution"], next_audio(), tail_cut=100)
        add_scene(tech["caution"], audio_file=a, bg_color=(60, 35, 25), label_text="⚠️ 注意点")
        a = make_audio(tech["summary"], next_audio(), tail_cut=80)
        add_scene(tech["summary"], audio_file=a, bg_color=(40, 40, 60), label_text=f"{label}　まとめ")
    # (5) まとめ
    a = make_audio(data["outro"]["recap"], next_audio(), tail_cut=80)
    add_scene(data["outro"]["recap"], audio_file=a, bg_color=(50, 20, 60),
              fontsize=FONT_SIZE_CHAPTER, label_text="📝 まとめ")
    # (6) CTA
    a = make_audio(data["outro"]["cta"], next_audio(), tail_cut=80)
    add_scene(data["outro"]["cta"], audio_file=a, bg_color=(70, 30, 70))

    # (7) 連結（映像コピー・音声再エンコード）
    print(f"  🔗 {len(clip_paths)}シーンを連結...")
    list_file = f"{TMP_DIR}/list.txt"
    with open(list_file, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.basename(cp)}'\n")
    merged = f"{TMP_DIR}/merged.mp4"
    os.system(f'cd {TMP_DIR} && ffmpeg -y -f concat -safe 0 -i list.txt '
              f'-c:v copy -c:a aac -b:a 192k merged.mp4 -loglevel error')

    # (8) BGM合成
    if BGM_PATH and os.path.exists(BGM_PATH):
        print("  🎵 BGMを合成...")
        os.system(
            f'ffmpeg -y -i "{merged}" -stream_loop -1 -i "{BGM_PATH}" '
            f'-filter_complex "[1:a]volume={BGM_VOLUME}[b];'
            f'[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a]" '
            f'-map 0:v -map "[a]" -c:v copy -c:a aac -shortest "{output_path}" -loglevel error'
        )
    else:
        os.replace(merged, output_path)

    for cp in clip_paths:
        if os.path.exists(cp):
            os.remove(cp)
    for extra in [list_file, merged]:
        if os.path.exists(extra):
            os.remove(extra)
    return output_path


# ----- YouTube -----
def get_youtube():
    creds = Credentials(token=None, refresh_token=YT_REFRESH_TOKEN,
                        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET,
                        token_uri="https://oauth2.googleapis.com/token")
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload(youtube, path, data):
    title = data.get("youtube_title", "恋愛テクニック解説")
    description = (
        f"{data.get('theme','')}\n\n恋愛心理テクニックを解説します。\n\n"
        "VOICEVOX:春日部つむぎ\n\n#恋愛 #恋愛心理 #モテ #恋愛テクニック #心理学"
    )
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": ["恋愛", "恋愛心理", "モテ", "恋愛テクニック", "心理学", "恋愛相談"],
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
    print("📝 テーマ＆構成を自動生成中...")
    data = generate_techniques(avoid)
    print(f"   テーマ：{data.get('theme')} / タイトル：{data.get('youtube_title')}")

    path = build_long_video(data)
    print(f"🎬 生成完了：{path}")

    youtube = get_youtube()
    res = upload(youtube, path, data)
    print(f"✅ 投稿成功： https://www.youtube.com/watch?v={res['id']}")

    log.append({"theme": data.get("theme", ""), "youtube_title": data.get("youtube_title", "")})
    save_log(log)
    print(f"📝 ログ更新（計{len(log)}件）")


if __name__ == "__main__":
    main()
