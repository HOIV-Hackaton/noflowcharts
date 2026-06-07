import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { runTerminalWebSocketUrl } from "../../services/backendApi";

type TerminalMessage =
  | { type: "agent_cancelled" }
  | { type: "agent_guidance_recorded" }
  | { type: "agent_phase_selected"; phase: string }
  | { type: "agent_proposal"; command_id: number; command: string; classification?: string; intent?: string; phase?: string | null; reason?: string }
  | { type: "agent_phase_selected"; phase: string }
  | { type: "agent_proposal"; command_id: number; command: string; classification?: string; intent?: string; phase?: string | null; reason?: string }
  | { type: "agent_waiting_for_guidance"; command_id?: number }
  | { type: "command_blocked"; command_id?: number; reason?: string }
  | { type: "command_cancelled"; command_id?: number }
  | { type: "command_completed"; command_id?: number; exit_code?: number }
  | { type: "command_running"; command_id?: number }
  | { type: "confirmation_required"; command_id: number; command: string; reason?: string }
  | { type: "error"; message: string }
  | { type: "output"; data: string }
  | { type: "status"; message: string }
  | { type: "terminal_closed"; reason?: string }
  | { type: "terminal_opened"; run_id?: string; session_id?: number }
  | { type: "terminal_output"; data: string };

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

export function TicketTerminal({
  runId,
  variant = "default",
}: {
  runId: string | null;
  variant?: "compact" | "default";
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const terminalHadErrorRef = useRef(false);
  const pendingConfirmationRef = useRef<PendingConfirmation | null>(null);
  const lastFitSizeRef = useRef({ height: 0, width: 0 });
  const resizeFrameRef = useRef<number | null>(null);
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
    terminal.writeln("\r\nOpening backend terminal bridge...");
    const socket = new WebSocket(runTerminalWebSocketUrl(runId, terminal.cols, terminal.rows));
    socketRef.current = socket;

    socket.onopen = () => {
      terminal.options.disableStdin = false;
      setConnectionState("connected");
      sendResize();
    };

    socket.onmessage = (event) => {
      const message = parseTerminalMessage(event.data);
      if (!message) {
        return;
      }

      if (message.type === "output" || message.type === "terminal_output") {
        setTerminalHasContent(true);
        terminal.write(message.data);
        return;
      }

      if (message.type === "error") {
        terminalHadErrorRef.current = true;
        setTerminalHasContent(true);
        terminal.writeln(`\r\n\x1b[31m${message.message}\x1b[0m`);
        return;
      }

      if (message.type === "agent_proposal" || message.type === "agent_phase_selected") {
        setAgentStarted(true);
      }

      if (message.type === "agent_cancelled") {
        setAgentStarted(false);
      }

      handleTerminalStatusMessage(terminal, message, setPendingCommand);
    };

    socket.onerror = () => {
      terminalHadErrorRef.current = true;
      terminal.writeln("\r\n\x1b[31mTerminal websocket failed.\x1b[0m");
    };

    socket.onclose = (event) => {
      socketRef.current = null;
      terminal.options.disableStdin = true;
      setPendingCommand(null);
      setAgentStarted(false);
      setConnectionState("disconnected");
      if (terminalHadErrorRef.current && event.reason) {
        setTerminalHasContent(true);
        terminal.writeln(`\r\n\x1b[31m${event.reason}\x1b[0m`);
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
    terminal.writeln(`\r\n\x1b[90m${agentStarted ? "Requesting next agent action..." : "Starting agent..."}\x1b[0m`);
    setAgentStarted(true);
  };

  const cancelAgent = () => {
    const socket = socketRef.current;
    const terminal = terminalRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !terminal) {
      return;
    }

    socket.send(JSON.stringify({ type: "agent_cancel" }));
    setTerminalHasContent(true);
    terminal.writeln("\r\n\x1b[90mCancelling agent mode...\x1b[0m");
    setAgentStarted(false);
  };

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
        <Button
          disabled={!runId || connectionState !== "disconnected"}
          onClick={connect}
          title={!runId ? "Approve the backend connection to create a run before connecting." : undefined}
          type="button"
        >
          {runId ? "Connect" : "Waiting for run"}
        </Button>
        <Button
          disabled={connectionState !== "connected"}
          onClick={requestAgentAction}
          type="button"
          variant="outline"
        >
          {agentStarted ? "Next action" : "Start agent"}
        </Button>
        <Button
          disabled={connectionState !== "connected" || !agentStarted}
          onClick={cancelAgent}
          type="button"
          variant="outline"
        >
          Stop agent
        </Button>
        <Button
          disabled={connectionState === "disconnected"}
          onClick={disconnect}
          type="button"
          variant="destructive"
        >
          Disconnect
        </Button>
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
      message.type === "output" ||
      message.type === "status" ||
      message.type === "terminal_closed" ||
      message.type === "terminal_opened" ||
      message.type === "terminal_output"
    ) {
      return message;
    }
  } catch {
    return null;
  }

  return null;
}

function formatAgentTerminalPhase(value: string) {
  const normalized = value.trim().replace(/[-_]+/g, " ").toLowerCase();
  if (!normalized) {
    return "Unknown";
  }

  return normalized
    .split(/\s+/)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function handleTerminalStatusMessage(
  terminal: Terminal,
  message: TerminalMessage,
  setPendingCommand: SetPendingCommand,
) {
  switch (message.type) {
    case "agent_cancelled":
      terminal.writeln("\r\n\x1b[90mAgent mode cancelled.\x1b[0m");
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
      terminal.writeln(
        message.exit_code === 0
          ? "\r\n\x1b[32mCommand completed successfully.\x1b[0m"
          : `\r\n\x1b[31mCommand completed with exit ${message.exit_code ?? "unknown"}.\x1b[0m`,
      );
      break;
    case "command_running":
      terminal.writeln("\r\n\x1b[36mCommand running...\x1b[0m");
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
    case "status":
      terminal.writeln(`\r\n\x1b[90m${message.message}\x1b[0m`);
      break;
    case "terminal_closed":
      setPendingCommand(null);
      terminal.writeln(`\r\n\x1b[90mTerminal closed${message.reason ? `: ${message.reason}` : ""}.\x1b[0m`);
      break;
    case "terminal_opened":
      terminal.writeln("\r\n\x1b[90mConnected.\x1b[0m");
      break;
    case "error":
    case "output":
    case "terminal_output":
      break;
  }
}

function formatAgentPhase(phase: string) {
  const normalized = phase.replace(/[_-]+/g, " ").trim();
  return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : "Unknown";
}
