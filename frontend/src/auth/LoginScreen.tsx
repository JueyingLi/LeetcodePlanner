import { useAuth } from "./AuthProvider";

export function LoginScreen() {
  const { signInWithGoogle } = useAuth();

  return (
    <div className="flex flex-col items-center justify-center h-[100dvh] bg-[#131F24] px-6 text-center">
      <div className="w-20 h-20 mb-5 rounded-2xl bg-[#1C2B33] flex items-center justify-center shadow-lg">
        <svg width="44" height="44" viewBox="0 0 64 64" fill="none" aria-hidden="true">
          <defs>
            <linearGradient id="peak" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#7BE22A" />
              <stop offset="1" stopColor="#46A302" />
            </linearGradient>
          </defs>
          {/* back peak */}
          <path d="M3 55 L22 25 L37 47 L26 55 Z" fill="#2F6B05" />
          {/* front peak */}
          <path d="M21 55 L42 15 L61 55 Z" fill="url(#peak)" />
          {/* snow cap */}
          <path d="M42 15 L49 29 L45 25.5 L42 28.5 L38.5 25 L35 29 Z" fill="#FFFFFF" />
          {/* star sparkle */}
          <path d="M53 12 L54.5 16.5 L59 18 L54.5 19.5 L53 24 L51.5 19.5 L47 18 L51.5 16.5 Z" fill="#FFC800" />
        </svg>
      </div>
      <h1 className="text-white font-bold text-2xl mb-1">LeetCode Crasher</h1>
      <p className="text-[#9CA3AF] text-sm mb-8">
        Duolingo-style interview prep
      </p>

      <button
        onClick={() => signInWithGoogle()}
        className="flex items-center gap-3 bg-white text-[#131F24] font-medium px-6 py-3 rounded-xl active:opacity-90 transition-opacity"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z" />
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
          <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z" />
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
        </svg>
        Sign in with Google
      </button>

      <p className="text-[#9CA3AF] text-xs mt-8 max-w-xs">
        You'll stay signed in on this device.
      </p>
    </div>
  );
}
