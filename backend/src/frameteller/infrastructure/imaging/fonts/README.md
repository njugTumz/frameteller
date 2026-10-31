# Fonts for burned-in captions, title and end cards

Noto fonts, licensed under the SIL Open Font License 1.1 (the `OFL-*.txt` files here). Pillow's bundled
font draws Latin text; these draw everything else. They are used unmodified.

| File | Version | Script | Source |
|---|---|---|---|
| `NotoSansJP-Regular.otf` | 2.004 | Japanese | [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk) `Sans/SubsetOTF/JP` |
| `NotoSansKR-Regular.otf` | 2.004 | Korean | [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk) `Sans/SubsetOTF/KR` |
| `NotoSansSC-Regular.otf` | 2.004 | Simplified Chinese | [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk) `Sans/SubsetOTF/SC` |
| `NotoSansDevanagari-Regular.ttf` | 2.007 | Hindi | [notofonts/devanagari](https://github.com/notofonts/devanagari) (hinted TTF from notofonts.github.io) |
| `NotoSansArabic-Regular.ttf` | 2.013 | Arabic | [notofonts/arabic](https://github.com/notofonts/arabic) (hinted TTF from notofonts.github.io) |

`OFL-NotoSansCJK.txt` covers the three CJK subsets, `OFL-NotoSansDevanagari.txt` and `OFL-NotoSansArabic.txt`
the other two. Shaping (Devanagari conjuncts, Arabic joining) and right-to-left order come from Pillow's raqm
layout, which uses HarfBuzz and FriBidi; both are in the backend image.
