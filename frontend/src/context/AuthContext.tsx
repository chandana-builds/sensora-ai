import React, { createContext, useContext, useEffect, useState } from "react";
import {
  AuthState,
  accountsEnabled,
  continueAsGuest as authContinueAsGuest,
  getAuth,
  isLocalSupabase,
  localMailpitUrl,
  onAuthChange,
  resetPasswordForEmail,
  resendVerificationEmail,
  signIn as authSignIn,
  signOut as authSignOut,
  signUp as authSignUp,
  updateDisplayName as authUpdateDisplayName,
} from "../lib/auth";

export interface UserProfile {
  id?: string;
  email?: string;
  displayName: string;
  kind: "guest" | "account";
}

interface AuthContextType {
  auth: AuthState | null;
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  accountsEnabled: boolean;
  isLocalSupabase: boolean;
  localMailpitUrl: string;
  signIn: (email: string, pass: string) => Promise<void>;
  signUp: (email: string, pass: string, displayName?: string) => Promise<boolean>;
  continueAsGuest: () => Promise<void>;
  signOut: () => void;
  resetPassword: (email: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
  updateDisplayName: (name: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuthState] = useState<AuthState | null>(() => getAuth());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Initial sync
    setAuthState(getAuth());
    setIsLoading(false);

    // Listen to changes across tabs or inside actions
    const unsub = onAuthChange(() => {
      setAuthState(getAuth());
    });
    return unsub;
  }, []);

  const user: UserProfile | null = auth
    ? {
        id: auth.userId,
        email: auth.email,
        displayName: auth.displayName || auth.email?.split("@")[0] || (auth.kind === "guest" ? "Guest User" : "User"),
        kind: auth.kind,
      }
    : null;

  const handleSignIn = async (email: string, pass: string) => {
    await authSignIn(email, pass);
    setAuthState(getAuth());
  };

  const handleSignUp = async (email: string, pass: string, displayName?: string) => {
    const autoSignedIn = await authSignUp(email, pass, displayName);
    setAuthState(getAuth());
    return autoSignedIn;
  };

  const handleContinueAsGuest = async () => {
    await authContinueAsGuest();
    setAuthState(getAuth());
  };

  const handleSignOut = () => {
    authSignOut();
    setAuthState(null);
  };

  const handleResetPassword = async (email: string) => {
    await resetPasswordForEmail(email);
  };

  const handleResendVerification = async (email: string) => {
    await resendVerificationEmail(email);
  };

  const handleUpdateDisplayName = (name: string) => {
    authUpdateDisplayName(name);
    setAuthState(getAuth());
  };

  return (
    <AuthContext.Provider
      value={{
        auth,
        user,
        isAuthenticated: !!auth,
        isLoading,
        accountsEnabled,
        isLocalSupabase,
        localMailpitUrl,
        signIn: handleSignIn,
        signUp: handleSignUp,
        continueAsGuest: handleContinueAsGuest,
        signOut: handleSignOut,
        resetPassword: handleResetPassword,
        resendVerification: handleResendVerification,
        updateDisplayName: handleUpdateDisplayName,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
