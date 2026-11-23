"""Run Cadence tools with a site-specific environment.

The environment is a shell snippet that puts the tools on PATH, given with `--env` or the
SKY130_TOOL_ENV variable, for example:
    SKY130_TOOL_ENV='source /opt/cadence/setup.sh; export OA_HOME=/opt/cadence/oa'
Per-tool additions go in SKY130_ENV_<TOOL> (tool = command name, upper case), applied after
the common snippet for that tool only. Example: Innovus 20.x needs an older OpenAccess than
Virtuoso 25.x (Abstract), and a global OA_HOME breaks Abstract with "symbol lookup error ...
liboaPrivateCDS.so":
    SKY130_ENV_INNOVUS='export OA_HOME=/opt/cadence/INNOVUS201/oa_v22.60.057'
Commands run as `bash -c "<snippet>; exec <cmd>"` with stdin closed (Cadence tools wait
on an open stdin otherwise).
"""
import os
import shlex
import subprocess


def env_snippet(explicit=None):
    return explicit if explicit is not None else os.environ.get('SKY130_TOOL_ENV', '')


def tool_snippet(tool):
    return os.environ.get('SKY130_ENV_' + os.path.basename(tool).upper().replace('-', '_'), '')


def run(cmd, cwd, log, env=None, timeout=None):
    """Run `cmd` (list) in `cwd`, output to `log`. Returns the exit status."""
    snippet = env_snippet(env) + '\n' + tool_snippet(cmd[0])
    script = '%s\nexec %s' % (snippet, ' '.join(shlex.quote(c) for c in cmd))
    os.makedirs(cwd, exist_ok=True)
    with open(log, 'w') as f:
        try:
            return subprocess.run(['bash', '-c', script], cwd=cwd, stdin=subprocess.DEVNULL,
                                  stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            f.write('\n*** timeout after %s s\n' % timeout)
            return 124


def which(tool, env=None):
    snippet = env_snippet(env)
    r = subprocess.run(['bash', '-c', '%s\ncommand -v %s' % (snippet, shlex.quote(tool))],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return r.stdout.strip() or None


def require(tools, env=None):
    missing = [t for t in tools if not which(t, env)]
    if missing:
        raise SystemExit('not found on PATH (set --env or SKY130_TOOL_ENV): %s' % ' '.join(missing))
