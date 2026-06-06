import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useRef, useState } from "react";

import { ticketTerminalWebSocketUrl } from "../../services/backendApi";

type TerminalMessage =
  | { type: "output"; data: string }
  | { type: "status"; message: string }
  | { type: "error"; message: string };

export function TicketTerminal({
  ticketId,
  variant = "default",
}: {
  ticketId: number;
  variant?: "compact" | "default";
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const lastFitSizeRef = useRef({ height: 0, width: 0 });
  const resizeFrameRef = useRef<number | null>(null);
  const [connectionState, setConnectionState] = useState<"disconnected" | "connecting" | "connected">("disconnected");

  useEffect(() => {
    const terminal = new Terminal({
      allowProposedApi: false,
      convertEol: true,
      cursorBlink: false,
      cursorStyle: "bar",
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
      fontSize: 13,
      fontWeight: "400",
      letterSpacing: 0,
      lineHeight: 1.25,
      rows: 28,
      scrollback: 5000,
      theme: {
        background: "#f5f5f5",
        black: "#171717",
        blue: "#0070f3",
        brightBlack: "#888888",
        brightBlue: "#0761d1",
        brightCyan: "#50e3c2",
        brightGreen: "#00a67d",
        brightMagenta: "#ff0080",
        brightRed: "#c50000",
        brightWhite: "#ffffff",
        brightYellow: "#f9cb28",
        cursor: "#171717",
        cyan: "#50e3c2",
        foreground: "#171717",
        green: "#00a67d",
        magenta: "#7928ca",
        red: "#ee0000",
        selectionBackground: "#d3e5ff",
        white: "#4d4d4d",
        yellow: "#f5a623",
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
      terminal.writeln("techbold remote terminal");
      terminal.writeln("Connect to open an interactive SSH shell for this ticket.");
      terminal.writeln("");
    }

    const inputDisposable = terminal.onData((data) => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
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
  }, [ticketId]);

  const connect = () => {
    const terminal = terminalRef.current;
    if (!terminal || connectionState !== "disconnected") {
      return;
    }

    fitTerminal(true);
    setConnectionState("connecting");
    terminal.writeln("\r\nOpening backend terminal bridge...");
    const socket = new WebSocket(ticketTerminalWebSocketUrl(ticketId, terminal.cols, terminal.rows));
    socketRef.current = socket;

    socket.onopen = () => {
      setConnectionState("connected");
      sendResize();
    };

    socket.onmessage = (event) => {
      const message = parseTerminalMessage(event.data);
      if (!message) {
        return;
      }

      if (message.type === "output") {
        terminal.write(message.data);
        return;
      }

      if (message.type === "error") {
        terminal.writeln(`\r\n\x1b[31m${message.message}\x1b[0m`);
        return;
      }

      terminal.writeln(`\r\n\x1b[90m${message.message}\x1b[0m`);
    };

    socket.onerror = () => {
      terminal.writeln("\r\n\x1b[31mTerminal websocket failed.\x1b[0m");
    };

    socket.onclose = () => {
      socketRef.current = null;
      setConnectionState("disconnected");
      terminal.writeln("\r\n\x1b[90mTerminal session closed.\x1b[0m");
    };
  };

  const disconnect = () => {
    socketRef.current?.close();
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
        <span className="sr-only" aria-live="polite">
          Terminal is {connectionState}.
        </span>
        <button
          className="button button-success"
          disabled={connectionState !== "disconnected"}
          onClick={connect}
          type="button"
        >
          Connect
        </button>
        <button
          className="button button-danger"
          disabled={connectionState === "disconnected"}
          onClick={disconnect}
          type="button"
        >
          Disconnect
        </button>
      </div>
      <div className="terminal-shell">
        <div className="terminal-grid" ref={containerRef} />
      </div>
    </section>
  );
}

function parseTerminalMessage(value: string): TerminalMessage | null {
  try {
    const message = JSON.parse(value) as TerminalMessage;
    if (message.type === "output" || message.type === "status" || message.type === "error") {
      return message;
    }
  } catch {
    return null;
  }

  return null;
}
