import * as React from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Info,
  Loader2,
  MoreVertical,
  TriangleAlert,
  X,
  XCircle,
  Eye,
  EyeOff,
} from "lucide-react";

type ClassName = { className?: string };

const cx = (...values: Array<string | false | null | undefined>) => values.filter(Boolean).join(" ");

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, ClassName {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  fullWidth?: boolean;
  icon?: React.ReactNode;
}

export function Button({ variant = "primary", size = "md", loading = false, disabled, children, className, fullWidth, icon, ...props }: ButtonProps) {
  return (
    <button className={cx("ui-button", `ui-button--${variant}`, size !== "md" && `ui-button--${size}`, fullWidth && "ui-button--full", className)} disabled={disabled || loading} {...props}>
      {loading ? <span className="ui-spinner" aria-hidden="true" /> : null}
      {!loading && icon ? <span className="ui-button__icon" aria-hidden="true">{icon}</span> : null}
      {children}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonProps, "children"> {
  label: string;
  children?: React.ReactNode;
}

export function Icon({ label, children, className }: { label?: string; children: React.ReactNode; className?: string }) {
  return <span className={className} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>{children}</span>;
}

export function IconButton({ label, size = "md", className, children, ...props }: IconButtonProps) {
  return <Button {...props} size={size} aria-label={label} className={cx("ui-icon-button", size === "sm" && "ui-icon-button--sm", className)}>{children}</Button>;
}

export interface LinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement>, ClassName { muted?: boolean; }
export function Link({ className, muted, ...props }: LinkProps) {
  return <a className={cx("ui-link", muted && "ui-link--muted", className)} {...props} />;
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cx("ui-control", className)} {...props} />
));
Input.displayName = "Input";

export const PasswordInput = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false);
  return (
    <div className="ui-password-wrap">
      <input ref={ref} {...props} type={visible ? "text" : "password"} className={cx("ui-control", className)} />
      <IconButton type="button" variant="ghost" size="sm" label={visible ? "Hide password" : "Show password"} className="ui-password-toggle" onClick={() => setVisible((value) => !value)}>
        {visible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
      </IconButton>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cx("ui-control", "ui-textarea", className)} {...props} />
));
Textarea.displayName = "Textarea";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement>, ClassName { options?: Array<{ value: string; label: string; disabled?: boolean }>; }
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(({ className, options, children, ...props }, ref) => (
  <div className="ui-select-wrap">
    <select ref={ref} className={cx("ui-control", "ui-select", className)} {...props}>
      {options ? options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>) : children}
    </select>
  </div>
));
Select.displayName = "Select";

export function Checkbox({ label, className, ...props }: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: React.ReactNode }) {
  return <label className={cx("ui-check", className)}><input {...props} type="checkbox" />{label ? <span>{label}</span> : null}</label>;
}

export function Radio({ label, className, ...props }: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: React.ReactNode }) {
  return <label className={cx("ui-check", className)}><input {...props} type="radio" />{label ? <span>{label}</span> : null}</label>;
}

export const DateTimeInput = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ type = "datetime-local", className, ...props }, ref) => (
  <input ref={ref} type={type} className={cx("ui-control", className)} {...props} />
));
DateTimeInput.displayName = "DateTimeInput";

export interface FieldErrorProps extends ClassName { children?: React.ReactNode; id?: string; }
export function FieldError({ children, id, className }: FieldErrorProps) {
  return children ? <p id={id} className={cx("ui-field__error", className)} role="alert">{children}</p> : null;
}

export interface FormFieldProps extends ClassName {
  label: React.ReactNode;
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  required?: boolean;
  children: React.ReactNode;
}
export function FormField({ label, htmlFor, hint, error, required, children, className }: FormFieldProps) {
  const hintId = htmlFor ? `${htmlFor}-hint` : undefined;
  const errorId = htmlFor ? `${htmlFor}-error` : undefined;
  return (
    <div className={cx("ui-field", className)}>
      <label className="ui-field__label" htmlFor={htmlFor}>{label}{required ? <span className="ui-field__required" aria-hidden="true">*</span> : null}</label>
      {React.isValidElement(children) ? React.cloneElement(children as React.ReactElement<{ "aria-describedby"?: string; "aria-invalid"?: boolean }>, {
        "aria-describedby": [hint && hintId, error && errorId].filter(Boolean).join(" ") || undefined,
        "aria-invalid": Boolean(error) || undefined,
      }) : children}
      {hint ? <span id={hintId} className="ui-field__hint">{hint}</span> : null}
      <FieldError id={errorId}>{error}</FieldError>
    </div>
  );
}

