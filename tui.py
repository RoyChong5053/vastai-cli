#!/usr/bin/env python3
"""VastAI CLI toolbox - single entry point with a small interactive menu.

Groups A-E (see project layout). The menu lets you pick which sub-tool to run;
a free-form "extra args" line is offered so the same action can also drive
non-interactive flags (e.g. --offer-id 123456, --no-confirm ...).

Runs a real curses UI when attached to a TTY; otherwise falls back to a simple
text menu + input() so it stays usable from scripts / non-interactive shells.
"""

import os
import sys
import json
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def python_bin():
    """Prefer the isolated .venv, fall back to whatever runs us."""
    candidate = ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


# ── group definitions ───────────────────────────────────────────────
# each action: (label, argv_or_None_for_submenu)

def _instances_actions(extra_placeholder=""):
    actions = [
        ("▶ 创建实例（交互式）", ["main.py"]),
        ("查看帮助 (--help)", ["main.py", "--help"]),
    ]
    return [("Instances · 管理 VastAI 实例 (python main.py)")] + actions


def _comfyui_actions(extra_placeholder=""):
    tasks = {
        "wan": "WAN2.2 AB10S 提示词顾问",
        "lora": "SDXL LoRA 泛化性测试",
        "probe": "SDXL 模型输出穷举测试（大方向 → 变体 → 批量渲染）",
    }
    head = ["comfyui_automation/run.sh"]
    actions = [(f"帮助 / list", [*head, "--help"])]
    for name, desc in tasks.items():
        # first half of the row is a description column; second is the argv
        label = f"{name} · {desc}"
        actions.append((label, [*head, name]))
    return [("ComfyUI 自动化（子项目自带 run.sh）")] + actions


def _auto_ssh_actions(extra_placeholder=""):
    head = ["auto-ssh.py"]
    return [
        ("AutoSSH · 连接最新 VastAI 实例 (python auto-ssh.py)", [*head]),
        ("查看帮助 (--help)", [*head, "--help"]),
    ]


def _qwen_actions(extra_placeholder=""):
    head = ["qwen-deploy.py"]
    variants = {
        "8B": "qwen36-27B-8GB",
        "12B": "qwen36-27B-12B",
        "24B": "qwen36-27B-24B",
    }
    actions = []
    for variant, script in variants.items():
        for act in ("deploy", "status", "stop", "logs"):
            label = f"{script} · {act}"
            action = [*head, act, variant]
            actions.append((label, action))
    return [("Qwen 模型部署（run-scripts/*.sh 的统一入口）")] + actions


def _rclone_actions(extra_placeholder=""):
    head = ["bash", str(ROOT / "rclone")]
    scripts = {
        "dn-vastai.sh": "从 VastAI 同步到本地 (download)",
        "vastai-auto-sync.sh": "自动双向同步",
    }
    actions = []
    for script, desc in scripts.items():
        label = f"{script} · {desc}"
        action = [*head, script]
        actions.append((label, action))
    return [("Rclone 同步（rclone/*.sh）")] + actions


GROUPS = [
    ("Instances", _instances_actions),
    ("ComfyUI", _comfyui_actions),
    ("AutoSSH", _auto_ssh_actions),
    ("Qwen", _qwen_actions),
    ("Rclone", _rclone_actions),
]

# ── execution ────────────────────────────────────────────────────────


def build_argv(base, extra_text):
    argv = list(base)
    if extra_text:
        try:
            argv.extend(shlex.split(extra_text))
        except ValueError as e:
            print(f"!! 无法解析参数 '{extra_text}': {e}")
    return argv


def run_with_env(argv):
    """Run argv with the isolated venv prepended to PATH (so its python wins),
    and cwd set to the project root so top-level imports resolve."""
    import subprocess

    if "bash" in argv[:1]:
        # shell scripts: honor their own env/PATH via a subshell
        joined = " ".join(shlex.quote(c) for c in argv)
        return os.system(f"{joined}")
    cmd = list(argv)
    venv_bin = str(ROOT / ".venv" / "bin")
    path_parts = [venv_bin] if os.path.exists(venv_bin) else []
    env = dict(os.environ)
    existing_path = env.get("PATH", "").split(os.pathsep)
    for p in path_parts:
        if p not in existing_path:
            existing_path.insert(0, p)
    env["PATH"] = os.pathsep.join(existing_path)
    return subprocess.run(cmd, cwd=str(ROOT), env=env).returncode


# ── menu rendering (curses) ──────────────────────────────────────────


