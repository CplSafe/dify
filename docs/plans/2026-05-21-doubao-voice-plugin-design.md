# 豆包语音插件设计文档（TTS + ASR）

- **日期**：2026-05-21
- **目标**：在 Dify 的 webapp 语音配置中提供豆包（火山引擎）语音能力——用户语音转文字（ASR / speech2text）、文字转语音（TTS）。
- **结论**：以**独立模型插件**形式交付，**零改动 Dify 主仓库**。

---

## 1. 背景与约束

### 现状探查结论
- Dify 已迁移到**插件化模型供应商架构**：核心代码不再内置任何供应商，全部由外部插件经 plugin daemon 动态加载。
- webapp 的语音下拉（`/apps/{id}/text-to-audio/voices`）动态读取"已安装的 TTS 插件"，因此**装上豆包插件即自动出现**，无需改前端。
- 官方 `langgenius/volcengine`（火山方舟）插件**只含 LLM 模型**，manifest 明确 `tts: false`，无法直接用。
- marketplace 无现成的豆包 TTS/ASR 模型插件。

### 方言能力（益阳话 / 湘语）
- 豆包语音官方支持八大官话（含西南官话）+ 粤语、四川话、上海话、南京话等主流方言。
- **湘语（益阳话）不在官方明确支持列表**。识别率取决于豆包模型本身，**尽力而为，不作硬性验收标准**。

### 凭证（已实测确认）
- 鉴权采用**单一 `X-Api-Key`**（新版 V3）。无需旧版 App Id + Access Token 配对。
- 实测 key 为方舟 UUID 格式，能直接调通 V3 TTS 与 ASR 接口。
- ⚠️ **安全**：调试期使用的明文 key 须在控制台**轮换/重置**；插件内作为加密 credential 存储，绝不硬编码。

---

## 2. 整体架构与数据流

**一个 provider（豆包语音）+ 两个 model（tts、speech2text）**，用户填一次凭证。

```
【文字转语音 TTS】
webapp 点喇叭 → Dify /apps/{id}/text-to-audio
  → ModelManager 取默认 TTS（豆包）
  → plugin daemon: dispatch/tts/invoke
  → 豆包插件 _invoke()
  → POST openspeech.bytedance.com/api/v3/tts/unidirectional (X-Api-Key)
  → 多行 JSON 流，逐行 base64 解码拼成 MP3 字节
  → yield 字节流回 webapp 播放

【语音转文字 ASR】
webapp 录音上传 → Dify /apps/{id}/audio-to-text
  → ModelManager 取默认 speech2text（豆包）
  → plugin daemon: dispatch/speech2text/invoke
  → 豆包插件 _invoke()
  → submit（base64 内联音频）→ 轮询 query 直到完成 → 返回识别文字
```

### 关键技术决策（均经真实请求验证）
1. **鉴权 = 单 `X-Api-Key`**（实测 `code:0` / `X-Api-Status-Code: 20000000`）。
2. **TTS 走 HTTP 单向流式** `/api/v3/tts/unidirectional`，Resource-Id `volc.service_type.10029`。
3. **ASR 走录音文件识别** submit/query，Resource-Id `volc.bigasr.auc`；**base64 内联音频**，无需公网 URL。
4. 全程纯 HTTP，无 WebSocket，匹配 webapp"录一段 / 读一段"交互。

---

## 3. 插件目录结构

```
doubao-voice/
├── manifest.yaml                 # 元信息 + 权限：model.tts=true, model.speech2text=true
├── main.py                       # 入口（脚手架生成）
├── requirements.txt              # dify_plugin, requests
├── .env.example                  # 本地 remote-install 调试
├── _assets/
│   └── icon.svg
├── provider/
│   ├── doubao_voice.yaml         # 供应商声明 + 凭证表单（api_key）
│   └── doubao_voice.py           # validate_provider_credentials()
└── models/
    ├── tts/
    │   ├── tts.yaml              # 模型声明 + 音色列表
    │   └── tts.py                # TTSModel 子类
    └── speech2text/
        ├── speech2text.yaml
        └── speech2text.py        # Speech2TextModel 子类
```

