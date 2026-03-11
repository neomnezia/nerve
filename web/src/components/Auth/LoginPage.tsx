import { useState, type FormEvent } from 'react';
import { useAuthStore } from '../../stores/authStore';

export function LoginPage() {
  const [password, setPassword] = useState('');
  const { login, loading, error } = useAuthStore();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    login(password);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f0f0f]">
      <form
        onSubmit={handleSubmit}
        className="bg-[#1a1a1a] p-8 rounded-lg border border-[#333] w-80"
      >
        <h1 className="text-xl font-semibold mb-6 text-center">Nerve</h1>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          autoFocus
          className="w-full px-3 py-2 bg-[#252525] border border-[#333] rounded text-[#e0e0e0] outline-none focus:border-[#6366f1] mb-4"
        />
        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-[#6366f1] hover:bg-[#818cf8] text-white rounded font-medium disabled:opacity-50 cursor-pointer"
        >
          {loading ? '...' : 'Login'}
        </button>
      </form>
    </div>
  );
}
