import { ModelTab } from '@/pages/AdminPanel';

export function ModelAccess() {
  return (
    <div className="h-full overflow-y-auto bg-black p-4 md:p-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.18em] text-[#8C8C8C]">Personal settings</p>
          <h1 className="mt-1 text-xl font-semibold text-white">Model Access</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8B8B8]">
            Your model and encrypted provider key are private to your account. They are used by Prepare, Visualize, and Publish only for your requests.
          </p>
        </div>
        <ModelTab />
      </div>
    </div>
  );
}
