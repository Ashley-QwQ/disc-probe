"""Tab completion: `python -m discprobe completion <shell>` prints a script for the shell to load.

The script holds every command and option as plain data, so pressing Tab never starts Python and
stays instant; regenerating it is the price after an update. Matching is by prefix over one
command's options, a few dozen at most, which is also what argparse accepts as an abbreviation.
Everything is keyed on `python -m discprobe`, and other uses of python keep the default completion.
"""

from __future__ import annotations

import sys

from .i18n import block, tr

SHELLS = ("powershell", "bash", "zsh")
PATH_DESTS = {"output", "geo", "picture", "design_npy", "correction", "layout", "spec", "out", "rings_layout",
              "refine_from", "output_dir", "image", "images", "scans", "phi"}
VALUE_HINTS = {"--geo": ("latest",), "--speed": ("4x", "8x", "16x", "24x")}
POSITIONAL_VALUES = {"results": ("geo", "timing", "info")}
USAGE = """\
Tab completion for disc-probe. Generate the script once, then have your shell load it:

PowerShell:
  python -m discprobe completion powershell > $HOME\\discprobe-completion.ps1
  add to $PROFILE:  . $HOME\\discprobe-completion.ps1
bash:
  python -m discprobe completion bash > ~/.discprobe-completion.bash
  add to ~/.bashrc:  source ~/.discprobe-completion.bash
zsh:
  python -m discprobe completion zsh > ~/.discprobe-completion.zsh
  add to ~/.zshrc:  source ~/.discprobe-completion.zsh

Add --lang zh to the first line for Chinese descriptions. Run it again after updating disc-probe."""


def _label(action) -> str:
    """What an option's value is, for the description."""
    if action.nargs == 0:
        return ""
    if action.choices:
        return "|".join(action.choices)
    if action.type is int:
        return tr("integer")
    if action.type is float:
        return tr("number")
    if getattr(action.type, "__name__", "") == "_speed":
        return tr("kB/s or 4x")
    return tr("path") if action.dest in PATH_DESTS else tr("text")


def table(build_parser):
    """{command: [(word, kind, values, label, help)]}; kind is "c" for a word, "v" for an option with a value, "f" without."""
    top, sub, _ = build_parser()
    rows = {"": [(a.dest, "c", (), "", tr(a.help)) for a in sub._choices_actions]}
    rows[""].append(("completion", "c", (), "", tr("print a script that adds Tab completion to your shell")))
    shared = [("--lang", "v", ("zh", "en"), "zh|en", tr("language of the text")),
              ("--no-animation", "f", (), "", tr("keep the screen still"))]
    rows[""] += shared + [("-h", "f", (), "", tr("show this help message and exit"))]
    for name, parser in sub.choices.items():
        rows[name] = [(value, "c", (), "", "") for value in POSITIONAL_VALUES.get(name, ())]
        for action in parser._actions:
            help_text = (action.help or "").replace("%%", "%")
            for flag in action.option_strings:
                values = tuple(action.choices or VALUE_HINTS.get(flag, ()))
                rows[name].append((flag, "f" if action.nargs == 0 else "v", values, _label(action), help_text))
        rows[name] += shared
    rows["completion"] = [(shell, "c", (), "", "") for shell in SHELLS]
    return rows


def _ps_text(text: str) -> str:
    """ASCII whatever the code page or the file's encoding; the completer unescapes it when shown."""
    out = text.replace("\\", "\\\\").replace("\t", " ").replace("'", "''")
    return "".join(ch if ch < "\x7f" else f"\\u{ord(ch):04x}" for ch in out)


