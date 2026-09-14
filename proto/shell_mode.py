"""Command-line mode: token completion and whole-line suggestion for shell commands.

Sources, in priority order:
  1. the user's own history (proto/data/shell_history.txt, one line per command; appended
     on every Enter in shell mode, importable from PSReadLine / bash history)
  2. a small built-in knowledge base of popular tools (subcommands, resources, flags)
  3. the LLM (handled by the caller) for anything else
"""
from __future__ import annotations

import re
import time
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
HISTORY = DATA / "shell_history.txt"

K8S_RES = ["pods", "pod", "po", "services", "svc", "deployments", "deploy", "nodes", "no", "namespaces", "ns",
           "configmaps", "cm", "secrets", "ingress", "ing", "pv", "pvc", "jobs", "cronjobs", "events", "all",
           "statefulsets", "sts", "daemonsets", "ds", "replicasets", "rs", "serviceaccounts", "sa", "endpoints", "ep"]
K8S_FLAGS = ["-n", "--namespace", "-A", "--all-namespaces", "-o", "wide", "yaml", "json", "-w", "--watch",
             "-l", "--selector", "--context", "-f", "--tail", "--since", "--previous", "-it", "--", "-c"]
CTR_SUB = ["ps", "logs", "run", "exec", "images", "pull", "push", "build", "compose", "stop", "start", "rm", "rmi",
           "restart", "inspect", "stats", "top", "cp", "login", "tag", "network", "volume", "system", "prune"]
CTR_FLAGS = ["-a", "-f", "--follow", "--tail", "-it", "-d", "--rm", "--name", "-p", "-v", "-e", "--network",
             "--namespace", "-n", "--platform", "-t", "--no-cache", "up", "down", "ls"]

KB: dict[str, dict[str, list[str]]] = {
    "kubectl": {"_": ["get", "describe", "logs", "apply", "delete", "exec", "port-forward", "rollout", "scale", "top",
                      "config", "create", "edit", "explain", "cp", "label", "annotate", "cluster-info", "version", "-n"],
                "get": K8S_RES + K8S_FLAGS, "describe": K8S_RES + K8S_FLAGS, "delete": K8S_RES + K8S_FLAGS,
                "logs": K8S_FLAGS, "exec": ["-it", "--", "/bin/sh", "/bin/bash", "-n"], "apply": ["-f", "-k", "-n"],
                "rollout": ["status", "restart", "history", "undo"], "scale": ["--replicas", "deployment"],
                "top": ["pods", "nodes"], "config": ["get-contexts", "use-context", "current-context", "view"],
                "port-forward": ["svc/", "pod/", "-n"], "create": K8S_RES + ["-f"], "edit": K8S_RES},
    "nerdctl": {"_": CTR_SUB + ["--namespace", "-n"], "logs": CTR_FLAGS, "ps": ["-a", "--all", "-q", "--format"],
                "run": CTR_FLAGS, "exec": ["-it", "-i", "-t", "/bin/sh", "/bin/bash"], "images": ["-a", "-q"],
                "compose": ["up", "down", "ps", "logs", "-f", "-d", "build", "pull", "restart"],
                "rm": ["-f"], "rmi": ["-f"], "system": ["prune", "info", "df"], "build": ["-t", "-f", "."],
                "stop": [], "start": [], "restart": [], "inspect": [], "stats": [], "pull": [], "push": []},
    "docker": {},  # filled below (same as nerdctl)
    "git": {"_": ["status", "add", "commit", "push", "pull", "fetch", "checkout", "switch", "branch", "log", "diff",
                  "merge", "rebase", "stash", "clone", "reset", "tag", "remote", "show", "init", "restore", "cherry-pick"],
            "commit": ["-m", "-am", "--amend", "-a"], "push": ["origin", "-u", "--force-with-lease", "--tags"],
            "pull": ["origin", "--rebase"], "checkout": ["-b", "main", "master", "--"], "switch": ["-c", "main"],
            "branch": ["-a", "-d", "-D", "-m"], "log": ["--oneline", "--graph", "--all", "-p", "-n"],
            "diff": ["--staged", "--cached", "HEAD", "--stat"], "stash": ["pop", "list", "push", "drop", "apply"],
            "reset": ["--hard", "--soft", "HEAD~1"], "remote": ["-v", "add", "origin", "set-url"],
            "rebase": ["-i", "main", "origin/main", "--continue", "--abort"], "add": ["-A", ".", "-p"],
            "clone": ["--depth", "1"], "restore": ["--staged", "."]},
    "ssh": {"_": ["-p", "-i", "-L", "-N", "-t", "-o"]}, "scp": {"_": ["-r", "-P", "-i"]},
    "systemctl": {"_": ["status", "start", "stop", "restart", "enable", "disable", "daemon-reload", "list-units", "--user"]},
    "journalctl": {"_": ["-u", "-f", "-n", "--since", "-b", "-xe"]},
    "ls": {"_": ["-la", "-l", "-a", "-lh", "-lt", "-R"]}, "cd": {"_": ["..", "~", "-"]}, "cat": {"_": []},
    "grep": {"_": ["-r", "-i", "-n", "-v", "-E", "-l", "--include"]}, "find": {"_": [".", "-name", "-type", "f", "d", "-mtime"]},
    "tail": {"_": ["-f", "-n"]}, "head": {"_": ["-n"]}, "ps": {"_": ["aux", "-ef"]}, "kill": {"_": ["-9"]},
    "python": {"_": ["-m", "-c", "-u"]}, "python3": {"_": ["-m", "-c", "-u"]}, "pip": {"_": ["install", "list", "freeze", "uninstall", "-r", "-U"]},
    "uv": {"_": ["run", "pip", "venv", "add", "sync", "lock", "init", "tool"], "pip": ["install", "list", "--python"], "venv": ["--python"]},
    "npm": {"_": ["install", "run", "start", "test", "build", "ci", "-g"]}, "npx": {"_": []}, "node": {"_": []},
    "curl": {"_": ["-s", "-L", "-o", "-O", "-X", "POST", "GET", "-H", "-d", "-k"]}, "wget": {"_": ["-O", "-q"]},
    "sudo": {"_": ["apt", "systemctl", "docker", "nerdctl", "-i", "-s"]},
    "apt": {"_": ["update", "upgrade", "install", "remove", "search", "list", "-y"]},
    "make": {"_": ["clean", "install", "build", "test", "-j"]}, "cmake": {"_": ["-B", "-S", "--build", "-DCMAKE_BUILD_TYPE=Release"]},
    "helm": {"_": ["install", "upgrade", "uninstall", "list", "repo", "template", "-n", "--namespace", "-f", "--set"]},
    "tmux": {"_": ["new", "-s", "attach", "-t", "ls", "kill-session"]}, "vim": {"_": []}, "nano": {"_": []},
    "chmod": {"_": ["+x", "755", "644", "-R"]}, "chown": {"_": ["-R"]}, "mkdir": {"_": ["-p"]}, "rm": {"_": ["-rf", "-r", "-f"]},
    "cp": {"_": ["-r", "-a"]}, "mv": {"_": []}, "echo": {"_": []}, "export": {"_": []}, "source": {"_": []},
    "wsl": {"_": ["-d", "--shutdown", "-l", "-v"]}, "winget": {"_": ["install", "search", "upgrade", "list", "--id"]},
    "gh": {"_": ["repo", "pr", "issue", "release", "auth", "api"], "pr": ["create", "list", "view", "checkout", "merge"],
           "release": ["create", "upload", "view", "list"], "auth": ["login", "status", "refresh"]},
}
KB["docker"] = KB["nerdctl"]
COMMANDS = set(KB)

