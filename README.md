# HD2 Major Order Recorder

绝地潜兵2（Helldivers 2）**重大指令 MO** 的变更记录器。

这个仓库**不负责通知**——通知在本机的 DSH 定时任务里（发现新 MO 会直接在聊天里说）。
GitHub 这边只做一件事：每小时看一眼 MO 换没换，**换了就往 `state/` 里记一笔**，于是 `git log` 就是一条完整的 MO 变更流水账。

> 换句话说：仓库是「存档」，不是「喇叭」。

## 怎么判断 MO 换了

1. 请求社区 API：`GET https://api.helldivers2.dev/api/v1/assignments`
   （必须带 `X-Super-Client` / `X-Super-Contact` 头，否则 400）
2. 取当前 MO 的 `id` 集合，和 [`state/mo_state.json`](state/mo_state.json) 比对
3. 有变化 → 追加一行到 [`state/history.md`](state/history.md)，更新 state，由 workflow 提交
4. 没变化 → **不写任何文件、不产生提交**（仓库不会被时间戳刷屏）

## 文件

| 文件 | 作用 |
| --- | --- |
| `check_mo.py` | 抓取 + 比对 + 写记录 |
| `state/mo_state.json` | 当前「见过哪些 MO」，机器读 |
| `state/history.md` | MO 变更流水表，人读 |
| `.github/workflows/mo-check.yml` | 每小时 `:05` (UTC) 跑一次，有变化才提交 |

## 降级逻辑

社区 API 是个人维护的服务，偶尔会 503。此时脚本退到 `helldiversstats.com` 的历史 MO 库（`/api/v1/historical-major-orders?limit=1`）；降级期间**不记录「MO 结束」**，避免数据滞后造成误记。

## 手动跑

```bash
python check_mo.py          # 有变化会改 state/ 下的文件
```

或者 Actions 页面 → `Run workflow`。

## 本地那套通知

本机 `F:\HOME\hns\mo_check.py` 才是发通知的那个（DSH 每小时跑一次）。两边互不干扰：一个记录，一个提醒。

## 许可

MIT，见 [LICENSE](LICENSE)。
