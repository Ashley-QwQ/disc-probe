# Standalone Windows helpers share the core's byte-zero drive lock.
function Read-DiscProbeDriveOwner($File) {
    try {
        $File.Position = 1
        $raw = [byte[]]::new(1024)
        $count = $File.Read($raw, 0, $raw.Length)
        [Text.Encoding]::UTF8.GetString($raw, 0, $count) | ConvertFrom-Json
    } catch {}
}

function Assert-DiscProbeBusy($Owner) {
    $names = @{burn='刻录'; erase='擦除'; info='读取光驱信息'; disc='检查光盘'; whois='读取光盘身份';
               swap='等待换盘'; timing='计时测量'; geo='几何测量'; label='读取光盘会话'; verify='刻后验证';
               calibrate='校准'}
    $zh = $en = ''
    if ($Owner.pid -and $Owner.action -and $names.ContainsKey($Owner.action)) {
        $zh = "（pid $($Owner.pid)，正在：$($names[$Owner.action])）"
        $en = " (pid $($Owner.pid), action: $($Owner.action))"
    }
    throw "这台光驱正在被另一个窗口或命令使用$zh。等它结束再试。 / This drive is in use by another window or command$en. Wait for it to finish and try again."
}

function Open-DiscProbeLane([string]$Path, [switch]$Existing) {
    $mode = if ($Existing) { 'Open' } else { 'OpenOrCreate' }
    $file = [IO.File]::Open($Path, $mode, 'ReadWrite', 'ReadWrite')
    try {
        $file.Lock(0, 1)
    } catch {
        $code = $_.Exception.GetBaseException().HResult -band 0xFFFF
        if ($code -ne 33) { $file.Dispose(); throw }
        try { $owner = Read-DiscProbeDriveOwner $file } finally { $file.Dispose() }
        Assert-DiscProbeBusy $owner
    }
    return $file
}

function Open-DiscProbeDriveLock([string]$Drive, [string]$Action) {
    if ($Drive -notmatch '(?i)^(?:\\\\[.?]\\)?([a-z])[:\\/]*$') {
        throw "请指定光驱盘符，例如 E:。 / Expected a drive letter such as E:."
    }
    $letter = $Matches[1].ToUpperInvariant()
    $base = $env:LOCALAPPDATA
    if (-not $base) { $base = Join-Path $HOME '.local\state' }
    $root = Join-Path $base 'disc-probe\drive-locks'
    [IO.Directory]::CreateDirectory($root) | Out-Null
    $gate = Join-Path $root "$letter.lock"
    $worker = Join-Path $root "$letter.worker"
    $native = Join-Path $root "$letter.native"
    $parent = if ($env:DISCPROBE_PARENT_DRIVE_LEASE) { $env:DISCPROBE_PARENT_DRIVE_LEASE | ConvertFrom-Json }
    if ($parent.path -eq $gate -and $parent.owner -in @($gate, $worker) -and $parent.token) {
        $file = Open-DiscProbeLane $native
    } else {
        $parent = $null
        $file = Open-DiscProbeLane $gate
    }
    try {
        if ($parent) {
            $parentFile = [IO.File]::Open($parent.owner, 'Open', 'ReadWrite', 'ReadWrite')
            try {
                $active = $false
                try { $parentFile.Lock(0, 1) } catch {
                    if (($_.Exception.GetBaseException().HResult -band 0xFFFF) -ne 33) { throw }
                    $active = $true
                }
                $owner = Read-DiscProbeDriveOwner $parentFile
                if (-not $active -or $owner.token -cne $parent.token) { Assert-DiscProbeBusy $null }
            } finally { $parentFile.Dispose() }
        } else {
            foreach ($lane in @($worker, $native)) {
                if ([IO.File]::Exists($lane)) {
                    $probe = Open-DiscProbeLane $lane -Existing
                    $probe.Dispose()
                }
            }
        }
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
