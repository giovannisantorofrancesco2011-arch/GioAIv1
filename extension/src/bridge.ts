// Il processo `mydevagent bridge`: una riga JSON per messaggio su stdin/stdout (vedi mydevagent/bridge.py).
import { ChildProcess, spawn } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";

export interface Install {
  home: string; // cartella di MyDevAgent ("" se trovato solo nel PATH)
  command: string;
  args: string[];
}

export class BridgeError extends Error {
  constructor(message: string, readonly hint = "") {
    super(message);
  }
}

const WIN = process.platform === "win32";

function venvPython(dir: string): string | undefined {
  for (const venv of [".venv", "venv"]) {
    const python = WIN ? path.join(dir, venv, "Scripts", "python.exe") : path.join(dir, venv, "bin", "python");
    if (fs.existsSync(python)) return python;
  }
  return undefined;
}

function onPath(name: string): string | undefined {
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    const file = path.join(dir, name);
    if (dir && fs.existsSync(file)) return file;
  }
  return undefined;
}

/** Dove è installato MyDevAgent: l'impostazione, le cartelle abituali, un livello sotto Desktop e Documenti, il PATH. */
export function locate(setting: string): Install | undefined {
  const home = os.homedir();
  const candidates = [setting, process.env.MYDEVAGENT_HOME || "", path.join(process.env.LOCALAPPDATA || home, "MyDevAgent"),
    path.join(home, "MyDevAgent")];
  for (const parent of ["Desktop", "OneDrive/Desktop", "Documents", "OneDrive/Documents", ""]) {
    try {
      for (const name of fs.readdirSync(path.join(home, parent))) candidates.push(path.join(home, parent, name));
    } catch {
      // la cartella non c'è
    }
  }
  for (const dir of candidates.filter(Boolean)) {
    const python = venvPython(dir);
    if (python && fs.existsSync(path.join(dir, "mydevagent", "__init__.py"))) {
      return { home: dir, command: python, args: ["-m", "mydevagent.cli", "bridge"] };
    }
  }
  const exe = onPath(WIN ? "mydevagent.exe" : "mydevagent");
  return exe ? { home: "", command: exe, args: ["bridge"] } : undefined;
}

type Pending = { resolve: (value: any) => void; reject: (error: BridgeError) => void };

export class Bridge implements vscode.Disposable {
  private proc?: ChildProcess;
  private pending = new Map<number, Pending>();
  private seq = 0;
  private buffer = "";
  private stderr: string[] = [];
  private readonly notifyEmitter = new vscode.EventEmitter<{ method: string; params: any }>();
  private readonly exitEmitter = new vscode.EventEmitter<string>();
  readonly onNotify = this.notifyEmitter.event;
  readonly onExit = this.exitEmitter.event; // con le ultime righe di errore

  constructor(private readonly log: vscode.OutputChannel) {}

  get running(): boolean {
    return this.proc !== undefined;
  }

  /** Avvia il ponte nella cartella del progetto e aspetta che sia pronto. */
  start(install: Install, root: string, profile: string): Promise<void> {
    this.stop();
    const args = [...install.args, ...(profile ? ["--profile", profile] : [])];
    this.log.appendLine(`> ${install.command} ${args.join(" ")}  (in ${root})`);
    const env: NodeJS.ProcessEnv = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1",
      NO_COLOR: "1" };
    if (install.home) env.MYDEVAGENT_HOME = install.home;
    const proc = spawn(install.command, args, { cwd: root, env, windowsHide: true });
    this.proc = proc;
    this.buffer = "";
    this.stderr = [];
    return new Promise<void>((resolve, reject) => {
      let ready = false;
      const timer = setTimeout(() => reject(new BridgeError("MyDevAgent non risponde", this.tail())), 90_000);
      proc.stdout!.on("data", (data: Buffer) => {
        this.buffer += data.toString("utf8");
        let newline;
        while ((newline = this.buffer.indexOf("\n")) >= 0) {
          const line = this.buffer.slice(0, newline).trim();
          this.buffer = this.buffer.slice(newline + 1);
          if (!line) continue;
          let message: any;
          try {
            message = JSON.parse(line);
          } catch {
            this.log.appendLine(`[stdout] ${line}`);
            continue;
          }
          if (message.method === "ready" && !ready) {
            ready = true;
            clearTimeout(timer);
            resolve();
          }
          this.dispatch(message);
        }
      });
      proc.stderr!.on("data", (data: Buffer) => {
        const text = data.toString("utf8");
        this.log.append(text);
        this.stderr.push(...text.split(/\r?\n/).filter((l) => l.trim()));
        this.stderr = this.stderr.slice(-40);
      });
      proc.on("error", (error) => {
        clearTimeout(timer);
        reject(new BridgeError("Non riesco ad avviare MyDevAgent", String(error.message)));
      });
      proc.on("exit", (code) => {
        clearTimeout(timer);
        this.log.appendLine(`[MyDevAgent si è chiuso: codice ${code}]`);
        if (this.proc !== proc) return;
        this.proc = undefined;
        const tail = this.tail();
        for (const p of this.pending.values()) p.reject(new BridgeError("MyDevAgent si è chiuso", tail));
        this.pending.clear();
        if (!ready) reject(new BridgeError("MyDevAgent si è chiuso durante l'avvio", tail));
        else this.exitEmitter.fire(tail);
      });
    });
  }

  private tail(): string {
    return this.stderr.slice(-8).join("\n");
  }

  private dispatch(message: any): void {
    if (message.id !== undefined && message.id !== null && ("result" in message || "error" in message)) {
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (!pending) return;
      if (message.error) pending.reject(new BridgeError(message.error.message, message.error.hint || ""));
      else pending.resolve(message.result);
    } else if (message.method) {
      this.notifyEmitter.fire({ method: message.method, params: message.params || {} });
    }
  }

  request<T = any>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const proc = this.proc;
    if (!proc || !proc.stdin || proc.stdin.destroyed) {
      return Promise.reject(new BridgeError("MyDevAgent non è avviato"));
    }
    const id = ++this.seq;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      proc.stdin!.write(JSON.stringify({ id, method, params }) + "\n");
    });
  }

  stop(): void {
    const proc = this.proc;
    if (!proc) return;
    this.proc = undefined;
    for (const p of this.pending.values()) p.reject(new BridgeError("MyDevAgent è stato riavviato"));
    this.pending.clear();
    try {
      proc.stdin!.write(JSON.stringify({ id: 0, method: "shutdown", params: {} }) + "\n");
    } catch {
      // già chiuso
    }
    setTimeout(() => proc.exitCode === null && proc.kill(), 3000);
  }

  dispose(): void {
    this.stop();
    this.notifyEmitter.dispose();
    this.exitEmitter.dispose();
  }
}