export type AlertTone = "success" | "warning" | "danger" | "info";
const alertIcons = { success: CheckCircle2, warning: TriangleAlert, danger: XCircle, info: Info } as const;
export interface AlertProps extends ClassName { tone?: AlertTone; title?: React.ReactNode; children: React.ReactNode; onClose?: () => void; }
export function Alert({ tone = "info", title, children, onClose, className }: AlertProps) {
  const Icon = alertIcons[tone];
  return <div className={cx("ui-alert", `ui-alert--${tone}`, className)} role={tone === "danger" ? "alert" : "status"}>
    <Icon size={18} aria-hidden="true" />
    <div className="ui-alert__content">{title ? <div className="ui-alert__title">{title}</div> : null}<div>{children}</div></div>
    {onClose ? <IconButton label="Dismiss" size="sm" variant="ghost" onClick={onClose}><X size={16} aria-hidden="true" /></IconButton> : null}
  </div>;
}

export type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger" | "info" | "information";
export function Badge({ tone = "neutral", children, className }: ClassName & { tone?: BadgeTone; children: React.ReactNode }) {
  return <span className={cx("ui-badge", `ui-badge--${tone}`, className)}>{children}</span>;
}

export interface CardProps extends React.HTMLAttributes<HTMLDivElement>, ClassName { padded?: boolean; }
export function Card({ padded = false, className, ...props }: CardProps) { return <div className={cx("ui-card", padded && "ui-card--padded", className)} {...props} />; }
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cx("ui-card__header", className)} {...props} />; }
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) { return <h2 className={cx("ui-card__title", className)} {...props} />; }

export interface DialogProps extends ClassName {
  open: boolean;
  title: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  labelledBy?: string;
}
export function Dialog({ open, title, onClose, children, footer, className, labelledBy }: DialogProps) {
  React.useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);
  if (!open) return null;
  const titleId = labelledBy ?? "ui-dialog-title";
  return <div className="ui-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={cx("ui-dialog", className)} role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header className="ui-dialog__header"><h2 className="ui-dialog__title" id={titleId}>{title}</h2><IconButton label="Close dialog" variant="ghost" onClick={onClose}><X size={18} aria-hidden="true" /></IconButton></header>
      <div className="ui-dialog__body">{children}</div>
      {footer ? <footer className="ui-dialog__footer">{footer}</footer> : null}
    </section>
  </div>;
}

export interface ConfirmationDialogProps extends Omit<DialogProps, "footer"> { confirmLabel?: string; cancelLabel?: string; onConfirm: () => void; tone?: "primary" | "danger"; loading?: boolean; }
export function ConfirmationDialog({ confirmLabel = "Confirm", cancelLabel = "Cancel", onConfirm, onClose, tone = "primary", loading, ...props }: ConfirmationDialogProps) {
  return <Dialog {...props} onClose={onClose} footer={<><Button variant="ghost" onClick={onClose} disabled={loading}>{cancelLabel}</Button><Button variant={tone} onClick={onConfirm} loading={loading}>{confirmLabel}</Button></>} />;
}

export interface DrawerProps extends ClassName { open: boolean; title: React.ReactNode; onClose: () => void; children: React.ReactNode; side?: "left" | "right"; }
export function Drawer({ open, title, onClose, children, side = "right", className }: DrawerProps) {
  React.useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);
  if (!open) return null;
  return <div className={cx("ui-overlay", "ui-drawer-overlay", side === "left" && "ui-drawer--left")} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className={cx("ui-drawer", className)} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : "Navigation drawer"}>
      <header className="ui-dialog__header"><h2 className="ui-dialog__title">{title}</h2><IconButton label="Close drawer" variant="ghost" onClick={onClose}><X size={18} aria-hidden="true" /></IconButton></header>
      <div className="ui-dialog__body">{children}</div>
    </aside>
  </div>;
}

