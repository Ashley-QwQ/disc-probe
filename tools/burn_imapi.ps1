<#
Burn an ISO image with Windows' own IMAPI2 at a chosen write speed (isoburn.exe cannot set one).

Without -Burn it only reports the recorder, the media, its blank state and the supported write
speeds, and writes nothing. With -Burn it writes the image as one closed session at the
nearest speed the drive lists.

  powershell -ExecutionPolicy Bypass -File tools\burn_imapi.ps1 -Drive H: -Iso iso\x.iso
  powershell -ExecutionPolicy Bypass -File tools\burn_imapi.ps1 -Drive H: -Iso iso\x.iso -Speed 8 -Burn

-Speed is in multiples of the medium's 1x (CD 75 sectors/s, DVD 675 sectors/s).
-Reload closes the tray again after the eject (tray-loading drives such as the GH70N), so the
burned disc can be read straight away.

Closing a CD needs some room beyond FreeSectorsOnMedia: on a 359,847-sector CD-R a 359,800-sector
image was refused at the start of Write ("stream too large"), 359,600 sectors went through.
#>
param(
    [string]$Drive = "H:",
    [string]$Iso,
    [double]$Speed = 0,
    [switch]$Burn,
    [switch]$Reload
)
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class IsoStream {
    [DllImport("shlwapi.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateStreamOnFileEx(string file, uint mode, uint attrs, bool create, IntPtr template, out IStream stream);
    public static IStream Open(string path) {
        IStream s;
        SHCreateStreamOnFileEx(path, 0x20 /* STGM_READ | STGM_SHARE_DENY_WRITE */, 0, false, IntPtr.Zero, out s);
        return s;
    }
}
"@

$master = New-Object -ComObject IMAPI2.MsftDiscMaster2
$recorder = $null
foreach ($id in $master) {
    $r = New-Object -ComObject IMAPI2.MsftDiscRecorder2
    $r.InitializeDiscRecorder($id)
    if ($r.VolumePathNames -contains ($Drive.TrimEnd('\') + '\')) { $recorder = $r }
}
if (-not $recorder) { throw "no IMAPI2 recorder at $Drive" }
"Recorder: $($recorder.VendorId.Trim()) $($recorder.ProductId.Trim()) rev $($recorder.ProductRevision) at $Drive"

$fmt = New-Object -ComObject IMAPI2.MsftDiscFormat2Data
if (-not $fmt.IsRecorderSupported($recorder)) { throw "recorder not supported for data writing" }
$fmt.Recorder = $recorder
$fmt.ClientName = "discprobe"
if (-not $fmt.IsCurrentMediaSupported($recorder)) { throw "no writable medium in $Drive" }

# IMAPI_MEDIA_PHYSICAL_TYPE: 2 CD-R, 3 CD-RW, 6 DVD+R, 8 DVD-R, ...
$type = $fmt.CurrentPhysicalMediaType
$isCd = $type -in 1, 2, 3
$unit = if ($isCd) { 75 } else { 675 }
"Media type $type ($(if ($isCd) {'CD'} else {'DVD'})), blank: $($fmt.MediaHeuristicallyBlank), " +
    "free sectors: $($fmt.FreeSectorsOnMedia), total: $($fmt.TotalSectorsOnMedia)"
$speeds = @($fmt.SupportedWriteSpeedDescriptors | ForEach-Object {
    "{0:0.#}x ({1} sectors/s, {2})" -f ($_.WriteSpeed / $unit), $_.WriteSpeed, $(if ($_.RotationTypeIsPureCAV) {'CAV'} else {'CLV/ZCLV'})
})
"Supported write speeds: " + ($speeds -join "; ")

if (-not $Iso) { return }
$path = (Resolve-Path $Iso).Path
$sectors = (Get-Item $path).Length / 2048
"Image: $path, $sectors sectors"
if ($sectors -gt $fmt.FreeSectorsOnMedia) { throw "image is larger than the free space on the medium" }
if (-not $Burn) { "Dry run: nothing written (add -Burn to write)."; return }
if (-not $fmt.MediaHeuristicallyBlank) { throw "medium is not blank; refusing to write" }

if ($Speed -gt 0) {
    # Ask for the nearest speed the drive lists: its 8x can be 5410 sectors/s on DVD, and asking
    # for 5400 falls to the 4x below.
    $want = $Speed * $unit
    $nearest = $fmt.SupportedWriteSpeedDescriptors | Sort-Object { [math]::Abs($_.WriteSpeed - $want) } | Select-Object -First 1
    $fmt.SetWriteSpeed($(if ($nearest) { $nearest.WriteSpeed } else { [int]$want }), $false)
}
"Requested write speed: $(if ($Speed -gt 0) {"${Speed}x"} else {'drive default'}); " +
    "drive reports {0:0.#}x" -f ($fmt.CurrentWriteSpeed / $unit)
$fmt.ForceMediaToBeClosed = $true
$stream = [IsoStream]::Open($path)
$t0 = Get-Date
"Writing ... (started $($t0.ToString('HH:mm:ss')))"
$fmt.Write($stream)
"Done in {0:0.0} min" -f ((Get-Date) - $t0).TotalMinutes
$recorder.EjectMedia()
if ($Reload) {
    Start-Sleep -Seconds 2
    $recorder.CloseTray()
    "Tray closed again."
}
