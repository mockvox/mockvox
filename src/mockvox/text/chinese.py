import os
import re
from pypinyin import lazy_pinyin, Style
from pypinyin.contrib.tone_convert import to_initials, to_finals_tone3
from mockvox.text.g2pw import correct_pronunciation
from mockvox.config import PRETRAINED_PATH
from mockvox.text.tone_sandhi import ToneSandhi
from mockvox.text.symbols import punctuation
from mockvox.text.zh_normalization import TextNormalizer
from mockvox.text.g2pw import G2PWPinyin
import jieba_fast.posseg as psg

pinyin_to_symbol_map = {
    line.split("\t")[0]: line.strip().split("\t")[1]
    for line in open(os.path.join(os.path.dirname(__file__), "opencpop-strict.txt")).readlines()
}

g2pw_model_path = os.path.join(PRETRAINED_PATH, 'G2PWModel')
bert_model_path = os.path.join(PRETRAINED_PATH, 'GPT-SoVITS/chinese-roberta-wwm-ext-large')
g2pw = G2PWPinyin(
    model_dir=g2pw_model_path,
    model_source=bert_model_path,
    v_to_u=False,
    neutral_tone_with_five=True)

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
    "/": ",",
    "—": "-",
    "~": "…",
    "～":"…",
}

tone_modifier = ToneSandhi()

def _get_initials_finals(word):
    initials = []
    finals = []

    orig_initials = lazy_pinyin(word, neutral_tone_with_five=True, style=Style.INITIALS)
    orig_finals = lazy_pinyin(
        word, neutral_tone_with_five=True, style=Style.FINALS_TONE3
    )

    for c, v in zip(orig_initials, orig_finals):
        initials.append(c)
        finals.append(v)
    return initials, finals

must_erhua = {
    "小院儿", "胡同儿", "范儿", "老汉儿", "撒欢儿", "寻老礼儿", "妥妥儿", "媳妇儿"
}
not_erhua = {
    "虐儿", "为儿", "护儿", "瞒儿", "救儿", "替儿", "有儿", "一儿", "我儿", "俺儿", "妻儿",
    "拐儿", "聋儿", "乞儿", "患儿", "幼儿", "孤儿", "婴儿", "婴幼儿", "连体儿", "脑瘫儿",
    "流浪儿", "体弱儿", "混血儿", "蜜雪儿", "舫儿", "祖儿", "美儿", "应采儿", "可儿", "侄儿",
    "孙儿", "侄孙儿", "女儿", "男儿", "红孩儿", "花儿", "虫儿", "马儿", "鸟儿", "猪儿", "猫儿",
    "狗儿", "少儿"
}
def _merge_erhua(initials: list[str],
                finals: list[str],
                word: str,
                pos: str) -> list[list[str]]:
    """
    Do erhub.
    """
    # fix er1
    for i, phn in enumerate(finals):
        if i == len(finals) - 1 and word[i] == "儿" and phn == 'er1':
            finals[i] = 'er2'

    # 发音
    if word not in must_erhua and (word in not_erhua or
                                        pos in {"a", "j", "nr"}):
        return initials, finals

    # "……" 等情况直接返回
    if len(finals) != len(word):
        return initials, finals

    assert len(finals) == len(word)

    # 与前一个字发同音
    new_initials = []
    new_finals = []
    for i, phn in enumerate(finals):
        if i == len(finals) - 1 and word[i] == "儿" and phn in {
                "er2", "er5"
        } and word[-2:] not in not_erhua and new_finals:
            phn = "er" + new_finals[-1][-1]

        new_initials.append(initials[i])
        new_finals.append(phn)

    return new_initials, new_finals

