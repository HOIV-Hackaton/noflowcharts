import {
  createContext,
  useContext,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  DEMO_EMAIL,
  DEMO_PASSWORD,
  SESSION_KEY,
  SESSION_LENGTH_MS,
} from "../../data/mockData";
import type { TechnicianSession } from "../../types";

type AuthContextValue = {
  session: TechnicianSession | null;
  login: (email: string, password: string) => { ok: true } | { ok: false; message: string };
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<TechnicianSession | null>(readStoredSession);

  const login = (email: string, password: string) => {
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password.trim()) {
      return { ok: false as const, message: "Enter technician email and password." };
    }

    if (normalizedEmail !== DEMO_EMAIL || password !== DEMO_PASSWORD) {
      return { ok: false as const, message: "Use the mock technician credentials for now." };
    }

    const nextSession: TechnicianSession = {
      email: normalizedEmail,
      name: "Demo Technician",
      role: "Technician",
      expiresAt: Date.now() + SESSION_LENGTH_MS,
    };

    sessionStorage.setItem(SESSION_KEY, JSON.stringify(nextSession));
    setSession(nextSession);
    return { ok: true as const };
  };

  const logout = () => {
    sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
  };

  return <AuthContext.Provider value={{ session, login, logout }}>{children}</AuthContext.Provider>;
}

export function AuthGuard({ children }: { children: ReactNode }) {
  const { session } = useAuth();

  if (!session || session.expiresAt < Date.now()) {
    return <LoginScreen />;
  }

  return <>{children}</>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}

function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState("");

  const submitLogin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const result = login(email, password);
    setError(result.ok ? "" : result.message);
  };

  return (
    <main className="login-screen">
      <section className="login-box" aria-labelledby="login-title">
        <h1 id="login-title">Technician login</h1>
        <p className="body-copy">Mock email/password auth until backend auth is connected.</p>

        <form className="form-stack" onSubmit={submitLogin}>
          <label>
            Email
            <input
              autoComplete="username"
              inputMode="email"
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              value={email}
            />
          </label>

          <label>
            Password
            <input
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>

          {error ? <p className="error-line">{error}</p> : null}

          <div className="button-row">
            <button className="button button-dark" type="submit">
              Sign in
            </button>
            <button
              className="button"
              onClick={() => {
                setEmail(DEMO_EMAIL);
                setPassword(DEMO_PASSWORD);
                setError("");
              }}
              type="button"
            >
              Fill mock login
            </button>
          </div>

          <p className="caption">Mock account: {DEMO_EMAIL}</p>
        </form>
      </section>
    </main>
  );
}

function readStoredSession() {
  const storedValue = sessionStorage.getItem(SESSION_KEY);

  if (!storedValue) {
    return null;
  }

  try {
    const parsedSession = JSON.parse(storedValue) as TechnicianSession;

    if (!parsedSession.email || parsedSession.expiresAt < Date.now()) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }

    return parsedSession;
  } catch {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}
