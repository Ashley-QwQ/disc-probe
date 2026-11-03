<#
Burn a 2048-byte-sector ISO with a chosen write speed through Windows IMAPI2 (the API
behind isoburn.exe, which cannot pick a speed). Nothing to install.

  powershell -File tools\burn_imapi.ps1 -Iso D:\disc-probe\iso\rings.iso -SpeedX 4
  powershell -File tools\burn_imapi.ps1 -ListSpeeds

-SpeedX is in DVD units (1x = 1,385,000 bytes/s) for DVD media and CD units
(1x = 176,400 bytes/s of audio, 75 sectors/s) for CD media. The disc is closed after
writing. The drive may still choose its own strategy; the script reports the average
speed it actually achieved.
#>
param(
    [string]$Iso,
    [string]$Drive = "H:",
    [double]$SpeedX = 4,
    [switch]$ListSpeeds
)
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class DiscprobeStream {
    [DllImport("shlwapi.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateStreamOnFileEx(string pszFile, uint grfMode, uint dwAttributes,
        bool fCreate, IStream pstmTemplate, out IStream ppstm);
    public static IStream OpenRead(string path) {
        IStream s;
        SHCreateStreamOnFileEx(path, 0x00000000 | 0x00000020, 0, false, null, out s);  // STGM_READ | STGM_SHARE_DENY_WRITE
        return s;
    }
}
"@

$master = New-Object -ComObject IMAPI2.MsftDiscMaster2
$recorder = $null
foreach ($id in $master) {
    $r = New-Object -ComObject IMAPI2.MsftDiscRecorder2
    $r.InitializeDiscRecorder($id)
    if ($r.VolumePathNames -contains "$Drive\") { $recorder = $r; break }
}
if (-not $recorder) { throw "no recorder at $Drive" }
"Recorder: $($recorder.VendorId.Trim()) $($recorder.ProductId.Trim()) $($recorder.ProductRevision.Trim())"

$fmt = New-Object -ComObject IMAPI2.MsftDiscFormat2Data
$fmt.Recorder = $recorder
$fmt.ClientName = "discprobe"
if (-not $fmt.IsCurrentMediaSupported($recorder)) { throw "the current disc cannot be written by IMAPI2" }
$isCd = $fmt.CurrentPhysicalMediaType -in 2, 3, 4   # CDROM, CDR, CDRW
$oneX = if ($isCd) { 75.0 } else { 1385000.0 / 2048.0 }  # sectors per second at 1x
"Media type $($fmt.CurrentPhysicalMediaType), blank: $($fmt.MediaHeuristicallyBlank), free sectors: $($fmt.FreeSectorsOnMedia)"
"Supported write speeds:"
foreach ($d in $fmt.SupportedWriteSpeedDescriptors) {
    "  {0,6:N1}x  ({1} sectors/s){2}" -f ($d.WriteSpeed / $oneX), $d.WriteSpeed, ($(if ($d.RotationTypeIsPureCAV) { "  pure CAV" } else { "" }))
}
if ($ListSpeeds) { return }

if (-not $Iso -or -not (Test-Path $Iso)) { throw "give -Iso with an existing image" }
if (-not $fmt.MediaHeuristicallyBlank) { throw "the disc is not blank" }
$bytes = (Get-Item $Iso).Length
if ($bytes % 2048 -ne 0) { throw "image size is not a multiple of 2048 bytes" }
if ($bytes / 2048 -gt $fmt.FreeSectorsOnMedia) { throw "image is larger than the free space on the disc" }

$sps = [int][math]::Round($SpeedX * $oneX)
$fmt.SetWriteSpeed($sps, $false)
$fmt.ForceMediaToBeClosed = $true
"Requested {0}x ({1} sectors/s); drive reports current write speed {2} sectors/s ({3:N1}x)" -f `
    $SpeedX, $sps, $fmt.CurrentWriteSpeed, ($fmt.CurrentWriteSpeed / $oneX)

$stream = [DiscprobeStream]::OpenRead((Resolve-Path $Iso).Path)
$t0 = Get-Date
"Writing $Iso ($([math]::Round($bytes / 1e9, 2)) GB) started $t0"
$fmt.Write($stream)
$sec = ((Get-Date) - $t0).TotalSeconds
"Finished in {0:N0} s: average {1:N2}x including lead-in/out and closing" -f $sec, (($bytes / 2048) / $sec / $oneX)
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($stream) | Out-Null
