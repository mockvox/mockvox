# -*- coding: utf-8 -*-
import os
import pickle
import re
import wordsegment
from g2p_en import G2p
from builtins import str as unicode
import nltk

from mockvox.text.en_normalization import normalize
from mockvox.text import symbols, punctuation
from mockvox.utils import MockVoxLogger

current_file_path = os.path.dirname(__file__)
CMU_DICT_PATH = os.path.join(current_file_path, "cmudict.rep")
CMU_DICT_FAST_PATH = os.path.join(current_file_path, "cmudict-fast.rep")
CMU_DICT_HOT_PATH = os.path.join(current_file_path, "engdict-hot.rep")
CACHE_PATH = os.path.join(current_file_path, "engdict_cache.pickle")
NAMECACHE_PATH = os.path.join(current_file_path, "namedict_cache.pickle")

# 适配中文及 g2p_en 标点
rep_map = {
    "[;:：，；]": ",",
    '["’]': "'",
    "。": ".",
    "！": "!",
    "？": "?",
}

class EnglishNormalizer:
    def __init__(self):
        self._g2p = en_G2p()

    def do_normalize(self, text):
        pattern = re.compile("|".join(re.escape(p) for p in rep_map.keys()))
        text = pattern.sub(lambda x: rep_map[x.group()], text)

        text = unicode(text)
        text = normalize(text)

        # 避免重复标点引起的参考泄露
        text = self._replace_consecutive_punctuation(text)
        return text

    def g2p(self, text):
        phone_list, word2ph = self._g2p(text)
        phones = [ph if ph != "<unk>" else "UNK" for ph in phone_list if ph not in [" ", "<pad>", "UW", "</s>", "<s>"]]

        return self._replace_phs(phones), word2ph

    @staticmethod
    def _replace_phs(phs):
        rep_map = {"'": "-"}
        phs_new = []
        for ph in phs:
            if ph in symbols:
                phs_new.append(ph)
            elif ph in rep_map.keys():
                phs_new.append(rep_map[ph])
            else:
                MockVoxLogger.warn(f"ph '{ph}' not in symbols: ")
        return phs_new

    @staticmethod
    def _replace_consecutive_punctuation(text):
        punctuations = "".join(re.escape(p) for p in punctuation)
        pattern = f"([{punctuations}\s])([{punctuations}])+"
        result = re.sub(pattern, r"\1", text)
        return result

