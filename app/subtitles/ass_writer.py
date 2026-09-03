_HEADER_TEMPLATE = """[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: {style_name},{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{outline},{shadow},2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _format_timestamp(seconds):
    seconds = max(0.0, seconds)
    total_cs = round(seconds * 100)
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("{", "\\{").replace("}", "\\}")
    return text.replace("\n", "\\N")


def write_ass(
    cues,
    output_path,
    video_width=1920,
    video_height=1080,
    title="Unlimited-OCR subtitles",
    font_name="Arial",
    font_size=48,
    outline=2,
    shadow=0,
    margin_v=40,
    style_name="Default",
):
    header = _HEADER_TEMPLATE.format(
        title=title,
        play_res_x=video_width,
        play_res_y=video_height,
        style_name=style_name,
        font_name=font_name,
        font_size=font_size,
        outline=outline,
        shadow=shadow,
        margin_v=margin_v,
    )

    lines = [header]
    for cue in cues:
        start = _format_timestamp(cue.start)
        end = _format_timestamp(cue.end)
        text = _escape_text(cue.text)
        if cue.italic:
            text = f"{{\\i1}}{text}{{\\i0}}"
        lines.append(f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
