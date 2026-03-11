import { Outlet } from 'react-router-dom';
import { NavRail } from './NavRail';

export function AppShell() {
  return (
    <div className="h-screen flex bg-[#0f0f0f]">
      <NavRail />
      <div className="flex-1 min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