class en_G2p(G2p):
    def __init__(self):
        super().__init__()
        self._check_nltk_resources()
        # 分词初始化
        wordsegment.load()

        # 扩展过时字典, 添加姓名字典
        self.cmu = self._get_dict()
        self.namedict = self._get_namedict()

        # 剔除读音错误的几个缩写
        for word in ["AE", "AI", "AR", "IOS", "HUD", "OS"]:
            del self.cmu[word.lower()]

        # 修正多音字
        self.homograph2features["read"] = (["R", "IY1", "D"], ["R", "EH1", "D"], "VBP")
        self.homograph2features["complex"] = (
            ["K", "AH0", "M", "P", "L", "EH1", "K", "S"],
            ["K", "AA1", "M", "P", "L", "EH0", "K", "S"],
            "JJ",
        )

    def _check_nltk_resources(self):
        pass
        try:
            nltk.data.find("taggers/averaged_perceptron_tagger")
            nltk.data.find("taggers/averaged_perceptron_tagger_eng")
            nltk.data.find("tokenizers/punkt_tab")
            nltk.data.find("corpora/cmudict")

        except LookupError:
            nltk.download('averaged_perceptron_tagger')
            nltk.download('averaged_perceptron_tagger_eng')
            nltk.download('punkt_tab')
            nltk.download('cmudict')

    def __call__(self, text):
        # tokenization
        words = nltk.word_tokenize(text)
        tokens = nltk.pos_tag(words) #, tagger=self.model)  # tuples of (word, tag)

        # steps
        prons = []
        word2ph = []
        for o_word, pos in tokens:
            # 还原 g2p_en 小写操作逻辑
            word = o_word.lower()

            if re.search("[a-z]", word) is None:
                pron = [word]
            # 先把单字母推出去
            elif len(word) == 1:
                # 单读 A 发音修正, 这里需要原格式 o_word 判断大写
                if o_word == "A":
                    pron = ["EY1"]
                else:
                    pron = self.cmu[word][0]
            # g2p_en 原版多音字处理
            elif word in self.homograph2features:  # Check homograph
                pron1, pron2, pos1 = self.homograph2features[word]
                if pos.startswith(pos1):
                    pron = pron1
                # pos1比pos长仅出现在read
                elif len(pos) < len(pos1) and pos == pos1[: len(pos)]:
                    pron = pron1
                else:
                    pron = pron2
            else:
                # 递归查找预测
                pron = self._qryword(o_word)

            word2ph += [len(pron)]
            prons.extend(pron)
            prons.extend([" "])

        return prons[:-1], word2ph

    def _qryword(self, o_word):
        word = o_word.lower()

        # 查字典, 单字母除外
        if len(word) > 1 and word in self.cmu:  # lookup CMU dict
            return self.cmu[word][0]

        # 单词仅首字母大写时查找姓名字典
        if o_word.istitle() and word in self.namedict:
            return self.namedict[word][0]

        # oov 长度小于等于 3 直接读字母
        if len(word) <= 3:
            phones = []
            for w in word:
                # 单读 A 发音修正, 此处不存在大写的情况
                if w == "a":
                    phones.extend(["EY1"])
                elif not w.isalpha():
                    phones.extend([w])
                else:
                    phones.extend(self.cmu[w][0])
            return phones

        # 尝试分离所有格
        if re.match(r"^([a-z]+)('s)$", word):
            phones = self._qryword(word[:-2])[:]
            # P T K F TH HH 无声辅音结尾 's 发 ['S']
            if phones[-1] in ["P", "T", "K", "F", "TH", "HH"]:
                phones.extend(["S"])
            # S Z SH ZH CH JH 擦声结尾 's 发 ['IH1', 'Z'] 或 ['AH0', 'Z']
            elif phones[-1] in ["S", "Z", "SH", "ZH", "CH", "JH"]:
                phones.extend(["AH0", "Z"])
            # B D G DH V M N NG L R W Y 有声辅音结尾 's 发 ['Z']
            # AH0 AH1 AH2 EY0 EY1 EY2 AE0 AE1 AE2 EH0 EH1 EH2 OW0 OW1 OW2 UH0 UH1 UH2 IY0 IY1 IY2 AA0 AA1 AA2 AO0 AO1 AO2
            # ER ER0 ER1 ER2 UW0 UW1 UW2 AY0 AY1 AY2 AW0 AW1 AW2 OY0 OY1 OY2 IH IH0 IH1 IH2 元音结尾 's 发 ['Z']
            else:
                phones.extend(["Z"])
            return phones

        # 尝试进行分词，应对复合词
        comps = wordsegment.segment(word.lower())

        # 无法分词的送回去预测
        if len(comps) == 1:
            return self.predict(word)

        # 可以分词的递归处理
        return [phone for comp in comps for phone in self._qryword(comp)]

    def _get_dict(self):
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "rb") as pickle_file:
                g2p_dict = pickle.load(pickle_file)
        else:
            g2p_dict = self._read_dict()
            self._cache_dict(g2p_dict, CACHE_PATH)

        g2p_dict = self._hot_reload_hot(g2p_dict)

        return g2p_dict

    @staticmethod
    def _get_namedict():
        if os.path.exists(NAMECACHE_PATH):
            with open(NAMECACHE_PATH, "rb") as pickle_file:
                name_dict = pickle.load(pickle_file)
        else:
            name_dict = {}

        return name_dict

    @staticmethod
    def _read_dict():
        g2p_dict = {}
        with open(CMU_DICT_PATH) as f:
            line = f.readline()
            line_index = 1
            while line:
                if line_index >= 57:
                    line = line.strip()
                    word_split = line.split("  ")
                    word = word_split[0].lower()
                    g2p_dict[word] = [word_split[1].split(" ")]

                line_index = line_index + 1
                line = f.readline()

        with open(CMU_DICT_FAST_PATH) as f:
            line = f.readline()
            line_index = 1
            while line:
                if line_index >= 0:
                    line = line.strip()
                    word_split = line.split(" ")
                    word = word_split[0].lower()
                    if word not in g2p_dict:
                        g2p_dict[word] = [word_split[1:]]

                line_index = line_index + 1
                line = f.readline()

        return g2p_dict

    @staticmethod
    def _cache_dict(g2p_dict, file_path):
        with open(file_path, "wb") as pickle_file:
            pickle.dump(g2p_dict, pickle_file)

    @staticmethod
    def _hot_reload_hot(g2p_dict):
        with open(CMU_DICT_HOT_PATH) as f:
            line = f.readline()
            line_index = 1
            while line:
                if line_index >= 0:
                    line = line.strip()
                    word_split = line.split(" ")
                    word = word_split[0].lower()
                    # 自定义发音词直接覆盖字典
                    g2p_dict[word] = [word_split[1:]]

                line_index = line_index + 1
                line = f.readline()

        return g2p_dict

if __name__ == '__main__':
    normalizer = EnglishNormalizer()
    text = "e.g. I used openai's AI tool to draw a picture."
    text = normalizer.do_normalize(text)
    phones, word2ph = normalizer.g2p(text)
    print(f"phones: {phones}")
    print(f"word2ph: {word2ph}")    