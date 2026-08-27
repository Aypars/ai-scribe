import { LoginForm } from "@/components/LoginForm";
import { AuthScreen } from "@/components/AuthScreen";

export default function LoginPage() {
  return (
    <AuthScreen title="Hesabına giriş yap" subtitle="Toplantılarına ve görev panosuna devam et.">
      <LoginForm />
    </AuthScreen>
  );
}
