/** Inline error for a failed load, with a button that retries it. */
export default function RetryNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="notice notice-error" role="alert">
      {message}{" "}
      <button className="link" onClick={onRetry}>Try again</button>
    </div>
  );
}
