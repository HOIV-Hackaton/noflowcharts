import { AuthGuard, AuthProvider } from "./features/auth/AuthProvider";
import { TechnicianConsole } from "./features/dashboard/TechnicianConsole";

function App() {
  return (
    <AuthProvider>
      <AuthGuard>
        <TechnicianConsole />
      </AuthGuard>
    </AuthProvider>
  );
}

export default App;
