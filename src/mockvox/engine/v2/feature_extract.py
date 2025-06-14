# -*- coding: utf-8 -*-
"""音频特征提取模块, 基于CNHubert模型实现语音特征提取"""

from typing import Optional
from pathlib import Path
import torch
import torchaudio
import numpy as np
from scipy.io import wavfile

from mockvox.config import ASR_PATH, PROCESS_PATH, DENOISED_ROOT_PATH, SLICED_ROOT_PATH
from mockvox.utils import MockVoxLogger, load_audio
from mockvox.models import CNHubert
from .asr import load_asr_data

class FeatureExtractor:
    """音频特征提取器, 负责处理音频文件并提取Hubert特征"""
    
    def __init__(self,
                 maxx: float = 0.95,  # 音频归一化最大系数
                 alpha: float = 0.5,  # 新旧音频增益混合比例
                 device: Optional[str] = None  # 指定计算设备
        ):
        # 初始化重采样器（32kHz -> 16kHz）
        self.resampler = torchaudio.transforms.Resample(
            orig_freq=32000,
            new_freq=16000,
            resampling_method='sinc_interpolation',
            lowpass_filter_width=16,
            rolloff=0.85,
            beta=5.0  # Kaiser窗口参数
        )
        
        # 音频处理参数
        self.maxx = maxx
        self.alpha = alpha
        # self.nan_fails = []  # 记录处理失败的文件

        # 加载预训练模型
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")        
        self.model = CNHubert().to(self.device)
   
    def extract(self, file_id: str, model_id: str, denoised: bool = True):
        """
        主处理流程
        :param file_id: 文件标识符
        :param model_id: 模型标识符
        :param denoised: 是否使用降噪后的音频
        """
        # 构建目录路径
        asr_dir = Path(ASR_PATH) / file_id
        wav_root = DENOISED_ROOT_PATH if denoised else SLICED_ROOT_PATH
        wav_dir = Path(wav_root) / file_id

        # 创建输出目录
        processed_dir = Path(PROCESS_PATH) / model_id
        hubert_dir = processed_dir / "cnhubert"
        wav32_dir = processed_dir / "wav32k"
        # 已处理
        if hubert_dir.exists(): 
            MockVoxLogger.info(
                "Feature extract has been done",
                extra={
                    "action": "feature_extracted",
                    "file_id": file_id
                }
            )
            return 

        hubert_dir.mkdir(parents=True, exist_ok=True)
        wav32_dir.mkdir(parents=True, exist_ok=True)

        # 处理ASR结果
        asr_data = load_asr_data(asr_dir)
        lines = asr_data["results"]
        for line in lines:
            wav_file = wav_dir / f"{line['key']}.wav"
            if not wav_file.exists():
                MockVoxLogger.warning(f"Audio file not found: {wav_file}")
                continue
                
            # 执行特征提取
            self._process_audio(
                wav_file_path=str(wav_file),
                wav32k_dir=str(wav32_dir),
                cnhubert_dir=str(hubert_dir)
            )

        MockVoxLogger.info(
            "Feature extract done",
            extra={
                "action": "feature_extracted",
                "file_id": file_id
            }
        )

    def _process_audio(self, wav_file_path, wav32k_dir, cnhubert_dir):
        """
        核心音频处理流程
        :param wav_file_path: 输入音频路径
        :param wav32k_dir: 32kHz音频输出目录
        :param cnhubert_dir: 特征文件输出目录
        """
        try:
            tmp_audio = load_audio(wav_file_path, 32000)  
            if tmp_audio is None:
                MockVoxLogger.error(f"Audio load failed: {wav_file_path}")
                return

            # 音频幅值校验
            tmp_max = np.abs(tmp_audio).max()
            if tmp_max > 2.2:
                MockVoxLogger.info(f"Audio amplitude verification: {wav_file_path} \n\
                               (Peak Value: {tmp_max:.2f})")
                return

            # 音频增益混合处理
            tmp_audio32 = (tmp_audio / tmp_max * (self.maxx * self.alpha*32768)) \
                + ((1 - self.alpha)*32768) * tmp_audio
            tmp_audio32b = (tmp_audio / tmp_max * (self.maxx * self.alpha*1145.14)) \
                + ((1 - self.alpha)*1145.14) * tmp_audio
            
            # 生成16kHz重采样音频
            audio_tensor = torch.from_numpy(tmp_audio32b).reshape(1, -1)
            tensor_wav16 = self.resampler(audio_tensor).to(self.device)  

            # 特征提取
            with torch.no_grad():
                hidden_states = self.model.model(tensor_wav16)["last_hidden_state"]
                ssl = hidden_states.transpose(1, 2).cpu()

            # 特征校验
            if torch.isnan(ssl).any():
                MockVoxLogger.info(f"NaN feature filtering: {wav_file_path}")
                return

            # 保存32kHz格式音频
            wav_path = Path(wav32k_dir) / Path(wav_file_path).name
            wavfile.write(
                str(wav_path),
                32000,
                tmp_audio32.astype("int16"),
            )

            # 保存特征文件
            feature_path = Path(cnhubert_dir) / f"{Path(wav_file_path).stem}.pt"
            torch.save(ssl, str(feature_path))
            MockVoxLogger.info(f"Feature extract done: \n\
                           Wav32: {wav_file_path} \n\
                           Feature: {feature_path}")
            
        except Exception as e:
            MockVoxLogger.error(f"Feature extract failed: {wav_file_path} \n\
                            Exception: {str(e)}")

if __name__ == '__main__':
    # 示例用法
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=str, help='processed file id.')
    parser.add_argument('model', type=str, help='model id.')
    args = parser.parse_args()

    extractor = FeatureExtractor()
    extractor.extract(args.file, args.model, denoised=True)