# Bug 记录：audio-to-text 报 maximum recursion depth exceeded

- **日期**：2026-05-22
- **现象**：webapp 录音转文字（`POST /api/audio-to-text`）返回
  `{"code":"completion_request_error","message":"[<任意语音插件>] Error: maximum recursion depth exceeded","status":400}`
- **影响面**：**所有 speech2text 插件**（豆包、通义 Tongyi、阿里云 TTS 等）全部中招 —— 与具体插件无关。
- **关键对照**：TTS（文字转语音）正常，只有 ASR（语音转文字）报错。

## 根因

`api/core/plugin/impl/model.py` 的 `_dispatch_payload` 把 `user_id` 原样放进
转发给 plugin_daemon 的 payload，再交给 `graphon` 的 `jsonable_encoder` 序列化。

webapp 调用链里，`user_id`（来自 `ModelManager.for_tenant(user_id=end_user)`，
最终源自 `audio_service.transcript_asr` 的 `end_user`）传进来的是一个
**`EndUser` ORM 对象**，而不是字符串。

`jsonable_encoder` 没有循环引用保护：遇到 ORM 对象走 fallback 分支
`dict(obj)/vars(obj)` → 递归遍历 `EndUser.__table__`（`Table('end_users')`）
→ Table → Column → DedupeColumnCollection → Table … 无限递归 → 栈溢出。

`jsonable_encoder` 把 RecursionError 包成 InvokeError 透传，api 在
`controllers/web/audio.py` 的 `except InvokeError` 分支返回 400，message 带上
插件名，所以看起来像“插件报错”，实则是 api 公共路径的 bug。

## 为什么排查曲折（教训）

- 直接调 `AudioService.transcript_asr`（手动构造、`end_user="probe"` 传字符串）
  **不复现** —— 因为字符串不会触发 ORM 递归。
- 只有走 webapp 真实 HTTP 请求（`end_user` 是 EndUser 对象）才复现。
- 中途误判过多个方向：插件代码、requests/httpx 的 gevent SSL 递归、
  gevent 25.9.1+py3.12（issue #26689）。这些都不是本 bug 的真因。
- **破案关键**：用户提供「通义、阿里云 ASR 也报同样递归」→ 锁定 api 公共路径。
- **定位手段**：在 `web/audio.py` 的 InvokeError 分支加 `logger.exception` 拿到
  完整堆栈，看到 `jsonable_encoder` 在 `model.py:565` 自递归；再在
  `encoders.py` 的 fallback 处打印 obj 类型，看到 `Table('end_users')`/`Column`。

## 修复

`api/core/plugin/impl/model.py` `_dispatch_payload`：

```python
payload: dict[str, Any] = {"data": data}
if user_id is not None:
    # user_id may arrive as an EndUser/Account ORM object; serialize to its
    # id string so jsonable_encoder does not recurse into the SQLAlchemy Table.
    payload["user_id"] = getattr(user_id, "id", None) or str(user_id)
return payload
```

一处修复，所有模型类型（LLM/TTS/ASR）的转发路径都受益。

## 注意事项

- 这是改 **Dify 本体代码**（非自研插件）。从上游拉新版时可能冲突，需留意。
- 这是 Dify 上游的 bug，理想是向官方提 issue/PR。
- 排查期间在服务器临时加过 DEBUG 日志（`encoders.py`、`web/audio.py`）和
  把 api gevent 降到 24.11.1，这些都不是本 bug 的必要修复，应清理/还原：
  - 还原 `encoders.py`（去掉 FALLBACK 调试打印）
  - 还原 `web/audio.py`（去掉 `logger.exception('DEBUG ...')`）
  - 还原 `model.py` 里 speech2text 那个临时的 credentials 净化（已被本修复取代，
    非必需，可保留亦可去掉）
  - api gevent 降级与否不影响本 bug，按需还原

## 与豆包语音插件的关系

无关。豆包语音插件本身功能正常（TTS/ASR 代码均经实测）。本 bug 是 Dify api
框架层的共性问题，恰好在接入豆包 ASR 时暴露。
