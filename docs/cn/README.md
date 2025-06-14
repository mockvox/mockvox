<div align="center">

<h1>🎤 MockVox</h1>

✨ 强大的少样本语音合成与语音克隆后台 ✨<br><br>

[**🇬🇧 English**](../../README.md) | **🇨🇳 中文简体**

</div>

---

## 🚀 介绍

本项目旨在打造一个可以社区化运作的语音合成&语音克隆平台。  
本项目改造自 [GPT_SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)，提供和GPT_SoVITS相同流程的语音合成&语音克隆功能。  

🌟 **核心功能**：

1. **🎧 零样本文本到语音 (TTS)**: 输入 5 秒的声音样本，即刻体验文本到语音转换
2. **🌍 跨语言全流程支持**: 支持英语、日语、韩语、粤语和中文的训练和推理
3. **🧠 少样本 TTS**: 仅需 1 分钟的训练数据即可微调模型，提升声音相似度和真实感

🔧 **主要改造点**：

1. **🌐 多语言架构升级**：
    * 实现​​多语言训练​​
    * 为每种语言配置专用 BERT 特征提取器
    * 增强多语言推理稳定性
2. **🖥️ 命令行交互**：去掉Web端，改用更灵活的命令行方式 [《命令行用户指南》](./cli.md)
3. **🏭 分布式架构**：基于 Celery 的多进程异步任务调度，支持高并发训练/推理
4. **⚡ 训练优化**：弃用 Pytorch Lightning，采用原生 Torch 训练方式
5. **🔊 ASR 升级**：英语模型改用 NVIDIA Parakeet，日韩模型采用 ModelScope 最新方案
6. **📦 工程优化**：代码重构与性能提升

---

## 📥 安装

### 克隆本项目

```bash
git clone https://github.com/mockvox/mockvox.git
cd mockvox
```

---

## 🚀 运行

### 🖥️ 本地运行

#### 1. 创建虚拟环境

```bash
🐍 创建 Python 虚拟环境
conda create -n mockvox python=3.11 -y
conda activate mockvox

📦 安装依赖
pip install -e . 
```

#### 2. 复制.env文件

```bash
cp .env.sample .env
```

#### 3. 安装 FFmpeg

```bash
🎬 Ubuntu 安装脚本
sudo apt update && sudo apt install ffmpeg
ffmpeg -version  # 验证安装
```

#### 4. 下载预训练模型

```bash
🔧 GPT-SoVITS核心组件
git clone https://hf-mirror.com/lj1995/GPT-SoVITS.git ./pretrained/GPT-SoVITS

🗣️ 语音处理全家桶
modelscope download --model 'damo/speech_frcrn_ans_cirm_16k' --local_dir './pretrained/damo/speech_frcrn_ans_cirm_16k' #降噪
modelscope download --model 'iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch' --local_dir './pretrained/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch' #普通话ASR
modelscope download --model 'iic/speech_fsmn_vad_zh-cn-16k-common-pytorch' --local_dir './pretrained/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch'
modelscope download --model 'iic/punc_ct-transformer_cn-en-common-vocab471067-large' --local_dir './pretrained/iic/punc_ct-transformer_cn-en-common-vocab471067-large' #标点恢复
git clone https://hf-mirror.com/alextomcat/G2PWModel.git ./pretrained/G2PWModel #词转音素


🌐 多语言扩展包（可选）
# 如果仅使用中文素材训练，则无需安装
modelscope download --model 'iic/speech_UniASR_asr_2pass-cantonese-CHS-16k-common-vocab1468-tensorflow1-online' --local_dir './pretrained/iic/speech_UniASR_asr_2pass-cantonese-CHS-16k-common-vocab1468-tensorflow1-online' #粤语ASR
git clone https://hf-mirror.com/nvidia/parakeet-tdt-0.6b-v2.git ./pretrained/nvidia/parakeet-tdt-0.6b-v2 #英语ASR
git clone https://hf-mirror.com/FacebookAI/roberta-large.git ./pretrained/FacebookAI/roberta-large #英语BERT
modelscope download --model 'iic/speech_UniASR_asr_2pass-ja-16k-common-vocab93-tensorflow1-offline'  --local_dir './pretrained/iic/speech_UniASR_asr_2pass-ja-16k-common-vocab93-tensorflow1-offline' #日语ASR
git clone https://hf-mirror.com/tohoku-nlp/bert-large-japanese-v2.git ./pretrained/tohoku-nlp/bert-large-japanese-v2 #日语BERT
modelscope download --model 'iic/speech_UniASR_asr_2pass-ko-16k-common-vocab6400-tensorflow1-online' --local_dir './pretrained/iic/speech_UniASR_asr_2pass-ko-16k-common-vocab6400-tensorflow1-online' #韩语ASR
git clone https://hf-mirror.com/klue/roberta-large.git ./pretrained/klue/roberta-large #韩语BERT
```

至此，命令行方式已经可以使用。 [《命令行用户指南》](./cli.md)

#### 4. 启动服务

如果要以后台API方式运行，则需启动以下服务：

```bash
🐳 Redis 容器
chmod +x startup_redis.sh && ./startup_redis.sh
chmod +x check_redis.sh && ./check_redis.sh  # ✅ 状态检查

⚙️ Celery 工作节点
nohup celery -A src.mockvox.worker.worker worker --loglevel=info --pool=prefork --concurrency=1 &

🌐 Web 服务
nohup python src/mockvox/main.py &
```

API调用参见: [API用户指南](./api.md)

### 🐳 Docker 容器运行

#### 在 Docker 容器内使用 GPU (Python/PyTorch)​​

在 Docker 容器内运行的 Python/PyTorch 应用中使用 NVIDIA GPU，宿主主机​​必须​​已正确安装 ​​NVIDIA Container Toolkit​​。

此工具包负责提供必要的驱动程序和运行时环境，使容器能够访问宿主机的 GPU 资源。有关详细的安装指南和系统要求，请参阅 ​[​NVIDIA Container Toolkit​官方文档](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

```bash
docker-compose up -d # 🚢 一键启动全栈服务
```

**说明**: 默认安装的docker镜像为full包，如果要单独安装中/英/日/韩/粤，请修改 `docker-compose.yml` 文件中的 MODEL_TYPE 变量。

---

## 🔍 扩展说明

- 📁 所有模型文件默认存储在 `./pretrained` 目录
- ⚠️ 首次运行需下载约 15GB 的模型文件
- 🔄 可通过修改 `.env` 文件调整服务配置
- 📚 完整命令行、API指南请参阅 [命令行用户指南](./cli.md) 或 [API用户指南](./api.md)

---

<div align="center">
  <sub>Built with ❤️ by MockVox Team | 📧 Contact: dev@mockvox.cn</sub>
</div>