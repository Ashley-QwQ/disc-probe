# Standalone Windows helpers share the core's byte-zero drive lock.
function Open-DiscProbeDriveLock([string]$Drive, [string]$Action) {
    if ($Drive -notmatch '(?i)^(?:\\\\[.?]\\)?([a-z])[:\\/]*$') {
        throw "Expected a drive letter such as E:."
    }
    $letter = $Matches[1].ToUpperInvariant()
    $base = $env:LOCALAPPDATA
    if (-not $base) { $base = Join-Path $HOME '.local\state' }
    $root = Join-Path $base 'disc-probe\drive-locks'
    [IO.Directory]::CreateDirectory($root) | Out-Null
    $file = [IO.File]::Open((Join-Path $root "$letter.lock"), 'OpenOrCreate', 'ReadWrite', 'ReadWrite')
    try {
        $file.Lock(0, 1)
    } catch {
        $code = $_.Exception.GetBaseException().HResult -band 0xFFFF
        if ($code -ne 33) { $file.Dispose(); throw }
        $owner = $null
        try {
            $file.Position = 1
            $raw = [byte[]]::new(1024)
            $count = $file.Read($raw, 0, $raw.Length)
            $owner = [Text.Encoding]::UTF8.GetString($raw, 0, $count) | ConvertFrom-Json
        } catch {} finally { $file.Dispose() }
        $names = @{burn='刻录'; erase='擦除'; info='读取光驱信息'; disc='检查光盘'; whois='读取光盘身份';
                   swap='等待换盘'; timing='计时测量'; geo='几何测量'; label='读取光盘会话'; verify='刻后验证'}
        $zh = $en = ''
        if ($owner.pid -and $owner.action -and $names.ContainsKey($owner.action)) {
            $zh = "（pid $($owner.pid)，正在：$($names[$owner.action])）"
            $en = " (pid $($owner.pid), action: $($owner.action))"
        }
        throw "这台光驱正在被另一个窗口或命令使用$zh。等它结束再试。 / This drive is in use by another window or command$en. Wait for it to finish and try again."
    }
    try {
        $raw = [Text.Encoding]::UTF8.GetBytes((@{pid=$PID;action=$Action;drive="${letter}:"} | ConvertTo-Json -Compress))
        $file.Position = 1
        $file.Write($raw, 0, $raw.Length)
        $file.SetLength($file.Position)
        $file.Flush()
        return $file
    } catch {
        $file.Dispose()
        throw
    }
}

function Close-DiscProbeDriveLock($Lease) {
    if ($null -ne $Lease) {
        try { $Lease.SetLength(1) } finally { $Lease.Dispose() }
    }
}
