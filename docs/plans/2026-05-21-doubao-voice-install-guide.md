# 豆包语音插件安装指南（实测记录）

- **日期**：2026-05-21
- **环境**：自建 Dify（宝塔部署），plugin_daemon 走 docker，compose 文件 `docker-compose.middleware.yaml`
- **结论**：网页导入因 daemon 的一个接口 bug 失败；改用**直接调 daemon 安装接口**一次成功。

---

## 关键坑：网页导入 `.difypkg` 报 400（decode 接口 bug）

### 现象
网页上传插件包后报：
```
Client error '400 Bad Request' for url
'.../management/decode/from_identifier?plugin_unique_identifier=...'
```

### 根因（已用源码 + 实测定位，非猜测）
Dify 安装本地包的流程 `install_from_local_pkg`（`api/services/plugin/plugin_service.py:401`）：
1. 先调 `decode_plugin_from_identifier`（**预检**，拿 verification 做 scope 校验）
2. 再调 `install_from_identifiers`（**真正安装**）

第 1 步打的是 daemon 的 `GET /management/decode/from_identifier`，该接口用 `BindRequest`→`ShouldBind` 绑 GET query，**对 query 参数绑定失败**，直接返回 `-400 PluginUniqueIdentifier failed on 'required' tag`，导致第 2 步永远走不到。

**实测对照**（带 daemon key `X-Api-Key` 直调）：
- `GET /management/fetch/manifest?plugin_unique_identifier=...` → **成功**，返回完整 manifest
- `GET /management/decode/from_identifier?plugin_unique_identifier=...` → **失败**，连已装的 `langgenius/volcengine` 也报同样的 `required` 错

→ 证明是 **decode 接口本身的 bug，与插件无关**。包、manifest 完全正常。

### 已排除的非根因
- 包大小 / nginx 上传限制：upload 步骤返回 200，包已落盘 `/app/storage/plugin_packages/...`
- 签名验证：`THIRD_PARTY_SIGNATURE_VERIFICATION_ENABLED` 关闭前后都 400（已关，见下）
- identifier 格式：用 daemon 的正则实测 MATCH，合法
- 包未持久化：`find /app/storage` 确认包在

---

## 解决办法：直接调 daemon 安装接口，绕过坏掉的 decode

`install/identifiers` 接口用 **JSON body**（不是 GET query），不触发该 bug。

### 步骤

```bash
# 1) 取 daemon 内部 key
KEY=$(docker exec dify-plugin_daemon-1 sh -c 'echo $PLUGIN_DAEMON_KEY')

# 2) 确认包已上传（先在网页上传一次 .difypkg，upload 步骤会成功落盘）
#    或确认存在：
docker exec dify-plugin_daemon-1 sh -c 'ls /app/storage/plugin_packages/<author>/<name>:<ver>@<checksum>'

# 3) 直接触发安装（替换 tenant_id 和 identifier）
curl -s -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"plugin_unique_identifiers":["<author>/<name>:<ver>@<checksum>"],"source":"package","metas":[{}]}' \
  "http://127.0.0.1:5002/plugin/<tenant_id>/management/install/identifiers"
# 返回 {"code":0,...,"task_id":"..."}

# 4) 查安装任务状态
curl -s -H "X-Api-Key: $KEY" \
  "http://127.0.0.1:5002/plugin/<tenant_id>/management/install/tasks?page=1&page_size=10"
# status:"success" 即装好
```

### 关键参数怎么拿
- **tenant_id**：从报错 URL 或 daemon 日志里取（形如 `3d863bd9-...`）
- **identifier**：`<author>/<name>:<version>@<checksum>`
  - checksum：`dify-plugin plugin checksum xxx.difypkg`
  - 或上传后从 daemon 日志 / `ls /app/storage/plugin_packages/` 取
- **PLUGIN_DAEMON_KEY**：`docker exec dify-plugin_daemon-1 env | grep PLUGIN_DAEMON_KEY`

---

## 打包 .difypkg

CLI（dify-plugin-daemon release 里的 `dify-plugin-<os>-<arch>`）：
```bash
# 下载（x86_64 Linux 示例）
curl -L -o /usr/local/bin/dify-plugin \
  "https://github.com/langgenius/dify-plugin-daemon/releases/download/0.6.1/dify-plugin-linux-amd64"
chmod +x /usr/local/bin/dify-plugin

# 打包（先排除 .venv / .env，否则包过大且含密钥）
dify-plugin plugin package ./doubao-voice
# → doubao-voice.difypkg
```

---

## 签名验证开关（本次为排查临时关闭）

文件 `docker/docker-compose.middleware.yaml` 的 plugin_daemon 环境：
```yaml
THIRD_PARTY_SIGNATURE_VERIFICATION_ENABLED: false   # 本次从 true 改 false
THIRD_PARTY_SIGNATURE_VERIFICATION_PUBLIC_KEYS: /app/keys/publickey.pem
FORCE_VERIFYING_SIGNATURE: false
```
改后重启（用与启动相同的命令，`up -d` 会重读配置；`restart` 不会）：
```bash
cd /data/dify/docker
docker compose --env-file middleware.env -f docker-compose.middleware.yaml -p dify up -d
```
> 注：经定位，400 与签名无关，是 decode 接口 bug。是否恢复 `ENABLED: true` 由安全策略决定；恢复后用 `dify-plugin signature sign` 给包签名即可。

---

## 安装后配置

1. Dify → 设置 → 模型供应商 → **豆包语音** → 填 **API Key**（豆包语音 `X-Api-Key`）→ 保存校验
2. 系统模型设置：TTS 选 `Doubao-TTS`，语音转文本选 `Doubao-ASR`
3. webapp 功能里开启文字转语音，验证朗读 + 录音转写

> ⚠️ 注意：app 里若残留旧供应商的音色（如通义 `sambert-zhiqian-v1`），需在 app 功能设置里重新选豆包音色，否则报 `55000000 resource ID is mismatched with speaker related resource`。

---

## 临时调试模式的清理

排查期间用 remote 调试模式（`python -m main` 连 `127.0.0.1:5003`）临时跑过插件。正式安装成功后应停掉，避免与正式安装的实例冲突。
- systemd 服务：`systemctl stop doubao-voice && systemctl disable doubao-voice`
- 裸进程：`ps aux | grep 'python -m main'` 找 PID 后 `kill`
