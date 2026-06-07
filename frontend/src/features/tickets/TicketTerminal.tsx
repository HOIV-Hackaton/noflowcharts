import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatAgentPhaseLabel, readAgentPhase } from "@/lib/serviceDesk";
import type { AgentPhase, WritePreview } from "@/types";
import { runTerminalWebSocketUrl } from "../../services/backendApi";

type TerminalMessage =
  | { type: "agent_auto_command"; command_id: number; command: string; classification?: string; intent?: string; phase?: string | null; reason?: string; write_preview?: WritePreview | null }
  | { type: "agent_cancelled" }
  | { type: "agent_guidance_recorded" }
  | { type: "agent_phase_selected"; phase: string }
  | { type: "agent_proposal"; command_id: number; command: string; classification?: string; intent?: string; phase?: string | null; reason?: string; write_preview?: WritePreview | null }
  | { type: "agent_waiting_for_guidance"; command_id?: number }
  | { type: "command_blocked"; command_id?: number; reason?: string }
  | { type: "command_cancelled"; command_id?: number }
  | { type: "command_completed"; command_id?: number; exit_code?: number }
  | { type: "command_running"; command_id?: number }
  | { type: "confirmation_required"; command_id: number; command: string; reason?: string }
  | { type: "error"; message: string }
  | { type: "knowledge_search_performed"; query?: string | null; result_count?: number | null; top_ticket_id?: number | null; top_chunk_type?: string | null; top_similarity_score?: number | null }
  | { type: "output"; data: string }
  | { type: "status"; message: string }
  | { type: "terminal_closed"; reason?: string }
  | { type: "terminal_opened"; run_id?: string; session_id?: number }
  | { type: "terminal_output"; data: string }
  | { type: "validation_evidence_collected"; command_id?: number; status?: string; validation_status?: string };

type PendingConfirmation = {
  classification?: string;
  command?: string;
  commandId: number;
  input: string;
  intent?: string;
  mode: "choose" | "comment" | "edit";
  phase?: string | null;
  reason?: string;
  source: "agent" | "manual";
};

type SetPendingCommand = (pending: PendingConfirmation | null) => void;
type TerminalWaitingState = {
  message: string;
  timer: number;
};