def curses_main():
    try:
        import curses
    except ImportError:
        text_mode()
        return

    def draw(win, items, index):
        win.erase()
        if sys.stdout.isatty():
            win.noutrefresh()
        h, w = win.getmaxyx()
        top = max(0, (index - 2))
        for i in range(top, min(top + h - 1, len(items) + 1)):
            if i == index:
                label = f"▶ {items[i][0]}".ljust(w)
            else:
                label = "  " + items[i][0].ljust(w)
            try:
                win.addstr(i, 0, label[:w], curses.color_pair(1) if i == index and hasattr(curses, 'color_pairs') else curses.A_NORMAL)
            except curses.error:
                pass
        help_line = "↑/↓ 选择   Enter 运行/进入   输入参数后回车=传参   Esc/Q 返回"
        try:
            win.addstr(h - 1, 0, help_line[:w].ljust(w), curses.A_REVERSE)
        except curses.error:
            pass
        curses.doupdate()

    def run_action(argv):
        # keep the TUI alive while a program uses the terminal so input/output work;
        # restore menu afterwards.
        code = run_with_env(argv)
        draw(win, items, index)
        return code

    curses.start_color()
    curses.use_default_colors()
    try:
        curses.init_pair(1, -1, 4)
    except curses.error:
        pass
    win = curses.initscr()
    curses.cbreak()
    curses.noecho()
    win.keypad(True)

    stack = [("Instances", _instances_actions)]
    try:
        while True:
            group_name, builder = stack[-1]
            items = [("", None)] + list(builder())  # index 0 == "back up"
            top_group = len(stack) == 1

            idx = 0
            while True:
                draw(win, items, idx)
                key = win.getch()
                if key in (curses.KEY_UP, ord("k")):
                    idx = max(0, idx - 1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    idx = min(len(items) - 1, idx + 1)
                elif key == curses.KEY_RESIZE:
                    draw(win, items, idx)
                    continue
                elif key in (27,) or chr(key) in ("Q", "q"):
                    return
                elif key in (ord("\n"), ord(" "), 10):
                    label, argv = items[idx]
                    if argv is None:
                        # back up / top-level exit slot
                        if not top_group:
                            stack.pop()
                        break
                    extra = entry(win) or ""
                    final_argv = build_argv(argv, extra)
                    run_action(final_argv)
                elif key in (ord("1"), ord("2")) and len(items) > 3:
                    # quick select first action when it's a group submenu? no-op; keep simple
                    pass
            if not top_group:
                break
    except KeyboardInterrupt:
        return
    finally:
        curses.endwin()


def entry(win):
    """Simple one-line text input at the bottom of the screen. Returns str or None (ESC)."""
    try:
        import curses
    except ImportError:
        return ""

    win.erase()
    h, w = win.getmaxyx()
    try:
        win.addstr(h - 1, 0, "extra args -> ".ljust(w), curses.A_REVERSE)
    except curses.error:
        pass
    curses.doupdate()
    buf = []
    while True:
        key = win.getch()
        if key in (27,) or chr(key) == "\n":
            break
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
                try:
                    win.move(h - 1, len(buf))
                except curses.error:
                    pass
                try:
                    win.addstr(h - 1, len(buf), " ".ljust(w)[: max(0, w - len(buf) - 1)], curses.A_REVERSE)
                except curses.error:
                    pass
            curses.doupdate()
        elif key == 9:
            # Tab -> submit current value as-is (allows spaces-free passthrough)
            break
        elif 32 <= key < 127:
            buf.append(chr(key))
            try:
                win.addstr(h - 1, len(buf), chr(key))
            except curses.error:
                pass
            curses.doupdate()
    return "".join(buf)


# ── menu rendering (text fallback) ───────────────────────────────────


def numbered(title, items):
    print(f"\n== {title} ==")
    for i, (label, _a) in enumerate(items):
        if not label:
            continue
        print(f"  {i:<3} {label}")


def text_mode(argv=None):
    """Fallback menu used when there is no TTY (or --no-tui was passed).

    Accepts either "G:I" to pick group G, action I within that group, or a bare
    index referring to the first group. Non-interactive use can pipe choices via stdin.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    menu_groups = [("Instances", _instances_actions), ("ComfyUI", _comfyui_actions),
                   ("AutoSSH", _auto_ssh_actions), ("Qwen", _qwen_actions),
                   ("Rclone", _rclone_actions)]

    numbered("top level (choose G:Action)", [(name, None) for name, _ in menu_groups])
    try:
        choice = input("\nchoose (e.g. 2:0): ").strip() or "1:0"
        if ":" in choice:
            g_i, i_str = choice.split(":", 1)
            group_index, idx = int(g_i), int(i_str)
        else:
            group_index, idx = 0, int(choice)

        name, builder = menu_groups[group_index]
        items = list(builder())
        extra = "" if os.environ.get("TEST_NON_INTERACTIVE") else input("(optional args): ").strip()
    except (EOFError, KeyboardInterrupt):
        return 0

    try:
        _label, argv_ = items[idx]
    except IndexError:
        print(f"!! invalid choice {choice}")
        return 1
    if not argv_:
        print("!! no action available for that selection")
        return 1
    final_argv = build_argv(argv_, extra)
    try:
        return run_with_env(final_argv)
    except Exception as e:
        print(f"!! failed to launch {final_argv!r}: {e}")
        return 1


# ── entry point ──────────────────────────────────────────────────────


def main():
    if "--no-tui" in sys.argv or not sys.stdin.isatty() or not os.environ.get("TERM"):
        try:
            text_mode()
        except (EOFError, KeyboardInterrupt):
            return 0
        return 0

    curses_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
