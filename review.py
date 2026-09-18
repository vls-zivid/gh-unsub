import curses

import requests

from unsub import (
    API,
    HEADERS,
    TIMEOUT,
    fetch_notifications,
    is_whitelisted,
    is_whitelisted_by_repo_or_reason,
    load_whitelist,
    save_whitelist,
)


def label_for(n):
    return f"{n['repository']['full_name']} - {n['subject']['title']}"


def confirm(stdscr, prompt):
    height, width = stdscr.getmaxyx()
    stdscr.move(height - 1, 0)
    stdscr.clrtoeol()
    stdscr.addnstr(height - 1, 0, prompt, width - 1)
    stdscr.refresh()
    curses.echo()
    curses.curs_set(1)
    try:
        answer = stdscr.getstr(height - 1, len(prompt)).decode().strip().lower()
    finally:
        curses.noecho()
        curses.curs_set(0)
    return answer in ("y", "yes")


def browse(stdscr, notifications):
    curses.curs_set(0)
    stdscr.keypad(True)
    pending = {}  # index -> "add" | "remove"
    idx = 0
    top = 0

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        rows = max(1, height - 2)

        if idx < top:
            top = idx
        if idx >= top + rows:
            top = idx - rows + 1

        header = (f"{len(notifications)} notifications  |  up/down j/k move  PgUp/PgDn  "
                  f"space/*: star for whitelist  x: unwhitelist  u: apply  q: quit")
        stdscr.addnstr(0, 0, header, width - 1, curses.A_BOLD)

        for row, i in enumerate(range(top, min(top + rows, len(notifications)))):
            n = notifications[i]
            state = pending.get(i)
            if state == "add":
                mark = "*"
            elif state == "remove":
                mark = "x"
            elif is_whitelisted(n):
                mark = "+"
            else:
                mark = " "
            cursor = ">" if i == idx else " "
            line = f"{cursor} {mark} {label_for(n)}"
            attr = curses.A_REVERSE if i == idx else curses.A_NORMAL
            stdscr.addnstr(row + 1, 0, line, width - 1, attr)

        adds = sum(1 for s in pending.values() if s == "add")
        removes = sum(1 for s in pending.values() if s == "remove")
        status = f"{idx + 1}/{len(notifications)}  to whitelist: {adds}  to unwhitelist: {removes}"
        stdscr.addnstr(height - 1, 0, status, width - 1)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord("k")):
            idx = max(0, idx - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            idx = min(len(notifications) - 1, idx + 1)
        elif key == curses.KEY_NPAGE:
            idx = min(len(notifications) - 1, idx + rows)
        elif key == curses.KEY_PPAGE:
            idx = max(0, idx - rows)
        elif key in (curses.KEY_HOME, ord("g")):
            idx = 0
        elif key in (curses.KEY_END, ord("G")):
            idx = len(notifications) - 1
        elif key in (ord(" "), ord("*"), ord("s")):
            pending[idx] = None if pending.get(idx) == "add" else "add"
            if pending[idx] is None:
                del pending[idx]
        elif key in (ord("x"), ord("X")):
            pending[idx] = None if pending.get(idx) == "remove" else "remove"
            if pending[idx] is None:
                del pending[idx]
        elif key == ord("u"):
            if confirm(stdscr, "Apply whitelist changes and unsubscribe the rest? [y/N] "):
                return pending, True
        elif key in (ord("q"), 27):
            return pending, False


def main():
    notifications = fetch_notifications()
    if not notifications:
        print("No notifications.")
        return

    pending, confirmed = curses.wrapper(browse, notifications)

    if not confirmed:
        print("Cancelled, nothing changed.")
        return

    to_add = {notifications[i]["id"] for i, s in pending.items() if s == "add"}
    to_remove = {notifications[i]["id"] for i, s in pending.items() if s == "remove"}

    if to_add or to_remove:
        whitelist = load_whitelist()
        thread_ids = [t for t in whitelist.get("thread_ids", []) if t not in to_remove]
        thread_ids += [t for t in to_add if t not in thread_ids]
        whitelist["thread_ids"] = thread_ids
        path = save_whitelist(whitelist)
        print(f"Whitelist updated ({len(to_add)} added, {len(to_remove)} removed) in {path}.")

    to_unsubscribe = []
    for i, n in enumerate(notifications):
        state = pending.get(i)
        if state == "add":
            continue
        if state == "remove":
            if is_whitelisted_by_repo_or_reason(n):
                continue
        elif is_whitelisted(n):
            continue
        to_unsubscribe.append(n)

    print(f"{len(to_unsubscribe)} notification(s) selected for unsubscribe.")

    for n in to_unsubscribe:
        tid = n["id"]
        label = label_for(n)
        try:
            put = requests.put(f"{API}/notifications/threads/{tid}/subscription",
                                headers=HEADERS, json={"ignored": True}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            print(f"Error unsubscribing ({exc}): {label}")
            continue
        if put.ok:
            print(f"Unsubscribed: {label}")
        else:
            print(f"Failed to unsubscribe ({put.status_code}): {label}")

    print(f"\n{len(to_unsubscribe)} unsubscribed, {len(notifications) - len(to_unsubscribe)} kept.")


if __name__ == "__main__":
    main()