- 凭证只在 provider 层定义一次（`api_key`），两模型共用。
- 每个 `.py` 预计 80–150 行，符合"多个小文件"原则。

---

## 4. TTS 模型设计

### `models/tts/tts.yaml`（音色列表 = webapp 下拉来源）
```yaml
model: Doubao-TTS
model_type: tts
model_properties:
  default_voice: zh_female_cancan_mars_bigtts
  audio_type: mp3
  word_limit: 1000          # 超长在代码里按标点分段
  max_workers: 5
  voices:
    - mode: zh_female_cancan_mars_bigtts
      name: 灿灿(女)
      language: [zh-Hans, en-US]
    - mode: zh_female_shuangkuaisisi_moon_bigtts
      name: 爽快思思(女)
      language: [zh-Hans]
    - mode: zh_male_wennuanahu_moon_bigtts
      name: 温暖阿虎(男)
      language: [zh-Hans]
    - mode: zh_male_jingqiangkanye_moon_bigtts
      name: 京腔侃爷(男·北京话)
      language: [zh-Hans]
    - mode: zh_female_wanwanxiaohe_moon_bigtts
      name: 湾湾小何(女·台湾腔)
      language: [zh-Hans]
    - mode: zh_male_yangguangqingnian_moon_bigtts
      name: 阳光青年(男)
      language: [zh-Hans]
    # 其余实测通过的音色照此追加
```
> 已实测可用音色（`code:0`）：cancan、M392_conversation、shuangkuaisisi、wennuanahu、wanwanxiaohe、jingqiangkanye、tianmeixiaoyuan、yangguangqingnian、zhixingnvsheng、qingshuangnanda 等（全公版音色已开通）。

### `models/tts/tts.py`（约 120 行）
继承 `TTSModel`，实现：
- `_invoke(model, tenant_id, credentials, content_text, voice, ...)`
- `get_tts_model_voices(...)` → 返回 yaml 的 voices（按 language 过滤）
- `validate_credentials(...)` → 复用 provider 校验

`_invoke` 逻辑：
1. 文本超 `word_limit` → 按句号/标点切段。
2. 每段 POST `/api/v3/tts/unidirectional`，header `X-Api-Key` + `X-Api-Resource-Id: volc.service_type.10029`。
3. 响应为**多行 JSON 流**，逐行 `base64.b64decode(line["data"])` 拼 MP3 字节。
4. `yield` 字节流（`Iterable[bytes]`），webapp 边收边播。
5. 错误：`code≠0` → 抛 `InvokeError` 子类（鉴权→`InvokeAuthorizationError`，限流→`InvokeRateLimitError`），透传 `message`。

请求体模板：
```json
{"user":{"uid":"<tenant_id>"},
 "req_params":{"text":"...","speaker":"<voice>",
   "audio_params":{"format":"mp3","sample_rate":24000}}}
```

---

## 5. ASR 模型设计（speech2text）

### Dify 接口契约
`Speech2TextModel._invoke(model, credentials, file, ...)` 收文件对象/字节，返回识别字符串。

### `models/speech2text/speech2text.yaml`
```yaml
model: Doubao-ASR
model_type: speech2text
model_properties:
  file_upload_limit: 100        # MB
  supported_file_extensions: mp3,wav,m4a,ogg,flac,aac
```

### `models/speech2text/speech2text.py`（约 110 行）
继承 `Speech2TextModel`，实现 `_invoke()` + `validate_credentials()`。

`_invoke` 逻辑（同步阻塞）：
1. 读 `file` 字节 → `base64`；由扩展名推断 `format`。
2. 生成唯一 `X-Api-Request-Id`（`uuid4`）。
3. **submit**：POST `/api/v3/auc/bigmodel/submit`，header `X-Api-Key` + `X-Api-Resource-Id: volc.bigasr.auc` + `X-Api-Request-Id` + `X-Api-Sequence: -1`，body 内联 `audio.data=base64` + `request.model_name=bigmodel`、`enable_itn/enable_punc=true`。
4. 校验响应头 `X-Api-Status-Code == 20000000`。
5. **query 轮询**：用**同一 `X-Api-Request-Id`** POST `/query`，每 1–2 秒一次，直到 `20000000` 且 body 含 `result.text`；最大 30 次防卡死，超时抛 `InvokeError`。
6. 返回 `result.text`。

