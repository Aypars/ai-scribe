"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { clearSession, fetchMe, getToken, type AuthUser } from "@/lib/api";

const USER_EVENT = "ai-scribe-user";

export function notifyAuthUserChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(USER_EVENT));
  }
}

export function useAuth() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    function load() {
      const token = getToken();
      if (!token) {
        router.replace("/login");
        return;
      }
      fetchMe(token)
        .then(setUser)
        .catch(() => {
          clearSession();
          router.replace("/login");
        });
    }
    load();
    window.addEventListener(USER_EVENT, load);
    return () => window.removeEventListener(USER_EVENT, load);
  }, [router]);

  function logout() {
    clearSession();
    router.replace("/login");
  }

  return { user, logout };
}
