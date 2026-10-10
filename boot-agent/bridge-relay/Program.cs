// TvRootBridgeRelay: headless token-gated TCP relay (TV:port -> 127.0.0.1:26101).
//
// WHY THIS EXISTS (2026-10-10): the relay used to live inside the manager
// UI process, so closing the manager (or the platform reaping it when the
// TV switches inputs) killed management access along with it. This relay
// has no window and no app lifecycle: it runs supervised under systemd
// (tvroot-bridge.service, written by the telemetry module each boot),
// survives manager open/close, and restarts on failure. The manager keeps
// only a port probe for its status page. Relay needs no root - it starts
// whenever the module runs - but binds the same port/token/log format as
// the old in-agent relay, so all tooling is unchanged.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

public static class BridgeRelay
{
    private const int DefaultPort = 26103;
    private const string DefaultTokenPath = "/opt/usr/share/selfroot/bridge.conf";
    private const string DefaultLogPath = "/home/owner/share/tmp/sdk_tools/selfroot-evidence/bridge.log";
    private const int SdbPort = 26101;
    private const int TokenLength = 32;

    private static string LogPath = DefaultLogPath;
    private static readonly object LogLock = new object();

    public static int Main(string[] args)
    {
        int port = DefaultPort;
        string tokenPath = DefaultTokenPath;
        if (args.Length > 0)
        {
            int parsed;
            if (!int.TryParse(args[0], out parsed) || parsed < 1024 || parsed > 65535)
            {
                Console.Error.WriteLine("usage: TvRootBridgeRelay [port] [tokenPath] [logPath]");
                return 2;
            }
            port = parsed;
        }
        if (args.Length > 1) tokenPath = args[1];
        if (args.Length > 2) LogPath = args[2];

        string token;
        try { token = File.ReadAllText(tokenPath).Trim(); }
        catch (Exception e)
        {
            Console.Error.WriteLine("cannot read token: " + e.GetType().Name);
            return 2;
        }
        if (!IsToken(token))
        {
            Console.Error.WriteLine("token must be 32 lowercase hex characters");
            return 2;
        }

        TcpListener listener;
        try
        {
            listener = new TcpListener(IPAddress.Any, port);
            listener.Start(8);
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("cannot listen on " + port + ": " + e.GetType().Name);
            return 3;
        }
        Log("relay listening on port " + port);
        while (true)
        {
            try
            {
                var client = listener.AcceptTcpClient();
                Task.Run(() => HandleBridgeClient(client, token));
            }
            catch (Exception e)
            {
                Log("listener error: " + e.GetType().Name);
                Thread.Sleep(1000);
            }
        }
    }

    private static bool IsToken(string token)
    {
        if (token == null || token.Length != TokenLength) return false;
        foreach (var character in token)
        {
            if (!((character >= '0' && character <= '9')
                || (character >= 'a' && character <= 'f'))) return false;
        }
        return true;
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
            var received = new byte[TokenLength];
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
                Log("rejected " + peer + " (token timeout)");
                return;
            }
            if (count != received.Length)
            {
                Log("rejected " + peer + " (missing or short token)");
                return;
            }
            if (!TokensMatch(received, token))
            {
                Log("rejected " + peer + " (wrong token)");
                return;
            }

            clientStream.ReadTimeout = Timeout.Infinite;
            upstream = new TcpClient(AddressFamily.InterNetwork);
            upstream.NoDelay = true;
            upstream.Connect(IPAddress.Loopback, SdbPort);
            Log("authorized " + peer);

            var upstreamStream = upstream.GetStream();
            var finished = new ManualResetEvent(false);
            var toSdbd = Task.Run(() => CopyBridgeStream(clientStream, upstreamStream, finished));
            var toClient = Task.Run(() => CopyBridgeStream(upstreamStream, clientStream, finished));
            finished.WaitOne();
            client.Close();
            upstream.Close();
            Task.WaitAll(new[] { toSdbd, toClient }, 1000);
            Log("closed " + peer);
        }
        catch (Exception error)
        {
            Log("connection " + peer + " failed: " + error.GetType().Name);
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
        for (int i = 0; i < TokenLength; i++)
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

    private static void Log(string message)
    {
        var line = "[" + DateTime.UtcNow.ToString("o") + "] bridge " + message + "\n";
        lock (LogLock)
        {
            try
            {
                var dir = Path.GetDirectoryName(LogPath);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                File.AppendAllText(LogPath, line);
            }
            catch { }
        }
        try { Console.WriteLine(line.TrimEnd()); } catch { }
    }
}
