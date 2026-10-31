"""Captions: short lines, each shown only while it is spoken."""

# ruff: noqa: RUF001  (full-width punctuation and curly quotes are the text under test)
from frameteller.domain import Animatic, AnimaticClip, Cue, MediaRef, caption_cues, caption_lines, to_srt


def test_lines_are_balanced_and_never_longer_than_ten_words() -> None:
    words = " ".join(f"w{i}" for i in range(23))
    lines = caption_lines(words)
    assert [len(line.split()) for line in lines] == [8, 8, 7]
    assert caption_lines("Short and sweet.") == ["Short and sweet."]
    assert caption_lines("   ") == []


def test_a_shot_shares_its_time_between_its_lines_by_word_count() -> None:
    clips = (
        AnimaticClip("s1", 1, MediaRef("a"), 0, 4000, caption=" ".join(["word"] * 12)),  # 6 + 6
        AnimaticClip("s2", 2, MediaRef("b"), 4000, 1000, caption=""),
        AnimaticClip("s3", 3, MediaRef("c"), 5000, 2000, caption="The end."),
    )
    cues = caption_cues(Animatic("p1", "t", clips), offset_ms=1000)
    assert [(c.start_ms, c.end_ms) for c in cues] == [(1000, 3000), (3000, 5000), (6000, 8000)]
    assert all(
        c.end_ms <= clip.start_ms + clip.duration_ms + 1000
        for c, clip in zip(cues, (clips[0], clips[0], clips[2]), strict=True)
    )


def test_translated_captions_replace_the_spoken_ones_in_clip_order() -> None:
    clips = (AnimaticClip("s1", 1, MediaRef("a"), 0, 2000, caption="Hello there."),)
    assert caption_cues(Animatic("p1", "t", clips), ["Bonjour."]) == [Cue(0, 2000, "Bonjour.")]


def test_srt() -> None:
    assert to_srt([Cue(1000, 2500, "One"), Cue(3_725_004, 3_726_000, "Two")]) == (
        "1\n00:00:01,000 --> 00:00:02,500\nOne\n\n2\n01:02:05,004 --> 01:02:06,000\nTwo\n"
    )


def test_chinese_japanese_and_korean_split_by_characters_about_fourteen_to_eighteen_a_line() -> None:
    ja = caption_lines("夜の屋上で、リナは「紙の凧」を拾った。そして空を見上げた。")
    assert ja == ["夜の屋上で、リナは「紙の凧」を", "拾った。そして空を見上げた。"]
    assert caption_lines("夜幕降临，丽娜接住了一只纸风筝。她笑了。") == ["夜幕降临，丽娜接住了", "一只纸风筝。她笑了。"]
    long = caption_lines("一二三四五六七八九十" * 4 + "。")
    assert [len(line) for line in long] == [14, 14, 13]
    assert not any(line[0] in "、。，」" for line in ja + long)  # a line never starts with a closing mark
    ko = caption_lines("밤이 오면 리나는 지붕 위에서 종이 연을 잡고 하늘을 올려다본다.")
    assert ko == ["밤이 오면 리나는 지붕 위에서", "종이 연을 잡고 하늘을 올려다본다."]  # whole words
    assert all(14 <= len(line) <= 18 for line in ja)
    assert all(sum(not ch.isspace() for ch in line) <= 18 for line in ko)


def test_a_japanese_shot_shares_its_time_by_characters() -> None:
    clips = (
        AnimaticClip("s1", 1, MediaRef("a"), 0, 3000, caption="一二三四五六七八九十" * 2 + "一二三四五六七八九十"),
    )
    cues = caption_cues(Animatic("p1", "t", clips))
    assert [(c.start_ms, c.end_ms, len(c.text)) for c in cues] == [(0, 1500, 15), (1500, 3000, 15)]
