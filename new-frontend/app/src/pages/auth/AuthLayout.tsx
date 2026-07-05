import { Outlet } from 'react-router-dom';
import { CheckCircle, FileSpreadsheet, MessageSquare, BarChart3 } from 'lucide-react';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen bg-[#000000]">
      {/* Left Panel - Desktop Only */}
      <div className="hidden lg:flex lg:w-[45%] xl:w-[42%] bg-gradient-to-br from-[#1A1A1A] to-[#1C1C1C] flex-col justify-between p-12 relative overflow-hidden">
        {/* Abstract pattern overlay */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute inset-0" style={{
            backgroundImage: `radial-gradient(circle at 20% 50%, #E4E4E7 0%, transparent 50%),
                              radial-gradient(circle at 80% 20%, #F97066 0%, transparent 40%),
                              radial-gradient(circle at 50% 80%, #E4E4E7 0%, transparent 40%)`,
          }} />
        </div>

        <div className="relative z-10">
          <span className="text-xl font-bold text-white tracking-tight">
            Event<span className="text-[#E4E4E7]">Horizon</span>
          </span>
        </div>

        <div className="relative z-10">
          <h2 className="text-3xl xl:text-4xl font-bold text-white leading-tight">
            AI-Powered Data Workspace
          </h2>
          <p className="mt-4 text-[#A1A1AA] text-base max-w-[380px] leading-relaxed">
            Transform raw data into actionable insights with AI-assisted analysis, interactive dashboards, and automated reporting.
          </p>

          <div className="mt-10 space-y-5">
            <FeatureBullet icon={FileSpreadsheet} text="Upload and transform CSV/Excel files" />
            <FeatureBullet icon={MessageSquare} text="Chat with AI to analyze your data" />
            <FeatureBullet icon={BarChart3} text="Build dashboards and generate reports" />
          </div>
        </div>

        <div className="relative z-10">
          <p className="text-xs text-[#71717A]">
            Trusted by data teams worldwide
          </p>
        </div>
      </div>

      {/* Right Panel */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-[420px]">
          {/* Mobile Logo */}
          <div className="lg:hidden mb-8 text-center">
            <span className="text-2xl font-bold text-white tracking-tight">
            Event<span className="text-[#E4E4E7]">Horizon</span>
            </span>
          </div>

          <Outlet />
        </div>
      </div>
    </div>
  );
}

function FeatureBullet({ icon: Icon, text }: { icon: typeof CheckCircle; text: string }) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="w-5 h-5 text-[#22C55E] flex-shrink-0" />
      <span className="text-sm text-[#A1A1AA]">{text}</span>
    </div>
  );
}
