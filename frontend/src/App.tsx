import { useEffect } from "react";
import { AuthGuard, AuthProvider } from "./features/auth/AuthProvider";
import { TechnicianConsole } from "./features/dashboard/TechnicianConsole";

function App() {
  useEffect(() => {
    document.documentElement.classList.add("dark");
    document.documentElement.style.colorScheme = "dark";
  }, []);

  return (
    <AuthProvider>
      <AuthGuard>
        <TechnicianConsole />
      </AuthGuard>
    </AuthProvider>
  );
}

export default App;