POWERSHELL = r"""# disc-probe completion for PowerShell, from `python -m discprobe completion powershell`.
# All the data is here, so pressing Tab never starts Python. Generate it again after an update.
$global:DiscprobeCompletion = @{
@TABLE@
}
Register-ArgumentCompleter -Native -CommandName python, python3, py -ScriptBlock {
    param($word, $ast, $cursor)
    $items = @($ast.CommandElements | Where-Object { $_.Extent.EndOffset -lt $cursor -or ($_.Extent.EndOffset -eq $cursor -and -not $word) } |
        ForEach-Object { $_.Extent.Text })
    $start = -1
    for ($i = 1; $i -lt $items.Count - 1; $i++) {
        if ($items[$i] -eq '-m' -and $items[$i + 1] -eq 'discprobe') { $start = $i + 2; break }
    }
    if ($start -lt 0) { return }
    $command = ''; $previous = ''
    for ($i = $start; $i -lt $items.Count; $i++) {
        if (-not $command -and $items[$i] -notlike '-*' -and $previous -ne '--lang') { $command = $items[$i] }
        $previous = $items[$i]
    }
    $rows = $global:DiscprobeCompletion[$command]
    if (-not $rows) { return }
    $values = $null
    foreach ($row in $rows) {
        $f = $row -split "`t"
        if ($f[0] -eq $previous -and $f[1] -eq 'v') { $values = @($f[2] -split ' ' | Where-Object { $_ }); break }
    }
    if ($null -ne $values) {
        if ($previous -eq '--drive') {
            $values = @([System.IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'CDRom' } | ForEach-Object { $_.Name.TrimEnd('\') })
        }
        foreach ($v in $values) {
            if ($v.StartsWith($word, 'OrdinalIgnoreCase')) {
                [System.Management.Automation.CompletionResult]::new($v, $v, 'ParameterValue', $v)
            }
        }
        return
    }
    foreach ($row in $rows) {
        if ($row.StartsWith($word, 'OrdinalIgnoreCase')) {
            $f = $row -split "`t"
            $type = if ($f[1] -eq 'c') { 'ParameterValue' } else { 'ParameterName' }
            $list = if ($f[3]) { "$($f[0]) <$($f[3])>" } else { $f[0] }
            $tip = [regex]::Unescape($f[4])
            $list = [regex]::Unescape($list)
            [System.Management.Automation.CompletionResult]::new($f[0], $list, $type, $(if ($tip) { "$list  $tip" } else { $list }))
        }
    }
}
"""


def powershell(rows) -> str:
    lines = []
    for command, entries in rows.items():
        lines.append(f"'{command}' = @(")
        lines += ["'" + "\t".join((word, kind, " ".join(values), _ps_text(label), _ps_text(text))) + "'"
                  for word, kind, values, label, text in entries]
        lines.append(")")
    return POWERSHELL.replace("@TABLE@", "\n".join(lines))


BASH = r"""# disc-probe completion for bash and zsh, from `python -m discprobe completion`.
# All the data is here, so pressing Tab never starts Python. Generate it again after an update.
_discprobe_complete() {
    local cur=${COMP_WORDS[COMP_CWORD]} previous= command= start=0 i word
    for ((i = 1; i < COMP_CWORD - 1; i++)); do
        if [[ ${COMP_WORDS[i]} == -m && ${COMP_WORDS[i + 1]} == discprobe ]]; then start=$((i + 2)); break; fi
    done
    COMPREPLY=()
    ((start > 0)) || return 0
    for ((i = start; i < COMP_CWORD; i++)); do
        word=${COMP_WORDS[i]}
        case $word in :|=) continue ;; esac     # the shell splits E: and --speed=4x at these
        if [[ -z $command && $word != -* && $word != *[!a-z]* ]]; then
            case $previous in @VALUE_FLAGS@) ;; *) command=$word ;; esac
        fi
        previous=$word
    done
    local words=
    case $previous in
@VALUES@
        @VALUE_FLAGS@) return 0 ;;
    esac
    if [[ -z $words ]]; then
        case $command in
@COMMANDS@
            *) return 0 ;;
        esac
    fi
    COMPREPLY=($(compgen -W "$words" -- "$cur"))
}
"""
BASH_TAIL = "complete -o default -o bashdefault -F _discprobe_complete python python3\n"
ZSH_HEAD = ("(( $+functions[compdef] )) || { autoload -Uz compinit && compinit; }\n"
            "autoload -Uz bashcompinit && bashcompinit\n")


def bash(rows) -> str:
    choices, value_flags = {}, set()
    for entries in rows.values():
        for word, kind, values, _, _ in entries:
            if kind == "v":
                value_flags.add(word)
                if values:
                    choices[word] = values
    values = [f"        {flag}) words=\"{' '.join(v)}\" ;;" for flag, v in sorted(choices.items())]
    commands = ["            " + (command or '""') + ') words="' + " ".join(e[0] for e in entries) + '" ;;'
                for command, entries in rows.items()]
    return (BASH.replace("@VALUE_FLAGS@", "|".join(sorted(value_flags)))
            .replace("@VALUES@", "\n".join(values)).replace("@COMMANDS@", "\n".join(commands))) + BASH_TAIL


def script(shell: str, build_parser) -> str:
    rows = table(build_parser)
    if shell == "powershell":
        return powershell(rows)
    return (ZSH_HEAD if shell == "zsh" else "") + bash(rows)


def main(args: list[str], build_parser, stream) -> None:
    """The script goes straight to the real output, past the line-by-line translation."""
    if len(args) == 1 and args[0] in SHELLS:
        if args[0] != "powershell" and hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="\n")        # Git Bash on Windows cannot read a script with CRLF
        stream.write(script(args[0], build_parser))
        stream.flush()
    elif not args or args[0] in ("-h", "--help"):
        print(block("completion", USAGE))
    else:
        print(block("completion", USAGE), file=sys.stderr)
        sys.exit(2)