export function TicketTerminal({
  autodiagnosisRunning = false,
  canStartAutodiagnosis = false,
  autoStartAgentRequestId = 0,
  onAgentPhaseChange,
  onTerminalConnectionError,
  onStartAutodiagnosis,
  runId,
  variant = "default",
}: {
  autodiagnosisRunning?: boolean;
  autoStartAgentRequestId?: number;
  canStartAutodiagnosis?: boolean;
  onAgentPhaseChange?: (phase: AgentPhase) => void;
  onStartAutodiagnosis?: () => void;
  onTerminalConnectionError?: (message: string) => void;
  runId: string | null;
  variant?: "compact" | "default";
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const terminalHadErrorRef = useRef(false);
  const pendingConfirmationRef = useRef<PendingConfirmation | null>(null);
  const pendingAgentStartRef = useRef(false);
  const lastAutoStartAgentRequestRef = useRef(0);
  const suppressRawInputUntilRef = useRef(0);
  const lastFitSizeRef = useRef({ height: 0, width: 0 });
  const resizeFrameRef = useRef<number | null>(null);
  const terminalWaitingRef = useRef<TerminalWaitingState | null>(null);
  const [connectionState, setConnectionState] = useState<"disconnected" | "connecting" | "connected">("disconnected");
  const [agentStarted, setAgentStarted] = useState(false);
  const [terminalHasContent, setTerminalHasContent] = useState(false);

  function setPendingCommand(next: PendingConfirmation | null) {
    pendingConfirmationRef.current = next;
  }

  function updatePendingCommand(patch: Partial<PendingConfirmation>) {
    const current = pendingConfirmationRef.current;
    if (!current) {
      return;
    }

    setPendingCommand({ ...current, ...patch });
  }

  function acceptPendingCommand() {
    const pending = pendingConfirmationRef.current;
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    if (!pending || !socket || socket.readyState !== WebSocket.OPEN || !terminal) {
      return;
    }

    setPendingCommand(null);
    suppressRawInputUntilRef.current = Date.now() + 300;
    socket.send(
      JSON.stringify({
        command_id: pending.commandId,
        type: pending.source === "agent" ? "agent_accept" : "manual_confirm",
      }),
    );
    terminal.writeln("\r\n\x1b[32mAccepted. Running command.\x1b[0m");
  }

  function rejectPendingCommand(reason = "Rejected from terminal.") {
    const pending = pendingConfirmationRef.current;
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    if (!pending || !socket || socket.readyState !== WebSocket.OPEN || !terminal) {
      return;
    }

    setPendingCommand(null);
    suppressRawInputUntilRef.current = Date.now() + 300;
    socket.send(
      JSON.stringify({
        command_id: pending.commandId,
        reason,
        type: pending.source === "agent" ? "agent_reject" : "manual_cancel",
      }),
    );
    terminal.writeln("\r\n\x1b[31mRejected.\x1b[0m");
  }

  function beginEditPendingCommand() {
    const pending = pendingConfirmationRef.current;
    const terminal = terminalRef.current;
    if (!pending || !terminal) {
      return;
    }

    if (pending.source !== "agent") {
      terminal.writeln("\r\n\x1b[90mEdit is available for agent proposals. Cancel and retype manual commands.\x1b[0m");
      return;
    }

    const command = pending.command ?? "";
    setPendingCommand({ ...pending, input: command, mode: "edit" });
    terminal.writeln("\r\n\x1b[33mEdit command, then press Enter:\x1b[0m");
    terminal.write(command);
  }

  function retryPendingCommand() {
    const pending = pendingConfirmationRef.current;
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    if (!pending || !socket || socket.readyState !== WebSocket.OPEN || !terminal) {
      return;
    }

    if (pending.source !== "agent") {
      terminal.writeln("\r\n\x1b[90mRetry is available for agent proposals. Cancel and retype manual commands.\x1b[0m");
      return;
    }

    const message = "Technician requested a retry. Do not repeat the same proposal unless it is clearly justified; propose the safest next step.";
    setPendingCommand(null);
    suppressRawInputUntilRef.current = Date.now() + 300;
    socket.send(JSON.stringify({ command_id: pending.commandId, reason: "Retry requested from terminal.", type: "agent_reject" }));
    socket.send(JSON.stringify({ message, type: "agent_message" }));
    terminal.writeln("\r\n\x1b[90mRetry requested. Waiting for a new agent proposal.\x1b[0m");
  }

  function submitEditedPendingCommand(command: string) {
    const pending = pendingConfirmationRef.current;
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    const nextCommand = command.trim();
    if (!pending || !socket || socket.readyState !== WebSocket.OPEN || !terminal || pending.source !== "agent") {
      return;
    }

    if (!nextCommand) {
      terminal.writeln("\r\n\x1b[31mEdited command cannot be empty.\x1b[0m");
      return;
    }

    setPendingCommand(null);
    suppressRawInputUntilRef.current = Date.now() + 300;
    socket.send(JSON.stringify({ command: nextCommand, command_id: pending.commandId, type: "agent_edit" }));
    terminal.writeln("\r\n\x1b[33mEdited command sent for safety review.\x1b[0m");
  }

  function beginCommentPendingCommand() {
    const pending = pendingConfirmationRef.current;
    const terminal = terminalRef.current;
    if (!pending || !terminal) {
      return;
    }

    if (pending.source !== "agent") {
      terminal.writeln("\r\n\x1b[90mComment is available for agent proposals. Cancel manual commands instead.\x1b[0m");
      return;
    }

    setPendingCommand({ ...pending, input: "", mode: "comment" });
    terminal.writeln("\r\n\x1b[90mComment / guidance, then press Enter:\x1b[0m");
  }

  function submitPendingComment(comment: string) {
    const pending = pendingConfirmationRef.current;
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    const message = comment.trim();
    if (!pending || !socket || socket.readyState !== WebSocket.OPEN || !terminal || pending.source !== "agent") {
      return;
    }

    if (!message) {
      terminal.writeln("\r\n\x1b[31mComment cannot be empty.\x1b[0m");
      return;
    }

    setPendingCommand(null);
    suppressRawInputUntilRef.current = Date.now() + 300;
    socket.send(JSON.stringify({ command_id: pending.commandId, reason: message, type: "agent_reject" }));
    socket.send(JSON.stringify({ message, type: "agent_message" }));
    terminal.writeln("\r\n\x1b[90mComment sent. Current proposal rejected with guidance.\x1b[0m");
  }

  function handlePendingTerminalInput(data: string) {
    const pending = pendingConfirmationRef.current;
    const terminal = terminalRef.current;
    if (!pending || !terminal) {
      return;
    }

    if (pending.mode === "edit" || pending.mode === "comment") {
      for (const char of data) {
        if (char === "\r" || char === "\n") {
          terminal.writeln("");
          if (pending.mode === "edit") {
            submitEditedPendingCommand(pendingConfirmationRef.current?.input ?? "");
          } else {
            submitPendingComment(pendingConfirmationRef.current?.input ?? "");
          }
          return;
        }

        if (char === "\b" || char === "\x7f") {
          const current = pendingConfirmationRef.current;
          if (current?.input) {
            updatePendingCommand({ input: current.input.slice(0, -1) });
            terminal.write("\b \b");
          }
          continue;
        }

        if (char >= " ") {
          const current = pendingConfirmationRef.current;
          updatePendingCommand({ input: `${current?.input ?? ""}${char}` });
          terminal.write(char);
        }
      }
      return;
    }

    const answer = data.trim().toLowerCase()[0];
    if (!answer) {
      return;
    }

    if (answer === "a" || answer === "y") {
      acceptPendingCommand();
      return;
    }

    if (answer === "r" || answer === "n") {
      rejectPendingCommand();
      return;
    }

    if (answer === "e") {
      beginEditPendingCommand();
      return;
    }

    if (answer === "t") {
      retryPendingCommand();
      return;
    }

    if (answer === "c") {
      beginCommentPendingCommand();
      return;
    }

    terminal.writeln(
      pending.source === "agent"
        ? "\r\nChoose: \x1b[32ma\x1b[0mccept, \x1b[31mr\x1b[0meject, \x1b[33me\x1b[0mdit, re\x1b[36mt\x1b[0mry, or \x1b[90mc\x1b[0momment."
        : "\r\nChoose: \x1b[32ma\x1b[0mccept or \x1b[31mr\x1b[0meject.",
    );
  }

  useEffect(() => {
    setConnectionState("disconnected");
    setAgentStarted(false);
    setTerminalHasContent(false);
    setPendingCommand(null);
    terminalHadErrorRef.current = false;

    const terminal = new Terminal({
      allowProposedApi: false,
      convertEol: true,
      cursorBlink: false,
      cursorStyle: "bar",
      disableStdin: true,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
      fontSize: 13,
      fontWeight: "400",
      letterSpacing: 0,
      lineHeight: 1.25,
      rows: 28,
      scrollback: 5000,
      theme: {
        background: "#09090b",
        black: "#18181b",
        blue: "#93c5fd",
        brightBlack: "#71717a",
        brightBlue: "#bfdbfe",
        brightCyan: "#a5f3fc",
        brightGreen: "#bbf7d0",
        brightMagenta: "#f0abfc",
        brightRed: "#fecaca",
        brightWhite: "#fafafa",
        brightYellow: "#fde68a",
        cursor: "#fafafa",
        cyan: "#67e8f9",
        foreground: "#e4e4e7",
        green: "#86efac",
        magenta: "#e879f9",
        red: "#fca5a5",
        selectionBackground: "#27272a",
        white: "#d4d4d8",
        yellow: "#facc15",
      },
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;

    if (containerRef.current) {
      terminal.open(containerRef.current);
      lastFitSizeRef.current = { height: 0, width: 0 };
      fitTerminal(true);
    }

    const inputDisposable = terminal.onData((data) => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }

      const pendingConfirmation = pendingConfirmationRef.current;
      if (pendingConfirmation) {
        handlePendingTerminalInput(data);
        return;
      }

      if (Date.now() < suppressRawInputUntilRef.current) {
        return;
      }

      socket.send(JSON.stringify({ type: "input", data }));
    });

    const resizeObserver = new ResizeObserver(() => scheduleFit());
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
      }
      socketRef.current?.close();
      finishTerminalWaiting({ keepLine: false });
      resizeObserver.disconnect();
      inputDisposable.dispose();
      terminal.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
      socketRef.current = null;
      setPendingCommand(null);
    };
  }, [runId]);

  const connect = () => {
    const terminal = terminalRef.current;
    if (!terminal || !runId || connectionState !== "disconnected") {
      return;
    }

    fitTerminal(true);
    terminalHadErrorRef.current = false;
    setPendingCommand(null);
    setConnectionState("connecting");
    setTerminalHasContent(true);
    terminal.clear();
    startTerminalWaiting("Opening backend terminal bridge...");
    const socket = new WebSocket(runTerminalWebSocketUrl(runId, terminal.cols, terminal.rows));
    socketRef.current = socket;

    socket.onopen = () => {
      terminal.options.disableStdin = true;
    };

    socket.onmessage = (event) => {
      const message = parseTerminalMessage(event.data);
      if (!message) {
        return;
      }

      if (message.type === "output" || message.type === "terminal_output") {
        finishTerminalWaiting();
        setTerminalHasContent(true);
        terminal.write(message.data);
        return;
      }

      if (message.type === "error") {
        finishTerminalWaiting();
        terminalHadErrorRef.current = true;
        setTerminalHasContent(true);
        terminal.writeln(`\r\n\x1b[31m${message.message}\x1b[0m`);
        if (isTerminalOpenError(message.message)) {
          onTerminalConnectionError?.(message.message);
        }
        return;
      }

      if (message.type === "terminal_opened") {
        terminal.options.disableStdin = false;
        setConnectionState("connected");
        window.setTimeout(sendResize, 0);
        if (pendingAgentStartRef.current) {
          pendingAgentStartRef.current = false;
          window.setTimeout(requestAgentAction, 0);
        }
      }

      if (message.type === "agent_auto_command" || message.type === "agent_proposal" || message.type === "agent_phase_selected") {
        setAgentStarted(true);
      }

      const agentPhase = readTerminalMessageAgentPhase(message);
      if (agentPhase) {
        onAgentPhaseChange?.(agentPhase);
      }

      if (message.type === "agent_cancelled") {
        setAgentStarted(false);
      }

      if (message.type === "validation_evidence_collected") {
        setAgentStarted(false);
      }

      handleTerminalStatusMessage(terminal, message, setPendingCommand, {
        finish: finishTerminalWaiting,
        start: startTerminalWaiting,
      });
    };

    socket.onerror = () => {
      finishTerminalWaiting();
      terminalHadErrorRef.current = true;
      terminal.writeln("\r\n\x1b[31mTerminal websocket failed.\x1b[0m");
    };

    socket.onclose = (event) => {
      socketRef.current = null;
      terminal.options.disableStdin = true;
      setPendingCommand(null);
      setAgentStarted(false);
      setConnectionState("disconnected");
      finishTerminalWaiting({ keepLine: !terminalHadErrorRef.current });
      if (terminalHadErrorRef.current) {
        return;
      }
      if (!terminalHadErrorRef.current) {
        setTerminalHasContent(true);
        terminal.writeln("\r\n\x1b[90mTerminal session closed.\x1b[0m");
      }
    };
  };

  const disconnect = () => {
    const terminal = terminalRef.current;
    if (terminal) {
      terminal.options.disableStdin = true;
    }
    socketRef.current?.close();
  };

  const requestAgentAction = () => {
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !terminal) {
      return;
    }

    socket.send(JSON.stringify({ type: agentStarted ? "agent_next" : "agent_start" }));
    setTerminalHasContent(true);
    startTerminalWaiting(agentStarted ? "Requesting next agent action..." : "Starting agent...");
    setAgentStarted(true);
  };

  useEffect(() => {
    if (!autoStartAgentRequestId || autoStartAgentRequestId === lastAutoStartAgentRequestRef.current || !runId) {
      return;
    }

    lastAutoStartAgentRequestRef.current = autoStartAgentRequestId;
    pendingAgentStartRef.current = true;
    if (connectionState === "connected") {
      pendingAgentStartRef.current = false;
      requestAgentAction();
      return;
    }

    if (connectionState === "disconnected") {
      connect();
    }
  }, [autoStartAgentRequestId, connectionState, runId]);

  const cancelAgent = () => {
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !terminal) {
      return;
    }

    socket.send(JSON.stringify({ type: "agent_cancel" }));
    setTerminalHasContent(true);
    finishTerminalWaiting();
    startTerminalWaiting("Cancelling agent mode...");
    setAgentStarted(false);
  };

  function startTerminalWaiting(message: string) {
    const terminal = terminalRef.current;
    if (!terminal) {
      return;
    }

    const currentWaiting = terminalWaitingRef.current;
    if (currentWaiting?.message === message) {
      return;
    }

    finishTerminalWaiting({ keepLine: false });

    if (prefersReducedTerminalMotion()) {
      terminal.writeln(`\r\n\x1b[90m${message}\x1b[0m`);
      return;
    }

    let frame = 0;
    const render = () => {
      terminal.write(`\r\x1b[2K${formatTerminalWaitingFrame(message, frame)}`);
      frame += 1;
    };

    terminal.write("\r\n");
    render();
    const timer = window.setInterval(render, 360);
    terminalWaitingRef.current = { message, timer };
  }

  function finishTerminalWaiting(options: { keepLine?: boolean } = {}) {
    const terminal = terminalRef.current;
    const waiting = terminalWaitingRef.current;
    if (!waiting) {
      return;
    }

    window.clearInterval(waiting.timer);
    terminalWaitingRef.current = null;

    if (!terminal) {
      return;
    }

    terminal.write("\r\x1b[2K");
    if (options.keepLine ?? true) {
      terminal.writeln(`\x1b[90m${waiting.message}\x1b[0m`);
    }
  }

  const scheduleFit = () => {
    if (resizeFrameRef.current !== null) {
      return;
    }

    resizeFrameRef.current = window.requestAnimationFrame(() => {
      resizeFrameRef.current = null;
      fitTerminal();
    });
  };

  const fitTerminal = (force = false) => {
    const container = containerRef.current;
    const fitAddon = fitAddonRef.current;

    if (!container || !fitAddon) {
      return;
    }

    const rect = container.getBoundingClientRect();
    const width = Math.round(rect.width);
    const height = Math.round(rect.height);

    if (width <= 0 || height <= 0) {
      return;
    }

    const lastSize = lastFitSizeRef.current;
    if (!force && lastSize.width === width && lastSize.height === height) {
      return;
    }

    lastFitSizeRef.current = { height, width };
    fitAddon.fit();
    sendResize();
  };

  const sendResize = () => {
    const terminal = terminalRef.current;
    const socket = socketRef.current;
    if (!terminal || !socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }));
  };

  return (
    <section className={["terminal-panel", variant === "compact" ? "terminal-panel-compact" : ""].join(" ")}>
      <div className="terminal-controls">
        {runId || connectionState !== "disconnected" ? (
          <Button
            disabled={!runId || connectionState !== "disconnected"}
            onClick={connect}
            title={!runId ? "Approve the backend connection to create a run before connecting." : undefined}
            type="button"
          >
            {connectionState === "connecting" ? "Connecting" : runId ? "Connect" : "Waiting for run"}
          </Button>
        ) : (
          <Button disabled title="Approve the backend connection to create a run before connecting." type="button">
            Waiting for run
          </Button>
        )}
        {connectionState === "connected" ? (
          <Button onClick={requestAgentAction} type="button" variant="outline">
            {agentStarted ? "Next agent action" : "Start agent"}
          </Button>
        ) : null}
        {onStartAutodiagnosis && (canStartAutodiagnosis || autodiagnosisRunning) ? (
          <Button disabled={autodiagnosisRunning} onClick={onStartAutodiagnosis} type="button" variant="outline">
            {autodiagnosisRunning ? "Automated diagnosis requested" : "Start automated diagnosis"}
          </Button>
        ) : null}
        {connectionState === "connected" && agentStarted ? (
          <Button onClick={cancelAgent} type="button" variant="outline">
            Stop agent
          </Button>
        ) : null}
        {connectionState !== "disconnected" ? (
          <Button onClick={disconnect} type="button" variant="destructive">
            Disconnect
          </Button>
        ) : null}
        <p className="terminal-safety-note">
          Commands that can open pagers or hang the terminal are automatically converted to non-interactive form or blocked.
        </p>
      </div>
      <div className={["terminal-shell", connectionState !== "connected" ? "terminal-shell-disabled" : ""].join(" ")}>
        {connectionState === "disconnected" && !terminalHasContent ? (
          <div className="terminal-inactive-state">
            <p className="terminal-inactive-title">Terminal inactive</p>
            <p className="terminal-inactive-detail">
              {runId ? "Backend run ready. Shell not connected." : "Waiting for approved backend run."}
            </p>
            <code>{runId ? "$ connect --manual-shell" : "$ run status: pending"}</code>
          </div>
        ) : null}
        <div className="terminal-grid" ref={containerRef} />
      </div>
    </section>
  );
}

