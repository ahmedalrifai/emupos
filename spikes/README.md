# Spikes

A spike is a short, throwaway experiment that answers one question before feature work starts (group 1 in `openspec/changes/bootstrap-emupos-v0-1/tasks.md`). Its output is a **written answer** in `docs/spikes/<kit>.md`, not product code. Nothing here ships, runs in CI or has to be maintained; a kit can be deleted once its answer is recorded.

| Kit | Task | Question | Runs on |
|---|---|---|---|
| [`windows-serial`](windows-serial/README.md) | 1.1 | Does signed com0com load with Secure Boot on, and is serialx or pyserial-in-a-thread the reliable COM backend? | Windows |
| [`keyboard-wedge`](keyboard-wedge/README.md) | 1.2 | Do injected keystrokes look like a real USB barcode scanner in a browser and a native field? | Windows, macOS, Linux X11 |
| [`windows-snmp`](windows-snmp/README.md) | 1.3 | What does the Windows TCP/IP port monitor ask over SNMP, and which answers show ready, paper out, door open, offline? | Windows |
| `printer-capture` | 1.4 | Which ESC/POS commands do real POS libraries send? | any |

## How to run

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/):
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. From the repository root, run a script:

   ```sh
   uv run spikes/<kit>/<script>.py --help
   ```

   Every Python script is a [PEP 723](https://peps.python.org/pep-0723/) script: the `# /// script` block at its top lists the Python version and the script's own dependencies. uv installs those into a throwaway environment (downloading Python 3.13 if needed). The emupos package itself is not installed or used.
3. Follow the kit's `README.md` step by step. Each kit names every file it writes.

## How to report results

1. Fill in `docs/spikes/<kit>.md` (a template with blanks). Write what you saw, including failures and "not tried".
2. Send it back with the raw outputs the kit produced (for example `result-*.json`, `snmp-log.jsonl`, `jobs/*.hex`, keylogger JSON, screenshots): open a pull request with the filled template and attach the raw files, or attach everything to the spike's GitHub issue.
3. Don't commit raw outputs unless asked; they are evidence for the write-up, not fixtures.

Linting: `spikes/ruff.toml` extends the root ruff config and only relaxes the rules that make no sense for experiments (the design D2 I/O boundary, asserts, fixed-argument subprocess calls).