错误映射：鉴权失败（`4500xxxx`）→`InvokeAuthorizationError`；其余非 0 →`InvokeBadRequestError`，透传 `message`。

> **实测验证**：TTS 生成"今天天气怎么样，我们去益阳吃米粉吧。"→ ASR base64 内联提交 → 轮询识别出"今天天气怎么样？我们去益阳吃米粉吧！"，标点 + ITN 正确。

---

## 6. 供应商凭证

### `provider/doubao_voice.yaml`
```yaml
provider_credential_schema:
  credential_form_schemas:
    - variable: api_key
      label: { en_US: API Key, zh_Hans: API Key }
      type: secret-input
      required: true
      placeholder: { zh_Hans: 填入豆包语音 X-Api-Key }
```

### `provider/doubao_voice.py`
`validate_provider_credentials` 拿 key 打一个**最小 TTS 请求**（2 字最快），`code==0` 即有效——比 ASR 轮询快，适合做凭证校验。

---

## 7. 安装与交付

### 安装流程（本地包）
1. `dify-plugin init` 生成骨架（或按第 3 节手建）。
2. 实现 provider + tts + speech2text。
3. 本地联调：`.env` 配 `REMOTE_INSTALL_HOST/KEY`，`python -m main` 连 Dify 实例即时调试。
4. 打包：`dify-plugin plugin package ./doubao-voice` → `doubao-voice.difypkg`。
5. 安装：Dify 控制台 → 插件 → 上传 `.difypkg`（实例若开 `FORCE_VERIFYING_SIGNATURE` 需关闭或自签名）。
6. 填凭证：模型供应商出现"豆包语音"→ 填 `X-Api-Key` → 自动校验。
7. 设默认：设置 → 模型设置 → 默认 TTS 与语音转文本均指向豆包。

### 验证清单
| # | 验证项 | 通过标准 |
|---|---|---|
| 1 | 凭证校验 | 正确 key 绿勾；错误 key 报错 |
| 2 | 音色下拉 | webapp 出现灿灿 / 京腔侃爷等音色 |
| 3 | TTS 朗读 | 点喇叭听到豆包音色 |
| 4 | ASR 转写 | 普通话录音正确转带标点文字 |
| 5 | 方言（尽力） | 益阳话识别率记录，不作硬验收 |
| 6 | 长文本 | >1000 字 TTS 分段拼接无截断 |
| 7 | 错误链路 | 错误 key → webapp 友好报错不崩 |

### 交付物
- `doubao-voice/` 插件源码
- `doubao-voice.difypkg` 安装包
- README：凭证获取、音色列表、已知限制

### 已知限制
- 湘语（益阳话）非官方支持方言，识别率依赖豆包模型，尽力而为。
- ASR 录音文件识别有秒级轮询延迟（非实时流式），符合 webapp"录完再转"。
- 单 key 含全公版音色；复刻音色需控制台单独授权，本期不含。

---

## 8. 接口速查（实测确认）

| 能力 | 方法 | Endpoint | Resource-Id | 鉴权 |
|---|---|---|---|---|
| TTS | POST | `/api/v3/tts/unidirectional` | `volc.service_type.10029` | `X-Api-Key` |
| ASR 提交 | POST | `/api/v3/auc/bigmodel/submit` | `volc.bigasr.auc` | `X-Api-Key` + `X-Api-Request-Id` + `X-Api-Sequence:-1` |
| ASR 查询 | POST | `/api/v3/auc/bigmodel/query` | `volc.bigasr.auc` | 同上（复用同一 Request-Id） |

Host：`openspeech.bytedance.com`
成功码：TTS `code:0`；ASR 响应头 `X-Api-Status-Code: 20000000`
