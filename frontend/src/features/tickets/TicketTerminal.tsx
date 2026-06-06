import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState, type MutableRefObject } from "react";

import { Button } from "@/components/ui/button";
import { runTerminalWebSocketUrl } from "../../services/backendApi";

type TerminalMessage =
  | { type: "agent_cancelled" }
  | { type: "agent_guidance_recorded" }
  | { type: "agent_proposal"; command_id: number; command: string; classification?: string; intent?: string; reason?: string }
  | { type: "agent_waiting_for_guidance"; command_id?: number }
  | { type: "command_blocked"; command_id?: number; reason?: string }
  | { type: "command_cancelled"; command_id?: number }
  | { type: "command_running"; command_id?: number }
  | { type: "confirmation_required"; command_id: number; command: string; reason?: string }
  | { type: "error"; message: string }
  | { type: "output"; data: string }
  | { type: "status"; message: string }
  | { type: "terminal_closed"; reason?: string }
  | { type: "terminal_opened"; run_id?: string; session_id?: number }
  | { type: "terminal_output"; data: string };

type PendingConfirmation = {
  commandId: number;
  source: "agent" | "manual";
};

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

  useEffect(() => {
    setConnectionState("disconnected");
    setAgentStarted(false);
    pendingConfirmationRef.current = null;
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
        const answer = data.trim().toLowerCase();
        if (!answer) {
          return;
        }

        if (answer === "y") {
          pendingConfirmationRef.current = null;
          socket.send(
            JSON.stringify({
              command_id: pendingConfirmation.commandId,
              type: pendingConfirmation.source === "agent" ? "agent_accept" : "manual_confirm",
            }),
          );
          terminal.writeln("\r\n\x1b[34mAccepted.\x1b[0m");
          return;
        }

        if (answer === "n") {
          pendingConfirmationRef.current = null;
          socket.send(
            JSON.stringify({
              command_id: pendingConfirmation.commandId,
              reason: "Rejected from terminal.",
              type: pendingConfirmation.source === "agent" ? "agent_reject" : "manual_cancel",
            }),
          );
          terminal.writeln("\r\n\x1b[31mRejected.\x1b[0m");
          return;
        }

        terminal.writeln("\r\nType y to accept or n to reject.");
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
    };
  }, [runId]);

  const connect = () => {
    const terminal = terminalRef.current;
    if (!terminal || !runId || connectionState !== "disconnected") {
      return;
    }

    fitTerminal(true);
    terminalHadErrorRef.current = false;
    pendingConfirmationRef.current = null;
    setConnectionState("connecting");
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
        terminal.write(message.data);
        return;
      }

      if (message.type === "error") {
        terminalHadErrorRef.current = true;
        terminal.writeln(`\r\n\x1b[31m${message.message}\x1b[0m`);
        return;
      }

      if (message.type === "agent_proposal") {
        setAgentStarted(true);
      }

      if (message.type === "agent_cancelled") {
        setAgentStarted(false);
      }

      handleTerminalStatusMessage(terminal, message, pendingConfirmationRef);
    };

    socket.onerror = () => {
      terminalHadErrorRef.current = true;
      terminal.writeln("\r\n\x1b[31mTerminal websocket failed.\x1b[0m");
    };

    socket.onclose = (event) => {
      socketRef.current = null;
      terminal.options.disableStdin = true;
      pendingConfirmationRef.current = null;
      setAgentStarted(false);
      setConnectionState("disconnected");
      if (terminalHadErrorRef.current && event.reason) {
        terminal.writeln(`\r\n\x1b[31m${event.reason}\x1b[0m`);
        return;
      }
      if (!terminalHadErrorRef.current) {
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
      </div>
      <div className={["terminal-shell", connectionState !== "connected" ? "terminal-shell-disabled" : ""].join(" ")}>
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
      message.type === "agent_proposal" ||
      message.type === "agent_waiting_for_guidance" ||
      message.type === "command_blocked" ||
      message.type === "command_cancelled" ||
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

function handleTerminalStatusMessage(
  terminal: Terminal,
  message: TerminalMessage,
  pendingConfirmationRef: MutableRefObject<PendingConfirmation | null>,
) {
  switch (message.type) {
    case "agent_cancelled":
      terminal.writeln("\r\n\x1b[90mAgent mode cancelled.\x1b[0m");
      break;
    case "agent_guidance_recorded":
      terminal.writeln("\r\n\x1b[90mAgent guidance recorded.\x1b[0m");
      break;
    case "agent_proposal":
      pendingConfirmationRef.current = {
        commandId: message.command_id,
        source: "agent",
      };
      terminal.writeln("\r\n\x1b[34mAgent proposed command:\x1b[0m");
      terminal.writeln(`\x1b[90mIntent:\x1b[0m ${message.intent ?? "Review command in terminal."}`);
      terminal.writeln(`\x1b[90mRisk:\x1b[0m ${message.classification ?? "unclassified"}`);
      if (message.reason) {
        terminal.writeln(`\x1b[90mReason:\x1b[0m ${message.reason}`);
      }
      terminal.writeln(`\x1b[1m${message.command}\x1b[0m`);
      terminal.writeln("Type y to accept or n to reject.");
      break;
    case "agent_waiting_for_guidance":
      terminal.writeln("\r\n\x1b[90mAgent is waiting for technician guidance.\x1b[0m");
      break;
    case "command_blocked":
      terminal.writeln(`\r\n\x1b[31mCommand blocked: ${message.reason ?? "safety policy"}\x1b[0m`);
      break;
    case "command_cancelled":
      terminal.writeln("\r\n\x1b[90mCommand cancelled.\x1b[0m");
      break;
    case "command_running":
      terminal.writeln("\r\n\x1b[90mCommand running...\x1b[0m");
      break;
    case "confirmation_required":
      pendingConfirmationRef.current = {
        commandId: message.command_id,
        source: "manual",
      };
      terminal.writeln("\r\n\x1b[33mConfirmation required before executing:\x1b[0m");
      terminal.writeln(`\x1b[1m${message.command}\x1b[0m`);
      if (message.reason) {
        terminal.writeln(`\x1b[90mReason:\x1b[0m ${message.reason}`);
      }
      terminal.writeln("Type y to run or n to cancel.");
      break;
    case "status":
      terminal.writeln(`\r\n\x1b[90m${message.message}\x1b[0m`);
      break;
    case "terminal_closed":
      pendingConfirmationRef.current = null;
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
