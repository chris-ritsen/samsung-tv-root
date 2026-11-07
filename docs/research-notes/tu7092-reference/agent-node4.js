'use strict';
// Manual, volatile root channel for the TU7092. No child_process or native addon.
var fs = require('fs');
var net = require('net');
var crypto = require('crypto');
var CONFIG = process.env.VETRO_AGENT_CONFIG;
var RUNTIME = process.env.VETRO_AGENT_RUNTIME;
var MAX_FRAME = 2 * 1024 * 1024;
var pending = {};
var jobs = [];
var active = null;
var socket = null;
var input;
var nonce;
var secret;
var outputBuffer = '';

function buffer(value, encoding) { return new Buffer(value, encoding); }
function equal(a, b) {
    if (a.length !== b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    return diff === 0;
}
function mac(payload) {
    return crypto.createHmac('sha256', secret).update(nonce)
        .update(buffer([0])).update(payload, 'utf8').digest('hex');
}
function send(payload) {
    if (socket && !socket.destroyed) socket.write(payload + '\t' + mac(payload) + '\n');
}
function fail(reason) { console.error(reason); process.exit(1); }
function identity() {
    var smack = fs.readFileSync('/proc/self/attr/current', 'utf8').trim();
    var status = fs.readFileSync('/proc/self/status', 'utf8');
    var caps = /^CapEff:\s*([0-9a-f]+)$/m.exec(status);
    return [process.pid, process.getuid(), process.geteuid(), process.getgid(),
        process.getegid(), caps ? caps[1] : '0', buffer(smack).toString('base64')].join('\t');
}
function onResult(line) {
    var f = line.split('\t');
    if (f.length !== 5 || !pending[f[0]] || !/^-?[0-9]+$/.test(f[1]) || !/^[01]$/.test(f[2])) return;
    if (f[0] !== active) return fail('executor sequence mismatch');
    delete pending[f[0]];
    active = null;
    send('RESULT\t' + line);
    dispatch();
}
function dispatch() {
    if (active !== null || !jobs.length) return;
    var job = jobs.shift();
    active = job[0];
    fs.write(input, job.join('\t') + '\n', null, 'utf8', function (err) {
        if (err) fail('executor write failed');
    });
}
function onFrame(line) {
    if (!nonce) {
        var hello = line.split('\t');
        if (hello.length !== 2 || hello[0] !== 'SAMSUNG-TV-ROOT/1' || !/^[a-f0-9]{64}$/.test(hello[1])) return socket.destroy();
        nonce = buffer(hello[1], 'hex');
        send('AUTH\t' + identity());
        return;
    }
    var sep = line.lastIndexOf('\t');
    if (sep < 0) return socket.destroy();
    var payload = line.slice(0, sep);
    if (!equal(line.slice(sep + 1), mac(payload))) return socket.destroy();
    var f = payload.split('\t');
    if (f[0] === 'PING' && f.length === 2) return send('PONG\t' + f[1]);
    if (f.length !== 4 || f[0] !== 'EXEC' || !/^[1-9][0-9]{0,9}$/.test(f[1]) ||
        !/^[0-9]+$/.test(f[2]) || +f[2] < 1 || +f[2] > 120000 ||
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(f[3]) ||
        buffer(f[3], 'base64').length > 65536) return socket.destroy();
    // Serialize jobs so long FIFO frames cannot interleave. Writes are async.
    if (Object.keys(pending).length >= 32 || pending[f[1]]) {
        return send('RESULT\t' + f[1] + '\t1\t0\t\t' + buffer('executor busy').toString('base64'));
    }
    pending[f[1]] = true;
    jobs.push(f.slice(1));
    dispatch();
}
function connect() {
    var cfg;
    try {
        var stat = fs.lstatSync(CONFIG);
        if (!stat.isFile() || (stat.mode & 63)) throw new Error('unsafe agent config permissions');
        cfg = JSON.parse(fs.readFileSync(CONFIG, 'utf8'));
        if (cfg.port % 1 || cfg.port < 1 || cfg.port > 65535 || !/^[A-Za-z0-9+/]{43}=$/.test(cfg.token)) throw new Error('invalid agent config');
        secret = buffer(cfg.token, 'base64');
    } catch (e) { return setTimeout(connect, 3000); }
    nonce = null;
    var incoming = '';
    socket = net.connect(cfg.port, '127.0.0.1');
    socket.on('data', function (chunk) {
        incoming += chunk.toString('utf8');
        if (incoming.length > MAX_FRAME) return socket.destroy();
        var index;
        while ((index = incoming.indexOf('\n')) >= 0) {
            var line = incoming.slice(0, index); incoming = incoming.slice(index + 1);
            onFrame(line);
            if (socket.destroyed) return;
        }
    });
    socket.on('error', function () {});
    socket.on('close', function () {
        // Exiting also terminates the executor and any in-flight command via supervisor traps.
        fail('Vetro connection closed; restart the manual root session');
    });
}
function run() {
    if (process.getuid() !== 0 || process.geteuid() !== 0 || process.getgid() !== 0 || process.getegid() !== 0) return fail('root identity required');
    if (!CONFIG || !RUNTIME) return fail('agent paths are required');
    var dir = fs.lstatSync(RUNTIME);
    if (!dir.isDirectory() || dir.uid !== process.getuid() || (dir.mode & 63)) return fail('private root runtime directory required');
    input = fs.openSync(RUNTIME + '/in.fifo', 'r+');
    var output = fs.openSync(RUNTIME + '/out.fifo', 'r+');
    var reader = fs.createReadStream(null, {fd: output});
    reader.on('data', function (chunk) {
        outputBuffer += chunk.toString('utf8');
        if (outputBuffer.length > MAX_FRAME * 2) return fail('executor output too large');
        var index;
        while ((index = outputBuffer.indexOf('\n')) >= 0) {
            onResult(outputBuffer.slice(0, index)); outputBuffer = outputBuffer.slice(index + 1);
        }
    });
    reader.on('error', function () { fail('executor read failed'); });
    connect();
}
module.exports = {run: run};
if (require.main === module) run();