function parseTerminalMessage(value: string): TerminalMessage | null {
  try {
    const message = JSON.parse(value) as TerminalMessage;
    if (
      message.type === "agent_cancelled" ||
      message.type === "agent_auto_command" ||
      message.type === "agent_guidance_recorded" ||
      message.type === "agent_phase_selected" ||
      message.type === "agent_proposal" ||
      message.type === "agent_waiting_for_guidance" ||
      message.type === "command_blocked" ||
      message.type === "command_cancelled" ||
      message.type === "command_completed" ||
      message.type === "command_running" ||
      message.type === "confirmation_required" ||
      message.type === "error" ||
      message.type === "knowledge_search_performed" ||
      message.type === "output" ||
      message.type === "status" ||
      message.type === "terminal_closed" ||
      message.type === "terminal_opened" ||
      message.type === "terminal_output" ||
      message.type === "validation_evidence_collected"
    ) {
      return message;
    }
  } catch {
    return null;
  }

  return null;
}

function formatAgentTerminalPhase(value: string) {
  const phase = readAgentPhase(value);
  if (phase) {
    return formatAgentPhaseLabel(phase);
  }

  const normalized = value.trim().replace(/[-_]+/g, " ").toLowerCase();
  if (!normalized) {
    return "Unknown";
  }

  return normalized
    .split(/\s+/)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function readTerminalMessageAgentPhase(message: TerminalMessage): AgentPhase | null {
  if (message.type === "agent_auto_command" || message.type === "agent_phase_selected" || message.type === "agent_proposal") {
    return readAgentPhase(message.phase);
  }

  return null;
}

function isTerminalOpenError(message: string) {
  return (
    message.startsWith("SSH terminal failed:") ||
    message === "Run was not found" ||
    message === "Technician must confirm SSH connection before opening terminal" ||
    message === "Terminal cannot be opened for a closed run"
  );
}

function prefersReducedTerminalMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function formatTerminalWaitingFrame(message: string, frame: number) {
  const base = message.replace(/[.\s]+$/, "");
  const characters = Array.from(base);
  const highlightableIndexes = characters
    .map((character, index) => (/\s/.test(character) ? -1 : index))
    .filter((index) => index >= 0);
  const activePosition = highlightableIndexes.length ? frame % highlightableIndexes.length : -1;
  const scannedText = characters
    .map((character, index) => {
      const characterPosition = highlightableIndexes.indexOf(index);
      if (characterPosition < 0 || activePosition < 0) {
        return character;
      }

      const distance = Math.min(
        Math.abs(characterPosition - activePosition),
        highlightableIndexes.length - Math.abs(characterPosition - activePosition),
      );

      if (distance === 0) {
        return `\x1b[97m\x1b[1m${character}\x1b[38;5;245m`;
      }
      if (distance === 1) {
        return `\x1b[38;5;252m${character}\x1b[38;5;245m`;
      }
      if (distance === 2) {
        return `\x1b[38;5;248m${character}\x1b[38;5;245m`;
      }
      return character;
    })
    .join("");
  const dots = ".".repeat((frame % 3) + 1);
  return `\x1b[38;5;245m${scannedText}\x1b[0m\x1b[90m${dots}\x1b[0m`;
}

function isAnimatedTerminalStatus(message: string) {
  const normalized = message.toLowerCase();
  return [
    "cancelling",
    "connecting",
    "generating",
    "loading",
    "opening",
    "preparing",
    "requesting",
    "running",
    "starting",
    "thinking",
    "waiting",
  ].some((term) => normalized.includes(term));
}

function handleTerminalStatusMessage(
  terminal: Terminal,
  message: TerminalMessage,
  setPendingCommand: SetPendingCommand,
  waiting: {
    finish: (options?: { keepLine?: boolean }) => void;
    start: (message: string) => void;
  },
) {
  if (message.type !== "status" || !isAnimatedTerminalStatus(message.message)) {
    waiting.finish();
  }

  switch (message.type) {
    case "agent_cancelled":
      terminal.writeln("\r\n\x1b[90mAgent mode cancelled.\x1b[0m");
      break;
    case "agent_auto_command":
      terminal.writeln("\r\n\x1b[36m╭─ Read-only diagnosis auto-running\x1b[0m");
      if (message.phase) {
        terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mPhase\x1b[0m ${formatAgentTerminalPhase(message.phase)}`);
      }
      terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mIntent\x1b[0m ${message.intent ?? "Read-only diagnostic command."}`);
      terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mRisk\x1b[0m ${message.classification ?? "read_only"}`);
      if (message.reason) {
        terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mReason\x1b[0m ${message.reason}`);
      }
      writeTerminalWritePreview(terminal, message.write_preview);
      terminal.writeln(`\x1b[36m│\x1b[0m \x1b[1m${message.command}\x1b[0m`);
      terminal.writeln("\x1b[36m╰─\x1b[0m Running automatically because it is read-only diagnosis.");
      break;
    case "agent_guidance_recorded":
      terminal.writeln("\r\n\x1b[90mAgent guidance recorded.\x1b[0m");
      break;
    case "agent_phase_selected":
      terminal.writeln(`\r\n\x1b[36mAgent phase: ${formatAgentTerminalPhase(message.phase)}\x1b[0m`);
      break;
    case "agent_proposal":
      setPendingCommand({
        classification: message.classification,
        command: message.command,
        commandId: message.command_id,
        input: "",
        intent: message.intent,
        mode: "choose",
        phase: message.phase,
        reason: message.reason,
        source: "agent",
      });
      terminal.writeln("\r\n\x1b[36m╭─ Agent proposed command\x1b[0m");
      if (message.phase) {
        terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mPhase\x1b[0m ${formatAgentTerminalPhase(message.phase)}`);
      }
      terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mIntent\x1b[0m ${message.intent ?? "Review command in terminal."}`);
      terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mRisk\x1b[0m ${message.classification ?? "unclassified"}`);
      if (message.reason) {
        terminal.writeln(`\x1b[36m│\x1b[0m \x1b[90mReason\x1b[0m ${message.reason}`);
      }
      writeTerminalWritePreview(terminal, message.write_preview);
      terminal.writeln(`\x1b[36m│\x1b[0m \x1b[1m${message.command}\x1b[0m`);
      terminal.writeln(
        "\x1b[36m╰─\x1b[0m \x1b[32m[a] accept\x1b[0m  \x1b[31m[r] reject\x1b[0m  \x1b[33m[e] edit\x1b[0m  \x1b[36m[t] retry\x1b[0m  \x1b[90m[c] comment\x1b[0m",
      );
      break;
    case "agent_waiting_for_guidance":
      terminal.writeln("\r\n\x1b[90mAgent is waiting for technician guidance.\x1b[0m");
      break;
    case "command_blocked":
      setPendingCommand(null);
      terminal.writeln("\r\n\x1b[41m\x1b[97m COMMAND BLOCKED BEFORE EXECUTION \x1b[0m");
      terminal.writeln(`\x1b[31mSafety reason: ${message.reason ?? "safety policy"}\x1b[0m`);
      terminal.writeln("\x1b[90mNo command was run. Review the terminal command history for original/final command details.\x1b[0m");
      break;
    case "command_cancelled":
      terminal.writeln("\r\n\x1b[90mCommand cancelled.\x1b[0m");
      break;
    case "command_completed":
      if (message.exit_code === 0) {
        terminal.writeln("\r\n\x1b[32mCommand completed successfully.\x1b[0m");
      } else if (typeof message.exit_code === "number") {
        terminal.writeln(`\r\n\x1b[31mCommand completed with exit ${message.exit_code}.\x1b[0m`);
      } else {
        terminal.writeln("\r\n\x1b[31mCommand ended before an exit code was captured.\x1b[0m");
      }
      break;
    case "command_running":
      waiting.start("Command running...");
      break;
    case "confirmation_required":
      setPendingCommand({
        command: message.command,
        commandId: message.command_id,
        input: "",
        mode: "choose",
        reason: message.reason,
        source: "manual",
      });
      terminal.writeln("\r\n\x1b[33m╭─ Manual command requires confirmation\x1b[0m");
      terminal.writeln(`\x1b[33m│\x1b[0m \x1b[1m${message.command}\x1b[0m`);
      if (message.reason) {
        terminal.writeln(`\x1b[33m│\x1b[0m \x1b[90mReason\x1b[0m ${message.reason}`);
      }
      terminal.writeln("\x1b[33m╰─\x1b[0m \x1b[32m[a] accept\x1b[0m  \x1b[31m[r] reject\x1b[0m");
      break;
    case "knowledge_search_performed": {
      const count = typeof message.result_count === "number" ? message.result_count : 0;
      const query = message.query?.trim() || "similar ticket context";
      const topMatch = formatKnowledgeTopMatch(message);
      terminal.writeln("\r\n\x1b[35m╭─ Tool used: search_knowledge_base\x1b[0m");
      terminal.writeln(`\x1b[35m│\x1b[0m \x1b[90mQuery\x1b[0m ${query}`);
      terminal.writeln(`\x1b[35m│\x1b[0m \x1b[90mResult\x1b[0m Found ${count} knowledge snippet${count === 1 ? "" : "s"}.`);
      if (topMatch) {
        terminal.writeln(`\x1b[35m│\x1b[0m \x1b[90mTop match\x1b[0m ${topMatch}`);
      }
      terminal.writeln("\x1b[35m╰─\x1b[0m Using retrieved memory as historical guidance only.");
      break;
    }
    case "status":
      if (isAnimatedTerminalStatus(message.message)) {
        waiting.start(message.message);
      } else {
        terminal.writeln(`\r\n\x1b[90m${message.message}\x1b[0m`);
      }
      break;
    case "terminal_closed":
      setPendingCommand(null);
      terminal.writeln(`\r\n\x1b[90mTerminal closed${message.reason ? `: ${message.reason}` : ""}.\x1b[0m`);
      break;
    case "terminal_opened":
      terminal.writeln("\r\n\x1b[90mConnected.\x1b[0m");
      break;
    case "validation_evidence_collected":
      setPendingCommand(null);
      terminal.writeln("\r\n\x1b[32mValidation evidence collected. Agent stopped. Confirm validation to generate the activity draft; Phoenix submission remains manual.\x1b[0m");
      break;
    case "error":
    case "output":
    case "terminal_output":
      break;
  }
}

function formatKnowledgeTopMatch(message: Extract<TerminalMessage, { type: "knowledge_search_performed" }>) {
  const ticket = typeof message.top_ticket_id === "number" ? `ticket ${message.top_ticket_id}` : null;
  const chunkType = message.top_chunk_type?.trim() ? message.top_chunk_type : null;
  const score = typeof message.top_similarity_score === "number" ? `score ${message.top_similarity_score.toFixed(2)}` : null;
  return [ticket, chunkType, score].filter(Boolean).join(" · ") || null;
}

function writeTerminalWritePreview(terminal: Terminal, preview: WritePreview | null | undefined) {
  if (!preview) {
    return;
  }

  const status = readPreviewString(preview, "status") ?? "available";
  const commandKind = readPreviewString(preview, "command_kind");
  const targetPath = readPreviewString(preview, "target_path");
  const reason = readPreviewString(preview, "reason");
  const diff = readPreviewString(preview, "diff");
  const truncated = preview.truncated === true;

  terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m╭─ WRITE PREVIEW · review before accepting\x1b[0m`);
  terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m│\x1b[0m status: ${status.split("_").join(" ")}`);
  if (commandKind) {
    terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m│\x1b[0m kind: ${commandKind.split("_").join(" ")}`);
  }
  if (targetPath) {
    terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m│\x1b[0m target: ${targetPath}`);
  }
  if (reason) {
    terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m│\x1b[0m reason: ${reason}`);
  }
  if (!diff) {
    terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m╰─ END WRITE PREVIEW\x1b[0m`);
    return;
  }

  const lines = diff.split(/\r?\n/);
  const visibleLines = lines.slice(0, 80);
  for (const line of visibleLines) {
    terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m│\x1b[0m ${formatTerminalDiffLine(line)}`);
  }
  if (truncated || lines.length > visibleLines.length) {
    terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m│\x1b[0m \x1b[90m... preview truncated\x1b[0m`);
  }
  terminal.writeln(`\x1b[36m│\x1b[0m   \x1b[33m╰─ END WRITE PREVIEW\x1b[0m`);
}

function formatTerminalDiffLine(line: string) {
  if (line.startsWith("+") && !line.startsWith("+++")) {
    return `\x1b[32m${line}\x1b[0m`;
  }
  if (line.startsWith("-") && !line.startsWith("---")) {
    return `\x1b[31m${line}\x1b[0m`;
  }
  if (line.startsWith("@@")) {
    return `\x1b[36m${line}\x1b[0m`;
  }
  if (line.startsWith("---") || line.startsWith("+++")) {
    return `\x1b[90m${line}\x1b[0m`;
  }
  return `\x1b[37m${line}\x1b[0m`;
}

function readPreviewString(preview: WritePreview, key: string) {
  const value = preview[key];
  return typeof value === "string" && value.trim() ? value : null;
}