class ChineseNormalizer:
    def __init__(self, mixed=False):
        self.tx = TextNormalizer()
        self.mixed = mixed

    def g2p(self, text):
        pattern = r"(?<=[{0}])\s*".format("".join(punctuation))
        sentences = [i for i in re.split(pattern, text) if i.strip() != ""]
        phones, word2ph = self._g2p(sentences)
        return phones, word2ph

    def _g2p(self, segments):
        phones_list = []
        word2ph = []
        for seg in segments:
            pinyins = []
            # Replace all English words in the sentence
            seg = re.sub("[a-zA-Z]+", "", seg)
            seg_cut = psg.lcut(seg)
            seg_cut = tone_modifier.pre_merge_for_modify(seg_cut)
            initials = []
            finals = []

            # g2pw采用整句推理
            pinyins = g2pw.lazy_pinyin(seg, neutral_tone_with_five=True, style=Style.TONE3)

            pre_word_length = 0
            for word, pos in seg_cut:
                sub_initials = []
                sub_finals = []
                now_word_length = pre_word_length + len(word)

                if pos == 'eng':
                    pre_word_length = now_word_length
                    continue

                word_pinyins = pinyins[pre_word_length:now_word_length]

                # 多音字消歧
                word_pinyins = correct_pronunciation(word,word_pinyins)

                for pinyin in word_pinyins:
                    if pinyin[0].isalpha():
                        sub_initials.append(to_initials(pinyin))
                        sub_finals.append(to_finals_tone3(pinyin,neutral_tone_with_five=True))
                    else:
                        sub_initials.append(pinyin)
                        sub_finals.append(pinyin)

                pre_word_length = now_word_length
                sub_finals = tone_modifier.modified_tone(word, pos, sub_finals)
                # 儿化
                sub_initials, sub_finals = _merge_erhua(sub_initials, sub_finals, word, pos)
                initials.append(sub_initials)
                finals.append(sub_finals)

            initials = sum(initials, [])
            finals = sum(finals, [])

            for c, v in zip(initials, finals):
                raw_pinyin = c + v
                # NOTE: post process for pypinyin outputs
                # we discriminate i, ii and iii
                if c == v:
                    assert c in punctuation
                    phone = [c]
                    word2ph.append(1)
                else:
                    v_without_tone = v[:-1]
                    tone = v[-1]

                    pinyin = c + v_without_tone
                    assert tone in "12345"

                    if c:
                        # 多音节
                        v_rep_map = {
                            "uei": "ui",
                            "iou": "iu",
                            "uen": "un",
                        }
                        if v_without_tone in v_rep_map.keys():
                            pinyin = c + v_rep_map[v_without_tone]
                    else:
                        # 单音节
                        pinyin_rep_map = {
                            "ing": "ying",
                            "i": "yi",
                            "in": "yin",
                            "u": "wu",
                        }
                        if pinyin in pinyin_rep_map.keys():
                            pinyin = pinyin_rep_map[pinyin]
                        else:
                            single_rep_map = {
                                "v": "yu",
                                "e": "e",
                                "i": "y",
                                "u": "w",
                            }
                            if pinyin[0] in single_rep_map.keys():
                                pinyin = single_rep_map[pinyin[0]] + pinyin[1:]

                    assert pinyin in pinyin_to_symbol_map.keys(), (pinyin, seg, raw_pinyin)
                    new_c, new_v = pinyin_to_symbol_map[pinyin].split(" ")
                    new_v = new_v + tone
                    phone = [new_c, new_v]
                    word2ph.append(len(phone))

                phones_list += phone
        return phones_list, word2ph

    @staticmethod
    def replace_punctuation(text):
        text = text.replace("嗯", "恩").replace("呣", "母")
        pattern = re.compile("|".join(re.escape(p) for p in rep_map.keys()))

        replaced_text = pattern.sub(lambda x: rep_map[x.group()], text)

        replaced_text = re.sub(
            r"[^\u4e00-\u9fa5" + "".join(punctuation) + r"]+", "", replaced_text
        )

        return replaced_text

    @staticmethod
    def replace_punctuation_with_en(text):
        text = text.replace("嗯", "恩").replace("呣", "母")
        pattern = re.compile("|".join(re.escape(p) for p in rep_map.keys()))

        replaced_text = pattern.sub(lambda x: rep_map[x.group()], text)

        replaced_text = re.sub(
            r"[^\u4e00-\u9fa5A-Za-z" + "".join(punctuation) + r"]+", "", replaced_text
        )

        return replaced_text

    @staticmethod
    def replace_consecutive_punctuation(text):
        punctuations = ''.join(re.escape(p) for p in punctuation)
        pattern = f'([{punctuations}])([{punctuations}])+'
        result = re.sub(pattern, r'\1', text)
        return result
        
    def do_normalize(self, text) -> str:
        sentences = self.tx.normalize(text)
        dest_text = ""
        for sentence in sentences:
            if self.mixed:
                dest_text += self.replace_punctuation_with_en(sentence)
            else:
                dest_text += self.replace_punctuation(sentence)

        # 避免重复标点引起的参考泄露
        dest_text = self.replace_consecutive_punctuation(dest_text)
        return dest_text