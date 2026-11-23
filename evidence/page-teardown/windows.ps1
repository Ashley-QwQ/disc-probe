param(
    [Parameter(Mandatory=$true)][ValidateSet('edge','close','service','disks')][string]$Action,
    [string]$Profile,
    [int]$BrowserPid
)
$ErrorActionPreference = 'Stop'
if ($Action -eq 'disks') {
    @(Get-PSDrive -Name D,F | Select-Object Name,Free) | ConvertTo-Json -Compress
    exit
}
if ($Action -eq 'service') {
    $p = Get-Process -Id 12472
    [pscustomobject]@{
        time = (Get-Date).ToString('o')
        listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8765 |
            Select-Object LocalAddress, LocalPort, OwningProcess)
        pid = $p.Id
        start_time = $p.StartTime.ToString('o')
        session = $p.SessionId
    } | ConvertTo-Json -Depth 4 -Compress
    exit
}

# Validate a full, quoted or unquoted profile argument, including its end boundary.
$path = [IO.Path]::GetFullPath($Profile).Replace('/', '\')
$pattern = '(?:^|\s)(?:"--user-data-dir=' + [regex]::Escape($path) + '"|--user-data-dir="' +
    [regex]::Escape($path) + '"|--user-data-dir=' + [regex]::Escape($path) + ')(?=\s|$)'
$edge = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'")
$tagged = @($edge | Where-Object { $_.CommandLine -and $_.CommandLine.Replace('/', '\') -match $pattern })
if ($Action -eq 'close') {
    # Every stopped process individually matches the private profile argument.
    foreach ($process in $tagged) {
        $current = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        if ($current -and $current.ProcessName -eq 'msedge' -and
            [math]::Abs(($current.StartTime - $process.CreationDate).TotalSeconds) -lt 1) {
            Stop-Process -InputObject $current -Force -ErrorAction SilentlyContinue
        }
    }
    exit
}

$root = $tagged | Where-Object { $_.ProcessId -eq $BrowserPid }
if (-not $root) { throw 'Edge root does not own the expected profile' }
$members = @{}
foreach ($process in $tagged) { $members[[int]$process.ProcessId] = $process }
do {
    $count = $members.Count
    foreach ($process in $edge) {
        $parent = $members[[int]$process.ParentProcessId]
        if ($parent -and $process.CreationDate -ge $parent.CreationDate) {
            $members[[int]$process.ProcessId] = $process
        }
    }
} while ($members.Count -gt $count)

$sample = Get-Date
$rows = foreach ($process in $members.Values | Sort-Object ProcessId) {
    $p = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    if (-not $p -or [math]::Abs(($p.StartTime - $process.CreationDate).TotalSeconds) -ge 1) { continue }
    $kind = if ($p.Id -eq $BrowserPid) { 'browser' } elseif ($process.CommandLine -match '--type=([^\s"]+)') { $Matches[1] } else { 'other' }
    $subtype = if ($process.CommandLine -match '--utility-sub-type=([^\s"]+)') { $Matches[1] } else { '' }
    [pscustomobject]@{
        pid = $p.Id
        parent_pid = $process.ParentProcessId
        process_type = $kind
        utility_subtype = $subtype
        private_bytes = $p.PrivateMemorySize64
        working_set_bytes = $p.WorkingSet64
    }
}
[pscustomobject]@{ time = $sample.ToString('o'); rows = @($rows) } | ConvertTo-Json -Depth 4 -Compress
