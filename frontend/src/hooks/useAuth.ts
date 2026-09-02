"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { clearSession, fetchMe, getToken, type AuthUser } from "@/lib/api";

export function useAuth() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
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
  }, [router]);

  function logout() {
    clearSession();
    router.replace("/login");
  }

  return { user, logout };
}