export interface DropdownItem { id: string; label: React.ReactNode; disabled?: boolean; onSelect?: () => void; }
export function DropdownMenu({ label = "Open menu", items, children }: { label?: string; items: DropdownItem[]; children?: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return <div className="ui-dropdown" ref={ref}>
    <Button variant="ghost" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{children ?? <><MoreVertical size={18} aria-hidden="true" /><span className="ui-visually-hidden">{label}</span></>}</Button>
    {open ? <div className="ui-dropdown__menu" role="menu">{items.map((item) => <button key={item.id} type="button" role="menuitem" className="ui-dropdown__item" disabled={item.disabled} onClick={() => { item.onSelect?.(); setOpen(false); }}>{item.label}</button>)}</div> : null}
  </div>;
}

export function Tooltip({ label, children }: { label: string; children: React.ReactNode }) {
  const [visible, setVisible] = React.useState(false);
  return <span className="ui-tooltip" onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)} onFocus={() => setVisible(true)} onBlur={() => setVisible(false)}>
    {children}{visible ? <span className="ui-tooltip__bubble" role="tooltip">{label}</span> : null}
  </span>;
}

export interface ToastMessage { id: string; title?: string; message: string; tone?: AlertTone; }
interface ToastContextValue { toast: (message: Omit<ToastMessage, "id">) => void; dismiss: (id: string) => void; }
const ToastContext = React.createContext<ToastContextValue | null>(null);
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = React.useState<ToastMessage[]>([]);
  const dismiss = React.useCallback((id: string) => setMessages((current) => current.filter((item) => item.id !== id)), []);
  const toast = React.useCallback((message: Omit<ToastMessage, "id">) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setMessages((current) => [...current, { ...message, id }]);
    window.setTimeout(() => dismiss(id), 5000);
  }, [dismiss]);
  return <ToastContext.Provider value={{ toast, dismiss }}>{children}<div className="ui-toast-region" aria-live="polite" aria-atomic="false">{messages.map((item) => <div className="ui-toast" key={item.id}><div className="ui-toast__body">{item.title ? <div className="ui-toast__title">{item.title}</div> : null}<div className="ui-toast__message">{item.message}</div></div><IconButton label="Dismiss notification" size="sm" variant="ghost" onClick={() => dismiss(item.id)}><X size={16} aria-hidden="true" /></IconButton></div>)}</div></ToastContext.Provider>;
}
export function useToast() {
  const context = React.useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}

export interface TabItem { id: string; label: React.ReactNode; disabled?: boolean; }
export function Tabs({ items, value, onChange, className }: { items: TabItem[]; value: string; onChange: (id: string) => void; className?: string }) {
  return <div className={cx("ui-tabs", className)} role="tablist">{items.map((item) => <button key={item.id} type="button" className="ui-tab" role="tab" aria-selected={item.id === value} disabled={item.disabled} onClick={() => onChange(item.id)}>{item.label}</button>)}</div>;
}

export function Breadcrumb({ items, className }: { items: Array<{ label: React.ReactNode; href?: string }>; className?: string }) {
  return <nav className={cx("ui-breadcrumb", className)} aria-label="Breadcrumb">{items.map((item, index) => <React.Fragment key={`${index}-${String(item.label)}`}>
    {index > 0 ? <span className="ui-breadcrumb__separator" aria-hidden="true">/</span> : null}
    {item.href && index < items.length - 1 ? <Link href={item.href}>{item.label}</Link> : <span aria-current={index === items.length - 1 ? "page" : undefined}>{item.label}</span>}
  </React.Fragment>)}</nav>;
}

