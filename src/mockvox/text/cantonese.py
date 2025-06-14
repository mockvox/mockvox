# -*- coding: utf-8 -*-
import re
import ToJyutping

from mockvox.text.symbols import punctuation
from mockvox.text.zh_normalization import TextNormalizer

punctuation_set = set(punctuation)

INITIALS = [
    "aa",
    "aai",
    "aak",
    "aap",
    "aat",
    "aau",
    "ai",
    "au",
    "ap",
    "at",
    "ak",
    "a",
    "p",
    "b",
    "e",
    "ts",
    "t",
    "dz",
    "d",
    "kw",
    "k",
    "gw",
    "g",
    "f",
    "h",
    "l",
    "m",
    "ng",
    "n",
    "s",
    "y",
    "w",
    "c",
    "z",
    "j",
    "ong",
    "on",
    "ou",
    "oi",
    "ok",
    "o",
    "uk",
    "ung",
]
INITIALS += ["sp", "spl", "spn", "sil"]

rep_map = {
    "：": ",",
    "；": ",",
    "，": ",",
    "。": ".",
    "！": "!",
    "？": "?",
    "\n": ".",
    "·": ",",
    "、": ",",
    "...": "…",
    "$": ".",
    "“": "'",
    "”": "'",
    '"': "'",
    "‘": "'",
    "’": "'",
    "（": "'",
    "）": "'",
    "(": "'",
    ")": "'",
    "《": "'",
    "》": "'",
    "【": "'",
    "】": "'",
    "[": "'",
    "]": "'",
    "—": "-",
    "～": "-",
    "~": "-",
    "「": "'",
    "」": "'",
}

class CantoneseNormalizer:
    def __init__(self):
        self.tx = TextNormalizer()

    def g2p(self, text):
        jyuping = self._get_jyutping(text)
        phones, word2ph = self._jyuping_to_initials_finals_tones(jyuping)
        return phones, word2ph
    
    def do_normalize(self, text):
        sentences = self.tx.normalize(text)
        dest_text = ""
        for sentence in sentences:
            dest_text += self._replace_punctuation(sentence)
        return dest_text
    
    @staticmethod
    def _get_jyutping(text):
        punct_pattern = re.compile(r"^[{}]+$".format(re.escape("".join(punctuation))))
        syllables = ToJyutping.get_jyutping_list(text)

        jyutping_array = []
        for word, syllable in syllables:
            if punct_pattern.match(word):
                puncts = re.split(r"([{}])".format(re.escape("".join(punctuation))), word)
                for punct in puncts:
                    if len(punct) > 0:
                        jyutping_array.append(punct)
            else:
                # match multple jyutping eg: liu4 ge3, or single jyutping eg: liu4
                if not re.search(r"^([a-z]+[1-6]+[ ]?)+$", syllable):
                    raise ValueError(f"Failed to convert {word} to jyutping: {syllable}")
                jyutping_array.append(syllable)

        return jyutping_array

    @staticmethod   
    def _jyuping_to_initials_finals_tones(jyuping_syllables):
        initials_finals = []
        tones = []
        word2ph = []

        for syllable in jyuping_syllables:
            if syllable in punctuation:
                initials_finals.append(syllable)
                tones.append(0)
                word2ph.append(1)  # Add 1 for punctuation
            elif syllable == "_":
                initials_finals.append(syllable)
                tones.append(0)
                word2ph.append(1)  # Add 1 for underscore
            else:
                try:
                    tone = int(syllable[-1])
                    syllable_without_tone = syllable[:-1]
                except ValueError:
                    tone = 0
                    syllable_without_tone = syllable

                for initial in INITIALS:
                    if syllable_without_tone.startswith(initial):
                        if syllable_without_tone.startswith("nga"):
                            initials_finals.extend(
                                [
                                    syllable_without_tone[:2],
                                    syllable_without_tone[2:] or syllable_without_tone[-1],
                                ]
                            )
                            tones.extend([-1, tone])
                            word2ph.append(2)
                        else:
                            final = syllable_without_tone[len(initial) :] or initial[-1]
                            initials_finals.extend([initial, final])
                            tones.extend([-1, tone])
                            word2ph.append(2)
                        break
        assert len(initials_finals) == len(tones)

        ### 魔改为辅音+带音调的元音
        phones = []
        for a, b in zip(initials_finals, tones):
            if b not in [-1, 0]:  ###防止粤语和普通话重合开头加Y，如果是标点，不加。
                todo = "%s%s" % (a, b)
            else:
                todo = a
            if todo not in punctuation_set:
                todo = "Y%s" % todo
            phones.append(todo)

        # return initials_finals, tones, word2ph
        return phones, word2ph

    @staticmethod
    def _replace_punctuation(text):
        # text = text.replace("嗯", "恩").replace("呣", "母")
        pattern = re.compile("|".join(re.escape(p) for p in rep_map.keys()))
        replaced_text = pattern.sub(lambda x: rep_map[x.group()], text)
        replaced_text = re.sub(r"[^\u4e00-\u9fa5" + "".join(punctuation) + r"]+", "", replaced_text)

        return replaced_text
    
if __name__ == "__main__":
    normalizer = CantoneseNormalizer()
    text = "佢個鋤頭太短啦。"
    text = normalizer.do_normalize(text)
    phones, word2ph = normalizer.g2p(text)
    print(phones, word2ph)