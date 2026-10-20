import json, os, subprocess, sys, tempfile
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills-launch.py")

def spawned(extra_env):
    home = tempfile.mkdtemp()
    env = {"PATH": os.environ["PATH"], "HOME": home, **extra_env}
    subprocess.run([sys.executable, HOOK], input=json.dumps({"session_id": "t1"}).encode(), env=env)
    return os.path.exists(os.path.join(home, ".claude", "cache", "skills-spawned-t1.txt"))

assert not spawned({"CLAUDE_CODE_SESSION_ATTENDED": "0", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})
assert not spawned({"CLAUDE_CODE_ENTRYPOINT": "sdk-ts"})
# interactive reaches the marker step (empty fake HOME => empty catalog => no GUI)
assert spawned({"CLAUDE_CODE_SESSION_ATTENDED": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"})
print("ok")
