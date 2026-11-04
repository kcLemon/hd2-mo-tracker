#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""绝地潜兵2 重大指令(MO)监视器 —— GitHub Actions 版

流程:
  1. 拉社区 API /api/v1/assignments
  2. 和 state/mo_state.json 里的 MO id 集合比对
  3. 有变化 -> 开一个 GitHub Issue(默认通知渠道) + 可选 Discord webhook
  4. 无变化 -> 静默退出, 由 workflow 提交新的 state

环境变量:
  GITHUB_TOKEN        由 Actions 自动注入, 用于开 issue
  GITHUB_REPOSITORY   owner/repo, 由 Actions 自动注入
  DISCORD_WEBHOOK_URL 可选, 配了才会额外推 Discord
  DRY_RUN=1           只打印, 不真的开 issue
"""
import json
import os
import sys
import datetime
import urllib.request
import urllib.error

API = "https://api.helldivers2.dev/api/v1/assignments"
HISTORY = "https://helldiversstats.com/api/v1/historical-major-orders?limit=%d"
HEADERS = {
    "X-Super-Client": "hd2-mo-tracker",
    "X-Super-Contact": "https://github.com/{repo}".format(
        repo=os.getenv("GITHUB_REPOSITORY", "hd2-mo-tracker")
    ),
    "Accept": "application/json",
    "User-Agent": "hd2-mo-tracker/1.0 (+github-actions)",
}
STATE = "state/mo_state.json"
REWARD_NAMES = {1: "Medals / 勋章", 2: "Requisition / 申购单", 3: "Super Credits / 超级货币", 4: "Samples / 样本"}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def http_json(url, method="GET", payload=None, token=None, timeout=30):
    data = None
    headers = dict(HEADERS)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        return r.status, (json.loads(raw) if raw.strip() else {})


def fetch_assignments():
    """返回 (assignments, degraded)。

    主 API 挂掉时退到 helldiversstats 的历史库（只取最新一条），
    degraded=True 表示数据是降级来的，此时**不报「MO 结束」**，只报新 MO 出现。
    """
    try:
        _, data = http_json(API, timeout=40)
        if isinstance(data, list):
            return data, False
        raise ValueError("unexpected payload")
    except Exception as e:
        print("primary api failed:", repr(e))
        for h in fetch_history(limit=1):
            oid = h.get("orderId32")
            if oid is None:
                continue
            print("fallback to helldiversstats, order", oid)
            return [{
                "id": oid,
                "title": h.get("title") or "MAJOR ORDER",
                "briefing": h.get("brief") or "",
                "tasks": [],
                "progress": [],
                "reward": {"type": 1, "amount": h.get("rewardMedals") or 0},
                "expiration": None,
            }], True
        raise


def fetch_history(limit=40):
    """历史 MO: 用作 briefing 兜底, 以及记录上一条指令。"""
    try:
        _, data = http_json(HISTORY % limit)
        return data.get("items") or []
    except Exception:
        return []


def load_state():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fmt_dt(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(iso)


def human_left(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        secs = int((dt - now_utc()).total_seconds())
        if secs <= 0:
            return "已到期"
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        if d:
            return "剩 %d 天 %d 小时" % (d, h)
        if h:
            return "剩 %d 小时 %d 分" % (h, m)
        return "剩 %d 分" % m
    except Exception:
        return ""


def goal_of(a):
    for t in a.get("tasks") or []:
        vals = t.get("values") or []
        vtypes = t.get("valueTypes") or []
        for i, vt in enumerate(vtypes):
            if vt == 3 and i < len(vals) and vals[i]:
                return vals[i]
    return None


def render(a, prev_titles, history):
    aid = a.get("id")
    title = (a.get("title") or "MAJOR ORDER").strip()
    brief = (a.get("briefing") or "").strip()
    lines = ["## MO 更新：#%s 《%s》" % (aid, title), ""]

    if brief:
        lines.append("**内容**：%s" % brief)
    else:
        for h in history:
            if str(h.get("orderId32")) == str(aid) and h.get("brief"):
                lines.append("**内容**（取自历史库）：%s" % h["brief"])
                break

    goal = goal_of(a)
    prog = (a.get("progress") or [0])[0]
    if goal:
        try:
            lines.append("**目标**：%s（当前 %s，%.1f%%）" % (format(goal, ","), format(prog, ","), prog * 100.0 / goal))
        except Exception:
            lines.append("**目标**：%s" % format(goal, ","))

    reward = a.get("reward") or {}
    if reward:
        lines.append("**奖励**：%s %s" % (reward.get("amount", "?"), REWARD_NAMES.get(reward.get("type"), "奖励")))

    exp = a.get("expiration")
    if exp:
        lines.append("**截止**：%s（%s）" % (fmt_dt(exp), human_left(exp)))

    if prev_titles:
        gone = ["#%s 《%s》" % (k, v) for k, v in prev_titles.items()]
        if gone:
            lines.append("")
            lines.append("_上一条已结束：%s_" % "、".join(gone))

    lines.append("")
    lines.append("<sub>%s · 数据源 api.helldivers2.dev</sub>" % now_utc().strftime("%Y-%m-%d %H:%M UTC"))
    return "\n".join(lines)


def open_issue(body, title):
    repo = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    if os.getenv("DRY_RUN") == "1" or not repo or not token:
        print("[dry-run] would open issue:", title)
        print(body)
        return
    try:
        status, resp = http_json(
            "https://api.github.com/repos/%s/issues" % repo,
            method="POST",
            payload={"title": title, "body": body},
            token=token,
        )
        print("issue created:", resp.get("html_url"), status)
    except urllib.error.HTTPError as e:
        print("issue failed:", e.code, e.read()[:300])
    except Exception as e:
        print("issue failed:", repr(e))


def discord(body, title):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return
    try:
        payload = {"embeds": [{"title": title[:250], "description": body[:3800], "color": 0xFFE710}]}
        http_json(url, method="POST", payload=payload)
        print("discord sent")
    except Exception as e:
        print("discord failed:", repr(e))


def main():
    try:
        assignments, degraded = fetch_assignments()
    except Exception as e:
        print("fetch failed, skip:", repr(e))
        return 0

    current = {str(a.get("id")): (a.get("title") or "").strip() for a in assignments if a.get("id") is not None}
    stamp = now_utc().isoformat(timespec="seconds")
    prev = load_state()

    if prev is None:
        save_state({"ids": sorted(current), "titles": current, "updated": stamp})
        print("baseline recorded:", ",".join(sorted(current)) or "-")
        return 0

    prev_ids = set(prev.get("ids") or [])
    cur_ids = set(current)
    added = cur_ids - prev_ids
    removed = prev_ids - cur_ids
    if degraded:
        # 降级数据可能滞后，不能据此判定「旧 MO 结束」
        removed = set()

    if not added and not removed:
        print("no change:", ",".join(sorted(cur_ids)) or "-")
        return 0

    # 只有真的变化了才写 state，避免仓库被时间戳刷屏
    save_state({"ids": sorted(current), "titles": current, "updated": stamp})

    history = fetch_history() if added else []
    prev_titles = {k: v for k, v in (prev.get("titles") or {}).items() if k in removed}
    for a in assignments:
        if str(a.get("id")) in added:
            brief = (a.get("briefing") or "Major Order").strip().replace("\n", " ")
            title = "MO 更新：%s" % brief[:90]
            body = render(a, prev_titles, history)
            open_issue(body, title)
            discord(body, title)
    if not added and removed:
        msg = "MO 结束：#%s 已下线，新指令尚未刷新。" % "、".join(sorted(removed))
        open_issue(msg, "MO 结束：%s" % "、".join(sorted(removed)))
        discord(msg, "MO 结束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
