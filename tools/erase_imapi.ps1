param([Parameter(Mandatory=$true)][string]$Drive, [switch]$Full, [switch]$CoreDriveLock)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'drive_lock.ps1')
$driveLease = Open-DiscProbeDriveLock $Drive 'erase'
try {
# Compile only here; -File is an explicit destructive operation. No legacy burn script changes state.
Add-Type -ReferencedAssemblies System.dll,System.Core.dll,Microsoft.CSharp.dll -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class MachineErase {
    static readonly Guid Events = new Guid("2735413A-7F64-5B0F-8F00-5D77AFBE261E");
    public delegate void UpdateHandler([MarshalAs(UnmanagedType.IDispatch)] object sender, int elapsed, int total);
    public static void Run(string drive, bool full) {
        RunWithFactory(drive, full, n => Activator.CreateInstance(Type.GetTypeFromProgID(n)),
            (f,h) => ComEventsHelper.Combine(f, Events, 0x200, h),
            (f,h) => ComEventsHelper.Remove(f, Events, 0x200, h));
    }
    public static void RunWithFactory(string drive, bool full, Func<string,object> create,
        Action<object,UpdateHandler> subscribe, Action<object,UpdateHandler> unsubscribe) {
        object masterObject=null, recorderObject=null, formatObject=null;
        UpdateHandler handler=null; bool subscribed=false;
        try {
            masterObject=create("IMAPI2.MsftDiscMaster2"); dynamic master=masterObject;
            for(int i=0;i<(int)master.Count;i++) {
                object candidate=create("IMAPI2.MsftDiscRecorder2"); dynamic r=candidate;
                r.InitializeDiscRecorder(master[i]); bool found=false;
                foreach(string volume in r.VolumePathNames)
                    if(String.Equals(volume.TrimEnd('\\'),drive.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase)) found=true;
                if(found) {recorderObject=candidate;break;}
                if(Marshal.IsComObject(candidate))Marshal.FinalReleaseComObject(candidate);
            }
            if(recorderObject==null)throw new InvalidOperationException("No recorder at requested drive.");
            dynamic recorder=recorderObject;
            bool rw=false;
            foreach(object p in recorder.CurrentProfiles) {
                int v=Convert.ToInt32(p);
                if(v==0x0A||v==0x13||v==0x14||v==0x1A||v==0x2A||v==0x43)rw=true;
            }
            if(!rw)throw new InvalidOperationException("Current media is not rewritable; refusing erase.");
            formatObject=create("IMAPI2.MsftDiscFormat2Erase"); dynamic fmt=formatObject;
            fmt.Recorder=recorder; fmt.ClientName="discprobe-erase"; fmt.FullErase=full;
            if(!fmt.IsCurrentMediaSupported(recorder))throw new InvalidOperationException("IMAPI cannot erase this medium.");
            handler=(sender,elapsed,total)=>{
                double fraction=total>0?Math.Min(.999,Math.Max(0,(double)elapsed/total)):0;
                Console.WriteLine("{\"type\":\"progress\",\"stage\":\"erasing\",\"fraction\":"+
                    fraction.ToString(System.Globalization.CultureInfo.InvariantCulture)+",\"elapsed_s\":"+elapsed+
                    ",\"eta_s\":"+Math.Max(0,total-elapsed)+"}");Console.Out.Flush();
            };
            subscribe(formatObject,handler);subscribed=true;
            fmt.EraseMedia();
        } finally {
            if(subscribed)unsubscribe(formatObject,handler);
            foreach(object obj in new object[]{formatObject,recorderObject,masterObject})
                if(obj!=null&&Marshal.IsComObject(obj))Marshal.FinalReleaseComObject(obj);
        }
    }
}
'@
try { [MachineErase]::Run($Drive, [bool]$Full) } catch { [Console]::Error.WriteLine($_.Exception.ToString()); exit 1 }
} finally {
    if ($null -ne $driveLease) { Close-DiscProbeDriveLock $driveLease }
}
