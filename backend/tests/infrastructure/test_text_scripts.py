"""Text in every script we caption: the right font per run, shaping by raqm, and right to left for Arabic."""

# ruff: noqa: RUF001  (full-width punctuation is the text under test)
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont, features

from frameteller.infrastructure.imaging.text import FILES, base_script, covers, draw_line, font, runs, textlength, wrap

SAMPLES = {
    "ja-JP": "夜の屋上で、リナは「紙の凧」を拾った。",
    "ko-KR": "밤이 오면 리나는 종이 연을 잡는다.",
    "zh-CN": "夜幕降临，丽娜接住了一只纸风筝。",
    "hi-IN": "छतों पर रात उतरती है, और लीना के हाथों में 3 पतंगें आ गिरती हैं।",
    "ar-SA": "يحلّ الليل فوق الأسطح، وتهبط 3 طائرات ورقية بين يدي لينا.",
}


def test_raqm_shapes_with_harfbuzz_and_fribidi() -> None:
    assert features.check("raqm")
    assert features.version("fribidi")
    assert features.version("harfbuzz")


@pytest.mark.parametrize(("language", "text"), SAMPLES.items())
def test_every_character_has_a_glyph_in_its_font(language: str, text: str) -> None:
    parts, _ = runs(text, language)
    assert [k for _, k in parts] == [language[:2]]  # one font for the whole line: spaces and digits go with it
    assert all(covers(k, ch) for t, k in parts for ch in t)


def test_latin_inside_hindi_and_arabic_keeps_the_latin_font() -> None:
    assert runs("frameteller.com पर अपनी कहानी सुनाइए", "hi-IN") == (
        [("frameteller.com ", "latin"), ("पर अपनी कहानी सुनाइए", "hi")],
        False,
    )
    assert runs("احكِ قصتك على frameteller.com", "ar-SA") == (
        [("احكِ قصتك على ", "ar"), ("frameteller.com", "latin")],
        True,
    )
    assert runs("在 frameteller.com 讲述你的故事", "zh-CN") == ([("在 frameteller.com 讲述你的故事", "zh")], False)
    assert base_script("Night falls.") == "latin"
    assert base_script("夜のパン屋さん") == "ja"  # kana: Japanese, even with no language given
    assert base_script("面包师") == "zh"


def ink(text: str, language: str, anchor: str = "ms") -> Image.Image:
    image = Image.new("L", (1400, 120))
    draw_line(ImageDraw.Draw(image), (700, 90), text, 52, (255,), language=language, anchor=anchor)
    return image


def test_an_arabic_line_reads_right_to_left_with_the_site_on_its_left() -> None:
    line = "احكِ قصتك على frameteller.com"
    total = textlength(line, 52, "ar-SA")
    site = textlength("frameteller.com", 52)
    left = 700 - total / 2
    drawn = ink(line, "ar-SA")
    alone = Image.new("L", (1400, 120))
    ImageDraw.Draw(alone).text((left, 90), "frameteller.com", font=font(52), fill=255, anchor="ls")
    region = (int(left), 0, int(left + site), 120)
    assert ImageChops.difference(drawn.crop(region), alone.crop(region)).getbbox() is None  # the site, on the left
    arabic = drawn.crop((int(left + site) + 2, 0, 1400, 120)).getbbox()
    assert arabic is not None  # and the Arabic words to its right


@pytest.mark.parametrize(("text", "script"), [("कि", "hi"), ("क्षत्रिय", "hi"), ("سلام", "ar")])
def test_shaping_reorders_and_joins_glyphs(text: str, script: str) -> None:
    shaped = Image.new("L", (300, 120))
    ImageDraw.Draw(shaped).text((10, 10), text, font=font(52, script), fill=255)
    basic = Image.new("L", (300, 120))
    plain = ImageFont.truetype(font(52, script).path, 52, layout_engine=ImageFont.Layout.BASIC)  # type: ignore[union-attr]
    ImageDraw.Draw(basic).text((10, 10), text, font=plain, fill=255)
    assert ImageChops.difference(shaped, basic).getbbox() is not None  # vowel signs move, letters join


def test_wrap_breaks_japanese_between_characters_and_keeps_a_line_that_fits() -> None:
    draw = ImageDraw.Draw(Image.new("L", (10, 10)))
    lines = wrap(draw, "夜の屋上で、リナは紙の凧を拾った。" * 3, 52, 600, language="ja-JP")
    assert len(lines) > 1
    assert all(textlength(line, 52, "ja-JP") <= 600 for line in lines)
    assert "".join(lines) == "夜の屋上で、リナは紙の凧を拾った。" * 3
    assert wrap(draw, "在 frameteller.com 讲述你的故事", 52, 1200, language="zh-CN") == [
        "在 frameteller.com 讲述你的故事"
    ]


def test_the_fonts_ship_with_their_licences() -> None:
    from frameteller.infrastructure.imaging.text import FONTS

    assert all((FONTS / name).is_file() for name in FILES.values())
    licences = sorted(p.name for p in FONTS.glob("OFL-*.txt"))
    assert licences == ["OFL-NotoSansArabic.txt", "OFL-NotoSansCJK.txt", "OFL-NotoSansDevanagari.txt"]
    assert all("SIL Open Font License" in (FONTS / n).read_text() for n in licences)
