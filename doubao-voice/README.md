# Doubao Voice (豆包语音) Plugin

Dify model plugin that adds **Doubao (Volcengine) voice** capabilities:

- **TTS (文字转语音)** — `Doubao-TTS`, via `/api/v3/tts/unidirectional`
- **ASR (语音转文字)** — `Doubao-ASR`, via the recording-file `/api/v3/auc/bigmodel` submit/query API

Once installed and set as the default TTS / speech-to-text model, it powers the
voice features in the Dify webapp (click-to-read and record-to-transcribe).

## Credentials

This plugin needs a single **API Key** (the V3 `X-Api-Key`).

1. Open the [Volcengine Doubao Voice console](https://console.volcengine.com/speech/app).
2. Enable **语音合成大模型 (TTS)** and **录音文件识别大模型 (ASR)**.
3. Copy the **API Key** and paste it into the plugin's credential field in Dify
   (模型供应商 → 豆包语音 → API Key).

## Voices

Public voices are declared in `models/tts/Doubao-TTS.yaml` (灿灿, 京腔侃爷,
湾湾小何, etc.). Add more by appending entries to the `voices` list using the
Volcengine `speaker` id as `mode`.

## Known limitations

- **Dialects**: Hunan / Yiyang (湘语) is not an officially supported dialect.
  Recognition accuracy depends on the Doubao model; treat it as best-effort.
- **ASR latency**: recording-file recognition polls for the result (seconds),
  it is not real-time streaming — matching the webapp "record then transcribe" flow.
- Custom (cloned) voices require separate console authorization and are not included.

## Install

```bash
dify-plugin plugin package ./doubao-voice
```

Upload the produced `.difypkg` in Dify (插件 → 安装 → 上传). If the instance
enforces signature verification, disable it for local packages or sign the package.
