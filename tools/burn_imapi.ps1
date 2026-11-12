<#
Burn an ISO image with Windows' own IMAPI2 at a chosen write speed (isoburn.exe cannot set one).

Without -Burn it only reports the recorder, the media, its blank state and the supported write
speeds, and writes nothing. With -Burn it writes the image as one closed session at the
nearest speed the drive lists.

  powershell -ExecutionPolicy Bypass -File tools\burn_imapi.ps1 -Drive H: -Iso iso\x.iso
  powershell -ExecutionPolicy Bypass -File tools\burn_imapi.ps1 -Drive H: -Iso iso\x.iso -Speed 8 -Burn

-Speed is in multiples of the medium's 1x (CD 75 sectors/s, DVD 675 sectors/s).
Windows' read-back check after the burn is turned off, as DiscImageStudio does. Picture data can be
slow or hard to read back, and a failed check reports the whole burn as failed after the data is
already on the disc. -Verify keeps Windows' default check.

-KeepOpen leaves the disc open after this session, so another can be added later. -Append adds a
session to such a disc; it needs -ExpectStart with the LBA the image was made for (`image --start-lba`,
from the next writable address `info` prints), and refuses if the drive would write anywhere else.

-Reload closes the tray again after the eject (tray-loading drives such as the GH70N), so the
burned disc can be read straight away. Without it, push the tray back in before measuring.

While writing it prints a line every 30 s with an estimate from the write speed. That estimate
is time only: IMAPI2's progress events would have to run inside the burn, and a burn can't be
retried on the same disc, so this stays out of the way of the write.

If Write fails, the script says whether that came before or after the time the data should have
taken, and gives the error code. IMAPI2 often reports only E_FAIL, with no reason.

Closing a CD needs some room beyond FreeSectorsOnMedia: on a 359,847-sector CD-R a 359,800-sector
image was refused at the start of Write ("stream too large"), 359,600 sectors went through.
#>
param(
    [string]$Drive = "H:",
    [string]$Iso,
    [double]$Speed = 0,
    [switch]$Burn,
    [switch]$Verify,
    [switch]$Reload,
    [switch]$KeepOpen,
    [switch]$Append,
    [long]$ExpectStart = -1,
    [switch]$Machine,
    [string]$CancelFile,
    [string]$IdentityPatch,
    [long]$IdentityOffset = 43008
)
$ErrorActionPreference = "Stop"
if ($IdentityPatch -and -not $Machine) { throw "Identity patches require Machine mode" }

