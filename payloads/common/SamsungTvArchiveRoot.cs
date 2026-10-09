using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;

internal static class SamsungTvArchiveRoot
{
    private const string StagingRoot = "/home/owner/share/tmp/sdk_tools/";
    private const string VerificationKey = "/usr/share/sdbd/public.pem";
    private const string Passwd = "/etc/passwd";
    private const int CloneNewMountNamespace = 0x00020000;
    private const uint MountBind = 4096;
    private const uint MountRecursive = 16384;
    private const uint MountPrivate = 1U << 18;
    private const int UnmountDetach = 2;
    private const ulong RequiredCapabilities = (1UL << 6) | (1UL << 21);

    public static int Main(string[] arguments)
    {
        string package;
        string staging;
        string onDemand;
        if (arguments.Length == 1 && ValidPackage(arguments[0]))
        {
            package = arguments[0];
            staging = StagingRoot + package + "/";
            onDemand = StagingRoot + "on-demand/";
        }
        else if (arguments.Length == 3 && ValidPackage(arguments[0]))
        {
            package = arguments[0];
            staging = arguments[1].EndsWith("/") ? arguments[1] : arguments[1] + "/";
            onDemand = arguments[2].EndsWith("/") ? arguments[2] : arguments[2] + "/";
        }
        else
        {
            Console.Error.WriteLine("usage: SamsungTvArchiveRoot.dll archive-root-HEX [staging on-demand]");
            return 2;
        }
        string logPath = "/tmp/archive-root-" + package + ".log";
        bool keyMounted = false;
        bool passwdMounted = false;
        try
        {
            ulong capabilities = ReadEffectiveCapabilities();
            if ((capabilities & RequiredCapabilities) != RequiredCapabilities)
            {
                throw new InvalidOperationException("CAP_SYS_ADMIN and CAP_SETGID are required");
            }
            if (unshare(CloneNewMountNamespace) != 0)
            {
                throw NativeError("unshare(CLONE_NEWNS)");
            }
            if (mount(null, "/", null,
                new UIntPtr(MountRecursive | MountPrivate), null) != 0)
            {
                throw NativeError("make root mount tree private");
            }
            if (mount(staging + "public.pem", VerificationKey, null,
                new UIntPtr(MountBind), null) != 0)
            {
                throw NativeError("bind verification key");
            }
            keyMounted = true;
            if (mount(staging + "passwd", Passwd, null,
                new UIntPtr(MountBind), null) != 0)
            {
                throw NativeError("bind passwd view");
            }
            passwdMounted = true;

            var start = new ProcessStartInfo("/usr/sbin/sdbd-tarlauncher");
            start.UseShellExecute = false;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.ArgumentList.Add("--package_name");
            start.ArgumentList.Add(package);
            start.ArgumentList.Add("-xzf");
            start.ArgumentList.Add(onDemand + package + ".tar.gz");
            start.ArgumentList.Add("--to-command=/bin/sh");
            using (Process process = Process.Start(start))
            {
                if (process == null)
                {
                    throw new InvalidOperationException("tarlauncher did not start");
                }
                var stdout = process.StandardOutput.ReadToEndAsync();
                var stderr = process.StandardError.ReadToEndAsync();
                process.WaitForExit();
                File.WriteAllText(logPath,
                    "exit=" + process.ExitCode.ToString(CultureInfo.InvariantCulture)
                    + "\nstdout:\n" + stdout.GetAwaiter().GetResult()
                    + "\nstderr:\n" + stderr.GetAwaiter().GetResult());
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            string message = error.GetType().Name + ": " + error.Message;
            try { File.WriteAllText(logPath, message + "\n"); }
            catch (Exception) { }
            Console.Error.WriteLine(message);
            return 1;
        }
        finally
        {
            if (passwdMounted) umount2(Passwd, UnmountDetach);
            if (keyMounted) umount2(VerificationKey, UnmountDetach);
        }
    }

    private static bool ValidPackage(string package)
    {
        const string prefix = "archive-root-";
        if (!package.StartsWith(prefix, StringComparison.Ordinal)
            || package.Length != prefix.Length + 16)
        {
            return false;
        }
        for (int i = prefix.Length; i < package.Length; i++)
        {
            char c = package[i];
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
            {
                return false;
            }
        }
        return true;
    }

    private static ulong ReadEffectiveCapabilities()
    {
        foreach (string line in File.ReadLines("/proc/self/status"))
        {
            if (line.StartsWith("CapEff:", StringComparison.Ordinal))
            {
                return ulong.Parse(line.Substring(7).Trim(),
                    NumberStyles.HexNumber, CultureInfo.InvariantCulture);
            }
        }
        throw new InvalidDataException("CapEff is missing from /proc/self/status");
    }

    private static Exception NativeError(string action)
    {
        return new InvalidOperationException(action + " failed, errno "
            + Marshal.GetLastWin32Error().ToString(CultureInfo.InvariantCulture));
    }

    [DllImport("libc", SetLastError = true)]
    private static extern int unshare(int flags);

    [DllImport("libc", SetLastError = true)]
    private static extern int mount(string source, string target, string filesystem,
        UIntPtr flags, string data);

    [DllImport("libc", SetLastError = true)]
    private static extern int umount2(string target, int flags);
}
