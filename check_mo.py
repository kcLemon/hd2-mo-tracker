#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""绝地潜兵2 重大指令(MO)记录器 —— GitHub Actions 版

它不负责通知：通知由本机的 DSH 定时任务做。
这里只做一件事——每小时看一眼 MO 有没有换，换了就往 state/ 里记一笔，
让仓库留下一条随时间增长的 MO 变更历史（git log 就是完整的流水账）。

流程:
  1. 拉社区 API /api/v1/assignments
  2. 与 state/mo_state.json 比对
  3. 有变化 -> 追加一行到 state/history.md，并更新 state/mo_state.json
  4. 无变化 -> 什么也不做（不写文件，不产生提交）
"""
import json
import os
import sys
import datetime
import urllib.request
import urllib.error

API = "https://api.helldivers2.dev/api/v1/assignments"
HISTORY_API = "https://helldiversstats.com/api/v1/historical-major-orders?limit=1"
HEADERS = {
    "X-Super-Client": "hd2-mo-tracker",
    "X-Super-Contact": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "hd2-mo-tracker"),
    "Accept": "application/json",
    "User-Agent": "hd2-mo-tracker/2.0 (+github-actions)",
}
STATE = "state/mo_state.json"
HISTORY = "state/history.md"
REWARD_NAMES = {1: "勋章", 2: "申购单", 3: "超级货币", 4: "样本"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def http_json(url, timeout=40):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}


def fetch_assignments():
    """返回 (assignments, degraded)；主 API 挂了就退到 helldiversstats 历史库。"""
    try:
        data = http_json(API)
        if isinstance(data, list):
            return data, False
        raise ValueError("unexpected payload")
    except Exception as e:
        print("primary api failed:", repr(e))
        try:
            items = (http_json(HISTORY_API) or {}).get("items") or []
            if items:
                h = items[0]
                print("fallback to helldiversstats, order", h.get("orderId32"))
                return [{
                    "id": h.get("orderId32"),
                    "title": h.get("title") or "MAJOR ORDER",
                    "briefing": h.get("brief") or "",
                    "tasks": [],
                    "progress": [],
                    "reward": {"type": 1, "amount": h.get("rewardMedals") or 0},
                    "expiration": None,
                }], True
        except Exception as e2:
            print("fallback failed:", repr(e2))
        raise


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


def append_history(rows):
    """rows: [(时间, 事件, MO id, 标题, 简报)]"""
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    new = not os.path.exists(HISTORY)
    with open(HISTORY, "a", encoding="utf-8") as f:
        if new:
            f.write("# MO 变更流水\n\n")
            f.write("| 时间 (UTC) | 事件 | MO id | 标题 | 简报 |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
        for when, event, oid, title, brief in rows:
            brief = (brief or "").replace("\n", " ").replace("|", "/")[:160]
            f.write("| %s | %s | %s | %s | %s |\n" % (when, event, oid, title.replace("|", "/"), brief))


def goal_of(a):
    for t in a.get("tasks") or []:
        vals = t.get("values") or []
        vtypes = t.get("valueTypes") or []
        for i, vt in enumerate(vtypes):
            if vt == 3 and i < len(vals) and vals[i]:
                return vals[i]
    return None


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
        append_history([(stamp, "基线", k, v, "") for k, v in sorted(current.items())])
        print("baseline recorded:", ",".join(sorted(current)) or "-")
        return 0

    prev_ids = set(prev.get("ids") or [])
    prev_titles = prev.get("titles") or {}
    cur_ids = set(current)
    added = cur_ids - prev_ids
    removed = prev_ids - cur_ids
    if degraded:
        removed = set()  # 降级数据可能滞后，不能据此认定旧 MO 结束

    if not added and not removed:
        print("no change:", ",".join(sorted(cur_ids)) or "-")
        return 0

    rows = []
    for a in assignments:
        aid = str(a.get("id"))
        if aid not in added:
            continue
        goal = goal_of(a)
        prog = (a.get("progress") or [0])[0]
        reward = (a.get("reward") or {})
        bits = []
        if goal:
            bits.append("目标 %s（当前 %s）" % (format(goal, ","), format(prog, ",")))
        if reward:
            bits.append("奖励 %s %s" % (reward.get("amount", "?"), REWARD_NAMES.get(reward.get("type"), "奖励")))
        if a.get("expiration"):
            bits.append("截止 %s" % a["expiration"])
        brief = (a.get("briefing") or "").strip()
        rows.append((stamp, "新 MO", aid, (a.get("title") or "MAJOR ORDER").strip(),
                     brief + ("；" + "；".join(bits) if bits else "")))
        print("NEW MO", aid, brief[:100])

    for aid in sorted(removed):
        rows.append((stamp, "结束", aid, prev_titles.get(aid, ""), ""))
        print("MO ENDED", aid)

    save_state({"ids": sorted(current), "titles": current, "updated": stamp})
    append_history(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