export function Pagination({ page, pageCount, totalPages, onPageChange, onChange, className }: { page: number; pageCount?: number; totalPages?: number; onPageChange?: (page: number) => void; onChange?: (page: number) => void; className?: string }) {
  const count = pageCount ?? totalPages ?? 0;
  const change = onPageChange ?? onChange ?? (() => undefined);
  if (count < 2) return null;
  return <nav className={cx("ui-pagination", className)} aria-label="Pagination"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => change(page - 1)}><ChevronLeft size={16} aria-hidden="true" />Previous</Button><div className="ui-pagination__pages">{Array.from({ length: count }, (_, index) => index + 1).map((item) => <Button key={item} variant={item === page ? "secondary" : "ghost"} size="sm" className="ui-pagination__page" aria-current={item === page ? "page" : undefined} onClick={() => change(item)}>{item}</Button>)}</div><Button variant="outline" size="sm" disabled={page >= count} onClick={() => change(page + 1)}>Next<ChevronRight size={16} aria-hidden="true" /></Button></nav>;
}

export function Skeleton({ width = "100%", height = "1rem", className }: { width?: string | number; height?: string | number; className?: string }) { return <span className={cx("ui-skeleton", className)} style={{ width, height }} aria-hidden="true" />; }
export function Spinner({ label = "Loading", className }: { label?: string; className?: string }) { return <span className={cx("ui-spinner-wrap", className)} role="status"><span className="ui-spinner" aria-hidden="true" /><span>{label}</span></span>; }

export interface StateProps { title?: React.ReactNode; message?: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string; }
export function EmptyState({ title = "Nothing here yet", message, description, action, className }: StateProps) { return <div className={cx("ui-state", className)}><div className="ui-state__icon" aria-hidden="true"><Info size={22} /></div><h2 className="ui-state__title">{title}</h2>{message ?? description ? <p className="ui-state__message">{message ?? description}</p> : null}{action}</div>; }
export function ErrorState({ title = "Something went wrong", message, description, action, className }: StateProps) { return <div className={cx("ui-state", className)} role="alert"><div className="ui-state__icon" aria-hidden="true"><AlertCircle size={22} /></div><h2 className="ui-state__title">{title}</h2><p className="ui-state__message">{message ?? description ?? "Please try again."}</p>{action}</div>; }
export interface RetryStateProps extends StateProps { onRetry?: () => void; }
export function ServiceUnavailableState({ onRetry, title, message, description, action, className }: RetryStateProps) { return <ErrorState className={className} title={title ?? "Service temporarily unavailable"} message={message ?? description ?? "We cannot reach the ticketing service right now. Your data has not been changed. Please try again shortly."} action={action ?? (onRetry ? <Button variant="outline" onClick={onRetry}>Retry</Button> : undefined)} />; }
export function UnauthorizedState({ action, title, message, description, className }: StateProps) { return <ErrorState className={className} title={title ?? "Sign in required"} message={message ?? description ?? "Sign in to continue and view this information."} action={action} />; }
export function ForbiddenState({ action, title, message, description, className }: StateProps) { return <ErrorState className={className} title={title ?? "You do not have access"} message={message ?? description ?? "Your account is not permitted to view this page."} action={action} />; }
export function NotFoundState({ title = "Page not found", message, description, action, className }: StateProps) { return <ErrorState className={className} title={title} message={message ?? description ?? "The page or resource you requested could not be found."} action={action} />; }

export interface DataTableColumn<T> { key: string; header: React.ReactNode; render: (row: T) => React.ReactNode; className?: string; }
export function DataTable<T extends { id?: string | number }>({ columns, rows, emptyState, caption, className }: { columns: Array<DataTableColumn<T>>; rows: T[]; emptyState?: React.ReactNode; caption?: string; className?: string }) {
  return <div className={cx("ui-table-wrap", className)}><table className="ui-table"><caption className="ui-visually-hidden">{caption ?? "Data table"}</caption><thead><tr>{columns.map((column) => <th key={column.key} className={column.className} scope="col">{column.header}</th>)}</tr></thead><tbody>{rows.length === 0 ? <tr><td colSpan={columns.length}>{emptyState ?? <EmptyState />}</td></tr> : rows.map((row, rowIndex) => <tr key={row.id ?? rowIndex}>{columns.map((column) => <td key={column.key} className={column.className}>{column.render(row)}</td>)}</tr>)}</tbody></table></div>;
}

export { Check, ChevronDown, Loader2 };
