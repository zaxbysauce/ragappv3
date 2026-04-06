import { useState, useEffect } from "react";
import { useNavigate, Navigate, Link, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/useAuthStore";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { KeyRound, LogIn, Loader2, Lock, User } from "lucide-react";

export default function LoginPage() {
  // API Key mode state (from existing implementation)
  const [apiKey, setApiKey] = useState("");

  // JWT mode state
  const [credentials, setCredentials] = useState({
    username: "",
    password: "",
  });

  const [error, setError] = useState("");

  // Use both old auth context and new auth store for dual mode support
  const { login: apiKeyLogin } = useAuth();
  const {
    login: jwtLogin,
    authMode,
    needsSetup,
    isLoading: storeLoading,
  } = useAuthStore();

  const navigate = useNavigate();
  const location = useLocation();
  // RT-03 fix: restore return-to URL after login
  const returnTo = (location.state as { from?: { pathname: string } })?.from?.pathname || "/";

  // Initialize auth store on mount
  useEffect(() => {
    useAuthStore.getState().init();
  }, []);

  // Determine auth modes
  const isJwtMode = authMode === "jwt";
  const isLoading = storeLoading;

  // Show loading while checking setup status
  if (needsSetup === null) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  // Redirect to setup if needsSetup is true
  if (needsSetup === true) {
    return <Navigate to="/setup" replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (isJwtMode) {
      // JWT mode: use username/password
      if (!credentials.username.trim() || !credentials.password) {
        setError("Please enter both username and password");
        return;
      }

      try {
        await jwtLogin(credentials.username, credentials.password);
        navigate(returnTo, { replace: true });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Login failed");
      }
    } else {
      // API key mode: use existing behavior
      if (!apiKey.trim()) {
        setError("Please enter an API key");
        return;
      }

      try {
        await apiKeyLogin(apiKey);
        navigate(returnTo, { replace: true });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Invalid API key");
      }
    }
  };

  const handleCredentialsChange = (field: string) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setCredentials((prev) => ({ ...prev, [field]: e.target.value }));
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-center mb-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <KeyRound className="h-6 w-6 text-primary" />
            </div>
          </div>
          <CardTitle className="text-2xl text-center">Welcome Back</CardTitle>
          <CardDescription className="text-center">
            {isJwtMode
              ? "Enter your credentials to access KnowledgeVault"
              : "Enter your API key to access KnowledgeVault"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {isJwtMode ? (
              // JWT Mode: Username/Password form
              <>
                <div className="space-y-2">
                  <label htmlFor="login-username" className="text-sm font-medium">Username</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="login-username"
                      type="text"
                      placeholder="Username"
                      value={credentials.username}
                      onChange={handleCredentialsChange("username")}
                      disabled={isLoading}
                      autoFocus
                      aria-required="true"
                      className="pl-10"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <label htmlFor="login-password" className="text-sm font-medium">Password</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="login-password"
                      type="password"
                      placeholder="Password"
                      value={credentials.password}
                      onChange={handleCredentialsChange("password")}
                      disabled={isLoading}
                      aria-required="true"
                      className="pl-10"
                    />
                  </div>
                </div>
              </>
            ) : (
              // API Key Mode: Existing API key input
              <div className="space-y-2">
                <label htmlFor="login-apikey" className="text-sm font-medium">API Key</label>
                <Input
                  id="login-apikey"
                  type="password"
                  placeholder="Enter your API key"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={isLoading}
                  autoFocus
                  aria-required="true"
                />
              </div>
            )}

            {error && (
              <p role="alert" className="text-sm text-destructive text-center">{error}</p>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={
                isLoading ||
                (isJwtMode
                  ? !credentials.username.trim() || !credentials.password
                  : !apiKey.trim())
              }
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying...
                </>
              ) : (
                <>
                  <LogIn className="mr-2 h-4 w-4" />
                  Sign In
                </>
              )}
            </Button>
          </form>
        </CardContent>

        {isJwtMode && (
          <CardFooter className="flex justify-center border-t pt-4">
            <p className="text-sm text-muted-foreground">
              Don't have an account?{" "}
              <Link
                to="/register"
                className="text-primary hover:underline font-medium"
              >
                Register
              </Link>
            </p>
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
