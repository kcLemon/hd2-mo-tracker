# HD2 Major Order Watcher

绝地潜兵2（Helldivers 2）**重大指令 MO** 变更监视器，跑在 GitHub Actions 上：每小时查一次，**有新 MO 才动**，开一个 Issue 通知你。

> 不依赖任何一台电脑开机 —— 24/7 由 GitHub 的定时任务负责。

## 它是怎么判断「新 MO」的

1. 请求社区 API：`GET https://api.helldivers2.dev/api/v1/assignments`
   （必须带 `X-Super-Client` / `X-Super-Contact` 两个头，否则 400）
2. 取当前 MO 的 `id` 集合，和仓库里的 [`state/mo_state.json`](state/mo_state.json) 比对
3. 集合有变化 → 组装中文报告 → 开 Issue；同时把新 state 提交回仓库
4. 没变化 → 什么也不做（只在日志里打一行）

`state/mo_state.json` 就是「见过哪些 MO」的记忆，由 workflow 自动 commit，**不要手动改**。

## 通知渠道

| 渠道 | 需要配置 | 说明 |
| --- | --- | --- |
| **GitHub Issue** | 无 | 默认开启。Issue 会带站内/邮件通知 |
| **Discord** | 仓库 Secrets 加 `DISCORD_WEBHOOK_URL` | 可选，配了就在开 Issue 的同时推一条 embed |

加 Discord：仓库 `Settings → Secrets and variables → Actions → New repository secret`，名字 `DISCORD_WEBHOOK_URL`，值是 Discord 频道的 Webhook URL。

## 手动跑一次

`Actions → HD2 Major Order Watcher → Run workflow`，或者本地：

```bash
DRY_RUN=1 python check_mo.py    # 只打印，不开 issue
```

首次运行（没有 state 文件）只会记录基线，不会通知。

## 改了 cron 的频率？

编辑 [`.github/workflows/mo-check.yml`](.github/workflows/mo-check.yml) 里的 `cron`。注意 GitHub 的定时任务**不保证准点**，高峰期可能延迟 5–20 分钟，偶尔会跳过某一次。

## 顺带用到的其它数据源

- `https://helldiversstats.com/api/v1/historical-major-orders?limit=N` — 历史 MO 归档，用来在 `briefing` 为空时补齐内容，也记录了上一条指令。

## 许可

MIT，见 [LICENSE](LICENSE)。
