export function ForbiddenNotice({ roles }: { roles?: string[] }) {
  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
      <p className="font-medium">Not visible to your role</p>
      {roles && roles.length > 0 && (
        <p className="mt-1 text-amber-700">Requires one of: {roles.join(', ')}.</p>
      )}
    </div>
  )
}