_history: list[str] = []
_first_tokens: Counter = Counter()


def load_history():
    _history.clear()
    _first_tokens.clear()
    if HISTORY.exists():
        for line in HISTORY.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line:
                _history.append(line)
                _first_tokens[line.split()[0]] += 1


def add_history(line: str):
    line = line.strip()
    if not line or (_history and _history[-1] == line):
        return
    DATA.mkdir(exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    _history.append(line)
    _first_tokens[line.split()[0]] += 1


def import_history(path: Path, limit: int = 5000) -> int:
    """Import lines from a PSReadLine / bash / zsh history file."""
    n = 0
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        line = re.sub(r"^: \d+:\d+;", "", line).strip()      # zsh extended format
        if line and not line.startswith("#"):
            add_history(line)
            n += 1
    return n


load_history()


def is_shell_line(line: str) -> bool:
    """is the current line (text before the composition) a shell command?"""
    m = re.match(r"\s*([A-Za-z0-9_./~-]+)", line)
    if not m:
        return False
    first = m.group(1)
    return first in COMMANDS or _first_tokens.get(first, 0) > 0


def command_completions(prefix: str, limit: int = 6) -> list[str]:
    """at line start: known command names (user's own first, by frequency)"""
    names = [c for c, _ in _first_tokens.most_common() if c.startswith(prefix)]
    names += sorted(c for c in COMMANDS if c.startswith(prefix) and c not in names)
    return names[:limit]


def token_completions(line: str, prefix: str, limit: int = 8) -> list[str]:
    """completions for the token being typed, given the tokens already on the line"""
    toks = line.split()
    out: list[str] = []
    seen: set[str] = set()

    def add(t):
        if t.startswith(prefix) and t != prefix and t not in seen:
            seen.add(t)
            out.append(t)

    # 1. history: tokens that followed exactly this line prefix (most recent first)
    joined = " ".join(toks)
    for h in reversed(_history):
        ht = h.split()
        if len(ht) > len(toks) and " ".join(ht[: len(toks)]) == joined:
            add(ht[len(toks)])
    # 2. history: any token used with this command at this position
    if toks:
        for h in reversed(_history):
            ht = h.split()
            if ht and ht[0] == toks[0] and len(ht) > len(toks):
                add(ht[len(toks)])
    # 3. knowledge base
    if toks:
        cmd = toks[0]
        if cmd == "sudo" and len(toks) > 1:
            cmd, toks = toks[1], toks[1:]
        kb = KB.get(cmd, {})
        sub = next((t for t in toks[1:] if t in kb), None)
        for t in (kb.get(sub, []) if sub else []) + kb.get("_", []):
            add(t)
    # 4. history: any token anywhere with this prefix
    if len(prefix) >= 2:
        for h in reversed(_history):
            for t in h.split()[1:]:
                add(t)
    return out[:limit]


def line_suggestion(line: str) -> str:
    """rest of the most recent history line that starts with the current line"""
    line = line.rstrip()
    if not line:
        return ""
    for h in reversed(_history):
        if h.startswith(line) and len(h) > len(line):
            return h[len(line):]
    return ""
