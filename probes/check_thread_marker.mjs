import { spawn } from 'node:child_process';
import readline from 'node:readline';

const [threadId, marker] = process.argv.slice(2);
if (!threadId || !marker) {
  process.stderr.write('Usage: node check_thread_marker.mjs <thread-id> <marker>\n');
  process.exit(2);
}

const child = spawn('codex.exe', ['app-server'], {
  stdio: ['pipe', 'pipe', 'pipe'],
  windowsHide: true,
});
const lines = readline.createInterface({ input: child.stdout });
let finished = false;
let stderr = '';
const timer = setTimeout(() => finish({ result: 'timeout' }, 2), 12000);

function send(value) {
  child.stdin.write(`${JSON.stringify(value)}\n`);
}

function finish(value, code = 0) {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  process.stdout.write(`${JSON.stringify(value)}\n`);
  child.kill();
  process.exitCode = code;
}

child.stderr.on('data', (chunk) => { stderr += chunk.toString().slice(0, 2000); });
child.on('error', (error) => finish({ result: 'process_error', message: error.message }, 2));
child.on('exit', (code) => {
  if (!finished) finish({ result: 'app_server_exited', code, detail: stderr.slice(-1000) }, 2);
});
lines.on('line', (line) => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  if (message.id === 1) {
    if (message.error) return finish({ result: 'initialize_error', error: message.error }, 2);
    send({ method: 'initialized', params: {} });
    send({ id: 2, method: 'thread/read', params: { threadId, includeTurns: true } });
  }
  if (message.id === 2) {
    if (message.error) return finish({ result: 'thread_read_error', error: message.error }, 2);
    const thread = message.result?.thread;
    const turns = thread?.turns ?? [];
    const userMessages = turns.flatMap((turn) => (turn.items ?? []).filter((item) => item.type === 'userMessage'));
    const userText = JSON.stringify(userMessages);
    const threadWithoutTurns = { ...thread, turns: [] };
    finish({ result: 'thread_read_ok', same_thread: thread?.id === threadId, marker_in_user_message: userText.includes(marker), marker_outside_turns: JSON.stringify(threadWithoutTurns).includes(marker), user_message_count: userMessages.length, turn_count: turns.length });
  }
});

send({ id: 1, method: 'initialize', params: { clientInfo: { name: 'agentrunner_probe', title: 'AgentRunner Probe', version: '0.0.1' } } });