Add-Type -ReferencedAssemblies System.dll,System.Core.dll,Microsoft.CSharp.dll -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using STATSTG = System.Runtime.InteropServices.ComTypes.STATSTG;
// A seekable, read-only IStream overlay. IMAPI sees the patched bytes while
// the original ISO stays open with FileAccess.Read and cannot be rewritten.
[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public sealed class IdentityStream : IStream, IDisposable {
    readonly System.IO.FileStream source;
    readonly byte[] patch;
    readonly long offset;
    readonly byte[][] parts;
    readonly long[] offsets;
    readonly string imagePath;
    public IdentityStream(string image, string patchFile, long patchOffset)
        : this(image, System.IO.File.ReadAllBytes(patchFile), patchOffset) { }
    IdentityStream(string image, byte[] patchBytes, long patchOffset) {
        patch = patchBytes;
        if (patchOffset != 43008) throw new ArgumentException("Invalid identity patch extent.");
        if (patch.Length == 8192) {
            parts = new byte[][] { patch }; offsets = new long[] { patchOffset };
        } else {
            using (var input = new System.IO.BinaryReader(new System.IO.MemoryStream(patch))) {
                if (System.Text.Encoding.ASCII.GetString(input.ReadBytes(8)) != "DPIDPAT2")
                    throw new ArgumentException("Invalid identity patch bundle.");
                int count = input.ReadInt32();
                if (count != 4) throw new ArgumentException("Invalid identity copy count.");
                parts = new byte[count][]; offsets = new long[count];
                for (int i = 0; i < count; i++) {
                    offsets[i] = input.ReadInt64(); int length = input.ReadInt32();
                    if (length != 8192 || offsets[i] < 43008 ||
                        (i > 0 && offsets[i] < offsets[i-1] + 8192))
                        throw new ArgumentException("Invalid identity copy extent.");
                    parts[i] = input.ReadBytes(length);
                    if (parts[i].Length != length) throw new ArgumentException("Short identity bundle.");
                }
                if (input.BaseStream.Position != patch.Length) throw new ArgumentException("Trailing identity bundle.");
            }
        }
        source = new System.IO.FileStream(image, System.IO.FileMode.Open, System.IO.FileAccess.Read, System.IO.FileShare.Read);
        offset = patchOffset;
        imagePath = image;
        if (offsets[offsets.Length-1] + parts[parts.Length-1].Length > source.Length) {
            source.Dispose(); throw new ArgumentException("Short ISO.");
        }
    }
    public void Read(byte[] buffer, int count, IntPtr read) {
        long start = source.Position;
        int n = source.Read(buffer, 0, count);
        for (int i = 0; i < parts.Length; i++) {
            long lo = Math.Max(start, offsets[i]), hi = Math.Min(start + n, offsets[i] + parts[i].Length);
            if (lo < hi) Array.Copy(parts[i], lo - offsets[i], buffer, lo - start, hi - lo);
        }
        if (read != IntPtr.Zero) Marshal.WriteInt32(read, n);
    }
    public void Seek(long move, int origin, IntPtr position) {
        long p = source.Seek(move, (System.IO.SeekOrigin)origin);
        if (position != IntPtr.Zero) Marshal.WriteInt64(position, p);
    }
    public void Stat(out STATSTG stat, int flags) { stat = new STATSTG(); stat.type = 2; stat.cbSize = source.Length; }
    public void CopyTo(IStream target, long count, IntPtr read, IntPtr written) {
        byte[] buffer = new byte[65536]; long total = 0;
        IntPtr got = Marshal.AllocHGlobal(4), put = Marshal.AllocHGlobal(4);
        try {
            while (total < count) {
                Read(buffer, (int)Math.Min(buffer.Length, count - total), got);
                int n = Marshal.ReadInt32(got); if (n == 0) break;
                target.Write(buffer, n, put);
                if (Marshal.ReadInt32(put) != n) throw new System.IO.IOException("Short stream write.");
                total += n;
            }
            if (read != IntPtr.Zero) Marshal.WriteInt64(read, total);
            if (written != IntPtr.Zero) Marshal.WriteInt64(written, total);
        } finally { Marshal.FreeHGlobal(got); Marshal.FreeHGlobal(put); }
    }
    public void Write(byte[] b, int n, IntPtr w) { throw new NotSupportedException(); }
    public void SetSize(long n) { throw new NotSupportedException(); }
    public void Commit(int flags) { }
    public void Revert() { throw new NotSupportedException(); }
    public void LockRegion(long o, long n, int t) { throw new NotSupportedException(); }
    public void UnlockRegion(long o, long n, int t) { throw new NotSupportedException(); }
    public void Clone(out IStream stream) {
        IdentityStream clone = new IdentityStream(imagePath, patch, offset);
        clone.Seek(source.Position, 0, IntPtr.Zero); stream = clone;
    }
    public void Dispose() { source.Dispose(); }
}
public static class IsoStream {
    [DllImport("shlwapi.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateStreamOnFileEx(string file, uint mode, uint attrs, bool create, IntPtr template, out IStream stream);
    public static IStream Open(string path) {
        IStream s;
        SHCreateStreamOnFileEx(path, 0x20 /* STGM_READ | STGM_SHARE_DENY_WRITE */, 0, false, IntPtr.Zero, out s);
        return s;
    }
}
// Windows SDK imapi2.idl. It is IUnknown, not the format's IDispatch, so PowerShell can't reach it directly.
[ComImport, Guid("D2FFD834-958B-426D-8470-2A13879C6A91"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IBurnVerification {
    void SetBurnVerificationLevel(int value);   // the setter comes first in the vtable
    int GetBurnVerificationLevel();
}
public static class BurnCheck {
    // 0 none, 1 quick, 2 full. Returns what the format reports afterwards.
    public static int Set(object format, int level) {
        IBurnVerification v = (IBurnVerification)format;
        v.SetBurnVerificationLevel(level);
        return v.GetBurnVerificationLevel();
    }
}
// Isolated JSONL mode. No recording or exclusive access is acquired by Inspect.
public static class MachineBurn {
    static readonly Guid Events = new Guid("2735413C-7F64-5B0F-8F00-5D77AFBE261E");
    public delegate void UpdateHandler([MarshalAs(UnmanagedType.IDispatch)] object sender,
                                      [MarshalAs(UnmanagedType.IDispatch)] object progress);
    static void Emit(string value) { Console.WriteLine(value); Console.Out.Flush(); }
    static string Number(double value) { return value.ToString(System.Globalization.CultureInfo.InvariantCulture); }
    static string Quote(string value) { return value == null ? "null" : "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", "") + "\""; }
    public static void Run(string drive, string image, double speed, bool burn, string cancel) {
        RunPatched(drive, image, speed, burn, cancel, "", 43008);
    }
    public static void RunPatched(string drive, string image, double speed, bool burn, string cancel, string patch, long offset) {
        RunWithFactory(drive, image, speed, burn, cancel,
            name => Activator.CreateInstance(Type.GetTypeFromProgID(name)),
            (format, handler) => ComEventsHelper.Combine(format, Events, 0x200, handler),
            (format, handler) => ComEventsHelper.Remove(format, Events, 0x200, handler), patch, offset);
    }
    // Injectable COM creation/event boundary for offline tests. Production uses only Run above.
    public static void RunWithFactory(string drive, string image, double speed, bool burn, string cancel,
        Func<string, object> create, Action<object, UpdateHandler> subscribe, Action<object, UpdateHandler> unsubscribe,
        string patch = "", long offset = 43008) {
        object masterObject = null, recorderObject = null, formatObject = null;
        IStream stream = null;
        UpdateHandler handler = null;
        bool subscribed = false;
        var clock = System.Diagnostics.Stopwatch.StartNew();
        try {
            masterObject = create("IMAPI2.MsftDiscMaster2");
            dynamic master = masterObject;
            for (int i = 0; i < (int)master.Count; i++) {
                object candidate = create("IMAPI2.MsftDiscRecorder2");
                dynamic r = candidate;
                r.InitializeDiscRecorder(master[i]);
                bool found = false;
                foreach (string volume in r.VolumePathNames)
                    if (String.Equals(volume.TrimEnd('\\'), drive.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) found = true;
                if (found) { recorderObject = candidate; break; }
                if (Marshal.IsComObject(candidate)) Marshal.FinalReleaseComObject(candidate);
            }
            if (recorderObject == null) throw new InvalidOperationException("No recorder at requested drive.");
            dynamic recorder = recorderObject;
            formatObject = create("IMAPI2.MsftDiscFormat2Data");
            dynamic fmt = formatObject;
            fmt.Recorder = recorder;
            fmt.ClientName = "discprobe-burn";
            if (!fmt.IsCurrentMediaSupported(recorder)) throw new InvalidOperationException("No writable medium.");
            int physical = (int)fmt.CurrentPhysicalMediaType;
            // Physical type plus CURRENT profile, never recorder-supported profiles.
            int profile = 0;
            foreach (object p in recorder.CurrentProfiles) {
                int v = Convert.ToInt32(p);
                if ((physical == 6 && v == 0x1B) || (physical == 7 && v == 0x1A) ||
                    (physical == 8 && v == 0x2B) || (physical == 9 && v == 0x11) ||
                    (physical == 10 && (v == 0x13 || v == 0x14)) ||
                    (physical == 11 && (v == 0x15 || v == 0x16)) ||
                    (physical == 13 && v == 0x2A)) profile = v;
            }
            if (profile == 0) throw new InvalidOperationException("Inserted medium is not a supported writable DVD.");
            bool blank = (bool)fmt.MediaPhysicallyBlank && (((int)fmt.CurrentMediaStatus & 2) != 0);
            long free = (long)fmt.FreeSectorsOnMedia;
            var speeds = new System.Collections.Generic.List<int>();
            foreach (object s in fmt.SupportedWriteSpeeds) {
                int value = Convert.ToInt32(s);
                if (value > 0 && !speeds.Contains(value)) speeds.Add(value);
            }
            speeds.Sort();
            if (!burn) {
                var values = speeds.ConvertAll(s => Number(s / 675.0));
                Emit("{\"media\":\"dvd\",\"blank\":" + (blank ? "true" : "false") +
                     ",\"vendor\":" + Quote((string)recorder.VendorId) + ",\"product\":" + Quote((string)recorder.ProductId) +
                     ",\"firmware\":" + Quote((string)recorder.ProductRevision) +
                     ",\"free_sectors\":" + free + ",\"speeds_x\":[" + String.Join(",", values) + "]}");
                return;
            }
            if (!blank) throw new InvalidOperationException("Disc is not physically blank; refusing write.");
            long bytes = new System.IO.FileInfo(image).Length;
            if (bytes <= 0 || bytes % 2048 != 0 || bytes / 2048 > free)
                throw new InvalidOperationException("Image size invalid or exceeds free sectors.");
            if (speeds.Count == 0) throw new InvalidOperationException("No supported write speeds.");
            int chosen = speeds[0];
            if (speed > 0) {
                foreach (int s in speeds) if (Math.Abs(s / 675.0 - speed) < Math.Abs(chosen / 675.0 - speed)) chosen = s;
                if (Math.Abs(chosen / 675.0 - speed) > Math.Max(.03, speed * .01))
                    throw new InvalidOperationException("Requested speed unsupported by inserted disc.");
            }
            fmt.BufferUnderrunFreeDisabled = false;
            fmt.ForceMediaToBeClosed = true;
            fmt.ForceOverwrite = false;
            if (BurnCheck.Set(formatObject, 0) != 0) throw new InvalidOperationException("Cannot disable verification.");
            fmt.SetWriteSpeed(chosen, false);
            int actualSpeed = (int)fmt.CurrentWriteSpeed;
            if (actualSpeed <= 0) throw new InvalidOperationException("Recorder did not report a valid actual speed.");
            Emit("{\"type\":\"speed\",\"actual_x\":" + Number(actualSpeed / 675.0) + "}");
            handler = delegate(object sender, object data) {
                dynamic update = data;
                if (!String.IsNullOrEmpty(cancel) && System.IO.File.Exists(cancel)) {
                    ((dynamic)sender).CancelWrite();
                    return;
                }
                double count = (double)update.SectorCount;
                double fraction = count > 0 ? ((double)update.LastWrittenLba - (double)update.StartLba + 1) / count : 0;
                // Data completion is not session completion. Keep the bar below 100% until Write returns.
                fraction = Math.Max(0, Math.Min(.999, fraction));
                Emit("{\"type\":\"progress\",\"fraction\":" + Number(fraction) +
                     ",\"elapsed_s\":" + Number((double)update.ElapsedTime) +
                     ",\"eta_s\":" + Number((double)update.RemainingTime) +
                     ",\"stage\":\"imapi-" + (int)update.CurrentAction + "\"}");
            };
            subscribe(formatObject, handler);
            subscribed = true;
            stream = String.IsNullOrEmpty(patch) ? IsoStream.Open(image) : new IdentityStream(image, patch, offset);
            if (!String.IsNullOrEmpty(cancel) && System.IO.File.Exists(cancel))
                throw new OperationCanceledException("Cancelled before Write.");
            fmt.Write(stream); // exactly once; never retry a failed WRITE
            Emit("{\"type\":\"progress\",\"fraction\":1,\"elapsed_s\":" + Number(clock.Elapsed.TotalSeconds) + ",\"eta_s\":0,\"stage\":\"completed\"}");
        } catch (Exception e) {
            Exception detail = e;
            while (detail.InnerException != null) detail = detail.InnerException;
            Console.Error.WriteLine("Burn/inspection failed. Details: 0x" + detail.HResult.ToString("X8") + " " + detail.Message);
            throw;
        } finally {
            if (subscribed) unsubscribe(formatObject, handler);
            if (stream is IDisposable) ((IDisposable)stream).Dispose();
            else if (stream != null && Marshal.IsComObject(stream)) Marshal.FinalReleaseComObject(stream);
            if (formatObject != null && Marshal.IsComObject(formatObject)) Marshal.FinalReleaseComObject(formatObject);
            if (recorderObject != null && Marshal.IsComObject(recorderObject)) Marshal.FinalReleaseComObject(recorderObject);
            if (masterObject != null && Marshal.IsComObject(masterObject)) Marshal.FinalReleaseComObject(masterObject);
        }
    }
}
"@

if ($Machine) {
    if ($Verify -or $Reload -or $KeepOpen -or $Append) { throw "Machine mode does not accept legacy session options" }
    try { [MachineBurn]::RunPatched($Drive, $Iso, $Speed, [bool]$Burn, $CancelFile, $IdentityPatch, $IdentityOffset) }
    catch { exit 1 }
    exit 0
}

function Get-WrittenTo($Recorder) {
    # Where the drive would write next, asked afresh after the failure; $null when it won't say (tray out, busy).
    try {
        $f = New-Object -ComObject IMAPI2.MsftDiscFormat2Data
        $f.Recorder = $Recorder
        if ($f.IsCurrentMediaSupported($Recorder) -and -not $f.MediaHeuristicallyBlank) { return [long]$f.NextWritableAddress }
    } catch { }
    return $null
}

function Write-BurnFailure($Failure, [double]$Seconds, [double]$EstimateSeconds, [string]$DriveName,
                           $Recorder = $null, [long]$StartLba = 0, [long]$ImageSectors = 0) {
    # The picture may be on the disc already, so the bare COM error says too little and sounds too final.
    # The drive's next writable address says how far it got; time alone misled once (a drive at half speed).
    $minutes = "{0:0.0} min" -f ($Seconds / 60)
    $next = if ($Recorder -and $ImageSectors -gt 0) { Get-WrittenTo $Recorder } else { $null }
    if ($null -ne $next -and $next -gt $StartLba) {
        $written = $next - $StartLba
        if ($written -lt 0.99 * $ImageSectors) {
            "The burn failed after $minutes. The drive stopped at LBA ${next}: it wrote {0} of {1} sectors ({2:0} %)." -f $written, $ImageSectors, (100 * $written / $ImageSectors)
        } else {
            "The burn reported an error after $minutes, but the drive says the data is all on the disc (next writable LBA $next): closing it failed."
        }
    } elseif ($EstimateSeconds -gt 0 -and $Seconds -ge 0.95 * $EstimateSeconds) {
        "The burn reported an error after $minutes, around or past the time the data should have taken."
        "So the data has probably reached the disc and closing it failed. That is a guess from the time; the drive did not say how far it got."
    } elseif ($EstimateSeconds -gt 0) {
        "The burn failed partway, after $minutes of about {0:0.0} min: the disc holds only part of the image." -f ($EstimateSeconds / 60)
    } else {
        "The burn failed after $minutes."
    }
    "Error code 0x{0:X8}: {1}" -f $Failure.Exception.HResult, $Failure.Exception.Message
    "To see what the disc holds: python -m discprobe info --drive $DriveName"
}

function Start-WriteHeartbeat([double]$EstimateSeconds, [int]$EverySeconds = 30) {
    # Write() blocks this thread, so another runspace does the talking. It touches no IMAPI2 object.
    $beat = [powershell]::Create()
    [void]$beat.AddScript({
        param($estimate, $every)
        $clock = { param($s) $t = [int][math]::Floor($s); "{0}:{1:00}" -f [math]::Floor($t / 60), ($t % 60) }
        $t0 = Get-Date
        while ($true) {
            Start-Sleep -Seconds $every
            $done = ((Get-Date) - $t0).TotalSeconds
            $left = $estimate - $done
            $state = if ($estimate -le 0) { "no estimate" }
                     elseif ($left -gt 0) { "about $(& $clock $left) left" }
                     else { "past the estimate, closing the disc can take a while" }
            [Console]::WriteLine("  still writing: $(& $clock $done) so far, $state")
        }
    }).AddArgument($EstimateSeconds).AddArgument($EverySeconds)
    [void]$beat.BeginInvoke()
    $beat
}

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
    "free sectors: $($fmt.FreeSectorsOnMedia), total: $($fmt.TotalSectorsOnMedia), next writable LBA: $($fmt.NextWritableAddress)"
$speeds = @($fmt.SupportedWriteSpeedDescriptors | ForEach-Object {
    "{0:0.#}x ({1} sectors/s, {2})" -f ($_.WriteSpeed / $unit), $_.WriteSpeed, $(if ($_.RotationTypeIsPureCAV) {'CAV'} else {'CLV/ZCLV'})
})
"Supported write speeds: " + ($speeds -join "; ")

if (-not $Iso) { return }
$path = (Resolve-Path $Iso).Path
$sectors = (Get-Item $path).Length / 2048
"Image: $path, $sectors sectors"
if ($sectors -gt $fmt.FreeSectorsOnMedia) { throw "image is larger than the free space on the medium" }
if ($Append) {
    # The image's bytes depend on where they land, so the start has to be exactly the one it was made for.
    if ($ExpectStart -lt 0) { throw "-Append needs -ExpectStart, the LBA the image was made for" }
    if ($fmt.MediaHeuristicallyBlank) { throw "the medium is blank; there is nothing to append to" }
    if ($fmt.NextWritableAddress -ne $ExpectStart) {
        throw "the drive would write at LBA $($fmt.NextWritableAddress), not at $ExpectStart; make the image for that LBA"
    }
} elseif (-not $fmt.MediaHeuristicallyBlank) { throw "medium is not blank; refusing to write (-Append adds a session)" }
if (-not $Burn) { "Dry run: nothing written (add -Burn to write)."; return }

if ($Speed -gt 0) {
    # Ask for the nearest speed the drive lists: its 8x can be 5410 sectors/s on DVD, and asking
    # for 5400 falls to the 4x below.
    $want = $Speed * $unit
    $nearest = $fmt.SupportedWriteSpeedDescriptors | Sort-Object { [math]::Abs($_.WriteSpeed - $want) } | Select-Object -First 1
    $fmt.SetWriteSpeed($(if ($nearest) { $nearest.WriteSpeed } else { [int]$want }), $false)
}
"Requested write speed: $(if ($Speed -gt 0) {"${Speed}x"} else {'drive default'}); " +
    "drive reports {0:0.#}x" -f ($fmt.CurrentWriteSpeed / $unit)
$fmt.ForceMediaToBeClosed = -not $KeepOpen
if ($KeepOpen) { "The disc stays open for another session." }
if (-not $Verify) {
    $level = [BurnCheck]::Set($fmt, 0)
    if ($level -ne 0) { throw "Windows did not accept turning off its check after the burn (level $level); nothing was written" }
    "Windows' check after the burn: off (-Verify turns it on)"
}
$stream = [IsoStream]::Open($path)
$t0 = Get-Date
"Writing ... (started $($t0.ToString('HH:mm:ss')))"
$estimate = if ($fmt.CurrentWriteSpeed -gt 0) { $sectors / $fmt.CurrentWriteSpeed } else { 0 }
if ($estimate -gt 0) { "The drive does not report progress here. Estimate from the write speed: about {0:0} min." -f ($estimate / 60) }
$beat = Start-WriteHeartbeat $estimate
try {
    try { $fmt.Write($stream) } finally { $beat.Stop(); $beat.Dispose() }
} catch {
    Write-BurnFailure $_ ((Get-Date) - $t0).TotalSeconds $estimate $Drive $recorder $(if ($Append) { $ExpectStart } else { 0 }) $sectors
    exit 1
}
"Done in {0:0.0} min" -f ((Get-Date) - $t0).TotalMinutes
$recorder.EjectMedia()
$closed = $false
if ($Reload) {
    Start-Sleep -Seconds 2
    # Slot and slim drives can't pull the tray in. The burn is already done, so this must not fail the script.
    try { $recorder.CloseTray(); $closed = $true } catch { }
}
if ($closed) { "Tray closed again. Give the drive a few seconds to read the disc." }
else { "The drive ejected the disc. Push the tray back in and wait a few seconds before measuring it." }
