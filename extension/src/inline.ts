// Ctrl+I: Vio riscrive la selezione (o scrive codice nuovo al cursore) direttamente nel file.
// La modifica resta evidenziata finché non la tieni (Ctrl+Invio) o la annulli (Esc).
import * as vscode from "vscode";
import { BridgeError } from "./bridge";
import type { Chat } from "./chat";

interface Pending {
  doc: vscode.TextDocument;
  range: vscode.Range;
  original: string;
  version: number;
}

export class InlineEdit implements vscode.CodeLensProvider, vscode.Disposable {
  private pending?: Pending;
  private undoing = false;
  private readonly lensEmitter = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this.lensEmitter.event;
  private readonly added = vscode.window.createTextEditorDecorationType({
    isWholeLine: true,
    backgroundColor: "rgba(168, 85, 247, 0.14)",
    borderColor: "#a855f7",
    borderStyle: "solid",
    borderWidth: "0 0 0 2px",
    overviewRulerColor: "#a855f7",
    overviewRulerLane: vscode.OverviewRulerLane.Left,
  });
  private readonly subscriptions: vscode.Disposable[];

  constructor(private readonly chat: Chat) {
    this.subscriptions = [
      vscode.workspace.onDidChangeTextDocument((e) => {
        // ponytail: qualsiasi altra modifica al file (anche un Ctrl+Z) vale come «tieni»: niente range da inseguire
        if (this.pending && e.document === this.pending.doc && e.document.version !== this.pending.version && !this.undoing) {
          this.clear();
        }
      }),
      vscode.window.onDidChangeVisibleTextEditors(() => this.decorate()),
      vscode.workspace.onDidCloseTextDocument((doc) => doc === this.pending?.doc && this.clear()),
    ];
  }

  async run(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    if (!this.chat.state.connected) {
      void vscode.window.showWarningMessage("Vio non è ancora collegata: apri la sua chat per vedere cosa manca.");
      this.chat.reveal();
      return;
    }
    this.clear();
    const doc = editor.document;
    const sel = editor.selection;
    let range: vscode.Range = sel;
    if (!sel.isEmpty) { // righe intere: il modello rispetta meglio l'indentazione
      const last = sel.end.character === 0 && sel.end.line > sel.start.line ? sel.end.line - 1 : sel.end.line;
      range = new vscode.Range(sel.start.line, 0, last, doc.lineAt(last).text.length);
    }
    const instruction = await vscode.window.showInputBox({
      title: "Modifica con Vio",
      prompt: sel.isEmpty ? "Cosa devo scrivere qui?" : "Cosa devo cambiare nel codice selezionato?",
      placeHolder: sel.isEmpty ? "es. una funzione che legge un CSV e restituisce le righe" : "es. aggiungi i tipi e gestisci gli errori",
      ignoreFocusOut: true,
    });
    if (!instruction?.trim()) return;
    const version = doc.version;
    const original = doc.getText(range);
    const before = doc.getText(new vscode.Range(Math.max(0, range.start.line - 80), 0, range.start.line, range.start.character));
    const lastLine = Math.min(doc.lineCount - 1, range.end.line + 40);
    const after = doc.getText(new vscode.Range(range.end, doc.lineAt(lastLine).range.end));
    let text: string | undefined;
    try {
      text = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Vio sta scrivendo…",
        cancellable: true }, (_progress, token) => Promise.race([
        this.chat.bridge.request<{ text: string }>("inline_edit", { path: this.chat.relative(doc.uri.fsPath),
          language: doc.languageId, before, selection: original, after, instruction }).then((r) => r.text),
        new Promise<undefined>((resolve) => token.onCancellationRequested(() => resolve(undefined))),
      ]));
    } catch (error) {
      const message = error instanceof BridgeError ? `${error.message}${error.hint ? ` (${error.hint})` : ""}` : String(error);
      void vscode.window.showErrorMessage(`Vio non è riuscita a modificare il codice: ${message}`);
      return;
    }
    if (text === undefined) return;
    if (doc.version !== version) {
      void vscode.window.showWarningMessage("Il file è cambiato mentre Vio scriveva: riprova.");
      return;
    }
    if (!(await editor.edit((edit) => edit.replace(range, text!)))) return;
    const end = doc.positionAt(doc.offsetAt(range.start) + text.length);
    this.pending = { doc, range: new vscode.Range(range.start, end), original, version: doc.version };
    void vscode.commands.executeCommand("setContext", "mydevagent.inlinePending", true);
    this.decorate();
    this.lensEmitter.fire();
  }

  accept(): void {
    this.clear();
  }

  async reject(): Promise<void> {
    const pending = this.pending;
    if (!pending) return;
    const edit = new vscode.WorkspaceEdit();
    edit.replace(pending.doc.uri, pending.range, pending.original);
    this.undoing = true;
    try {
      await vscode.workspace.applyEdit(edit);
    } finally {
      this.undoing = false;
    }
    this.clear();
  }

  private clear(): void {
    if (!this.pending) return;
    this.pending = undefined;
    void vscode.commands.executeCommand("setContext", "mydevagent.inlinePending", false);
    this.decorate();
    this.lensEmitter.fire();
  }

  private decorate(): void {
    for (const editor of vscode.window.visibleTextEditors) {
      const mine = this.pending && editor.document === this.pending.doc;
      const range = this.pending?.range;
      const hasText = range && !range.isEmpty;
      editor.setDecorations(this.added, mine && hasText ? [{
        range: range.end.character === 0 && range.end.line > range.start.line ? range.with({ end: range.end.translate(-1) }) : range,
        hoverMessage: this.pending!.original
          ? new vscode.MarkdownString().appendMarkdown("**Prima era così:**").appendCodeblock(this.pending!.original, this.pending!.doc.languageId)
          : undefined,
      }] : []);
    }
  }

  provideCodeLenses(doc: vscode.TextDocument): vscode.CodeLens[] {
    if (!this.pending || doc !== this.pending.doc) return [];
    const at = new vscode.Range(this.pending.range.start, this.pending.range.start);
    const lines = (text: string) => (text ? text.replace(/\n$/, "").split("\n").length : 0);
    const added = lines(doc.getText(this.pending.range));
    const removed = lines(this.pending.original);
    return [
      new vscode.CodeLens(at, { title: "$(check) Tieni (Ctrl+Invio)", command: "mydevagent.acceptInline" }),
      new vscode.CodeLens(at, { title: "$(discard) Annulla (Esc)", command: "mydevagent.rejectInline" }),
      new vscode.CodeLens(at, { title: `Vio: −${removed} +${added} righe`, command: "" }),
    ];
  }

  dispose(): void {
    this.subscriptions.forEach((s) => s.dispose());
    this.added.dispose();
    this.lensEmitter.dispose();
  }
}
