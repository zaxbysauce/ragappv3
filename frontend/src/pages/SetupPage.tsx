import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/useAuthStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Database, Shield, User, Loader2 } from "lucide-react";

export default function SetupPage() {
  const [formData, setFormData] = useState({
    username: "",
    full_name: "",
    password: "",
    confirmPassword: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { register, needsSetup, isLoading } = useAuthStore();
  const navigate = useNavigate();

  // Redirect to login if setup is already complete
  useEffect(() => {
    if (needsSetup === false) {
      navigate("/login", { replace: true });
    }
  }, [needsSetup, navigate]);

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Username validation
    if (!formData.username.trim()) {
      newErrors.username = "Username is required";
    } else if (formData.username.length < 3) {
      newErrors.username = "Username must be at least 3 characters";
    }

    // Password validation
    if (!formData.password) {
      newErrors.password = "Password is required";
    } else if (formData.password.length < 8) {
      newErrors.password = "Password must be at least 8 characters";
    }

    // Confirm password validation
    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = "Passwords do not match";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleChange = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
    // Clear error for this field when user starts typing
    if (errors[field]) {
      setErrors((prev) => ({ ...prev, [field]: "" }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      await register(
        formData.username,
        formData.password,
        formData.full_name || undefined
      );
      // Navigate to home page on success (user is already authenticated)
      navigate("/");
    } catch {
      // Error is handled by the store, we just prevent navigation
    }
  };

  // Show loading state while checking setup status
  if (needsSetup === null || needsSetup === undefined) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="mt-4 text-muted-foreground">Checking setup status...</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-center mb-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Database className="h-6 w-6 text-primary" />
            </div>
          </div>
          <CardTitle className="text-2xl text-center">Initial Setup</CardTitle>
          <CardDescription className="text-center">
            Create the first superadmin account to get started
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="setup-username" className="text-sm font-medium">Username</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="setup-username"
                  type="text"
                  placeholder="Username (required)"
                  value={formData.username}
                  onChange={handleChange("username")}
                  disabled={isLoading}
                  autoFocus
                  aria-required="true"
                  aria-describedby={errors.username ? "setup-username-error" : undefined}
                  aria-invalid={!!errors.username}
                  className="pl-10"
                />
              </div>
              {errors.username && (
                <p id="setup-username-error" className="text-sm text-destructive">{errors.username}</p>
              )}
            </div>

            <div className="space-y-2">
              <label htmlFor="setup-fullname" className="text-sm font-medium">Full name</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="setup-fullname"
                  type="text"
                  placeholder="Full name (optional)"
                  value={formData.full_name}
                  onChange={handleChange("full_name")}
                  disabled={isLoading}
                  aria-required="false"
                  className="pl-10"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="setup-password" className="text-sm font-medium">Password</label>
              <div className="relative">
                <Shield className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="setup-password"
                  type="password"
                  placeholder="Password (min 8 characters)"
                  value={formData.password}
                  onChange={handleChange("password")}
                  disabled={isLoading}
                  aria-required="true"
                  aria-describedby={errors.password ? "setup-password-error" : undefined}
                  aria-invalid={!!errors.password}
                  className="pl-10"
                />
              </div>
              {errors.password && (
                <p id="setup-password-error" className="text-sm text-destructive">{errors.password}</p>
              )}
            </div>

            <div className="space-y-2">
              <label htmlFor="setup-confirm-password" className="text-sm font-medium">Confirm Password</label>
              <div className="relative">
                <Shield className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="setup-confirm-password"
                  type="password"
                  placeholder="Confirm password"
                  value={formData.confirmPassword}
                  onChange={handleChange("confirmPassword")}
                  disabled={isLoading}
                  aria-required="true"
                  aria-describedby={errors.confirmPassword ? "setup-confirm-password-error" : undefined}
                  aria-invalid={!!errors.confirmPassword}
                  className="pl-10"
                />
              </div>
              {errors.confirmPassword && (
                <p id="setup-confirm-password-error" className="text-sm text-destructive">{errors.confirmPassword}</p>
              )}
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={
                !formData.username.trim() ||
                !formData.password ||
                !formData.confirmPassword ||
                isLoading
              }
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating Account...
                </>
              ) : (
                <>
                  <Shield className="mr-2 h-4 w-4" />
                  Create Superadmin Account
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
