export function StatusBadge({ value }: { value: string }) {
  const normalised = value.toUpperCase();
  const tone =
    normalised === 'UP' ||
    normalised === 'CONFIRMED' ||
    normalised === 'ON_SALE' ||
    normalised === 'AVAILABLE'
      ? 'is-success'
      : normalised === 'DOWN' ||
          normalised === 'FAILED' ||
          normalised === 'CANCELLED'
        ? 'is-danger'
        : normalised === 'PENDING'
          ? 'is-pending'
          : 'is-neutral';

  return <span className={`status-badge ${tone}`}>{value}</span>;
}
