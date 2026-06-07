import {
  createContext,
  useContext,
  useEffect,
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  const isLoginRoute = window.location.pathname.startsWith("/onboarding/login");

  useEffect(() => {
    if (!session || session.expiresAt < Date.now()) {
      if (!isLoginRoute) {
        replaceRoute("/onboarding/login");
      }
      return;
    }

    if (isLoginRoute || window.location.pathname === "/" || window.location.pathname === "/app") {
      replaceRoute("/app/overview");
    }
  }, [isLoginRoute, session]);

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
    if (result.ok) {
      replaceRoute("/app/overview");
    }
  };

  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-6 text-foreground">
      <Card className="w-full max-w-md" aria-labelledby="login-title">
        <CardHeader>
          <CardTitle className="text-2xl" id="login-title">
            Technician login
          </CardTitle>
          <CardDescription>techbold service desk workspace</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submitLogin}>
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-foreground">Email</span>
              <Input
                autoComplete="username"
                inputMode="email"
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                value={email}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-foreground">Password</span>
              <Input
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
            </label>

            {error ? <p className="rounded-lg border bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p> : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit">Sign in</Button>
              <Button
                onClick={() => {
                  setEmail(DEMO_EMAIL);
                  setPassword(DEMO_PASSWORD);
                  setError("");
                }}
                type="button"
                variant="outline"
              >
                Fill mock login
              </Button>
            </div>

            <p className="text-xs text-muted-foreground">Mock account: {DEMO_EMAIL}</p>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function replaceRoute(path: string) {
  if (window.location.pathname === path) {
    return;
  }

  window.history.replaceState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
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
