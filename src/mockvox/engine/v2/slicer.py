import os
import numpy as np
import time
from pathlib import Path
from typing import List
from scipy.io import wavfile

from mockvox.config import get_config
from mockvox.utils import load_audio, MockVoxLogger

cfg = get_config()

# This function is obtained from librosa.
def get_rms(
    y,
    frame_length=2048,
    hop_length=512,
    pad_mode="constant",
):
    padding = (int(frame_length // 2), int(frame_length // 2))
    y = np.pad(y, padding, mode=pad_mode)

    axis = -1
    # put our new within-frame axis at the end for now
    out_strides = y.strides + tuple([y.strides[axis]])
    # Reduce the shape on the framing axis
    x_shape_trimmed = list(y.shape)
    x_shape_trimmed[axis] -= frame_length - 1
    out_shape = tuple(x_shape_trimmed) + tuple([frame_length])
    xw = np.lib.stride_tricks.as_strided(y, shape=out_shape, strides=out_strides)
    if axis < 0:
        target_axis = axis - 1
    else:
        target_axis = axis + 1
    xw = np.moveaxis(xw, -1, target_axis)
    # Downsample along the target axis
    slices = [slice(None)] * xw.ndim
    slices[axis] = slice(0, None, hop_length)
    x = xw[tuple(slices)]

    # Calculate power
    power = np.mean(np.abs(x) ** 2, axis=-2, keepdims=True)

    return np.sqrt(power)

class Slicer:
    def __init__(
        self,
        sr: int,
        threshold: float = -40.0,
        min_length: int = 5000,
        min_interval: int = 300,
        hop_size: int = 20,
        max_sil_kept: int = 5000,
    ):
        if not min_length >= min_interval >= hop_size:
            raise ValueError(
                "The following condition must be satisfied: min_length >= min_interval >= hop_size"
            )
        if not max_sil_kept >= hop_size:
            raise ValueError(
                "The following condition must be satisfied: max_sil_kept >= hop_size"
            )
        min_interval = sr * min_interval / 1000
        self.threshold = 10 ** (threshold / 20.0)
        self.hop_size = round(sr * hop_size / 1000)
        self.win_size = min(round(min_interval), 4 * self.hop_size)
        self.min_length = round(sr * min_length / 1000 / self.hop_size)
        self.min_interval = round(min_interval / self.hop_size)
        self.max_sil_kept = round(sr * max_sil_kept / 1000 / self.hop_size)

    def _apply_slice(self, waveform, begin, end):
        if len(waveform.shape) > 1:
            return waveform[
                :, begin * self.hop_size : min(waveform.shape[1], end * self.hop_size)
            ]
        else:
            return waveform[
                begin * self.hop_size : min(waveform.shape[0], end * self.hop_size)
            ]

    # @timeit
    def slice(self, waveform):
        if len(waveform.shape) > 1:
            samples = waveform.mean(axis=0)
        else:
            samples = waveform
        if samples.shape[0] <= self.min_length:
            return [waveform]
        rms_list = get_rms(
            y=samples, frame_length=self.win_size, hop_length=self.hop_size
        ).squeeze(0)
        sil_tags = []
        silence_start = None
        clip_start = 0
        for i, rms in enumerate(rms_list):
            # Keep looping while frame is silent.
            if rms < self.threshold:
                # Record start of silent frames.
                if silence_start is None:
                    silence_start = i
                continue
            # Keep looping while frame is not silent and silence start has not been recorded.
            if silence_start is None:
                continue
            # Clear recorded silence start if interval is not enough or clip is too short
            is_leading_silence = silence_start == 0 and i > self.max_sil_kept
            need_slice_middle = (
                i - silence_start >= self.min_interval
                and i - clip_start >= self.min_length
            )
            if not is_leading_silence and not need_slice_middle:
                silence_start = None
                continue
            # Need slicing. Record the range of silent frames to be removed.
            if i - silence_start <= self.max_sil_kept:
                pos = rms_list[silence_start : i + 1].argmin() + silence_start
                if silence_start == 0:
                    sil_tags.append((0, pos))
                else:
                    sil_tags.append((pos, pos))
                clip_start = pos
            elif i - silence_start <= self.max_sil_kept * 2:
                pos = rms_list[
                    i - self.max_sil_kept : silence_start + self.max_sil_kept + 1
                ].argmin()
                pos += i - self.max_sil_kept
                pos_l = (
                    rms_list[
                        silence_start : silence_start + self.max_sil_kept + 1
                    ].argmin()
                    + silence_start
                )
                pos_r = (
                    rms_list[i - self.max_sil_kept : i + 1].argmin()
                    + i
                    - self.max_sil_kept
                )
                if silence_start == 0:
                    sil_tags.append((0, pos_r))
                    clip_start = pos_r
                else:
                    sil_tags.append((min(pos_l, pos), max(pos_r, pos)))
                    clip_start = max(pos_r, pos)
            else:
                pos_l = (
                    rms_list[
                        silence_start : silence_start + self.max_sil_kept + 1
                    ].argmin()
                    + silence_start
                )
                pos_r = (
                    rms_list[i - self.max_sil_kept : i + 1].argmin()
                    + i
                    - self.max_sil_kept
                )
                if silence_start == 0:
                    sil_tags.append((0, pos_r))
                else:
                    sil_tags.append((pos_l, pos_r))
                clip_start = pos_r
            silence_start = None
        # Deal with trailing silence.
        total_frames = rms_list.shape[0]
        if (
            silence_start is not None
            and total_frames - silence_start >= self.min_interval
        ):
            silence_end = min(total_frames, silence_start + self.max_sil_kept)
            pos = rms_list[silence_start : silence_end + 1].argmin() + silence_start
            sil_tags.append((pos, total_frames + 1))
        # Apply and return slices.
        ####音频+起始时间+终止时间
        if len(sil_tags) == 0:
            return [[waveform,0,int(total_frames*self.hop_size)]]
        else:
            chunks = []
            if sil_tags[0][0] > 0:
                chunks.append([self._apply_slice(waveform, 0, sil_tags[0][0]),0,int(sil_tags[0][0]*self.hop_size)])
            for i in range(len(sil_tags) - 1):
                chunks.append(
                    [self._apply_slice(waveform, sil_tags[i][1], sil_tags[i + 1][0]),int(sil_tags[i][1]*self.hop_size),int(sil_tags[i + 1][0]*self.hop_size)]
                )
            if sil_tags[-1][1] < total_frames:
                chunks.append(
                    [self._apply_slice(waveform, sil_tags[-1][1], total_frames),int(sil_tags[-1][1]*self.hop_size),int(total_frames*self.hop_size)]
                )
            return chunks


def slice_audio(input_path: str, output_dir: str) -> List[str]:
    """音频文件切割函数
    
    Args:
        input_path: 输入音频文件路径
        output_dir: 切片输出目录
        
    Returns:
        切片输出文件名(数组)
        
    Raises:
        FileNotFoundError: 文件不存在
        RuntimeError: 切割处理失败
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    
    try:
        slicer = Slicer(
            sr=32000,                               # 长音频采样率
            threshold=      int(cfg.THRESHOLD),     # 音量小于这个值视作静音的备选切割点
            min_length=     int(cfg.MIN_LENGTH),    # 每段最小多长，如果第一段太短一直和后面段连起来直到超过这个值
            min_interval=   int(cfg.MIN_INTERVAL),  # 最短切割间隔
            hop_size=       int(cfg.HOP_SIZE),      # 怎么算音量曲线，越小精度越大计算量越高（不是精度越大效果越好）
            max_sil_kept=   int(cfg.MAX_SIL_KEPT),  # 切完后静音最多留多长
        )

        audio = load_audio(input_path, 32000)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = str(int(time.time()))
        sliced_files = []
        for chunk, start, end in slicer.slice(audio):
            # 音量归一化处理
            tmp_max = np.abs(chunk).max()
            if(tmp_max>1):chunk/=tmp_max
            chunk = (chunk / tmp_max * (cfg.MAX_NORMALIZED * cfg.ALPHA_MIX)) + (1 - cfg.ALPHA_MIX) * chunk

            if chunk.size == 0:
                MockVoxLogger.warning("Skip empty slice")
                continue

            sliced_file = os.path.join(
                output_dir,
                f"{timestamp}_{start:010d}_{end:010d}.wav"  
            )
            sliced_files.append(sliced_file)
            
            wavfile.write(
                sliced_file,
                32000,
                (chunk * 32767).astype(np.int16)
            )

        del slicer, audio
        return sliced_files

    except Exception as e:
        MockVoxLogger.error(
            f"Slice failed: {input_path} \nException: {str(e)}",
            extra={"action": "slice_error"}
        )
        raise RuntimeError(f"Slice failed: {str(e)}") from e